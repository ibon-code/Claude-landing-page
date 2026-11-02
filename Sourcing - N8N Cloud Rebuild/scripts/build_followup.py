"""Generates 'Pipeline - Follow-up': ONE follow-up, FOLLOWUP_DAYS after the automated first email, in the same
Gmail thread, only if nobody from the startup replied. Never a second one.

Guardrails (agreed with the user 2026-11-02, after a founder once received 7 emails):
- Only rows whose first email was sent by 'Pipeline - Salesforce Outreach' ('Message ID' + 'Thread ID' set,
  'Outreach Status' = Sent ...). Contacts from the old local pipeline never get a follow-up.
- Nothing is sent if 'Followed Up' is TRUE, 'Follow-up Status' is not empty, 'Meeting' is set, or Playbook = YES.
- Gmail decides, not the sheet:
    * the thread holds exactly 1 message and it is ours, addressed to this email (no reply in the thread);
    * no message from the startup since the first email (from the exact address, or from its company domain
      when that isn't free mail or our own domain);
    * no bounce mentioning the address;
    * Gmail Sent holds exactly 1 'Plug and Play' email to this address, and it is the original.
      After the follow-up there are 2, so a third email can never pass this check.
  The 7 days are counted from the Gmail date of the original message.
- Rows that must stop for good (reply, bounce, thread problem) get 'Follow-up Status' = 'Stopped: ...'.
- One email at a time: the row is claimed ('Follow-up Status' = Sending ...) and the Sent count is checked
  again right before sending. If anything fails after the claim the row stays claimed and is never retried.
- Max PER_RUN_CAP per 15-min run and DAILY_CAP follow-ups a day (Gmail Sent and sheet, whichever is higher),
  Mon-Fri 09:00-17:59 Europe/Rome. DRY_RUN: nothing sent, nothing written, one preview email to me.
- TEST_ONLY_EMAIL: live run that may only follow up this address, with no waiting time (for testing).

Usage: python3 build_followup.py <out_dir> [--live] [--test-email ADDR] [--deploy]   (the workflow is created/updated INACTIVE)
"""
import json, os, sys, uuid, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from email_signature import SIGNATURE_HTML  # noqa: E402

out_dir = sys.argv[1]
DEPLOY = "--deploy" in sys.argv

# Live sending only with an explicit --live flag. --test-email ADDR: may only email ADDR, any time of day.
DRY_RUN = "--live" not in sys.argv
TEST_ONLY_EMAIL = sys.argv[sys.argv.index("--test-email") + 1].lower() if "--test-email" in sys.argv else None
FOLLOWUP_DAYS = 7
DAILY_CAP = 20
PER_RUN_CAP = 3
MAX_CHECKS_PER_RUN = 15   # oldest eligible rows checked in Gmail per run
NAME = "Pipeline - Follow-up"
ALERT_NAME = "Util - Error Alert"
ME = "i.bon@pnptc.com"
SENDER = "Iacopo Bon <i.bon@pnptc.com>"
CALENDLY = "https://calendly.com/i-bon"

DOC = {"__rl": True, "value": "1LpPqSKXOvB2FdqNGNnlVBpPDvnfDrYml7npHJEZpKxc", "mode": "list",
       "cachedResultName": "Sourcing - N8N Cloud",
       "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1LpPqSKXOvB2FdqNGNnlVBpPDvnfDrYml7npHJEZpKxc/edit?usp=drivesdk"}
PIPELINE = {"__rl": True, "value": "114224284", "mode": "id"}
GS_CRED = {"googleSheetsOAuth2Api": {"id": "gRSPd8YEw5iadWsy", "name": "Google Sheets (Iacopo Bon)"}}
GMAIL_CRED = {"gmailOAuth2": {"id": "3FF4ROo5Rl75aufp", "name": "Gmail (Iacopo Bon)"}}
RETRY = {"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 5000}
GAPI = "https://gmail.googleapis.com/gmail/v1/users/me"


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
    """Gmail REST call with the Gmail OAuth credential. One output item per input item."""
    p = {"method": method, "url": url, "authentication": "predefinedCredentialType",
         "nodeCredentialType": "gmailOAuth2", "options": {}}
    if query:
        p.update({"sendQuery": True, "queryParameters": {"parameters": [{"name": k, "value": v} for k, v in query]}})
    if body:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
    return node(name, "n8n-nodes-base.httpRequest", 4.2, pos, p, credentials=GMAIL_CRED,
                **(RETRY if retry else {}), **extra)


def if_true(name, pos, expr):
    return node(name, "n8n-nodes-base.if", 2, pos, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                       "conditions": [{"id": str(uuid.uuid4()), "leftValue": expr, "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                       "combinator": "and"},
        "options": {}})


config_js = f"""const DRY_RUN = {json.dumps(DRY_RUN)};
const TEST_ONLY_EMAIL = {json.dumps(TEST_ONLY_EMAIL)};
const FOLLOWUP_DAYS = TEST_ONLY_EMAIL ? 0 : {FOLLOWUP_DAYS};
const DAILY_CAP = {DAILY_CAP};
const PER_RUN_CAP = {PER_RUN_CAP};
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
return [{{ json: {{ dryRun: DRY_RUN, testOnlyEmail: TEST_ONLY_EMAIL, followupDays: FOLLOWUP_DAYS,
  dailyCap: DAILY_CAP, perRunCap: PER_RUN_CAP, today, dayStartEpoch }} }}];
"""

select_js = r"""const cfg = $('Config').first().json;
const isChecked = v => typeof v === 'boolean' ? v : ['TRUE', 'YES'].includes(String(v || '').trim().toUpperCase());
const norm = e => String(e || '').trim().toLowerCase();
const rows = $('Pipeline - Get Rows').all().map(it => it.json);

const sent = ($('Gmail - Follow-ups Sent Today').first().json.messages || []).length;
const inSheet = rows.filter(r => String(r['Date Followed Up'] || '').slice(0, 10) === cfg.today).length;
const sentToday = Math.max(sent, inSheet);
const remaining = Math.max(0, cfg.dailyCap - sentToday);
if (!remaining && !cfg.dryRun) return [];

const DAY = 86400000;
const cands = [];
for (const r of rows) {
  const email = norm(r['Email']);
  if (!email || !String(r['Message ID'] || '').trim() || !String(r['Thread ID'] || '').trim()) continue;
  if (!isChecked(r['Contacted']) || isChecked(r['Followed Up']) || isChecked(r['Playbook'])) continue;
  if (!/^Sent /.test(String(r['Outreach Status'] || ''))) continue;
  if (String(r['Follow-up Status'] || '').trim() || String(r['Meeting'] || '').trim()) continue;
  if (cfg.testOnlyEmail && email !== cfg.testOnlyEmail.toLowerCase()) continue;
  // Cheap pre-filter on the sheet date; Gmail's own date decides later.
  const d = /^\d{4}-\d{2}-\d{2}/.test(String(r['Date Contacted'] || '')) ? Date.parse(String(r['Date Contacted']).slice(0, 10)) : 0;
  if (d && Date.now() - d < (cfg.followupDays - 1) * DAY) continue;
  cands.push({ r, email, d });
}
cands.sort((a, b) => a.d - b.d);
return cands.slice(0, """ + str(MAX_CHECKS_PER_RUN) + r""").map(({ r, email }) => ({ json: {
  row_number: r.row_number, email, name: String(r['Startup name'] || '').trim(),
  fullName: String(r['Full Name'] || '').trim(), messageId: String(r['Message ID']).trim(),
  threadId: String(r['Thread ID']).trim(), outreachCount: Number(r['Outreach Count'] || 0),
  sentToday, remainingToday: remaining,
} }));
"""

MY_DOMAIN = ME.split("@")[1]
# Gmail queries, built per candidate
q_sent = "={{ 'in:sent to:' + $json.email + ' subject:\"Plug and Play\"' }}"
q_from = ("={{ (() => { const c = $('Select Follow-up Candidates').item.json; const d = c.email.split('@')[1];"
          " const free = /^(gmail|googlemail|outlook|hotmail|live|yahoo|icloud|me|aol|proton|protonmail|gmx|mail|yandex|zoho)\\./.test(d)"
          " || d === '" + MY_DOMAIN + "'; return '-in:sent from:' + (free ? c.email : '@' + d); })() }}")
q_bounce = "={{ '(from:mailer-daemon OR from:postmaster) \"' + $('Select Follow-up Candidates').item.json.email + '\"' }}"

evaluate_js = ("const SIGNATURE_HTML = " + json.dumps(SIGNATURE_HTML) + ";\n"
               + "const SENDER = " + json.dumps(SENDER) + ";\nconst ME = " + json.dumps(ME) + ";\n"
               + "const CALENDLY = " + json.dumps(CALENDLY) + ";\n" + r"""const cfg = $('Config').first().json;
const cands = $('Select Follow-up Candidates').all();
const threads = $('Gmail - Get Thread').all(), sents = $('Gmail - Sent To Address').all();
const froms = $('Gmail - Messages From Startup').all(), bounces = $('Gmail - Bounces').all();
const hdr = (m, n) => (((m.payload || {}).headers || []).find(h => h.name.toLowerCase() === n.toLowerCase()) || {}).value || '';
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const GENERIC = new Set(['info', 'contact', 'contacts', 'hello', 'hi', 'hey', 'team', 'office', 'admin', 'support',
  'sales', 'press', 'media', 'marketing', 'hr', 'jobs', 'careers', 'enquiries', 'inquiries', 'enquiry', 'inquiry',
  'general', 'mail', 'email', 'founders', 'partnerships', 'partners', 'bd', 'business', 'ciao', 'hola', 'kontakt',
  'contatti', 'investors', 'ir', 'help', 'service', 'welcome']);
function greetingFor(c) {
  const local = c.email.split('@')[0].replace(/[0-9]+$/, '');
  if (GENERIC.has(local)) return c.name + ' team';
  const first = (c.fullName.split(/\s+/)[0] || '').replace(/[,.]+$/, '');
  if (!/^\p{L}[\p{L}'’-]{1,24}$/u.test(first)) return c.name + ' team';
  const oneCase = first === first.toUpperCase() || first === first.toLowerCase();
  return oneCase ? first[0].toUpperCase() + first.slice(1).toLowerCase() : first;
}
const b64 = s => Buffer.from(s, 'utf8').toString('base64');
const b64url = s => b64(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const wrap = s => s.replace(/(.{76})/g, '$1\r\n');

const out = [];
cands.forEach((it, i) => {
  const c = it.json;
  const base = { row_number: c.row_number, email: c.email, name: c.name, outreachCount: c.outreachCount,
                 threadId: c.threadId, messageId: c.messageId };
  const stop = reason => out.push({ json: { ...base, action: 'stop', reason } });
  const review = reason => out.push({ json: { ...base, action: 'review', reason } });
  const wait = reason => out.push({ json: { ...base, action: 'wait', reason } });
  const t = threads[i].json, s = sents[i].json, f = froms[i].json, b = bounces[i].json;
  if ([t, s, f, b].some(x => x.error || !x || typeof x !== 'object')) return review('Gmail check failed');
  const msgs = t.messages || [];
  if (!msgs.length) return review('Thread not found in Gmail');
  const orig = msgs[0];
  if (orig.id !== c.messageId) return review('Thread does not start with the stored Message ID');
  if (msgs.length > 1) return stop(msgs.some(m => !hdr(m, 'From').toLowerCase().includes(ME)) ? 'Replied in thread' : 'Thread already has more than one email');
  if (!hdr(orig, 'From').toLowerCase().includes(ME)) return review('Original email is not from me');
  if (!hdr(orig, 'To').toLowerCase().includes(c.email)) return review('Original email was not sent to ' + c.email);
  const subject = hdr(orig, 'Subject').replace(/^\s*re:\s*/i, '');
  if (!/^Plug and Play <> /.test(subject)) return review('Original subject is not an outreach subject: ' + subject.slice(0, 60));
  const rfcId = hdr(orig, 'Message-ID');
  if (!rfcId) return review('Original email has no Message-ID header');
  if ((b.messages || []).length) return stop('Bounced');
  if ((f.messages || []).length) return stop('Startup wrote back (inbox)');
  const sentList = s.messages || [];
  if (sentList.length !== 1 || sentList[0].id !== c.messageId) return stop('Gmail Sent has ' + sentList.length + ' Plug and Play emails to this address (must be exactly the original)');
  const days = (Date.now() - Number(orig.internalDate)) / 86400000;
  if (!(days >= cfg.followupDays)) return wait('Only ' + days.toFixed(1) + ' days since the first email');

  const greeting = greetingFor(c);
  const text = `Hi ${greeting},\n\nBumping this in case it got buried. Still keen to grab 10 minutes, hear what you're building at ${c.name}, and see if there's potential alignment with our corporate network at Plug and Play.\n\nOpen to a quick chat? Feel free to reply directly or grab a slot here: ${CALENDLY}\n\nBest,\n\nIacopo`;
  const html = `<p>Hi ${esc(greeting)},</p><p>Bumping this in case it got buried. Still keen to grab 10 minutes, hear what you're building at ${esc(c.name)}, and see if there's potential alignment with our corporate network at Plug and Play.</p><p>Open to a quick chat? Feel free to reply directly or grab a slot here: <a href="${CALENDLY}">${CALENDLY}</a></p><p>Best,</p>` + SIGNATURE_HTML;
  if (/undefined|\bnull\b|NaN|\{\{|\}\}/.test(text + html + subject)) return review('Rendered follow-up contains a placeholder');
  const reSubject = 'Re: ' + subject;
  const boundary = 'b' + Math.random().toString(36).slice(2) + Date.now();
  const mime = [
    'From: ' + SENDER, 'To: ' + c.email, 'Subject: =?UTF-8?B?' + b64(reSubject) + '?=',
    'In-Reply-To: ' + rfcId, 'References: ' + rfcId, 'MIME-Version: 1.0',
    'Content-Type: multipart/alternative; boundary="' + boundary + '"', '',
    '--' + boundary, 'Content-Type: text/plain; charset="UTF-8"', 'Content-Transfer-Encoding: base64', '', wrap(b64(text)),
    '--' + boundary, 'Content-Type: text/html; charset="UTF-8"', 'Content-Transfer-Encoding: base64', '', wrap(b64(html)),
    '--' + boundary + '--', '',
  ].join('\r\n');
  out.push({ json: { ...base, action: 'send', subject: reSubject, greeting, htmlBody: html, days: Number(days.toFixed(1)),
                     sendBody: { raw: b64url(mime), threadId: c.threadId } } });
});
// Only the first PER_RUN_CAP (or what's left of today's cap) are sent; the others wait for the next run.
let room = cfg.dryRun ? Infinity : Math.min(cfg.perRunCap, cands.length ? cands[0].json.remainingToday : 0);
for (const o of out) if (o.json.action === 'send') { if (room > 0) room--; else o.json.action = 'wait'; }
return out.filter(o => o.json.action !== 'wait' || cfg.dryRun);
""")

digest_js = f"""const items = $input.all().map(it => it.json);
const first = $('Select Follow-up Candidates').first().json;
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const key = items.map(e => e.email + '|' + e.action + '|' + (e.reason || e.subject)).join('\\n');
const sd = $getWorkflowStaticData('global');
const manual = ['manual', 'test'].includes($execution.mode);
if (!manual && sd.lastDigestKey === key) return [];
sd.lastDigestKey = key;
const send = items.filter(e => e.action === 'send'), other = items.filter(e => e.action !== 'send');
let html = `<p><b>DRY RUN follow-up - nessuna email inviata.</b> Follow-up gia' inviati oggi: ${{first.sentToday}} / {DAILY_CAP}. Nel live: max {PER_RUN_CAP} ogni 15 min, lun-ven 9-18.</p>`;
html += `<p>Partirebbero: ${{send.length}} - Altri: ${{other.length}}</p>`;
if (other.length) html += '<ul>' + other.map(e => `<li>${{esc(e.name)}} &lt;${{esc(e.email)}}&gt;: ${{esc(e.action)}} - ${{esc(e.reason)}}</li>`).join('') + '</ul>';
for (const e of send) html += `<hr><p><b>To:</b> ${{esc(e.email)}} (thread ${{esc(e.threadId)}}, ${{e.days}} giorni)<br><b>Subject:</b> ${{esc(e.subject)}}</p>${{e.htmlBody}}`;
return [{{ json: {{ subject: `[DRY RUN] Follow-up preview - ${{send.length}} pronti, ${{other.length}} altri`, html }} }}];
"""

status_js = """return $input.all().filter(it => it.json.action !== 'wait').map(it => ({ json: { row_number: it.json.row_number,
  'Follow-up Status': (it.json.action === 'stop' ? 'Stopped: ' : 'Needs review: ') + it.json.reason } }));
"""
claim_js = """const e = $('Loop Over Follow-ups').first().json;
return [{ json: { row_number: e.row_number, 'Follow-up Status': 'Sending ' + new Date().toISOString() } }];
"""
recheck_js = """// Right before sending: still exactly 1 automated email (the original) to this address in Gmail Sent.
const e = $('Loop Over Follow-ups').first().json;
const list = $input.first().json.messages || [];
const ok = !$input.first().json.error && list.length === 1 && list[0].id === e.messageId;
return [{ json: { ...e, okToSend: ok, sentCount: list.length } }];
"""
blocked_js = """const e = $('Re-check Sent Count').first().json;
return [{ json: { row_number: e.row_number, 'Follow-up Status': 'Blocked: Gmail Sent has ' + e.sentCount + ' Plug and Play emails to this address ' + new Date().toISOString() } }];
"""
mark_sent_js = """const e = $('Re-check Sent Count').first().json;
const g = $input.first().json;
const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Rome' }).format(new Date());
return [{ json: { row_number: e.row_number, 'Followed Up': true, 'Date Followed Up': today,
  'Outreach Count': (e.outreachCount || 0) + 1, 'Follow-up Message ID': g.id || '',
  'Follow-up Status': 'Sent ' + new Date().toISOString() } }];
"""
mark_failed_js = """// Not retried automatically: clear 'Follow-up Status' to try again (check Gmail Sent first).
const e = $('Re-check Sent Count').first().json;
const err = $input.first().json.error;
const msg = (err && (err.message || err.description)) || JSON.stringify(err || 'unknown');
return [{ json: { row_number: e.row_number, 'Follow-up Status': 'Send failed: ' + String(msg).slice(0, 150) } }];
"""

L = "Loop Over Follow-ups"
nodes = [
    node("Follow-up Trigger", "n8n-nodes-base.scheduleTrigger", 1.2, [0, 0],
         {"rule": {"interval": [{"field": "cronExpression", "expression": "7,22,37,52 9-17 * * 1-5"}]}}),
    code("Config", [220, 0], config_js),
    node("Pipeline - Get Rows", "n8n-nodes-base.googleSheets", 4.5, [440, 0],
         {"documentId": DOC, "sheetName": PIPELINE, "options": {}}, credentials=GS_CRED, **RETRY),
    gmail_api("Gmail - Follow-ups Sent Today", [660, 0], f"{GAPI}/messages",
              [("q", "={{ 'in:sent subject:\"Re: Plug and Play\" after:' + $('Config').first().json.dayStartEpoch }}"),
               ("maxResults", "100")], executeOnce=True),
    code("Select Follow-up Candidates", [880, 0], select_js),
    gmail_api("Gmail - Get Thread", [1100, 0],
              f"={{{{ '{GAPI}/threads/' + $json.threadId + '?format=metadata&metadataHeaders=From&metadataHeaders=To"
              "&metadataHeaders=Subject&metadataHeaders=Message-ID' }}}}", onError="continueRegularOutput"),
    gmail_api("Gmail - Sent To Address", [1320, 0], f"{GAPI}/messages",
              [("q", q_sent.replace("$json.email", "$('Select Follow-up Candidates').item.json.email")), ("maxResults", "20")],
              onError="continueRegularOutput"),
    gmail_api("Gmail - Messages From Startup", [1540, 0], f"{GAPI}/messages",
              [("q", q_from), ("maxResults", "5")], onError="continueRegularOutput"),
    gmail_api("Gmail - Bounces", [1760, 0], f"{GAPI}/messages",
              [("q", q_bounce), ("maxResults", "5")], onError="continueRegularOutput"),
    code("Evaluate Follow-ups", [1980, 0], evaluate_js),
    if_true("Dry Run?", [2200, 0], "={{ $('Config').first().json.dryRun }}"),
    code("Build Dry-Run Digest", [2420, -220], digest_js),
    node("Send Digest to Me", "n8n-nodes-base.gmail", 2.1, [2640, -220],
         {"resource": "message", "operation": "send", "sendTo": ME, "subject": "={{ $json.subject }}",
          "emailType": "html", "message": "={{ $json.html }}", "options": {"appendAttribution": False}},
         credentials=GMAIL_CRED),
    node("Send?", "n8n-nodes-base.if", 2, [2420, 120], {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                       "conditions": [{"id": str(uuid.uuid4()), "leftValue": "={{ $json.action }}", "rightValue": "send",
                                       "operator": {"type": "string", "operation": "equals"}}],
                       "combinator": "and"}, "options": {}}),
    code("Stop / Review Payload", [2640, 320], status_js),
    sheets_update("Pipeline - Write Stop Status", [2860, 320]),
    node(L, "n8n-nodes-base.splitInBatches", 3, [2640, 100], {"batchSize": 1, "options": {}}),
    code("Claim Payload", [2860, 100], claim_js),
    sheets_update("Pipeline - Claim Row", [3080, 100]),
    gmail_api("Gmail - Sent To Address (again)", [3300, 100], f"{GAPI}/messages",
              [("q", "={{ 'in:sent to:' + $('" + L + "').first().json.email + ' subject:\"Plug and Play\"' }}"),
               ("maxResults", "20")], onError="continueRegularOutput"),
    code("Re-check Sent Count", [3520, 100], recheck_js),
    if_true("Still Exactly One?", [3740, 100], "={{ $json.okToSend }}"),
    code("Mark Blocked", [3960, -60], blocked_js),
    gmail_api("Send Follow-up", [3960, 140], f"{GAPI}/messages/send", method="POST",
              body="={{ JSON.stringify($json.sendBody) }}", retry=False, onError="continueErrorOutput"),
    code("Mark Sent", [4180, 60], mark_sent_js),
    code("Mark Send Failed", [4180, 240], mark_failed_js),
    sheets_update("Pipeline - Write Result", [4400, 100]),
]


def to(n):
    return [{"node": n, "type": "main", "index": 0}]


straight = ["Follow-up Trigger", "Config", "Pipeline - Get Rows", "Gmail - Follow-ups Sent Today",
            "Select Follow-up Candidates", "Gmail - Get Thread", "Gmail - Sent To Address",
            "Gmail - Messages From Startup", "Gmail - Bounces", "Evaluate Follow-ups", "Dry Run?"]
connections = {a: {"main": [to(b)]} for a, b in zip(straight, straight[1:])}
connections.update({
    "Dry Run?": {"main": [to("Build Dry-Run Digest"), to("Send?")]},
    "Build Dry-Run Digest": {"main": [to("Send Digest to Me")]},
    "Send?": {"main": [to(L), to("Stop / Review Payload")]},
    "Stop / Review Payload": {"main": [to("Pipeline - Write Stop Status")]},
    L: {"main": [[], to("Claim Payload")]},
    "Claim Payload": {"main": [to("Pipeline - Claim Row")]},
    "Pipeline - Claim Row": {"main": [to("Gmail - Sent To Address (again)")]},
    "Gmail - Sent To Address (again)": {"main": [to("Re-check Sent Count")]},
    "Re-check Sent Count": {"main": [to("Still Exactly One?")]},
    "Still Exactly One?": {"main": [to("Send Follow-up"), to("Mark Blocked")]},
    "Mark Blocked": {"main": [to("Pipeline - Write Result")]},
    "Send Follow-up": {"main": [to("Mark Sent"), to("Mark Send Failed")]},
    "Mark Sent": {"main": [to("Pipeline - Write Result")]},
    "Mark Send Failed": {"main": [to("Pipeline - Write Result")]},
    "Pipeline - Write Result": {"main": [to(L)]},
})

wf = {"name": NAME, "nodes": nodes, "connections": connections,
      "settings": {"executionOrder": "v1", "timezone": "Europe/Rome"}}
json.dump(wf, open(f"{out_dir}/followup.json", "w"), indent=1)
open(f"{out_dir}/followup_evaluate.js", "w").write(evaluate_js)
open(f"{out_dir}/followup_select.js", "w").write(select_js)
print("generated", "DRY_RUN" if DRY_RUN else "LIVE", "test-only " + TEST_ONLY_EMAIL if TEST_ONLY_EMAIL else "",
      f"| after {FOLLOWUP_DAYS} days | cap {DAILY_CAP}/day {PER_RUN_CAP}/run")

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
    print("follow-up workflow:", res["id"], "| active:", res["active"], "| nodes:", len(res["nodes"]))
    backups = os.path.join(ROOT, "Sourcing - N8N Cloud Rebuild", "workflow_backups")
    json.dump(res, open(os.path.join(backups, f"{NAME}.json"), "w"), indent=2)
