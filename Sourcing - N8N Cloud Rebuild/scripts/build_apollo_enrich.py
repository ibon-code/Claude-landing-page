"""Generates 'Pipeline - Apollo Enrich' (every 15 min, offset 5 min after Move to Pipeline).

For each Pipeline row without an email and not yet attempted, in one linear pass
(every node emits exactly one item per row, so later nodes zip results by index):
  1. Resolve the company domain. Only if Website is a source-site URL (BetaList/tech.eu/Wamda),
     look the company up in Apollo by exact name (1 credit) and use its real domain.
  2. Search people at that domain (free) and rank by title: CEO > founder > president/MD >
     other C-level > VP/head/director. Prefer people Apollo flags has_email; if none, still
     try the best-ranked person.
  3. Reveal that one person via people/match (1 Apollo credit when an email comes back).
  4. No email from Apollo -> read the startup's homepage and /contact page and take a public
     contact address on the startup's own domain (e.g. hello@, founders@).
  5. 'Company LinkedIn' = the company page linked on the startup's own site, else (only for rows
     whose domain had to be looked up in Apollo) Apollo's company page; the page name must match. 'Not found' when neither.
     Rows that already went through enrichment but have no 'Company LinkedIn' yet get a light
     company-only pass that reads only the startup's website (no Apollo calls, 0 credits).
Every attempted row gets 'Apollo Enrich' filled in, so it is never retried automatically.
Rows marked 'No contact in Apollo' by the first version are retried once with this logic.
Clear the cell to force a retry.
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
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
# Requests go out 5 at a time so a large backlog doesn't trip Apollo's rate limit.
BATCHING = {"batching": {"batch": {"batchSize": 5, "batchInterval": 1000}}}
# Plain website reads (no rate-limited API): larger batches so a big backlog finishes well within 15 minutes.
PAGE_BATCHING = {"batching": {"batch": {"batchSize": 15, "batchInterval": 200}}}
MAX_PER_RUN = 3 if TEST else 1000  # effectively "all pending rows"


def code(name, pos, js):
    return {"name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos,
            "parameters": {"jsCode": js}}


def apollo(name, pos, url, body_expr, call_when="$json.mode !== 'companyOnly'"):
    # Rows that don't need a given Apollo call get an unreachable URL instead (fails, costs nothing).
    url_expr = "={{ " + call_when + " ? '" + url + "' : 'https://invalid.invalid' }}"
    return {"name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": pos,
            "parameters": {"method": "POST", "url": url_expr, "authentication": "genericCredentialType",
                           "genericAuthType": "httpHeaderAuth", "sendBody": True, "specifyBody": "json",
                           "jsonBody": body_expr, "options": BATCHING},
            "credentials": APOLLO_CRED, "continueOnFail": True, "onError": "continueRegularOutput"}


def fetch_page(name, pos, url_expr):
    return {"name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": pos,
            "parameters": {"url": url_expr, "sendHeaders": True,
                           "headerParameters": {"parameters": [{"name": "User-Agent", "value": BROWSER_UA}]},
                           "options": {**PAGE_BATCHING, "timeout": 10000,
                                       "response": {"response": {"responseFormat": "text", "neverError": True}}}},
            "continueOnFail": True, "onError": "continueRegularOutput"}


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
  const hasEmail = !!String(j['Email'] || '').trim();
  const status = String(j['Apollo Enrich'] || '').trim();
  const hasCompanyLinkedIn = !!String(j['Company LinkedIn'] || '').trim();
  // 'No contact in Apollo' was written by the first version, which had no fallbacks: retry once.
  const needsContact = !hasEmail && (!status || status.startsWith('No contact in Apollo'));
  let mode;
  if (needsContact) mode = 'full';
  else if (!hasCompanyLinkedIn) mode = 'companyOnly';
  else continue;
  out.push({ json: { row_number: j.row_number, name, domain: domainOf(j['Website']), mode } });
  if (out.length >= MAX_PER_RUN) break;
}
return out;
""".replace("__MAX__", str(MAX_PER_RUN))

resolve_js = r"""// Rows that already had a real domain pass through; the others take the domain of the
// Apollo company whose name matches exactly (never a fuzzy match, to avoid wrong contacts).
const norm = s => String(s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
const rows = $('Select Rows to Enrich').all();
return $input.all().map((item, i) => {
  const row = rows[i].json;
  const orgs = item.json.organizations || item.json.accounts || [];
  let domain = row.domain, resolvedWebsite = '', org = null;
  if (!domain) {
    org = orgs.find(o => norm(o.name) === norm(row.name) && o.primary_domain) || null;
    if (org) { domain = org.primary_domain; resolvedWebsite = 'https://' + org.primary_domain; }
  } else {
    org = orgs.find(o => String(o.primary_domain || '').toLowerCase() === domain) || null;
  }
  return { json: { ...row, domain, resolvedWebsite, companyLinkedin: (org && org.linkedin_url) || '' } };
});
"""

rank_js = r"""const RANKS = [
  ['ceo', 'chief executive'],
  ['founder'],
  ['president', 'managing director', 'general manager', 'owner'],
  ['coo', 'cto', 'cfo', 'cpo', 'cmo', 'chief'],
  ['vp', 'vice president', 'head of', 'director', 'partner', 'principal'],
];
function titleRank(t) {
  t = String(t || '').toLowerCase();
  for (let r = 0; r < RANKS.length; r++) if (RANKS[r].some(k => t.includes(k))) return r;
  return 99;
}
const byRank = (a, b) => titleRank(a.title) - titleRank(b.title);
const rows = $('Resolve Domain').all();
return $input.all().map((item, i) => {
  const row = rows[i].json;
  const people = (row.domain && row.mode === 'full') ? (item.json.people || []).filter(p => p.id) : [];
  const withEmail = people.filter(p => p.has_email).sort(byRank);
  // Nobody flagged has_email: still try the best-ranked person, Apollo sometimes finds one.
  const pick = withEmail[0] || people.slice().sort(byRank)[0] || null;
  const apolloError = !!(row.domain && item.json.error);
  return { json: { ...row, candidateId: pick ? pick.id : null, peopleFound: people.length, apolloError } };
});
"""

reveal_js = r"""const rows = $('Pick Best Contact').all();
return $input.all().map((item, i) => {
  const row = rows[i].json;
  const p = (row.candidateId && item.json.person) || {};
  // Apollo returns a placeholder like email_not_unlocked@domain.com when it has no real address.
  const email = /not_unlocked|@domain\.com$/i.test(p.email || '') ? '' : (p.email || '');
  return { json: { ...row,
    apolloError: row.apolloError || !!(row.candidateId && item.json.error),
    email,
    linkedin: p.linkedin_url || '',
    fullName: p.name || [p.first_name, p.last_name].filter(Boolean).join(' '),
    jobTitle: p.title || p.headline || '',
  }};
});
"""

HOME_URL = "={{ $json.domain ? 'https://' + $json.domain : 'https://invalid.invalid' }}"
def sub_page_url(path):
    r = "$('Apollo Reveal Result').all()[$itemIndex].json"
    return (f"={{{{ {r}.domain ? 'https://' + {r}.domain + '{path}' : 'https://invalid.invalid' }}}}")

final_js = r"""// Final outcome per row. Website emails and LinkedIn links are only taken from the startup's
// own pages; website emails must be on its own domain (no agency, CDN or tracking addresses).
const rows = $('Apollo Reveal Result').all();
const homes = $('Fetch Homepage').all();
const contacts = $('Fetch Contact Page').all();
const TODAY = __TODAY__;
const PREFERRED = ['founders', 'founder', 'ceo', 'hello', 'hi', 'contact', 'info', 'team', 'partnerships', 'business', 'sales'];
const text = it => (it && typeof it.json.data === 'string') ? it.json.data : '';
const norm = s => String(s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
function siteEmail(html, domain) {
  if (!html || !domain) return '';
  const base = domain.replace(/^www\./, '');
  const found = new Set();
  for (const m of String(html).matchAll(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g)) {
    const e = m[0].toLowerCase();
    const host = e.split('@')[1];
    if (/\.(png|jpe?g|gif|svg|webp)$/.test(e)) continue;
    if (host === base || host.endsWith('.' + base)) found.add(e);
  }
  const list = [...found];
  list.sort((a, b) => {
    const ra = PREFERRED.indexOf(a.split('@')[0]), rb = PREFERRED.indexOf(b.split('@')[0]);
    return (ra < 0 ? 99 : ra) - (rb < 0 ? 99 : rb);
  });
  return list[0] || '';
}
function linkedinLinks(html, kind) {
  const re = new RegExp('linkedin\\.com/' + kind + '/([A-Za-z0-9_%-]+)', 'gi');
  const seen = [];
  for (const m of String(html || '').matchAll(re)) {
    const url = 'https://www.linkedin.com/' + kind + '/' + m[1].toLowerCase();
    if (!seen.includes(url)) seen.push(url);
  }
  return seen;
}
// A company page linked on the site must look like this startup (sites often link their CMS or agency).
function matchesStartup(url, row) {
  const slug = norm(String(url).split('/company/')[1]);
  if (!slug) return false;
  const keys = [norm(row.name), norm(String(row.domain || '').split('.')[0])].filter(k => k.length >= 4);
  return keys.some(k => slug.includes(k) || k.includes(slug));
}
const out = [];
$input.all().forEach((item, i) => {
  const row = rows[i].json;
  // Apollo errored (e.g. rate limit): write nothing, so the row is simply retried next run.
  if (row.mode === 'full' && row.apolloError && !row.email) return;
  const pages = [text(homes[i]), text(contacts[i]), text(item)].join('\n');
  const upd = { row_number: row.row_number };
  if (row.resolvedWebsite) upd['Website'] = row.resolvedWebsite;

  // The startup's own site is the most reliable source for its company page; Apollo's is only a fallback,
  // and both must look like this startup.
  const siteCompany = linkedinLinks(pages, 'company').find(u => matchesStartup(u, row)) || '';
  const apolloCompany = row.companyLinkedin && matchesStartup(row.companyLinkedin, row) ? row.companyLinkedin : '';
  upd['Company LinkedIn'] = siteCompany || apolloCompany || 'Not found';

  if (row.mode === 'companyOnly') {
    out.push({ json: { row_number: row.row_number, 'Company LinkedIn': upd['Company LinkedIn'] } });
    return;
  }
  if (!row.domain) {
    upd['Apollo Enrich'] = 'No website found - ' + TODAY;
  } else if (row.email) {
    upd['Email'] = row.email;
    upd['Full Name'] = row.fullName;
    upd['Job title'] = row.jobTitle;
    upd['Apollo Enrich'] = 'Found - ' + TODAY;
  } else {
    const email = siteEmail(pages, row.domain);
    if (email) {
      upd['Email'] = email;
      upd['Job title'] = 'Generic contact (website)';
      upd['Apollo Enrich'] = 'Email from website - ' + TODAY;
    } else {
      // No email anywhere: still record who the best contact is, for a LinkedIn approach.
      if (row.fullName) { upd['Full Name'] = row.fullName; upd['Job title'] = row.jobTitle; }
      upd['Apollo Enrich'] = (row.peopleFound ? 'No email found' : 'No people in Apollo') + ', none on website - ' + TODAY;
    }
  }
  out.push({ json: upd });
});
return out;
""".replace("__TODAY__", TODAY)

nodes = [
    {"name": "Apollo Enrich Trigger", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 0],
     "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "5-59/15 * * * *"}]}}},
    {"name": "Pipeline - Get Rows", "type": "n8n-nodes-base.googleSheets", "typeVersion": 4.5, "position": [220, 0],
     "parameters": {"documentId": DOC, "sheetName": PIPELINE, "options": {}}, "credentials": GS_CRED},
    code("Select Rows to Enrich", [440, 0], select_js),
    # Organization Search costs 1 Apollo credit per call: only used to find the real domain of rows
    # whose Website is a BetaList/tech.eu/Wamda link.
    apollo("Apollo - Find Company", [660, 0], "https://api.apollo.io/api/v1/mixed_companies/search",
           "={{ JSON.stringify({ q_organization_name: $json.name, per_page: 5 }) }}",
           call_when="$json.mode === 'full' && !$json.domain"),
    code("Resolve Domain", [880, 0], resolve_js),
    # A domain that can't exist returns 0 people, so rows without a domain never search all of Apollo.
    apollo("Apollo - Search People", [1100, 0], "https://api.apollo.io/api/v1/mixed_people/api_search",
           "={{ JSON.stringify({ q_organization_domains_list: [($json.mode === 'full' && $json.domain) || 'invalid.invalid'], per_page: 10 }) }}"),
    code("Pick Best Contact", [1320, 0], rank_js),
    apollo("Apollo - Reveal Email", [1540, 0], "https://api.apollo.io/api/v1/people/match",
           "={{ JSON.stringify({ id: $json.candidateId || 'none' }) }}"),
    code("Apollo Reveal Result", [1760, 0], reveal_js),
    fetch_page("Fetch Homepage", [1980, 0], HOME_URL),
    fetch_page("Fetch Contact Page", [2200, 0], sub_page_url("/contact")),
    fetch_page("Fetch About Page", [2420, 0], sub_page_url("/about")),
    code("Build Row Update", [2640, 0], final_js),
    {"name": "Pipeline - Write Enrichment", "type": "n8n-nodes-base.googleSheets", "typeVersion": 4.5,
     "position": [2860, 0], "credentials": GS_CRED,
     "parameters": {"operation": "update", "documentId": DOC, "sheetName": PIPELINE,
                    "columns": {"mappingMode": "autoMapInputData", "value": {},
                                "matchingColumns": ["row_number"], "schema": []},
                    "options": {"handlingExtraData": "insertInNewColumn"}}},
]
names = [n["name"] for n in nodes]
connections = {a: {"main": [[{"node": b, "type": "main", "index": 0}]]} for a, b in zip(names, names[1:])}

json.dump({"name": "Pipeline - Apollo Enrich", "nodes": nodes, "connections": connections,
           "settings": {"executionOrder": "v1"}}, open(f"{out_dir}/enrich.json", "w"), indent=1)
print("ok", "TEST" if TEST else "PROD")
