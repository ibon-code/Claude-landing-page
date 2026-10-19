"""Fix Daily Harvest execution order: load existing Sourcing rows BEFORE the 4 source branches.

With executionOrder v1 the trigger's parallel branches run top-to-bottom, so BetaList ran before
'Sourcing - Get Existing' and its dedup failed ("Node 'Sourcing - Get Existing' hasn't been executed"),
killing the whole run every day. New chain: Trigger -> Get Existing -> Existing Rows Loaded (1 item)
-> BetaList / Apollo / TechEU / Wamda. Also adds 3 retries to every Google Sheets node.
Idempotent: safe to re-run. Updates the backup JSON afterwards.
"""
import json, os, urllib.request, urllib.error, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WF_ID = "1D0Q5agDQFAsVtFd"
GATE = "Existing Rows Loaded"
SOURCES = ["BetaList - Fetch Feed", "Apollo - Search Companies", "TechEU - Fetch Feed", "Wamda - Fetch Feed"]

env = {}
for line in open(os.path.join(ROOT, ".env")):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
base, key = env["N8N_CLOUD_BASE_URL"].rstrip("/"), env["N8N_CLOUD_API_KEY"]


def call(method, path, body=None):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"X-N8N-API-KEY": key, "Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{e.code}: {e.read().decode()[:600]}")


w = call("GET", f"/api/v1/workflows/{WF_ID}")
c = w["connections"]
c["Daily Harvest Trigger"] = {"main": [[{"node": "Sourcing - Get Existing", "type": "main", "index": 0}]]}
c["Sourcing - Get Existing"] = {"main": [[{"node": GATE, "type": "main", "index": 0}]]}
c[GATE] = {"main": [[{"node": s, "type": "main", "index": 0} for s in SOURCES]]}
for n in w["nodes"]:
    if n["name"] == "Sourcing - Get Existing":
        n["position"] = [224, -480]
    if n["type"] == "n8n-nodes-base.googleSheets":
        n.update(retryOnFail=True, maxTries=3, waitBetweenTries=5000)
if not any(n["name"] == GATE for n in w["nodes"]):
    w["nodes"].append({
        "parameters": {"jsCode": "// Single item so each source branch runs once, after the existing rows are loaded\n"
                                 "return [{ json: { existingRows: $input.all().length } }];"},
        "id": str(uuid.uuid4()), "name": GATE, "type": "n8n-nodes-base.code", "typeVersion": 2,
        "position": [448, -480]})

res = call("PUT", f"/api/v1/workflows/{WF_ID}",
           {"name": w["name"], "nodes": w["nodes"], "connections": c, "settings": {"executionOrder": "v1"}})
print("OK - active:", res["active"], "| live version updated:", res.get("versionId") == res.get("activeVersionId"))
print("Trigger ->", [o["node"] for o in res["connections"]["Daily Harvest Trigger"]["main"][0]])
print(GATE, "->", [o["node"] for o in res["connections"][GATE]["main"][0]])
backup = os.path.join(ROOT, "Sourcing - N8N Cloud Rebuild", "workflow_backups", "Sourcing - Daily Harvest.json")
json.dump(res, open(backup, "w"), indent=2)
print("Backup saved:", backup)
