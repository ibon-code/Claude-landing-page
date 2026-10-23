"""Creates 'Util - Playbook MCP Setup': an inactive workflow with an MCP Client node already pointed at
Playbook's MCP endpoint (MCP OAuth2). The OAuth login can only be done in the n8n UI, once:
open the node, pencil next to the credential -> Connect -> sign in to Playbook.
After that the node's Tool dropdown lists Playbook's tools, so we can pick the domain lookup.
Idempotent: re-running updates the same workflow (never touches the credential).
"""
import json, os, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NAME = "Util - Playbook MCP Setup"
ENDPOINT = "https://playbook-backend-prod01.cloud.playbook.vc/v3/mcp/playbook/"

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


existing = next((w for w in call("GET", "/api/v1/workflows?limit=250")["data"] if w["name"] == NAME), None)
mcp = {"name": "Playbook MCP", "type": "@n8n/n8n-nodes-langchain.mcpClient", "typeVersion": 1.1,
       "position": [440, 0],
       "parameters": {"serverTransport": "httpStreamable", "endpointUrl": ENDPOINT,
                      "authentication": "mcpOAuth2Api", "tool": {"__rl": True, "mode": "list", "value": ""},
                      "inputMode": "json", "jsonInput": "={}", "options": {}}}
if existing:  # keep whatever credential/tool the user already selected in the UI
    old = next((n for n in call("GET", f"/api/v1/workflows/{existing['id']}")["nodes"] if n["name"] == "Playbook MCP"), None)
    if old:
        mcp = old
nodes = [{"name": "Run Test", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [220, 0],
          "parameters": {}}, mcp]
body = {"name": NAME, "nodes": nodes,
        "connections": {"Run Test": {"main": [[{"node": "Playbook MCP", "type": "main", "index": 0}]]}},
        "settings": {"executionOrder": "v1"}}
res = call("PUT", f"/api/v1/workflows/{existing['id']}", body) if existing else call("POST", "/api/v1/workflows", body)
print("OK", res["id"], "active:", res["active"])
print(f"{base}/workflow/{res['id']}")
