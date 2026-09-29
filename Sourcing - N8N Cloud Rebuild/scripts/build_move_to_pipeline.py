"""Generates two n8n workflows:
- 'Pipeline - Move to Pipeline' (permanent, every 15 min): copies Sourcing rows with
  'Move to Pipeline?' = TRUE into the Pipeline tab, skipping any startup already there.
  Rows are NOT deleted from Sourcing (the harvest dedups against them).
- 'TEMP - Set Move Flags from AI Verdict' (one-off): sets 'Move to Pipeline?' to TRUE for
  rows whose AI Notes start with PASS and FALSE for scored rejects.
"""
import json, sys
out_dir = sys.argv[1]

DOC = {"__rl": True, "value": "1LpPqSKXOvB2FdqNGNnlVBpPDvnfDrYml7npHJEZpKxc", "mode": "list",
       "cachedResultName": "Sourcing - N8N Cloud",
       "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1LpPqSKXOvB2FdqNGNnlVBpPDvnfDrYml7npHJEZpKxc/edit?usp=drivesdk"}
SOURCING = {"__rl": True, "value": "0", "mode": "id"}
PIPELINE = {"__rl": True, "value": "114224284", "mode": "id"}
GS_CRED = {"googleSheetsOAuth2Api": {"id": "gRSPd8YEw5iadWsy", "name": "Google Sheets (Iacopo Bon)"}}


def sheets(name, pos, sheet, **params):
    return {"name": name, "type": "n8n-nodes-base.googleSheets", "typeVersion": 4.5, "position": pos,
            "parameters": {"documentId": DOC, "sheetName": sheet, **params, "options": {}},
            "credentials": GS_CRED}


def code(name, pos, js):
    return {"name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos,
            "parameters": {"jsCode": js}}


def chain(nodes):
    names = [n["name"] for n in nodes]
    return {a: {"main": [[{"node": b, "type": "main", "index": 0}]]} for a, b in zip(names, names[1:])}


AUTOMAP = lambda match: {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": match, "schema": []}

select_js = r"""function isChecked(v) {
  if (typeof v === 'boolean') return v;
  if (typeof v === 'string') return v.trim().toUpperCase() === 'TRUE';
  return false;
}
// Source sites (listing/article URLs used as a fallback Website) are shared by many
// startups, so they can't identify one — dedup those rows by name only.
const SOURCE_DOMAINS = new Set(['betalist.com', 'tech.eu', 'wamda.com', 'linkedin.com']);
function normalizeDomain(url) {
  const d = String(url || '').trim().toLowerCase()
    .replace(/^https?:\/\//, '').replace(/^www\./, '').split('/')[0].split('?')[0];
  return SOURCE_DOMAINS.has(d) ? '' : d;
}
const pipeline = $('Pipeline - Get Rows').all().map(it => it.json);
const inPipelineDomains = new Set(pipeline.map(r => normalizeDomain(r['Website'])).filter(Boolean));
const inPipelineNames = new Set(pipeline.map(r => String(r['Startup name'] || '').trim().toLowerCase()).filter(Boolean));
const out = [];
for (const item of $('Sourcing - Get Rows').all()) {
  const j = item.json;
  if (!isChecked(j['Move to Pipeline?'])) continue;
  const name = String(j['Organization Name'] || '').trim();
  const domain = normalizeDomain(j['Website']);
  if (!name) continue;
  if (inPipelineNames.has(name.toLowerCase()) || (domain && inPipelineDomains.has(domain))) continue;
  inPipelineNames.add(name.toLowerCase());
  if (domain) inPipelineDomains.add(domain);
  out.push({ json: { 'Startup name': name, 'Website': j['Website'] || '' } });
}
return out;
"""

move_nodes = [
    {"name": "Move to Pipeline Trigger", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2,
     "position": [0, 0], "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "*/15 * * * *"}]}}},
    sheets("Sourcing - Get Rows", [220, 0], SOURCING),
    {**sheets("Pipeline - Get Rows", [440, 0], PIPELINE), "alwaysOutputData": True, "executeOnce": True},
    code("Select Rows to Move", [660, 0], select_js),
    sheets("Pipeline - Append", [880, 0], PIPELINE, operation="append", columns=AUTOMAP([])),
]
json.dump({"name": "Pipeline - Move to Pipeline", "nodes": move_nodes, "connections": chain(move_nodes),
           "settings": {"executionOrder": "v1"}}, open(f"{out_dir}/move.json", "w"), indent=1)

flags_js = r"""// Only rows the AI scoring has already judged; unscored rows are left untouched.
const out = [];
for (const item of $input.all()) {
  const j = item.json;
  const notes = String(j['AI Notes'] || '');
  if (!notes) continue;
  out.push({ json: { row_number: j.row_number, 'Move to Pipeline?': notes.startsWith('PASS') } });
}
return out;
"""
flag_nodes = [
    {"name": "Manual Trigger", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [0, 0], "parameters": {}},
    sheets("Sourcing - Get Rows", [220, 0], SOURCING),
    code("Flag from AI Verdict", [440, 0], flags_js),
    sheets("Sourcing - Write Flags", [660, 0], SOURCING, operation="update", columns=AUTOMAP(["row_number"])),
]
json.dump({"name": "TEMP - Set Move Flags from AI Verdict", "nodes": flag_nodes, "connections": chain(flag_nodes),
           "settings": {"executionOrder": "v1"}}, open(f"{out_dir}/flags.json", "w"), indent=1)
print("ok")
