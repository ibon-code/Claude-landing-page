"""Generates 'Pipeline - Salesforce Outreach' (guarded version) and 'Util - Error Alert'.

Guardrails (agreed with the user 2026-10-19):
- Sends only Mon-Fri 09:00-17:59 Europe/Rome, max DAILY_CAP per day (counted from Gmail Sent AND the
  sheet, whichever is higher), max PER_RUN_CAP per 15-min run.
- One email at a time: the row is CLAIMED ('Outreach Status' = Sending ...) before sending. If the claim
  write fails nothing is sent; if the post-send write fails the row stays 'Sending' and is never retried
  (fail closed: a missing mark can never cause a second email).
- Right before each send, Gmail Sent is searched for the same recipient + subject; a hit marks the row
  instead of sending again.
- Greeting is deterministic (first name from 'Full Name', or '<Startup> team' for generic inboxes /
  no usable name). Claude only picks industry + partners, and partners must be real names from
  pnp_partners_reference.json. Any rendered email containing undefined/null/{{ is rejected.
- Rows that fail validation get 'Outreach Status' = 'Needs review: ...' (clear the cell to retry).
- DRY_RUN = True: nothing is sent and nothing is written; one preview digest goes to the user instead.
- Any execution error emails the user via 'Util - Error Alert' (max one alert per workflow per hour).

Usage: python3 build_outreach.py <out_dir> [--deploy]
--deploy creates/updates both workflows on n8n via API. The Outreach workflow stays INACTIVE.
"""
import json, os, sys, uuid, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from email_signature import SIGNATURE_HTML  # noqa: E402

out_dir = sys.argv[1]
DEPLOY = "--deploy" in sys.argv

DRY_RUN = True
DAILY_CAP = 20
PER_RUN_CAP = 3
OUTREACH_ID = "1TkdOwL5o1WWC6a8"
ALERT_NAME = "Util - Error Alert"
ME = "i.bon@pnptc.com"

PARTNERS = json.load(open(os.path.join(ROOT, "pnp_partners_reference.json")))
DOC = {"__rl": True, "value": "1LpPqSKXOvB2FdqNGNnlVBpPDvnfDrYml7npHJEZpKxc", "mode": "list",
       "cachedResultName": "Sourcing - N8N Cloud",
       "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1LpPqSKXOvB2FdqNGNnlVBpPDvnfDrYml7npHJEZpKxc/edit?usp=drivesdk"}
PIPELINE = {"__rl": True, "value": "114224284", "mode": "id"}
GS_CRED = {"googleSheetsOAuth2Api": {"id": "gRSPd8YEw5iadWsy", "name": "Google Sheets (Iacopo Bon)"}}
GMAIL_CRED = {"gmailOAuth2": {"id": "3FF4ROo5Rl75aufp", "name": "Gmail (Iacopo Bon)"}}
RETRY = {"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 5000}


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
                 "options": {"handlingExtraData": "insertInNewColumn"}},
                credentials=GS_CRED, **RETRY)


def gmail_search(name, pos, q, limit, **extra):
    return node(name, "n8n-nodes-base.gmail", 2.1, pos,
                {"resource": "message", "operation": "getAll", "returnAll": False, "limit": limit,
                 "simple": True, "filters": {"q": q}, "options": {}},
                credentials=GMAIL_CRED, alwaysOutputData=True, **RETRY, **extra)


def gmail_send(name, pos, to, subject, html, **extra):
    return node(name, "n8n-nodes-base.gmail", 2.1, pos,
                {"resource": "message", "operation": "send", "sendTo": to, "subject": subject,
                 "emailType": "html", "message": html, "options": {"appendAttribution": False}},
                credentials=GMAIL_CRED, **extra)


def if_true(name, pos, expr):
    return node(name, "n8n-nodes-base.if", 2, pos, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                       "conditions": [{"id": str(uuid.uuid4()), "leftValue": expr, "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                       "combinator": "and"},
        "options": {}})


config_js = f"""// Single place for every outreach limit. Outside the sending window a live run stops here.
const DRY_RUN = {json.dumps(DRY_RUN)};
const DAILY_CAP = {DAILY_CAP};
const PER_RUN_CAP = {PER_RUN_CAP};
const now = new Date();
const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {{
  timeZone: 'Europe/Rome', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', weekday: 'short', hour12: false }}).formatToParts(now).map(p => [p.type, p.value]));
const hour = Number(parts.hour);
const inWindow = !['Sat', 'Sun'].includes(parts.weekday) && hour >= 9 && hour < 18;
if (!DRY_RUN && !inWindow) return [];
const today = `${{parts.year}}-${{parts.month}}-${{parts.day}}`;
// Rome midnight as epoch seconds (offset probed so DST is handled)
const probe = new Date(`${{today}}T00:00:00Z`);
const romeAtProbe = new Date(probe.toLocaleString('en-US', {{ timeZone: 'Europe/Rome' }}));
const utcAtProbe = new Date(probe.toLocaleString('en-US', {{ timeZone: 'UTC' }}));
const dayStartEpoch = Math.floor((probe.getTime() - (romeAtProbe - utcAtProbe)) / 1000);
return [{{ json: {{ dryRun: DRY_RUN, dailyCap: DAILY_CAP, perRunCap: PER_RUN_CAP, today, dayStartEpoch, inWindow }} }}];
"""

select_js = r"""function isChecked(v) {
  if (typeof v === 'boolean') return v;
  if (typeof v === 'string') return v.trim().toUpperCase() === 'TRUE';
  return false;
}
const cfg = $('Config').first().json;
const GENERIC = new Set(['info', 'contact', 'contacts', 'hello', 'hi', 'hey', 'team', 'office', 'admin', 'support',
  'sales', 'press', 'media', 'marketing', 'hr', 'jobs', 'careers', 'enquiries', 'inquiries', 'enquiry', 'inquiry',
  'general', 'mail', 'email', 'founders', 'partnerships', 'partners', 'bd', 'business', 'ciao', 'hola', 'kontakt',
  'contatti', 'info.it', 'investors', 'ir', 'help', 'service', 'welcome']);
const JUNK_LOCAL = /^(no-?reply|do-?not-?reply|postmaster|abuse|privacy|legal|gdpr|dpo|unsubscribe|webmaster|billing|invoices?|accounts?|security|bounce|mailer-daemon)$/;
const JUNK_DOMAIN = /(^|\.)(example\.(com|org)|domain\.com|email\.com|sentry\.io|wixpress\.com|test\.com|yourdomain\.com)$/;
const EMAIL_RE = /^[a-z0-9._%+'-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$/;

const rows = $('Pipeline - Get Rows').all().map(it => it.json);
const norm = e => String(e || '').trim().toLowerCase();
// Addresses already handled anywhere in the sheet (contacted, claimed, failed, under review)
const used = new Set(rows.filter(r => isChecked(r['Contacted']) || String(r['Outreach Status'] || '').trim())
  .map(r => norm(r['Email'])).filter(Boolean));

const sentInGmail = $('Gmail - Sent Today').all().filter(it => it.json && it.json.id).length;
const sentInSheet = rows.filter(r => String(r['Date Contacted'] || '').slice(0, 10) === cfg.today).length;
const sentToday = Math.max(sentInGmail, sentInSheet);
const remaining = Math.max(0, cfg.dailyCap - sentToday);
const limit = cfg.dryRun ? remaining : Math.min(cfg.perRunCap, remaining);

const out = [];
const seen = new Set();
for (const r of rows) {
  if (out.length >= limit) break;
  const email = norm(r['Email']);
  const name = String(r['Startup name'] || '').trim();
  if (!email || !name) continue;
  if (!isChecked(r['Salesforce']) || isChecked(r['Contacted']) || isChecked(r['Playbook'])) continue;
  if (String(r['Meeting'] || '').trim() || String(r['Outreach Status'] || '').trim()) continue;
  if (Number(r['Outreach Count'] || 0) >= 3) continue;
  if (used.has(email) || seen.has(email)) continue;
  const [local, domain] = email.split('@');
  if (!EMAIL_RE.test(email) || JUNK_LOCAL.test(local) || JUNK_DOMAIN.test(domain)) continue;
  if (/\.(png|jpe?g|gif|svg|webp)$/.test(email)) continue;
  if (/test company|delete me/i.test(name) || name.length > 60) continue;
  seen.add(email);
  out.push({ json: {
    row_number: r.row_number, name, email, website: String(r['Website'] || '').trim(),
    jobTitle: r['Job title'] || '', fullName: String(r['Full Name'] || '').trim(),
    generic: GENERIC.has(local.replace(/[0-9]+$/, '')), outreachCount: Number(r['Outreach Count'] || 0),
    sentToday, remainingToday: remaining,
  } });
}
return out;
"""

prompt_js = "const PARTNERS = " + json.dumps(PARTNERS) + ";\n" + r"""function stripTags(s) {
  return (s || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}
const originals = $('Select Candidates').all();
const out = [];
$input.all().forEach((item, i) => {
  const orig = originals[i].json;
  const html = typeof item.json.data === 'string' ? item.json.data : '';
  let siteSummary = '';
  if (html) {
    const titleMatch = /<title[^>]*>([\s\S]*?)<\/title>/i.exec(html);
    const descMatch = /<meta[^>]+name=["']description["'][^>]+content=["']([\s\S]*?)["']/i.exec(html);
    const parts = [];
    if (titleMatch) parts.push(stripTags(titleMatch[1]));
    if (descMatch) parts.push(stripTags(descMatch[1]));
    siteSummary = parts.join(' — ').slice(0, 400);
  }
  const prompt = "You are helping personalize a VC outreach email. Given a startup, pick the single best-fitting industry category from this list of Plug and Play corporate-partner verticals, and 1-2 of the most plausibly relevant partner names from that category's list:\n\n"
    + JSON.stringify(PARTNERS)
    + "\n\nStartup: " + orig.name + "\nWebsite: " + orig.website + "\n"
    + "What the startup's own homepage says about itself: " + (siteSummary || 'not available') + "\n"
    + "Founder/contact title: " + (orig.jobTitle || 'unknown') + "\n\n"
    + "Base the industry classification primarily on what the homepage says, not on the company name alone.\n"
    + 'Return ONLY JSON (no prose, no markdown fences): {"industry": "...", "partners": "..."}\n'
    + "industry: a natural, human-readable phrase for the vertical (e.g. \"mobility and physical AI\"), not the all-caps category label.\n"
    + 'partners: 1-2 partner names copied EXACTLY as written in the list, joined with " and ", e.g. "BMW Group and Bosch Germany" or "PepsiCo".';
  out.push({ json: { prompt, max_tokens: 200 } });
});
return out;
"""

email_js = ("const PARTNERS = " + json.dumps(PARTNERS) + ";\n"
            + "const SIGNATURE_HTML = " + json.dumps(SIGNATURE_HTML) + ";\n"
            + r"""const CALENDLY_LINK = "https://calendly.com/i-bon";
const ALL_PARTNERS = [...new Set(Object.values(PARTNERS).flat())].sort((a, b) => b.length - a.length);
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function greetingFor(c) {
  if (c.generic) return c.name + ' team';
  const first = (c.fullName.split(/\s+/)[0] || '').replace(/[,.]+$/, '');
  if (!/^\p{L}[\p{L}'’-]{1,24}$/u.test(first)) return c.name + ' team';
  const isOneCase = first === first.toUpperCase() || first === first.toLowerCase();
  return isOneCase ? first[0].toUpperCase() + first.slice(1).toLowerCase() : first;
}
function checkPartners(p) {
  let rest = String(p || ''); let found = 0;
  for (const name of ALL_PARTNERS) {
    const idx = rest.toLowerCase().indexOf(name.toLowerCase());
    if (idx >= 0) { rest = rest.slice(0, idx) + ' ' + rest.slice(idx + name.length); found++; }
  }
  rest = rest.replace(/\band\b/gi, '').replace(/[,&\s]/g, '');
  return found >= 1 && found <= 2 && rest === '';
}

const candidates = $('Select Candidates').all();
const out = [];
$input.all().forEach((item, i) => {
  const c = candidates[i].json;
  const info = item.json || {};
  const base = { row_number: c.row_number, email: c.email, name: c.name, outreachCount: c.outreachCount };
  let reason = '';
  const industry = String(info.industry || '').trim();
  const partners = String(info.partners || '').trim();
  if (info.error || !industry || !partners) reason = 'Claude returned no usable answer';
  else if (!/^[\p{L}][\p{L}\s&,\/'-]{2,60}$/u.test(industry)) reason = 'Odd industry text: ' + industry.slice(0, 60);
  else if (!checkPartners(partners)) reason = 'Partners not in the PnP list: ' + partners.slice(0, 80);
  if (reason) { out.push({ json: { ...base, valid: false, reason } }); return; }

  const greeting = greetingFor(c);
  const subject = 'Plug and Play <> ' + c.name;
  const html = "<p>Hi " + esc(greeting) + ",</p><p>I came across " + esc(c.name) + " while mapping out startups in the " + esc(industry) + " space.</p><p>I'm on the Ventures team at Plug and Play Tech Center. We invest at the early stage (early backers of Dropbox, PayPal and Honey), but the bigger part of our model is commercial: we run innovation programs for corporate partners and introduce startups to the ones actively looking. In " + esc(industry) + " that includes " + esc(partners) + ".</p><p>Even if you aren't currently fundraising, I'd love to learn more about what you're building and see if there might be potential alignment with our ecosystem down the line.</p><p>Are you open to a quick 30 minute intro chat this week? Feel free to reply directly, or grab a slot on my calendar here: <a href=\"" + CALENDLY_LINK + "\">" + CALENDLY_LINK + "</a></p><p>Best,</p>" + SIGNATURE_HTML;
  if (/undefined|\bnull\b|NaN|\{\{|\}\}/.test(html + subject)) {
    out.push({ json: { ...base, valid: false, reason: 'Rendered email contains a placeholder' } }); return;
  }
  out.push({ json: { ...base, valid: true, subject, htmlBody: html, greeting, industry, partners } });
});
return out;
""")

digest_js = f"""// DRY RUN: one preview email to the user, nothing sent to startups, nothing written to the sheet.
// On scheduled runs the same preview is not repeated.
const items = $input.all().map(it => it.json);
const first = $('Select Candidates').first().json;
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const key = items.map(e => e.email + '|' + e.valid + '|' + (e.subject || e.reason)).join('\\n');
const sd = $getWorkflowStaticData('global');
const manual = ['manual', 'test'].includes($execution.mode);
if (!manual && sd.lastDigestKey === key) return [];
sd.lastDigestKey = key;
const ok = items.filter(e => e.valid), bad = items.filter(e => !e.valid);
let html = `<p><b>DRY RUN - nessuna email inviata.</b> Gia' inviate oggi: ${{first.sentToday}} / {DAILY_CAP}. Nel live partirebbero max {PER_RUN_CAP} ogni 15 min, lun-ven 9-18.</p>`;
html += `<p>Pronte: ${{ok.length}} - Da rivedere: ${{bad.length}}</p>`;
if (bad.length) html += '<ul>' + bad.map(e => `<li>${{esc(e.name)}} &lt;${{esc(e.email)}}&gt;: ${{esc(e.reason)}}</li>`).join('') + '</ul>';
for (const e of ok) html += `<hr><p><b>To:</b> ${{esc(e.email)}}<br><b>Subject:</b> ${{esc(e.subject)}}</p>${{e.htmlBody}}`;
return [{{ json: {{ subject: `[DRY RUN] Outreach preview - ${{ok.length}} pronte, ${{bad.length}} da rivedere`, html }} }}];
"""

claim_js = """const e = $('Loop Over Emails').first().json;
return [{ json: { row_number: e.row_number, 'Outreach Status': 'Sending ' + new Date().toISOString() } }];
"""

already_js = """// Last safety net against a double send: same recipient + same subject already in Gmail Sent.
const e = $('Loop Over Emails').first().json;
const hit = $input.all().some(it => it.json && it.json.id);
return [{ json: { ...e, alreadySent: hit } }];
"""

mark_already_js = """const e = $('Already Sent Check').first().json;
return [{ json: { row_number: e.row_number, Contacted: true,
  'Outreach Status': 'Already sent (found in Gmail) ' + new Date().toISOString() } }];
"""

mark_sent_js = """const e = $('Already Sent Check').first().json;
const g = $input.first().json;
const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Rome' }).format(new Date());
return [{ json: { row_number: e.row_number, Contacted: true, 'Date Contacted': today, 'Followed Up': false,
  'Outreach Count': (e.outreachCount || 0) + 1, 'Message ID': g.id || '', 'Thread ID': g.threadId || '',
  'Outreach Status': 'Sent ' + new Date().toISOString() } }];
"""

mark_failed_js = """// Not retried automatically: clear 'Outreach Status' in the sheet to try again.
const e = $('Already Sent Check').first().json;
const err = $input.first().json.error;
const msg = (err && (err.message || err.description)) || JSON.stringify(err || 'unknown');
return [{ json: { row_number: e.row_number, 'Outreach Status': 'Send failed: ' + String(msg).slice(0, 150) } }];
"""

review_js = """return $input.all().map(it => ({ json: { row_number: it.json.row_number,
  'Outreach Status': 'Needs review: ' + it.json.reason } }));
"""

loop_q = ("={{ 'in:sent to:' + $('Loop Over Emails').first().json.email + ' subject:\"' + "
          "$('Loop Over Emails').first().json.subject.replace(/\"/g, '') + '\"' }}")
L = "Loop Over Emails"
nodes = [
    node("Outreach Trigger", "n8n-nodes-base.scheduleTrigger", 1.2, [0, 0],
         {"rule": {"interval": [{"field": "cronExpression", "expression": "*/15 9-17 * * 1-5"}]}}),
    code("Config", [220, 0], config_js),
    node("Pipeline - Get Rows", "n8n-nodes-base.googleSheets", 4.5, [440, 0],
         {"documentId": DOC, "sheetName": PIPELINE, "options": {}}, credentials=GS_CRED, **RETRY),
    gmail_search("Gmail - Sent Today", [660, 0],
                 "={{ 'in:sent subject:\"Plug and Play <>\" after:' + $('Config').first().json.dayStartEpoch }}",
                 100, executeOnce=True),
    code("Select Candidates", [880, 0], select_js),
    node("Fetch Startup Homepage", "n8n-nodes-base.httpRequest", 4.2, [1100, 0],
         {"url": "={{ $json.website }}", "sendHeaders": True,
          "headerParameters": {"parameters": [{"name": "User-Agent", "value": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}]},
          "options": {"timeout": 15000, "response": {"response": {"responseFormat": "text", "neverError": True}}}},
         onError="continueRegularOutput"),
    code("Build Personalization Prompt", [1320, 0], prompt_js),
    node("Call Claude", "n8n-nodes-base.executeWorkflow", 1.2, [1540, 0],
         {"workflowId": {"__rl": True, "value": "V5wGQ55LdYLhSCmf", "mode": "list",
                         "cachedResultName": "Util - Claude Messages API"},
          "workflowInputs": {"mappingMode": "defineBelow",
                             "value": {"prompt": "={{ $json.prompt }}", "max_tokens": "={{ $json.max_tokens }}"},
                             "matchingColumns": [], "schema": []},
          "mode": "each", "options": {}}, onError="continueRegularOutput"),
    code("Build + Validate Email", [1760, 0], email_js),
    if_true("Dry Run?", [1980, 0], "={{ $('Config').first().json.dryRun }}"),
    code("Build Dry-Run Digest", [2200, -220], digest_js),
    gmail_send("Send Digest to Me", [2420, -220], ME, "={{ $json.subject }}", "={{ $json.html }}"),
    if_true("Valid?", [2200, 120], "={{ $json.valid }}"),
    code("Needs Review Payload", [2420, 320], review_js),
    sheets_update("Pipeline - Mark Needs Review", [2640, 320]),
    node(L, "n8n-nodes-base.splitInBatches", 3, [2420, 100], {"batchSize": 1, "options": {}}),
    code("Claim Payload", [2640, 100], claim_js),
    sheets_update("Pipeline - Claim Row", [2860, 100]),
    gmail_search("Gmail - Already Sent?", [3080, 100], loop_q, 1),
    code("Already Sent Check", [3300, 100], already_js),
    if_true("Already Sent?", [3520, 100], "={{ $json.alreadySent }}"),
    code("Mark Already Sent", [3740, -60], mark_already_js),
    gmail_send("Send Outreach Email", [3740, 140], "={{ $json.email }}", "={{ $json.subject }}",
               "={{ $json.htmlBody }}", onError="continueErrorOutput"),
    code("Mark Sent", [3960, 60], mark_sent_js),
    code("Mark Send Failed", [3960, 240], mark_failed_js),
    sheets_update("Pipeline - Write Result", [4180, 100]),
]


def to(n):
    return [{"node": n, "type": "main", "index": 0}]


straight = ["Outreach Trigger", "Config", "Pipeline - Get Rows", "Gmail - Sent Today", "Select Candidates",
            "Fetch Startup Homepage", "Build Personalization Prompt", "Call Claude", "Build + Validate Email",
            "Dry Run?"]
connections = {a: {"main": [to(b)]} for a, b in zip(straight, straight[1:])}
connections.update({
    "Dry Run?": {"main": [to("Build Dry-Run Digest"), to("Valid?")]},
    "Build Dry-Run Digest": {"main": [to("Send Digest to Me")]},
    "Valid?": {"main": [to(L), to("Needs Review Payload")]},
    "Needs Review Payload": {"main": [to("Pipeline - Mark Needs Review")]},
    L: {"main": [[], to("Claim Payload")]},  # output 0 = done, output 1 = next item
    "Claim Payload": {"main": [to("Pipeline - Claim Row")]},
    "Pipeline - Claim Row": {"main": [to("Gmail - Already Sent?")]},
    "Gmail - Already Sent?": {"main": [to("Already Sent Check")]},
    "Already Sent Check": {"main": [to("Already Sent?")]},
    "Already Sent?": {"main": [to("Mark Already Sent"), to("Send Outreach Email")]},
    "Mark Already Sent": {"main": [to("Pipeline - Write Result")]},
    "Send Outreach Email": {"main": [to("Mark Sent"), to("Mark Send Failed")]},
    "Mark Sent": {"main": [to("Pipeline - Write Result")]},
    "Mark Send Failed": {"main": [to("Pipeline - Write Result")]},
    "Pipeline - Write Result": {"main": [to(L)]},
})

alert_js = """// One alert per workflow per hour, so a workflow failing every 15 min doesn't flood the inbox.
const d = $input.first().json;
const wf = (d.workflow && d.workflow.name) || 'unknown workflow';
const sd = $getWorkflowStaticData('global');
const last = (sd.lastAlert || {})[wf] || 0;
if (Date.now() - last < 60 * 60 * 1000) return [];
sd.lastAlert = { ...(sd.lastAlert || {}), [wf]: Date.now() };
const ex = d.execution || {};
const err = ex.error || {};
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
return [{ json: {
  subject: '[n8n] Errore in ' + wf,
  html: `<p>Il workflow <b>${esc(wf)}</b> e' andato in errore.</p>`
    + `<p><b>Nodo:</b> ${esc(ex.lastNodeExecuted || err.node?.name || '-')}<br><b>Errore:</b> ${esc(err.message || '-')}</p>`
    + (ex.url ? `<p><a href="${esc(ex.url)}">Apri l'esecuzione</a></p>` : ''),
} }];
"""
alert = {"name": ALERT_NAME, "settings": {"executionOrder": "v1"}, "nodes": [
    node("Error Trigger", "n8n-nodes-base.errorTrigger", 1, [0, 0], {}),
    code("Build Alert", [220, 0], alert_js),
    gmail_send("Email Me", [440, 0], ME, "={{ $json.subject }}", "={{ $json.html }}", **RETRY),
], "connections": {"Error Trigger": {"main": [to("Build Alert")]}, "Build Alert": {"main": [to("Email Me")]}}}

outreach = {"name": "Pipeline - Salesforce Outreach", "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1", "timezone": "Europe/Rome"}}
json.dump(outreach, open(f"{out_dir}/outreach.json", "w"), indent=1)
json.dump(alert, open(f"{out_dir}/error_alert.json", "w"), indent=1)
print("generated", "DRY_RUN" if DRY_RUN else "LIVE", f"cap {DAILY_CAP}/day {PER_RUN_CAP}/run")

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

    live = call("GET", f"/api/v1/workflows/{OUTREACH_ID}")
    if live["active"]:
        raise SystemExit("Outreach is ACTIVE on n8n - refusing to overwrite a live sender. Deactivate it first.")
    existing = [w for w in call("GET", "/api/v1/workflows?limit=250")["data"] if w["name"] == ALERT_NAME]
    a = call("PUT", f"/api/v1/workflows/{existing[0]['id']}", alert) if existing else call("POST", "/api/v1/workflows", alert)
    print("error alert workflow:", a["id"])
    outreach["settings"]["errorWorkflow"] = a["id"]
    o = call("PUT", f"/api/v1/workflows/{OUTREACH_ID}", outreach)
    print("outreach updated - active:", o["active"], "| nodes:", len(o["nodes"]))
    backups = os.path.join(ROOT, "Sourcing - N8N Cloud Rebuild", "workflow_backups")
    json.dump(o, open(os.path.join(backups, "Pipeline - Salesforce Outreach.json"), "w"), indent=2)
    json.dump(a, open(os.path.join(backups, f"{ALERT_NAME}.json"), "w"), indent=2)
