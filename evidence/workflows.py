"""The shared server and static-site source of workflow names and presets."""
import json
from pathlib import Path

def workflows():
    return json.loads((Path(__file__).resolve().parent/'workflows.json').read_text(encoding='utf-8'))
