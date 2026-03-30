"""PowerPoint generation service — PptxGenJS via Node.js."""

import logging
import os
import subprocess
import tempfile
import uuid

from opentelemetry import trace


logger = logging.getLogger(__name__)

_tracer = trace.get_tracer(__name__)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
# node_modules lives next to this service's parent package.json
NODE_MODULES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "node_modules"))


def execute_pptxgenjs(script: str, customer_name: str = "Customer") -> str:
    """Write a PptxGenJS script to a temp file, execute it, return the .pptx path.

    The script must use the literal string ``OUTPUT_PATH`` as the fileName
    argument to ``pres.writeFile()``. This function replaces it with the
    real output path before execution.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in customer_name).strip().replace(" ", "_")
    filename = f"OneStopAgent-{safe_name}-{uuid.uuid4().hex[:8]}.pptx"
    output_path = os.path.join(OUTPUT_DIR, filename)

    # Inject the real output path — use forward slashes for Node on all platforms
    abs_output = os.path.abspath(output_path).replace("\\", "/")
    script = script.replace("OUTPUT_PATH", f'"{abs_output}"')

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
