import json, sys
S = sys.argv[1]
TEST = len(sys.argv) > 2 and sys.argv[2] == "test"

DOC = {"__rl": True, "value": "1LpPqSKXOvB2FdqNGNnlVBpPDvnfDrYml7npHJEZpKxc", "mode": "list",
       "cachedResultName": "Sourcing - N8N Cloud",
       "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1LpPqSKXOvB2FdqNGNnlVBpPDvnfDrYml7npHJEZpKxc/edit?usp=drivesdk"}
SHEET = {"__rl": True, "value": "0", "mode": "id"}
GS_CRED = {"googleSheetsOAuth2Api": {"id": "gRSPd8YEw5iadWsy", "name": "Google Sheets (Iacopo Bon)"}}

CRITERIA = open(f"{S}/criteria.txt").read()

batch_code = r"""// Picks Sourcing rows that have never been scored (empty 'AI Moat Score') and
// groups them into batches, one Claude call per batch.
const BATCH_SIZE = __BATCH_SIZE__;
const MAX_BATCHES = __MAX_BATCHES__; // safety cap on Claude calls per run
const CRITERIA = __CRITERIA__;

const unscored = $input.all()
  .map(it => it.json)
  .filter(j => j['Organization Name'] && (j['AI Moat Score'] === '' || j['AI Moat Score'] === undefined || j['AI Moat Score'] === null));

const out = [];
for (let b = 0; b < unscored.length && out.length < MAX_BATCHES; b += BATCH_SIZE) {
  const rows = unscored.slice(b, b + BATCH_SIZE);
  const candidates = rows.map(r => ({
    id: r.row_number,
    name: r['Organization Name'],
    description: String(r['Description'] || '').slice(0, 600),
    website: r['Website'] || '',
    source: r['Source'] || '',
    funding_usd: r['Funding USD (parsed)'] || null,
  }));
  const prompt = CRITERIA
    + '\n\nHere are the candidate startups as a JSON array:\n'
    + JSON.stringify(candidates)
    + '\n\nReturn ONLY a JSON array (no prose, no markdown fences), one object per candidate, in this exact shape:\n'
    + '[{"id": 0, "company_name": "...", "pass": true|false, "enterprise_fit": true|false, "is_ai_agent": true|false, '
    + '"has_physical_component": true|false, "is_excluded_space_or_defence": true|false, "moat_score": 1-5, "geography_guess": "...", "reasoning": "one short sentence covering enterprise fit, physical component, and moat"}]\n'
    + '"id" must be echoed back EXACTLY as given in the input so results can be matched. "company_name" is the '
    + 'clean startup name only (e.g. from a news headline like "Acme raises $2M", company_name is "Acme") - '
    + 'strip any funding/news phrasing.\n'
    + 'moat_score reflects how defensible the product looks (5 = strong moat, 1 = trivially replicable). '
    + 'is_excluded_space_or_defence is true for space/satellite/aerospace companies, consumer/hobby drones, and purely military products '
    + '(weapons, strike drones); it is FALSE for dual-use drone/UAV/counter-drone/defence tech with credible civil or industrial buyers. '
    + 'pass must be false whenever enterprise_fit is false, is_ai_agent is true or is_excluded_space_or_defence is true, regardless of moat_score.';
  out.push({ json: { prompt, max_tokens: 4000, rows } });
}
return out;
"""
batch_code = (batch_code.replace("__BATCH_SIZE__", "5" if TEST else "15")
              .replace("__MAX_BATCHES__", "1" if TEST else "12")
              .replace("__CRITERIA__", json.dumps(CRITERIA)))

update_code = r"""// Zips each Claude batch result back to its sheet rows (by row_number) and builds
// the in-place update. Rejected candidates get AI Moat Score 0 so they are never
// re-scored and sort to the bottom; the real moat score stays visible in AI Notes.
const batches = $('Build Scoring Batches').all();
const NEWS_SOURCES = ['tech.eu', 'TechEU', 'Wamda'];
const out = [];
$input.all().forEach((item, i) => {
  const rows = (batches[i] && batches[i].json.rows) || [];
  const results = Array.isArray(item.json.result) ? item.json.result : [];
  const byId = {};
  for (const r of results) byId[String(r.id)] = r;
  for (const row of rows) {
    const r = byId[String(row.row_number)];
    if (!r) continue; // missing/malformed -> left unscored, retried next run
    const moat = Number(r.moat_score) || 0;
    // Hard rules enforced in code too: the model sometimes passes an excluded space/defence company despite the criteria.
    const pass = r.pass === true && r.enterprise_fit !== false && r.is_ai_agent !== true && r.is_excluded_space_or_defence !== true;
    const upd = {
      row_number: row.row_number,
      'AI Moat Score': pass ? moat : 0,
      'AI Notes': (pass ? 'PASS' : 'REJECT') + ' (moat ' + moat + '/5) - ' + (r.reasoning || ''),
      'Move to Pipeline?': pass, // picked up by 'Pipeline - Move to Pipeline'
    };
    if (!row['Headquarters Location'] && r.geography_guess) upd['Headquarters Location'] = r.geography_guess;
    if (NEWS_SOURCES.some(s => String(row['Source'] || '').toLowerCase() === s.toLowerCase()) && r.company_name) {
      upd['Organization Name'] = r.company_name;
    }
    out.push({ json: upd });
  }
});
return out;
"""

nodes = [
    {"name": "Weekly Scoring Trigger", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2,
     "position": [0, 0], "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 13 * * 1"}]}}},
    {"name": "Sourcing - Get Rows", "type": "n8n-nodes-base.googleSheets", "typeVersion": 4.5,
     "position": [220, 0], "parameters": {"documentId": DOC, "sheetName": SHEET, "options": {}}, "credentials": GS_CRED},
    {"name": "Build Scoring Batches", "type": "n8n-nodes-base.code", "typeVersion": 2,
     "position": [440, 0], "parameters": {"jsCode": batch_code}},
    {"name": "Call Claude", "type": "n8n-nodes-base.executeWorkflow", "typeVersion": 1.2,
     "position": [660, 0], "parameters": {
        "workflowId": {"__rl": True, "value": "V5wGQ55LdYLhSCmf", "mode": "list", "cachedResultName": "Util - Claude Messages API"},
        "workflowInputs": {"mappingMode": "defineBelow",
                           "value": {"prompt": "={{ $json.prompt }}", "max_tokens": "={{ $json.max_tokens }}"},
                           "matchingColumns": [], "schema": []},
        "mode": "each", "options": {}}},
    {"name": "Build Row Updates", "type": "n8n-nodes-base.code", "typeVersion": 2,
     "position": [880, 0], "parameters": {"jsCode": update_code}},
    {"name": "Sourcing - Write Scores", "type": "n8n-nodes-base.googleSheets", "typeVersion": 4.5,
     "position": [1100, 0], "parameters": {"operation": "update", "documentId": DOC, "sheetName": SHEET,
        "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": ["row_number"], "schema": []},
        "options": {}}, "credentials": GS_CRED},
]
order = [n["name"] for n in nodes]
connections = {a: {"main": [[{"node": b, "type": "main", "index": 0}]]} for a, b in zip(order, order[1:])}
# Second entry point so other workflows (e.g. a one-off lead import) can run scoring immediately.
nodes.append({"name": "When Called by Another Workflow", "type": "n8n-nodes-base.executeWorkflowTrigger",
              "typeVersion": 1.1, "position": [0, 200], "parameters": {"inputSource": "passthrough"}})
connections["When Called by Another Workflow"] = {"main": [[{"node": "Sourcing - Get Rows", "type": "main", "index": 0}]]}
wf = {"name": "Sourcing - Weekly AI Scoring", "nodes": nodes, "connections": connections,
      "settings": {"executionOrder": "v1"}}
json.dump(wf, open(f"{S}/scoring.json", "w"), indent=1)
print("ok", "TEST" if TEST else "PROD")
