"""Generates 'Pipeline - Playbook Invite' (semi-automatic, agreed with the user 2026-11-03).

After a first meeting the user sets 'Playbook Invite' = YES on a Pipeline row.
  A. n8n creates the startup profile on Playbook (MCP create_startup, text written by Claude from the startup's
     own homepage, country/vertical picked from Playbook's own lists) and emails the user the Team link.
  B. The user presses + in the profile's Team (name + email of the founder -> Playbook sends its invitation),
     then sets 'Team Added' = YES. n8n sends our standard "Playbook invite" email.
  The Playbook MCP has no "add team member" tool yet (requested 2026-11-02, id b7a5456c-...): that is the
  only manual step.

Guardrails:
- A row is claimed before anything happens ('Playbook Invite Status' = Creating profile / Sending ...) and is
  never retried automatically after the claim: any failure becomes 'Needs review: ...' / 'Send failed: ...'.
- No duplicate profile: stop if Playbook already has the exact website domain, or 'Playbook' = YES.
- Stop if the recipient email is personal mail or our own domain (Playbook refuses those domains).
- Claude may only use countries/verticals from Playbook's lists, and only facts from the homepage.
  Empty homepage = review (never invent a profile).
- Our email: only after 'Team Added' = YES on a row whose profile n8n created; hard block if Gmail Sent
  already has a "Playbook invite" email to that address (all time); max PER_RUN_CAP per run, DAILY_CAP a day.
- Mon-Fri 09:00-17:59 Europe/Rome. DRY_RUN: nothing created on Playbook, nothing written, no founder email,
  one preview email to me. TEST_ONLY_EMAIL: live, but only for rows whose recipient is that address.

Usage: python3 build_playbook_invite.py <out_dir> [--live] [--test-email ADDR] [--deploy]  (created/updated INACTIVE)
"""
import json, os, sys, uuid, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from email_signature import SIGNATURE_HTML  # noqa: E402

out_dir = sys.argv[1]
DEPLOY = "--deploy" in sys.argv
DRY_RUN = "--live" not in sys.argv
TEST_ONLY_EMAIL = sys.argv[sys.argv.index("--test-email") + 1].lower() if "--test-email" in sys.argv else None
DAILY_CAP = 20
PER_RUN_CAP = 3
NAME = "Pipeline - Playbook Invite"
ALERT_NAME = "Util - Error Alert"
ME = "i.bon@pnptc.com"
SENDER = "Iacopo Bon <i.bon@pnptc.com>"
PLAYBOOK_APP = "https://app.playbook.vc"
PARTNERS_URL = "https://www.plugandplaytechcenter.com/innovation-services/corporations/our-corporate-partners"

DOC = {"__rl": True, "value": "1LpPqSKXOvB2FdqNGNnlVBpPDvnfDrYml7npHJEZpKxc", "mode": "list",
       "cachedResultName": "Sourcing - N8N Cloud",
       "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1LpPqSKXOvB2FdqNGNnlVBpPDvnfDrYml7npHJEZpKxc/edit?usp=drivesdk"}
PIPELINE = {"__rl": True, "value": "114224284", "mode": "id"}
GS_CRED = {"googleSheetsOAuth2Api": {"id": "gRSPd8YEw5iadWsy", "name": "Google Sheets (Iacopo Bon)"}}
GMAIL_CRED = {"gmailOAuth2": {"id": "3FF4ROo5Rl75aufp", "name": "Gmail (Iacopo Bon)"}}
PLAYBOOK_CRED = {"mcpOAuth2Api": {"id": "TerVDTem462Rn6TK", "name": "Playbook MCP - Iacopo Bon"}}
PLAYBOOK_MCP = "https://playbook-backend-prod01.cloud.playbook.vc/v3/mcp/playbook/"
CLAUDE_UTIL = {"__rl": True, "value": "V5wGQ55LdYLhSCmf", "mode": "list", "cachedResultName": "Util - Claude Messages API"}
RETRY = {"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 5000}
GAPI = "https://gmail.googleapis.com/gmail/v1/users/me"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
LA, LB = "Loop Create", "Loop Send"


def node(name, typ, ver, pos, params, **extra):
    return {"id": str(uuid.uuid4()), "name": name, "type": typ, "typeVersion": ver, "position": pos,
            "parameters": params, **extra}


def code(name, pos, js, **extra):
    return node(name, "n8n-nodes-base.code", 2, pos, {"jsCode": js}, **extra)


def sheets_update(name, pos):
    return node(name, "n8n-nodes-base.googleSheets", 4.5, pos,
                {"operation": "update", "documentId": DOC, "sheetName": PIPELINE,
                 "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": ["row_number"],
                             "schema": []},
                 "options": {"handlingExtraData": "insertInNewColumn", "cellFormat": "RAW"}},
                credentials=GS_CRED, **RETRY)


def gmail_api(name, pos, url, query=None, method="GET", body=None, retry=True, **extra):
    p = {"method": method, "url": url, "authentication": "predefinedCredentialType",
         "nodeCredentialType": "gmailOAuth2", "options": {}}
    if query:
        p.update({"sendQuery": True, "queryParameters": {"parameters": [{"name": k, "value": v} for k, v in query]}})
    if body:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
    return node(name, "n8n-nodes-base.httpRequest", 4.2, pos, p, credentials=GMAIL_CRED,
                **(RETRY if retry else {}), **extra)


def gmail_send_me(name, pos, subject_expr, html_expr):
    return node(name, "n8n-nodes-base.gmail", 2.1, pos,
                {"resource": "message", "operation": "send", "sendTo": ME, "subject": subject_expr,
                 "emailType": "html", "message": html_expr, "options": {"appendAttribution": False}},
                credentials=GMAIL_CRED, onError="continueRegularOutput")


def mcp(name, pos, tool, json_expr, **extra):
    return node(name, "@n8n/n8n-nodes-langchain.mcpClient", 1.1, pos,
                {"serverTransport": "httpStreamable", "endpointUrl": PLAYBOOK_MCP, "authentication": "mcpOAuth2Api",
                 "tool": {"__rl": True, "mode": "list", "value": tool, "cachedResultName": tool},
                 "inputMode": "json", "jsonInput": json_expr, "options": {"timeout": 60000}},
                credentials=PLAYBOOK_CRED, onError="continueRegularOutput", **extra)


def if_true(name, pos, expr):
    return node(name, "n8n-nodes-base.if", 2, pos, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                       "conditions": [{"id": str(uuid.uuid4()), "leftValue": expr, "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                       "combinator": "and"},
        "options": {}})


# ---------------------------------------------------------------- shared JS
COMMON = r"""
const isYes = v => typeof v === 'boolean' ? v : ['TRUE', 'YES'].includes(String(v || '').trim().toUpperCase());
const norm = e => String(e || '').trim().toLowerCase();
const EMAIL_RE = /^[^@\s,;<>]+@[^@\s,;<>]+\.[a-z]{2,}$/;
const FREE = /^(gmail|googlemail|outlook|hotmail|live|yahoo|icloud|me|aol|proton|protonmail|gmx|mail|yandex|zoho)\./;
const host = u => String(u || '').trim().toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '').split(/[\/?#]/)[0];
const nowIso = () => new Date().toISOString();
function recipientOf(r) {
  const mc = norm(r['Meeting contact']);
  if (mc) return { email: mc, name: String(r['Meeting contact name'] || '').trim() };
  return { email: norm(r['Email']), name: String(r['Full Name'] || '').trim() };
}
"""

config_js = f"""const DRY_RUN = {json.dumps(DRY_RUN)};
const TEST_ONLY_EMAIL = {json.dumps(TEST_ONLY_EMAIL)};
const now = new Date();
const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {{
  timeZone: 'Europe/Rome', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', weekday: 'short', hour12: false }}).formatToParts(now).map(p => [p.type, p.value]));
const hour = Number(parts.hour);
const inWindow = !['Sat', 'Sun'].includes(parts.weekday) && hour >= 9 && hour < 18;
if (!DRY_RUN && !inWindow && !TEST_ONLY_EMAIL) return [];
const today = `${{parts.year}}-${{parts.month}}-${{parts.day}}`;
const probe = new Date(`${{today}}T00:00:00Z`);
const romeAtProbe = new Date(probe.toLocaleString('en-US', {{ timeZone: 'Europe/Rome' }}));
const utcAtProbe = new Date(probe.toLocaleString('en-US', {{ timeZone: 'UTC' }}));
const dayStartEpoch = Math.floor((probe.getTime() - (romeAtProbe - utcAtProbe)) / 1000);
return [{{ json: {{ dryRun: DRY_RUN, testOnlyEmail: TEST_ONLY_EMAIL, dailyCap: {DAILY_CAP}, perRunCap: {PER_RUN_CAP},
  today, dayStartEpoch }} }}];
"""

# ---------------------------------------------------------------- A. create profile
select_create_js = COMMON + r"""const cfg = $('Config').first().json;
const out = [];
for (const it of $('Pipeline - Get Rows').all()) {
  const r = it.json;
  if (!isYes(r['Playbook Invite']) || String(r['Playbook Invite Status'] || '').trim()) continue;
  const name = String(r['Startup name'] || '').trim();
  const rec = recipientOf(r);
  if (cfg.testOnlyEmail && rec.email !== cfg.testOnlyEmail) continue;
  if (!cfg.testOnlyEmail && /test company|delete me/i.test(name)) continue;
  let problem = '';
  const domain = host(r['Website']);
  if (!name) problem = 'Startup name is empty';
  else if (!domain || !/\./.test(domain)) problem = 'Website is empty or not a domain';
  else if (!EMAIL_RE.test(rec.email)) problem = 'No valid recipient email (Meeting contact / Email)';
  else if (isYes(r['Playbook'])) problem = 'Playbook column says YES: the startup is already on Playbook';
  else {
    const recDomain = rec.email.split('@')[1];
    if (FREE.test(recDomain) || recDomain === 'pnptc.com') problem = 'Recipient uses a personal or Plug and Play email (' + recDomain + '): Playbook will not accept it in the Team. Put the founder company email in Meeting contact';
  }
  const ed = rec.email.split('@')[1] || '';
  out.push({ json: { row_number: r.row_number, name, domain, website: 'https://' + domain,
    email: rec.email, fullName: rec.name, problem,
    domainNote: (!problem && ed !== domain && !ed.endsWith('.' + domain)) ? ed : '' } });
  if (out.length >= cfg.perRunCap) break;
}
return out;
"""

claim_create_js = """const e = $('""" + LA + """').first().json;
return [{ json: { row_number: e.row_number, 'Playbook Invite Status': 'Creating profile ' + new Date().toISOString() } }];
"""

precheck_js = r"""// Stop before any Playbook write if the row has a problem or Playbook already has this exact domain.
const e = $('""" + LA + r"""').first().json;
const host = u => String(u || '').trim().toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '').split(/[\/?#]/)[0];
if (e.problem) return [{ json: { ...e, ok: false, reason: e.problem } }];
const it = $input.first();
let sc = it.json.structuredContent;
if (!sc) sc = (it.json.content || []).map(c => c.text).find(t => t && typeof t === 'object');
if (it.json.error || !sc || !Array.isArray(sc.results))
  return [{ json: { ...e, ok: false, reason: 'Playbook search failed (MCP login expired?): ' + JSON.stringify(it.json.error || it.json).slice(0, 150) } }];
const hit = sc.results.find(s => host(s.website) === e.domain || host(s.domain_name) === e.domain);
if (hit) return [{ json: { ...e, ok: false, reason: 'Already on Playbook: ' + (hit.url || hit.name || hit.company_name || '') } }];
return [{ json: { ...e, ok: true } }];
"""

LISTS_HELPER = r"""
// MCP list tools: collect every {id, name} object, wherever it sits in the response.
function idNames(it) {
  if (!it || !it.json || it.json.error) return null;
  const out = [];
  const walk = o => {
    if (Array.isArray(o)) return o.forEach(walk);
    if (o && typeof o === 'object') {
      const nm = o.name || o.country_name || o.vertical_name || o.title || o.label;
      if ((typeof o.id === 'number' || /^\d+$/.test(String(o.id))) && typeof nm === 'string') out.push({ id: Number(o.id), name: nm.trim() });
      Object.values(o).forEach(v => { if (v && typeof v === 'object') walk(v); });
    }
  };
  walk(it.json.structuredContent || it.json.content || it.json);
  const seen = new Set();
  return out.filter(x => !seen.has(x.id) && seen.add(x.id));
}
"""

prompt_js = LISTS_HELPER + r"""const e = $('Pre-check').first().json;
const countries = idNames($('Playbook - List Countries').first());
const verticals = idNames($('Playbook - List Verticals').first());
const html = String($input.first().json.data || $input.first().json.body || '');
const strip = s => s.replace(/<script[\s\S]*?<\/script>/gi, ' ').replace(/<style[\s\S]*?<\/style>/gi, ' ')
  .replace(/<[^>]+>/g, ' ').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&#39;|&rsquo;/g, "'").replace(/\s+/g, ' ').trim();
const meta = n => { const m = new RegExp('<meta[^>]+(?:name|property)=["\']' + n + '["\'][^>]+content=["\']([^"\']*)', 'i').exec(html); return m ? strip(m[1]) : ''; };
const title = (/<title[^>]*>([\s\S]*?)<\/title>/i.exec(html) || [])[1] || '';
const body = strip(html).slice(0, 3500);
const site = [strip(title), meta('description'), meta('og:description'), body].filter(Boolean).join('\n').slice(0, 4500);
let reason = '';
if (!countries || !countries.length) reason = 'Could not read the country list from Playbook';
else if (!verticals || !verticals.length) reason = 'Could not read the vertical list from Playbook';
else if (site.length < 200) reason = 'Homepage not readable (too little text): profile not created to avoid inventing it';
if (reason) return [{ json: { ...e, ok: false, reason } }];
const prompt = 'You write a startup profile for Playbook, the startup database of Plug and Play Tech Center.\n'
  + 'Use ONLY facts stated in the homepage text below. No hype, no superlatives, no guesses.\n\n'
  + 'Startup: ' + e.name + '\nWebsite: ' + e.website + '\n\nHomepage text:\n' + site + '\n\n'
  + 'Allowed verticals (copy names exactly): ' + JSON.stringify(verticals.map(v => v.name)) + '\n'
  + 'Allowed countries (copy names exactly): ' + JSON.stringify(countries.map(c => c.name)) + '\n\n'
  + 'Return ONLY JSON (no prose, no markdown fences):\n'
  + '{"one_liner": "what the company does, max 120 characters", '
  + '"description": "2-4 factual sentences: product, customers, how it works", '
  + '"verticals": ["1 or 2 names from the allowed list"], '
  + '"country": "HQ country from the allowed list, or empty string if the homepage does not say", '
  + '"hq_city": "HQ city if stated, else empty string", "founded": "4-digit year if stated, else empty string"}';
return [{ json: { ...e, ok: true, prompt, max_tokens: 700 } }];
"""

validate_js = LISTS_HELPER + r"""const e = $('Build Profile Prompt').first().json;
const info = $input.first().json || {};
const countries = idNames($('Playbook - List Countries').first()) || [];
const verticals = idNames($('Playbook - List Verticals').first()) || [];
const byName = (list, n) => list.find(x => x.name.toLowerCase() === String(n || '').trim().toLowerCase());
const one = String(info.one_liner || '').trim(), desc = String(info.description || '').trim();
const vs = (Array.isArray(info.verticals) ? info.verticals : [info.verticals]).filter(Boolean).map(v => byName(verticals, v));
const country = byName(countries, info.country);
const city = String(info.hq_city || '').trim(), founded = String(info.founded || '').trim();
let reason = '';
if (info.error || !one || !desc) reason = 'Claude returned no usable profile';
else if (one.length < 10 || one.length > 160) reason = 'One-liner has an odd length: ' + one.slice(0, 80);
else if (desc.length < 60 || desc.length > 1500) reason = 'Description has an odd length';
else if (!vs.length || vs.length > 2 || vs.some(v => !v)) reason = 'Vertical not in the Playbook list: ' + JSON.stringify(info.verticals).slice(0, 80);
else if (!country) reason = 'HQ country not stated on the homepage or not in the Playbook list: ' + String(info.country || '(empty)').slice(0, 40);
else if (/undefined|\bnull\b|NaN|\{\{|\}\}|lorem ipsum/i.test(one + desc + city)) reason = 'Profile text contains a placeholder';
if (reason) return [{ json: { ...e, ok: false, reason } }];
const create = { company_name: e.name, website: e.website, one_liner: one, description: desc,
  country_id: country.id, vertical_ids: vs.map(v => v.id) };
if (city && city.length <= 60) create.hq_city = city;
if (/^(19|20)\d\d$/.test(founded)) create.founded = founded;
return [{ json: { ...e, ok: true, create, countryName: country.name, verticalNames: vs.map(v => v.name) } }];
"""

parse_created_js = r"""const e = $('Validate Profile').first().json;
const it = $input.first();
const find = o => {
  if (!o || typeof o !== 'object') return null;
  if (Array.isArray(o)) { for (const x of o) { const f = find(x); if (f) return f; } return null; }
  const id = o.id ?? o.startup_id;
  if ((typeof id === 'number' || /^\d+$/.test(String(id))) && (o.company_name || o.name || o.website || o.startup_id)) return Number(id);
  for (const v of Object.values(o)) { const f = find(v); if (f) return f; }
  return null;
};
const id = it.json.error ? null : find(it.json.structuredContent || it.json.content || it.json);
if (!id) return [{ json: { ...e, ok: false, created: !it.json.error,
  reason: it.json.error ? 'create_startup failed: ' + JSON.stringify(it.json.error).slice(0, 150)
                        : 'create_startup answered without a startup id - check Playbook before retrying' } }];
return [{ json: { ...e, ok: true, startupId: id,
  profileUrl: '""" + PLAYBOOK_APP + r"""/discover/startups/' + id + '/overview',
  teamUrl: '""" + PLAYBOOK_APP + r"""/discover/startups/' + id + '/team' } }];
"""

created_status_js = r"""const e = $('Parse Created Startup').first().json;
return [{ json: { row_number: e.row_number, 'Playbook Profile URL': e.profileUrl,
  'Playbook Invite Status': 'Profile created ' + new Date().toISOString() + ' - add the founder in Team, then set Team Added = YES' } }];
"""

notify_created_js = r"""const e = $('Parse Created Startup').first().json;
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const [first, ...rest] = String(e.fullName || '').split(/\s+/);
let html = `<p>Profilo Playbook creato per <b>${esc(e.name)}</b> (riga ${e.row_number}).</p>`;
if (e.domainNote) html += `<p><b>Prima:</b> ACTIONS &gt; Manage domains &gt; Add domain <b>${esc(e.domainNote)}</b> (l'email del founder non e' sul dominio del sito).</p>`;
html += `<ol><li>Apri il Team: <a href="${e.teamUrl}">${e.teamUrl}</a></li>`
  + `<li>Premi <b>+</b> accanto a "Startup Team" (Member Profile) e inserisci:<br>First name: <b>${esc(first || '')}</b> &nbsp; Last name: <b>${esc(rest.join(' '))}</b><br>Email: <b>${esc(e.email)}</b> &nbsp; Job role: <b>CEO</b> &gt; SUBMIT</li>`
  + `<li>Controlla che la scheda dica "Invitation sent", poi metti <b>Team Added = YES</b> sulla riga ${e.row_number}: la nostra email parte da sola.</li></ol>`
  + `<p>Testo del profilo (controllalo su Playbook):<br><i>${esc(e.create.one_liner)}</i><br>${esc(e.create.description)}<br>`
  + `Paese: ${esc(e.countryName)} - Settore: ${esc(e.verticalNames.join(', '))}${e.create.hq_city ? ' - Citta: ' + esc(e.create.hq_city) : ''}</p>`;
return [{ json: { subject: 'Playbook: aggiungi ' + (e.fullName || e.email) + ' nel Team di ' + e.name, html } }];
"""

review_js = r"""// Any stop in branch A. Live: written on the row + email to me. Dry run: only collected for the preview.
const src = $input.first().json;
return [{ json: { row_number: src.row_number, name: src.name, email: src.email,
  'Playbook Invite Status': 'Needs review: ' + String(src.reason || 'unknown').slice(0, 300) } }];
"""

notify_review_js = r"""const e = $input.first().json;
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
return [{ json: { subject: 'Playbook invite da rivedere: ' + e.name,
  html: `<p><b>${esc(e.name)}</b> (riga ${e.row_number}, ${esc(e.email)}): nessun profilo creato, nessuna email inviata.</p><p>${esc(e['Playbook Invite Status'])}</p><p>Sistema la riga e svuota 'Playbook Invite Status' per riprovare.</p>` } }];
"""

dry_create_js = r"""const e = $('Validate Profile').first().json;
return [{ json: { kind: 'create', row_number: e.row_number, name: e.name, email: e.email, create: e.create,
  countryName: e.countryName, verticalNames: e.verticalNames, domainNote: e.domainNote } }];
"""

# ---------------------------------------------------------------- B. send our email
select_send_js = COMMON + r"""const cfg = $('Config').first().json;
const rows = $('Pipeline - Get Rows').all().map(it => it.json);
const sentGmail = ($('Gmail - Invites Sent Today').first().json.messages || []).length;
const sentSheet = rows.filter(r => String(r['Date Playbook Invite'] || '').slice(0, 10) === cfg.today).length;
const sentToday = Math.max(sentGmail, sentSheet);
const room = Math.max(0, cfg.dailyCap - sentToday);
const limit = cfg.dryRun ? cfg.perRunCap : Math.min(cfg.perRunCap, room);
const out = [];
for (const r of rows) {
  if (out.length >= limit) break;
  if (!isYes(r['Team Added']) || !isYes(r['Playbook Invite'])) continue;
  if (!/^Profile created /.test(String(r['Playbook Invite Status'] || ''))) continue;
  const rec = recipientOf(r);
  if (!EMAIL_RE.test(rec.email)) continue;
  if (cfg.testOnlyEmail && rec.email !== cfg.testOnlyEmail) continue;
  out.push({ json: { row_number: r.row_number, name: String(r['Startup name'] || '').trim(), email: rec.email,
    fullName: rec.name, sentToday } });
}
return out;
"""

build_email_js = ("const SIGNATURE_HTML = " + json.dumps(SIGNATURE_HTML) + ";\nconst SENDER = " + json.dumps(SENDER)
                  + ";\nconst PLAYBOOK = " + json.dumps(PLAYBOOK_APP) + ";\nconst PARTNERS = " + json.dumps(PARTNERS_URL)
                  + ";\n" + r"""const e = $('""" + LB + r"""').first().json;
const g = $input.first().json;
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const base = { row_number: e.row_number, name: e.name, email: e.email };
// Hard block: any earlier "Playbook invite" email to this address in Gmail Sent (fail closed on errors).
if (g.error || !g || typeof g !== 'object') return [{ json: { ...base, ok: false, reason: 'Gmail check failed - not sent' } }];
if ((g.messages || []).length) return [{ json: { ...base, ok: false, reason: 'Blocked: a Playbook invite email to this address is already in Gmail Sent' } }];
const first = (String(e.fullName || '').split(/\s+/)[0] || '').replace(/[,.]+$/, '');
// Generic inbox or no usable first name: "Dear <Startup>'s team" (legal suffix and tagline dropped).
function teamOf(name) {
  const full = String(name || '').trim();
  let n = full.split(/\s+[-|–—:]\s+/)[0];
  n = n.replace(/[,\s]+(inc|llc|ltd|limited|gmbh|ag|as|sa|sas|sl|s\.l|srl|bv|b\.v|ab|oy|corp|corporation|co)\.?$/i, '').trim().replace(/[,.]+$/, '');
  n = n || full;
  return n + (/s$/i.test(n) ? "'" : "'s") + ' team';
}
const greeting = /^\p{L}[\p{L}'’-]{1,24}$/u.test(first) ? 'Hi ' + first : 'Dear ' + teamOf(e.name);
const subject = 'Plug and Play - ' + e.name + ' Playbook invite';
const text = `${greeting},\n\nIt was a pleasure speaking with you, I really enjoyed learning about ${e.name} and your team.\n\nI sent you an invitation to complete the profile at ${PLAYBOOK}. Can you check to see if you can log in? Your profile there should serve as a starting point to apply your company to meet with our partners and network. The invitation expires after 48 hours.\n\nAdditionally, here is the list of our corporate partners for reference: ${PARTNERS}\n\nPlease keep me posted on your project's progress, and I would love to receive your deck if you have one!\n\nBest,\n\nIacopo`;
const html = `<p>${esc(greeting)},</p><p>It was a pleasure speaking with you, I really enjoyed learning about ${esc(e.name)} and your team.</p><p>I sent you an invitation to complete the profile at <a href="${PLAYBOOK}">${PLAYBOOK}</a>. Can you check to see if you can log in? Your profile there should serve as a starting point to apply your company to meet with our partners and network. <strong>The invitation expires after 48 hours.</strong></p><p>Additionally, <a href="${PARTNERS}">here is the list of our corporate partners</a> for reference.</p><p>Please keep me posted on your project's progress, and I would love to receive your deck if you have one!</p><p>Best,</p>` + SIGNATURE_HTML;
if (/undefined|\bnull\b|NaN|\{\{|\}\}/.test(text + html + subject)) return [{ json: { ...base, ok: false, reason: 'Rendered email contains a placeholder' } }];
const b64 = s => Buffer.from(s, 'utf8').toString('base64');
const b64url = s => b64(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const wrap = s => s.replace(/(.{76})/g, '$1\r\n');
const boundary = 'b' + Math.random().toString(36).slice(2) + Date.now();
const mime = ['From: ' + SENDER, 'To: ' + e.email, 'Subject: =?UTF-8?B?' + b64(subject) + '?=', 'MIME-Version: 1.0',
  'Content-Type: multipart/alternative; boundary="' + boundary + '"', '',
  '--' + boundary, 'Content-Type: text/plain; charset="UTF-8"', 'Content-Transfer-Encoding: base64', '', wrap(b64(text)),
  '--' + boundary, 'Content-Type: text/html; charset="UTF-8"', 'Content-Transfer-Encoding: base64', '', wrap(b64(html)),
  '--' + boundary + '--', ''].join('\r\n');
return [{ json: { ...base, ok: true, subject, htmlBody: html, sendBody: { raw: b64url(mime) } } }];
""")

claim_send_js = """const e = $('Build Invite Email').first().json;
return [{ json: { row_number: e.row_number, 'Playbook Invite Status': 'Sending ' + new Date().toISOString() } }];
"""
mark_sent_js = """const e = $('Build Invite Email').first().json;
const g = $input.first().json;
const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Rome' }).format(new Date());
return [{ json: { row_number: e.row_number, 'Playbook Invite Status': 'Sent ' + new Date().toISOString(),
  'Date Playbook Invite': today, 'Playbook Invite Message ID': g.id || '' } }];
"""
mark_failed_js = """// Not retried automatically: check Gmail Sent, then set the status back to 'Profile created ...' to retry.
const e = $('Build Invite Email').first().json;
const err = $input.first().json.error;
const msg = (err && (err.message || err.description)) || JSON.stringify(err || 'unknown');
return [{ json: { row_number: e.row_number, 'Playbook Invite Status': 'Send failed: ' + String(msg).slice(0, 150) } }];
"""
mark_blocked_js = """const e = $input.first().json;
return [{ json: { row_number: e.row_number, 'Playbook Invite Status': e.reason + ' ' + new Date().toISOString() } }];
"""
dry_send_js = """const e = $('Build Invite Email').first().json;
return [{ json: { kind: 'send', row_number: e.row_number, name: e.name, email: e.email, ok: e.ok, reason: e.reason || '',
  subject: e.subject || '', htmlBody: e.htmlBody || '' } }];
"""

# ---------------------------------------------------------------- dry-run digest + reminder
digest_js = r"""if (!$('Config').first().json.dryRun) return [];
// Nodes inside the loops run once per row: read every run, not only the last one.
const pick = n => { const all = []; for (let run = 0; run < 50; run++) { let items;
  try { items = $(n).all(0, run); } catch (e) { break; } if (!items || !items.length) break;
  all.push(...items.map(i => i.json)); } return all; };
const creates = pick('Dry Preview Create'), reviews = pick('Review Payload'), sends = pick('Dry Preview Send');
if (!creates.length && !reviews.length && !sends.length) return [];
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
let html = '<p><b>DRY RUN Playbook invite - niente creato su Playbook, nessuna email ai founder, niente scritto nel foglio.</b></p>';
if (creates.length) html += '<h3>Profili che verrebbero creati</h3>' + creates.map(c => `<p><b>${esc(c.name)}</b> (riga ${c.row_number}, founder ${esc(c.email)})${c.domainNote ? ' - dominio email da aggiungere: ' + esc(c.domainNote) : ''}<br><i>${esc(c.create.one_liner)}</i><br>${esc(c.create.description)}<br>Paese: ${esc(c.countryName)} - Settore: ${esc(c.verticalNames.join(', '))}${c.create.hq_city ? ' - Citta: ' + esc(c.create.hq_city) : ''}</p>`).join('');
if (reviews.length) html += '<h3>Da rivedere (nessun profilo)</h3><ul>' + reviews.map(r => `<li>${esc(r.name)} (riga ${r.row_number}): ${esc(r['Playbook Invite Status'])}</li>`).join('') + '</ul>';
if (sends.length) html += '<h3>Email di invito</h3>' + sends.map(s => s.ok ? `<hr><p><b>To:</b> ${esc(s.email)}<br><b>Subject:</b> ${esc(s.subject)}</p>${s.htmlBody}` : `<p>${esc(s.name)} &lt;${esc(s.email)}&gt;: ${esc(s.reason)}</p>`).join('');
return [{ json: { subject: `[DRY RUN] Playbook invite - ${creates.length} profili, ${reviews.length} da rivedere, ${sends.filter(s => s.ok).length} email`, html } }];
"""

reminder_js = COMMON + r"""// Once a day: rows whose profile was created over a day ago but 'Team Added' is still not YES.
const cfg = $('Config').first().json;
const sd = $getWorkflowStaticData('global');
if (sd.lastReminder === cfg.today) return [];
const DAY = 86400000;
const stuck = $('Pipeline - Get Rows').all().map(i => i.json).filter(r => {
  const m = /^Profile created (\S+)/.exec(String(r['Playbook Invite Status'] || ''));
  return m && !isYes(r['Team Added']) && Date.now() - Date.parse(m[1]) > DAY;
});
if (!stuck.length) return [];
if (!cfg.dryRun) sd.lastReminder = cfg.today;
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
return [{ json: { subject: `Playbook: ${stuck.length} founder da aggiungere nel Team`,
  html: '<p>Profilo creato ma Team Added non ancora YES:</p><ul>' + stuck.map(r => `<li>${esc(r['Startup name'])} (riga ${r.row_number}) - <a href="${esc(String(r['Playbook Profile URL'] || '').replace(/\/overview$/, '/team'))}">Team</a></li>`).join('') + '</ul>' } }];
"""

# ---------------------------------------------------------------- nodes
DRY = "={{ $('Config').first().json.dryRun }}"
LIVE = "={{ !$('Config').first().json.dryRun }}"
nodes = [
    node("Playbook Invite Trigger", "n8n-nodes-base.scheduleTrigger", 1.2, [0, 0],
         {"rule": {"interval": [{"field": "cronExpression", "expression": "4,19,34,49 9-17 * * 1-5"}]}}),
    code("Config", [220, 0], config_js),
    node("Pipeline - Get Rows", "n8n-nodes-base.googleSheets", 4.5, [440, 0],
         {"documentId": DOC, "sheetName": PIPELINE, "options": {}}, credentials=GS_CRED, **RETRY),
    # reminder
    code("Reminder", [660, -400], reminder_js),
    gmail_send_me("Send Reminder", [880, -400], "={{ $json.subject }}", "={{ $json.html }}"),
    # A
    code("Select Profiles To Create", [660, 0], select_create_js),
    node(LA, "n8n-nodes-base.splitInBatches", 3, [880, 0], {"batchSize": 1, "options": {}}),
    code("Claim Create Payload", [1100, 100], claim_create_js),
    if_true("Live? (claim)", [1320, 100], LIVE),
    sheets_update("Pipeline - Claim Create", [1540, 0]),
    mcp("Playbook - Search Domain", [1760, 100], "search_startups",
        "={{ { query: $('" + LA + "').first().json.domain || 'none', max_results: 10 } }}"),
    code("Pre-check", [1980, 100], precheck_js),
    if_true("Pre-check OK?", [2200, 100], "={{ $json.ok }}"),
    node("Fetch Startup Homepage", "n8n-nodes-base.httpRequest", 4.2, [2420, 0],
         {"url": "={{ $('" + LA + "').first().json.website }}", "sendHeaders": True,
          "headerParameters": {"parameters": [{"name": "User-Agent", "value": UA}]},
          "options": {"timeout": 15000, "response": {"response": {"responseFormat": "text", "neverError": True}}}},
         onError="continueRegularOutput"),
    mcp("Playbook - List Countries", [2640, 0], "list_countries", "={{ {} }}"),
    mcp("Playbook - List Verticals", [2860, 0], "list_verticals", "={{ {} }}"),
    code("Build Profile Prompt", [3080, 0], prompt_js.replace("$input.first().json.data", "$('Fetch Startup Homepage').first().json.data")
         .replace("$input.first().json.body", "$('Fetch Startup Homepage').first().json.body")),
    if_true("Prompt OK?", [3300, 0], "={{ $json.ok }}"),
    node("Call Claude", "n8n-nodes-base.executeWorkflow", 1.2, [3520, -100],
         {"workflowId": CLAUDE_UTIL,
          "workflowInputs": {"mappingMode": "defineBelow",
                             "value": {"prompt": "={{ $json.prompt }}", "max_tokens": "={{ $json.max_tokens }}"},
                             "matchingColumns": [], "schema": []},
          "mode": "each", "options": {}}, onError="continueRegularOutput"),
    code("Validate Profile", [3740, -100], validate_js),
    if_true("Profile OK?", [3960, -100], "={{ $json.ok }}"),
    if_true("Dry Run? (create)", [4180, -200], DRY),
    code("Dry Preview Create", [4400, -320], dry_create_js),
    mcp("Playbook - Create Startup", [4400, -120], "create_startup", "={{ $json.create }}"),
    code("Parse Created Startup", [4620, -120], parse_created_js),
    if_true("Created?", [4840, -120], "={{ $json.ok }}"),
    mcp("Playbook - Set Logo", [5060, -220], "set_startup_logo", "={{ { startup_id: $json.startupId } }}"),
    code("Created Status", [5280, -220], created_status_js),
    sheets_update("Pipeline - Write Created", [5500, -220]),
    code("Notify Created", [5720, -220], notify_created_js),
    gmail_send_me("Email Me - Add Founder", [5940, -220], "={{ $json.subject }}", "={{ $json.html }}"),
    code("Review Payload", [4400, 300], review_js),
    if_true("Live? (review)", [4620, 300], LIVE),
    sheets_update("Pipeline - Write Review", [4840, 260]),
    code("Notify Review", [5060, 260], notify_review_js),
    gmail_send_me("Email Me - Review", [5280, 260], "={{ $json.subject }}", "={{ $json.html }}"),
    # B
    gmail_api("Gmail - Invites Sent Today", [660, 700], f"{GAPI}/messages",
              [("q", "={{ 'in:sent subject:\"Playbook invite\" after:' + $('Config').first().json.dayStartEpoch }}"),
               ("maxResults", "100")], executeOnce=True),
    code("Select Emails To Send", [880, 700], select_send_js),
    node(LB, "n8n-nodes-base.splitInBatches", 3, [1100, 700], {"batchSize": 1, "options": {}}),
    gmail_api("Gmail - Invite Already Sent?", [1320, 800], f"{GAPI}/messages",
              [("q", "={{ 'in:sent to:' + $('" + LB + "').first().json.email + ' subject:\"Playbook invite\"' }}"),
               ("maxResults", "5")], onError="continueRegularOutput"),
    code("Build Invite Email", [1540, 800], build_email_js),
    if_true("Dry Run? (send)", [1760, 800], DRY),
    code("Dry Preview Send", [1980, 700], dry_send_js),
    if_true("Email OK?", [1980, 900], "={{ $json.ok }}"),
    code("Claim Send Payload", [2200, 860], claim_send_js),
    sheets_update("Pipeline - Claim Send", [2420, 860]),
    gmail_api("Send Invite Email", [2640, 860], f"{GAPI}/messages/send", method="POST",
              body="={{ JSON.stringify($('Build Invite Email').first().json.sendBody) }}", retry=False,
              onError="continueErrorOutput"),
    code("Mark Invite Sent", [2860, 800], mark_sent_js),
    code("Mark Invite Failed", [2860, 960], mark_failed_js),
    code("Mark Invite Blocked", [2200, 1060], mark_blocked_js),
    sheets_update("Pipeline - Write Send Result", [3080, 900]),
    # digest (dry run), after both loops
    code("Build Dry-Run Digest", [660, 1300], digest_js),
    gmail_send_me("Send Digest to Me", [880, 1300], "={{ $json.subject }}", "={{ $json.html }}"),
]


def to(*ns):
    return [{"node": n, "type": "main", "index": 0} for n in ns]


connections = {
    "Playbook Invite Trigger": {"main": [to("Config")]},
    "Config": {"main": [to("Pipeline - Get Rows")]},
    # Branches run top to bottom (executionOrder v1): reminder, A (create), B (send), digest.
    "Pipeline - Get Rows": {"main": [to("Reminder", "Select Profiles To Create", "Gmail - Invites Sent Today",
                                       "Build Dry-Run Digest")]},
    "Reminder": {"main": [to("Send Reminder")]},
    # A
    "Select Profiles To Create": {"main": [to(LA)]},
    LA: {"main": [[], to("Claim Create Payload")]},
    "Claim Create Payload": {"main": [to("Live? (claim)")]},
    "Live? (claim)": {"main": [to("Pipeline - Claim Create"), to("Playbook - Search Domain")]},
    "Pipeline - Claim Create": {"main": [to("Playbook - Search Domain")]},
    "Playbook - Search Domain": {"main": [to("Pre-check")]},
    "Pre-check": {"main": [to("Pre-check OK?")]},
    "Pre-check OK?": {"main": [to("Fetch Startup Homepage"), to("Review Payload")]},
    "Fetch Startup Homepage": {"main": [to("Playbook - List Countries")]},
    "Playbook - List Countries": {"main": [to("Playbook - List Verticals")]},
    "Playbook - List Verticals": {"main": [to("Build Profile Prompt")]},
    "Build Profile Prompt": {"main": [to("Prompt OK?")]},
    "Prompt OK?": {"main": [to("Call Claude"), to("Review Payload")]},
    "Call Claude": {"main": [to("Validate Profile")]},
    "Validate Profile": {"main": [to("Profile OK?")]},
    "Profile OK?": {"main": [to("Dry Run? (create)"), to("Review Payload")]},
    "Dry Run? (create)": {"main": [to("Dry Preview Create"), to("Playbook - Create Startup")]},
    "Dry Preview Create": {"main": [to(LA)]},
    "Playbook - Create Startup": {"main": [to("Parse Created Startup")]},
    "Parse Created Startup": {"main": [to("Created?")]},
    "Created?": {"main": [to("Playbook - Set Logo"), to("Review Payload")]},
    "Playbook - Set Logo": {"main": [to("Created Status")]},
    "Created Status": {"main": [to("Pipeline - Write Created")]},
    "Pipeline - Write Created": {"main": [to("Notify Created")]},
    "Notify Created": {"main": [to("Email Me - Add Founder")]},
    "Email Me - Add Founder": {"main": [to(LA)]},
    "Review Payload": {"main": [to("Live? (review)")]},
    "Live? (review)": {"main": [to("Pipeline - Write Review"), to(LA)]},
    "Pipeline - Write Review": {"main": [to("Notify Review")]},
    "Notify Review": {"main": [to("Email Me - Review")]},
    "Email Me - Review": {"main": [to(LA)]},
    # B. A profile created in this run can't be emailed in the same run: 'Team Added' is set by the user.
    "Gmail - Invites Sent Today": {"main": [to("Select Emails To Send")]},
    "Select Emails To Send": {"main": [to(LB)]},
    LB: {"main": [[], to("Gmail - Invite Already Sent?")]},
    "Gmail - Invite Already Sent?": {"main": [to("Build Invite Email")]},
    "Build Invite Email": {"main": [to("Dry Run? (send)")]},
    "Dry Run? (send)": {"main": [to("Dry Preview Send"), to("Email OK?")]},
    "Dry Preview Send": {"main": [to(LB)]},
    "Email OK?": {"main": [to("Claim Send Payload"), to("Mark Invite Blocked")]},
    "Claim Send Payload": {"main": [to("Pipeline - Claim Send")]},
    "Pipeline - Claim Send": {"main": [to("Send Invite Email")]},
    "Send Invite Email": {"main": [to("Mark Invite Sent"), to("Mark Invite Failed")]},
    "Mark Invite Sent": {"main": [to("Pipeline - Write Send Result")]},
    "Mark Invite Failed": {"main": [to("Pipeline - Write Send Result")]},
    "Mark Invite Blocked": {"main": [to("Pipeline - Write Send Result")]},
    "Pipeline - Write Send Result": {"main": [to(LB)]},
    "Build Dry-Run Digest": {"main": [to("Send Digest to Me")]},
}

wf = {"name": NAME, "nodes": nodes, "connections": connections,
      "settings": {"executionOrder": "v1", "timezone": "Europe/Rome"}}
json.dump(wf, open(f"{out_dir}/playbook_invite.json", "w"), indent=1)
print("generated", "DRY_RUN" if DRY_RUN else "LIVE", "test-only " + TEST_ONLY_EMAIL if TEST_ONLY_EMAIL else "",
      f"| cap {DAILY_CAP}/day {PER_RUN_CAP}/run")

if DEPLOY:
    env = {}
    for line in open(os.path.join(ROOT, ".env")):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    base, key = env["N8N_CLOUD_BASE_URL"].rstrip("/"), env["N8N_CLOUD_API_KEY"]

    def call(method, path, body=None):
        req = urllib.request.Request(base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-N8N-API-KEY": key, "Content-Type": "application/json"})
        try:
            return json.load(urllib.request.urlopen(req))
        except urllib.error.HTTPError as e:
            raise SystemExit(f"{method} {path} -> {e.code}: {e.read().decode()[:800]}")

    all_wf = call("GET", "/api/v1/workflows?limit=250")["data"]
    alert = [w for w in all_wf if w["name"] == ALERT_NAME]
    if alert:
        wf["settings"]["errorWorkflow"] = alert[0]["id"]
    existing = [w for w in all_wf if w["name"] == NAME]
    if existing and existing[0]["active"]:
        raise SystemExit(f"{NAME} is ACTIVE on n8n - refusing to overwrite a live sender. Deactivate it first.")
    res = call("PUT", f"/api/v1/workflows/{existing[0]['id']}", wf) if existing else call("POST", "/api/v1/workflows", wf)
    print("playbook invite workflow:", res["id"], "| active:", res["active"], "| nodes:", len(res["nodes"]))
    backups = os.path.join(ROOT, "Sourcing - N8N Cloud Rebuild", "workflow_backups")
    json.dump(res, open(os.path.join(backups, f"{NAME}.json"), "w"), indent=2)
