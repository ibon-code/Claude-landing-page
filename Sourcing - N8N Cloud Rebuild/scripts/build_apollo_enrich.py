"""Generates 'Pipeline - Apollo Enrich' (every 15 min, offset 5 min after Move to Pipeline).

For each Pipeline row without an email and not yet attempted:
  1. Resolve the company domain. If Website is a source-site URL (BetaList/tech.eu/Wamda),
     look the company up in Apollo by exact name and use its real domain.
  2. Search people at that domain (free) and pick the best title with has_email.
  3. Reveal that one person via people/match (1 Apollo credit).
Every attempted row gets 'Apollo Enrich' filled in (found / not found / no website), so it
is never retried automatically and you can see at a glance whether a contact exists.
Clear that cell to force a retry.
"""
import json, sys
out_dir = sys.argv[1]
TEST = len(sys.argv) > 2 and sys.argv[2] == "test"

DOC = {"__rl": True, "value": "1LpPqSKXOvB2FdqNGNnlVBpPDvnfDrYml7npHJEZpKxc", "mode": "list",
       "cachedResultName": "Sourcing - N8N Cloud",
       "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1LpPqSKXOvB2FdqNGNnlVBpPDvnfDrYml7npHJEZpKxc/edit?usp=drivesdk"}
PIPELINE = {"__rl": True, "value": "114224284", "mode": "id"}
GS_CRED = {"googleSheetsOAuth2Api": {"id": "gRSPd8YEw5iadWsy", "name": "Google Sheets (Iacopo Bon)"}}
APOLLO_CRED = {"httpHeaderAuth": {"id": "tsTg37ICmuv8HBpC", "name": "Apollo Header Auth"}}
MAX_PER_RUN = 3 if TEST else 10


def code(name, pos, js):
    return {"name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos,
            "parameters": {"jsCode": js}}


def apollo(name, pos, url, body_expr):
    return {"name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": pos,
            "parameters": {"method": "POST", "url": url, "authentication": "genericCredentialType",
                           "genericAuthType": "httpHeaderAuth", "sendBody": True, "specifyBody": "json",
                           "jsonBody": body_expr, "options": {}},
            "credentials": APOLLO_CRED, "continueOnFail": True, "onError": "continueRegularOutput"}


TODAY = "new Date().toISOString().slice(0, 10)"

select_js = r"""const MAX_PER_RUN = __MAX__;
const SOURCE_DOMAINS = new Set(['betalist.com', 'tech.eu', 'wamda.com', 'linkedin.com']);
function domainOf(url) {
  const d = String(url || '').trim().toLowerCase()
    .replace(/^https?:\/\//, '').replace(/^www\./, '').split('/')[0].split('?')[0];
  return SOURCE_DOMAINS.has(d) ? '' : d;
}
const out = [];
for (const item of $input.all()) {
  const j = item.json;
  const name = String(j['Startup name'] || '').trim();
  if (!name) continue;
  if (String(j['Email'] || '').trim()) continue;          // already has a contact
  if (String(j['Apollo Enrich'] || '').trim()) continue;  // already attempted
  out.push({ json: { row_number: j.row_number, name, domain: domainOf(j['Website']) } });
  if (out.length >= MAX_PER_RUN) break;
}
return out;
""".replace("__MAX__", str(MAX_PER_RUN))

resolve_js = r"""// Rows that already had a real domain pass through; the others take the domain of the
// Apollo company whose name matches exactly (never a fuzzy match, to avoid wrong contacts).
const norm = s => String(s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
const rows = $('Select Rows to Enrich').all();
const out = [];
$input.all().forEach((item, i) => {
  const row = rows[i].json;
  let domain = row.domain, resolvedWebsite = '';
  if (!domain) {
    const orgs = item.json.organizations || item.json.accounts || [];
    const hit = orgs.find(o => norm(o.name) === norm(row.name) && o.primary_domain);
    if (hit) { domain = hit.primary_domain; resolvedWebsite = 'https://' + hit.primary_domain; }
  }
  out.push({ json: { ...row, domain, resolvedWebsite } });
});
return out;
"""

with_domain_js = "return $input.all().filter(it => it.json.domain);"

no_domain_js = r"""return $input.all().filter(it => !it.json.domain).map(it => ({ json: {
  row_number: it.json.row_number,
  'Apollo Enrich': 'No website found - ' + __TODAY__,
}}));
""".replace("__TODAY__", TODAY)

rank_js = r"""const PRIORITY_TITLES = [
  ['ceo', 'chief executive officer', 'founder', 'co-founder', 'cofounder', 'owner', 'president',
   'managing director', 'general manager'],
  ['coo', 'cto', 'cfo', 'cpo', 'vp', 'vice president', 'head of', 'director', 'partner', 'principal'],
];
function titleRank(t) {
  t = String(t || '').toLowerCase();
  for (let r = 0; r < PRIORITY_TITLES.length; r++) if (PRIORITY_TITLES[r].some(k => t.includes(k))) return r;
  return 99;
}
const rows = $('With Domain').all();
const out = [];
$input.all().forEach((item, i) => {
  const people = (item.json.people || []).filter(p => p.has_email && p.id);
  people.sort((a, b) => titleRank(a.title) - titleRank(b.title));
  out.push({ json: { ...rows[i].json, candidateId: people.length ? people[0].id : null, candidates: people.length } });
});
return out;
"""

has_candidate_js = "return $input.all().filter(it => it.json.candidateId);"

no_candidate_js = r"""return $input.all().filter(it => !it.json.candidateId).map(it => {
  const upd = { row_number: it.json.row_number, 'Apollo Enrich': 'No contact in Apollo - ' + __TODAY__ };
  if (it.json.resolvedWebsite) upd['Website'] = it.json.resolvedWebsite;
  return { json: upd };
});
""".replace("__TODAY__", TODAY)

found_js = r"""const rows = $('Has Candidate').all();
const out = [];
$input.all().forEach((item, i) => {
  const row = rows[i].json;
  const p = item.json.person || {};
  const upd = { row_number: row.row_number };
  if (row.resolvedWebsite) upd['Website'] = row.resolvedWebsite;
  if (p.email) {
    upd['Email'] = p.email;
    upd['Full Name'] = p.name || [p.first_name, p.last_name].filter(Boolean).join(' ');
    upd['Job title'] = p.title || p.headline || '';
    upd['Apollo Enrich'] = 'Found - ' + __TODAY__;
  } else {
    upd['Apollo Enrich'] = 'Email not revealed - ' + __TODAY__;
  }
  out.push({ json: upd });
});
return out;
""".replace("__TODAY__", TODAY)

write = {"name": "Pipeline - Write Enrichment", "type": "n8n-nodes-base.googleSheets", "typeVersion": 4.5,
         "position": [2200, 0], "credentials": GS_CRED,
         "parameters": {"operation": "update", "documentId": DOC, "sheetName": PIPELINE,
                        "columns": {"mappingMode": "autoMapInputData", "value": {},
                                    "matchingColumns": ["row_number"], "schema": []},
                        "options": {"handlingExtraData": "insertInNewColumn"}}}

nodes = [
    {"name": "Apollo Enrich Trigger", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 0],
     "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "5-59/15 * * * *"}]}}},
    {"name": "Pipeline - Get Rows", "type": "n8n-nodes-base.googleSheets", "typeVersion": 4.5, "position": [220, 0],
     "parameters": {"documentId": DOC, "sheetName": PIPELINE, "options": {}}, "credentials": GS_CRED},
    code("Select Rows to Enrich", [440, 0], select_js),
    apollo("Apollo - Find Company", [660, 0], "https://api.apollo.io/api/v1/mixed_companies/search",
           "={{ JSON.stringify($json.domain ? { q_organization_domains_list: [$json.domain], per_page: 1 } "
           ": { q_organization_name: $json.name, per_page: 5 }) }}"),
    code("Resolve Domain", [880, 0], resolve_js),
    code("With Domain", [1100, -120], with_domain_js),
    code("No Domain", [1100, 160], no_domain_js),
    apollo("Apollo - Search People", [1320, -120], "https://api.apollo.io/api/v1/mixed_people/api_search",
           "={{ JSON.stringify({ q_organization_domains_list: [$json.domain], per_page: 10 }) }}"),
    code("Pick Best Contact", [1540, -120], rank_js),
    code("Has Candidate", [1760, -240], has_candidate_js),
    code("No Candidate", [1760, 0], no_candidate_js),
    apollo("Apollo - Reveal Email", [1980, -240], "https://api.apollo.io/api/v1/people/match",
           "={{ JSON.stringify({ id: $json.candidateId }) }}"),
    code("Build Found Update", [2200, -240], found_js),
    {**write, "position": [2420, 0]},
]


def link(a, b):
    connections.setdefault(a, {"main": [[]]})["main"][0].append({"node": b, "type": "main", "index": 0})


connections = {}
for a, b in [("Apollo Enrich Trigger", "Pipeline - Get Rows"), ("Pipeline - Get Rows", "Select Rows to Enrich"),
             ("Select Rows to Enrich", "Apollo - Find Company"), ("Apollo - Find Company", "Resolve Domain"),
             ("Resolve Domain", "With Domain"), ("Resolve Domain", "No Domain"),
             ("With Domain", "Apollo - Search People"), ("Apollo - Search People", "Pick Best Contact"),
             ("Pick Best Contact", "Has Candidate"), ("Pick Best Contact", "No Candidate"),
             ("Has Candidate", "Apollo - Reveal Email"), ("Apollo - Reveal Email", "Build Found Update"),
             ("No Domain", "Pipeline - Write Enrichment"), ("No Candidate", "Pipeline - Write Enrichment"),
             ("Build Found Update", "Pipeline - Write Enrichment")]:
    link(a, b)

json.dump({"name": "Pipeline - Apollo Enrich", "nodes": nodes, "connections": connections,
           "settings": {"executionOrder": "v1"}}, open(f"{out_dir}/enrich.json", "w"), indent=1)
print("ok", "TEST" if TEST else "PROD")
