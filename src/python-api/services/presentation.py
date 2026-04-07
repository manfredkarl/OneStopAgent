"""PowerPoint generation service — PptxGenJS via Node.js."""

import logging
import os
import shutil
import subprocess
import tempfile
import uuid

from opentelemetry import trace


logger = logging.getLogger(__name__)

_tracer = trace.get_tracer(__name__)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
# node_modules lives next to this service's parent package.json
NODE_MODULES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "node_modules"))


def _sanitize_pptxgenjs_script(script: str) -> str:
    """Fix common LLM-generated PptxGenJS script issues."""
    import re

    # Fix invalid layout values — PptxGenJS only accepts these:
    # LAYOUT_16x9, LAYOUT_16x10, LAYOUT_4x3, LAYOUT_WIDE, LAYOUT_USER
    valid_layouts = {"LAYOUT_16x9", "LAYOUT_16x10", "LAYOUT_4x3", "LAYOUT_WIDE", "LAYOUT_USER"}

    # Find pres.layout = "..." and validate
    layout_match = re.search(r'pres\.layout\s*=\s*["\']([^"\']+)["\']', script)
    if layout_match:
        layout_val = layout_match.group(1)
        if layout_val not in valid_layouts:
            # Replace with default
            script = script[:layout_match.start()] + 'pres.layout = "LAYOUT_16x9"' + script[layout_match.end():]
            logger.warning("Fixed invalid PptxGenJS layout '%s' → 'LAYOUT_16x9'", layout_val)
    elif "pres.layout" not in script:
        # No layout set — inject default after pres creation
        script = script.replace(
            "const pres = new pptxgen();",
            'const pres = new pptxgen();\npres.layout = "LAYOUT_16x9";',
            1,
        )

    # Fix hex colors with # prefix (PptxGenJS wants bare hex)
    script = re.sub(r'color:\s*["\']#([0-9a-fA-F]{6})["\']', r'color: "\1"', script)
    script = re.sub(r'background:\s*\{\s*color:\s*["\']#([0-9a-fA-F]{6})["\']', r'background: { color: "\1"', script)

    return script


def execute_pptxgenjs(script: str, customer_name: str = "Customer") -> str:
    """Write a PptxGenJS script to a temp file, execute it, return the .pptx path.

    The script must use the literal string ``OUTPUT_PATH`` as the fileName
    argument to ``pres.writeFile()``. This function replaces it with the
    real output path before execution.
    """
    if not shutil.which("node"):
        raise RuntimeError("Node.js is not installed or not in PATH. Cannot generate PPTX.")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in customer_name).strip().replace(" ", "_")
    filename = f"OneStopAgent-{safe_name}-{uuid.uuid4().hex[:8]}.pptx"
    output_path = os.path.join(OUTPUT_DIR, filename)

    # Inject the real output path — use forward slashes for Node on all platforms
    abs_output = os.path.abspath(output_path).replace("\\", "/")
    script = script.replace("OUTPUT_PATH", f'"{abs_output}"')

    # Sanitize common LLM script issues (invalid layouts, # in hex colors)
    script = _sanitize_pptxgenjs_script(script)

    # Write script to temp file
    script_fd, script_path = tempfile.mkstemp(suffix=".js", prefix="pptxgen_")
    try:
        with os.fdopen(script_fd, "w", encoding="utf-8") as f:
            f.write(script)

        env = {**os.environ, "NODE_PATH": NODE_MODULES}
        with _tracer.start_as_current_span("pptxgenjs.execute") as span:
            span.set_attribute("pptx.customer_name", customer_name)
            span.set_attribute("pptx.output_path", abs_output)
            span.set_attribute("pptx.script_length", len(script))

            result = subprocess.run(
                ["node", script_path],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=OUTPUT_DIR,
                env=env,
            )

            span.set_attribute("pptx.exit_code", result.returncode)

            if result.returncode != 0:
                span.set_attribute("pptx.error", result.stderr[:300])
                logger.error("PptxGenJS script failed (exit %d):\nstdout: %s\nstderr: %s",
                             result.returncode, result.stdout[:500], result.stderr[:500])
                raise RuntimeError(f"PptxGenJS script failed: {result.stderr[:300]}")

            if not os.path.isfile(output_path):
                span.set_attribute("pptx.error", "output_not_found")
                raise FileNotFoundError(f"PptxGenJS ran but output not found at {output_path}")

            span.set_attribute("pptx.success", True)
            logger.info("Generated PPTX: %s", output_path)
            return output_path

    finally:
        # Clean up temp script
        try:
            os.unlink(script_path)
        except OSError:
            pass
