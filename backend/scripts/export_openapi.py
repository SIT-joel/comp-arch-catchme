"""Export the OpenAPI schema from the implemented routes to docs/openapi.json."""
import json
import sys

sys.path.insert(0, ".")

from app.main import app

spec = app.openapi()
out = "../docs/openapi.json"
with open(out, "w", encoding="utf-8") as fh:
    json.dump(spec, fh, indent=2, sort_keys=True)
print(f"wrote {out} with {len(spec['paths'])} paths")
