import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.v1.api import app
from app.v1 import captcha  # noqa: F401 -- registers CAPTCHA routes on the v1 application

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
schema = app.openapi()
schema["servers"] = [{"url": "/api/v1"}]
body = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
path = Path(__file__).resolve().parents[2] / "docs/api-v1/openapi.json"
if args.check:
    if not path.exists() or path.read_text() != body:
        raise SystemExit(
            "OpenAPI artifact is stale; run python scripts/export_openapi.py"
        )
else:
    path.write_text(body)
