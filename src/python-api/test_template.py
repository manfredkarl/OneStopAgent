import json, subprocess, tempfile, os

from agents.presentation_agent import SLIDE_TEMPLATE

data = {
    "customer": "Test Corp",
    "tagline": "Test tagline",
    "executiveSummary": ["Bullet 1", "Bullet 2"],
    "problemStatement": "Test problem",
    "scenarios": [{"title": "Test", "description": "Desc", "azure_services": ["App Service"]}],
}

script = SLIDE_TEMPLATE.replace("__DATA_PLACEHOLDER__", json.dumps(data))
output_path = os.path.abspath("test_deck.pptx").replace("\\", "/")
script = script.replace("OUTPUT_PATH", f'"{output_path}"')

fd, path = tempfile.mkstemp(suffix=".js")
with os.fdopen(fd, "w") as f:
    f.write(script)

result = subprocess.run(
    ["node", path], capture_output=True, text=True, timeout=30,
    env={**os.environ, "NODE_PATH": os.path.join(os.getcwd(), "node_modules")},
)
print(f"Exit: {result.returncode}")
if result.stderr:
    print(f"STDERR: {result.stderr[:800]}")
if result.stdout:
    print(f"STDOUT: {result.stdout[:200]}")
os.unlink(path)
