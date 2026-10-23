"""Read-only: prints the latest executions of a workflow. Usage: python3 last_executions.py <workflow_id> [n]"""
import json, os, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
env = {}
for line in open(os.path.join(ROOT, ".env")):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
url = (f"{env['N8N_CLOUD_BASE_URL'].rstrip('/')}/api/v1/executions?workflowId={sys.argv[1]}"
       f"&limit={sys.argv[2] if len(sys.argv) > 2 else 5}")
req = urllib.request.Request(url, headers={"X-N8N-API-KEY": env["N8N_CLOUD_API_KEY"]})
for e in json.load(urllib.request.urlopen(req))["data"]:
    print(e["id"], e["status"], e["startedAt"], e.get("stoppedAt"))
