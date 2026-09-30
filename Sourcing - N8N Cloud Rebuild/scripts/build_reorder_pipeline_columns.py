"""One-off (2026-09-30): in the Pipeline tab, delete the 'CEO LinkedIn' column and move
'Company LinkedIn' to column F, shifting 'Contacted' and everything after it one column right.
Reads the header row first and refuses to run if the layout isn't what we expect."""
import json, sys

SHEET_ID = "1LpPqSKXOvB2FdqNGNnlVBpPDvnfDrYml7npHJEZpKxc"
PIPELINE_GID = 114224284
CRED = {"googleSheetsOAuth2Api": {"id": "gRSPd8YEw5iadWsy", "name": "Google Sheets (Iacopo Bon)"}}


def sheets_api(name, pos, method, url, body_expr=None):
    params = {"method": method, "url": url, "authentication": "predefinedCredentialType",
              "nodeCredentialType": "googleSheetsOAuth2Api", "options": {}}
    if body_expr:
        params.update({"sendBody": True, "specifyBody": "json", "jsonBody": body_expr})
    return {"name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": pos,
            "parameters": params, "credentials": CRED}


plan_js = """const header = ($json.values && $json.values[0]) || [];
const F = 5; // column F, zero-based
if (header[F] !== 'Contacted') throw new Error('Column F is "' + header[F] + '", expected "Contacted" - nothing changed. Header: ' + header.join(' | '));
let company = header.indexOf('Company LinkedIn');
if (company < 0) throw new Error('No "Company LinkedIn" column - nothing changed. Header: ' + header.join(' | '));
const requests = [];
const ceo = header.indexOf('CEO LinkedIn');
if (ceo >= 0) {
  requests.push({ deleteDimension: { range: { sheetId: GID, dimension: 'COLUMNS', startIndex: ceo, endIndex: ceo + 1 } } });
  if (company > ceo) company -= 1;
}
if (company !== F) {
  requests.push({ moveDimension: { source: { sheetId: GID, dimension: 'COLUMNS', startIndex: company, endIndex: company + 1 }, destinationIndex: F } });
}
return [{ json: { requests, before: header } }];
""".replace("GID", str(PIPELINE_GID))

nodes = [
    {"name": "Manual Trigger", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [0, 0], "parameters": {}},
    sheets_api("Read Pipeline Header", [220, 0], "GET",
               f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/Pipeline!1:1"),
    {"name": "Plan Column Changes", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [440, 0],
     "parameters": {"jsCode": plan_js}},
    sheets_api("Apply Column Changes", [660, 0], "POST",
               f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}:batchUpdate",
               "={{ JSON.stringify({ requests: $json.requests }) }}"),
    sheets_api("Read Header After", [880, 0], "GET",
               f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/Pipeline!1:1"),
]
names = [n["name"] for n in nodes]
conn = {a: {"main": [[{"node": b, "type": "main", "index": 0}]]} for a, b in zip(names, names[1:])}
json.dump({"name": "TEMP - Reorder Pipeline Columns", "nodes": nodes, "connections": conn,
           "settings": {"executionOrder": "v1"}}, open(sys.argv[1], "w"))
print("ok")
