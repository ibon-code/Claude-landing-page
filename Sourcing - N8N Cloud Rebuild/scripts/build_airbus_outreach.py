"""Generates the 3 n8n workflows for the one-time Airbus DS data-management outreach (30 startups).

  1. 'Airbus outreach | 1. Invio iniziale'      manual trigger: one email per startup (all contacts in To, CC from the
                                                 sheet, PDF attached), then writes Sent at / Thread ID / Message ID /
                                                 Follow-up due on the row. 60-120 s between emails.
  2. 'Airbus outreach | 2. Risposte e follow-up' Mon-Fri 09:30 Europe/Madrid + manual: marks Replied, or sends ONE
                                                 follow-up in the same thread once Follow-up due has passed.
  3. 'Airbus outreach | Errori'                  error workflow of 1 and 2: emails me what failed.

Source of truth for the texts: the Google Sheet (tab Emails, columns Subject / Body HTML / Follow-up subject /
Follow-up body HTML). The workflows send them unchanged: no signature, no n8n attribution, no tracking.

Guardrails:
- Only Status = Ready and Sent at empty. Hold or anything else is skipped.
- Before every first email: no placeholders, valid addresses, PDF > 0 bytes, and Gmail Sent must not already hold an
  'Airbus Defence and Space' email to that startup's first address (so a re-run never sends twice even if the
  sheet was not updated).
- The row is written right after each send. Send errors become 'Error: ...' and are never retried automatically.
- Replies: any message in the thread after the first one from outside OWN_DOMAINS, or any inbox message from the
  startup's domain(s) since the first email. Bounces and auto-replies are not replies: they go to Automation notes.
- Follow-up: only Status = Sent, today >= Follow-up due date, no reply, and the thread holds no second email from me.
- TEST_MODE (default): only TEST_ROWS, everything goes to TEST_RECIPIENT with no CC and a [TEST] subject; the real
  recipients are shown in a banner on top; status goes to the 'Test log' tab, the Emails tab is never written.
  In TEST_MODE a reply is any thread message whose Gmail id is not one we sent (column 'Gmail IDs'), so a test
  reply written from my own mailbox counts.

Usage: python3 build_airbus_outreach.py <out_dir> [--live] [--test-rows 'A|B'] [--deploy]
  --test-rows  startups used in TEST_MODE (default: SPREAD AI|eccenca|Agon)
  --live    TEST_MODE = false (real recipients). Only after the user's explicit 'OK, vai'.
  --deploy  create/update on n8n (refuses to overwrite an ACTIVE workflow). Workflows are created INACTIVE.
"""
import json, os, sys, uuid, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

out_dir = sys.argv[1]
DEPLOY = "--deploy" in sys.argv
TEST_MODE = "--live" not in sys.argv

ME = "i.bon@pnptc.com"
SHEET_ID = "1IR6rO48OiW0dnJNBpMDbxl85QGGdbuFoqewyCWYinzw"
PDF_FILE_ID = "1Se0tZT4Bc7BfVnrLXjeqNuFoJr7Frth9"
TEST_ROWS = sys.argv[sys.argv.index("--test-rows") + 1] if "--test-rows" in sys.argv else "SPREAD AI|eccenca|Agon"
TZ = "Europe/Madrid"

NAME1 = "Airbus outreach | 1. Invio iniziale"
NAME2 = "Airbus outreach | 2. Risposte e follow-up"
NAME3 = "Airbus outreach | Errori"

GS_CRED = {"googleSheetsOAuth2Api": {"id": "gRSPd8YEw5iadWsy", "name": "Google Sheets (Iacopo Bon)"}}
GMAIL_CRED = {"gmailOAuth2": {"id": "3FF4ROo5Rl75aufp", "name": "Gmail (Iacopo Bon)"}}
DRIVE_CRED = {"googleDriveOAuth2Api": {"id": "X1Ej9b8SiNlxQZ0H", "name": "Google Drive (Iacopo Bon)"}}
RETRY = {"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 5000}
GAPI = "https://gmail.googleapis.com/gmail/v1/users/me"
DOC = {"__rl": True, "value": SHEET_ID, "mode": "id"}


def tab(name):
    return {"__rl": True, "value": name, "mode": "name"}


def node(name, typ, ver, pos, params, **extra):
    return {"id": str(uuid.uuid4()), "name": name, "type": typ, "typeVersion": ver, "position": pos,
            "parameters": params, **extra}


def code(name, pos, js, **extra):
    return node(name, "n8n-nodes-base.code", 2, pos, {"jsCode": js}, **extra)


def settings(pos):
    vals = [("TEST_MODE", TEST_MODE, "boolean"), ("TEST_RECIPIENT", ME, "string"), ("ME", ME, "string"),
            ("SHEET_ID", SHEET_ID, "string"), ("PDF_FILE_ID", PDF_FILE_ID, "string"),
            ("OWN_DOMAINS", "pnptc.com", "string"), ("TEST_ROWS", TEST_ROWS, "string"),
            ("MIN_DELAY_S", 60, "number"), ("MAX_DELAY_S", 120, "number")]
    return node("Settings", "n8n-nodes-base.set", 3.4, pos, {
        "assignments": {"assignments": [{"id": str(uuid.uuid4()), "name": n, "value": v, "type": t}
                                        for n, v, t in vals]},
        "options": {}})


def sheets_get(name, pos, tab_name):
    return node(name, "n8n-nodes-base.googleSheets", 4.5, pos,
                {"documentId": DOC, "sheetName": tab(tab_name), "options": {}},
                credentials=GS_CRED, alwaysOutputData=True, executeOnce=True, **RETRY)


def sheets_write(name, pos, tab_name, operation, match=None):
    cols = {"mappingMode": "autoMapInputData", "value": {}, "schema": []}
    if match:
        cols["matchingColumns"] = [match]
    return node(name, "n8n-nodes-base.googleSheets", 4.5, pos,
                {"operation": operation, "documentId": DOC, "sheetName": tab(tab_name), "columns": cols,
                 "options": {"handlingExtraData": "ignoreIt", "cellFormat": "RAW"}},
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


def if_true(name, pos, expr):
    return node(name, "n8n-nodes-base.if", 2, pos, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                       "conditions": [{"id": str(uuid.uuid4()), "leftValue": expr, "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                       "combinator": "and"},
        "options": {}})


def wait_node(name, pos, loop_node):
    return node(name, "n8n-nodes-base.wait", 1.1, pos, {
        "amount": "={{ (() => { const s = $('Settings').first().json; return Math.round(s.MIN_DELAY_S + Math.random() * (s.MAX_DELAY_S - s.MIN_DELAY_S)); })() }}",
        "unit": "seconds"}, webhookId=str(uuid.uuid4()))


def send_me(name, pos):
    return node(name, "n8n-nodes-base.gmail", 2.1, pos,
                {"resource": "message", "operation": "send", "sendTo": "={{ $('Settings').first().json.ME }}",
                 "subject": "={{ $json.subject }}", "emailType": "html", "message": "={{ $json.html }}",
                 "options": {"appendAttribution": False}}, credentials=GMAIL_CRED)


def to(n):
    return [{"node": n, "type": "main", "index": 0}]


# Shared JS helpers (dates in Europe/Madrid, 'YYYY-MM-DD HH:mm').
HELPERS = r"""const TZ = 'Europe/Madrid';
function madrid(d) {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: TZ, year: 'numeric', month: '2-digit',
    day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', weekday: 'short' })
    .formatToParts(d).map(x => [x.type, x.value]));
  return { s: `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}`, date: `${p.year}-${p.month}-${p.day}`, wd: p.weekday };
}
const str = v => String(v ?? '').trim();
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const splitList = v => str(v).split(/[,;]/).map(s => s.trim()).filter(Boolean);
const EMAIL_RE = /^[^@\s<>(),;:"]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$/;
const PLACEHOLDER_RE = /\[[^\]]*\]|\{\{|\}\}|\bundefined\b|\bNaN\b/;
"""

# ---------------------------------------------------------------- WF1: first email
build_queue_js = HELPERS + r"""const S = $('Settings').first().json;
const rows = $('Sheets - Get Emails').all().map(i => i.json).filter(r => str(r['Startup name']));
const tpl = Object.fromEntries($('Sheets - Get Template').all().map(i => [str(i.json['Field']), str(i.json['Value'])]));
const followDays = Number(tpl['Follow-up after (days)']);
const senderName = tpl['Sender name'];
if (!(followDays > 0) || !senderName) throw new Error('Template tab: Follow-up after (days) or Sender name missing');
const testLog = $('Sheets - Get Test log').all().map(i => i.json).filter(r => str(r['Startup name']));
const testRows = str(S.TEST_ROWS).split('|').map(s => s.trim()).filter(Boolean);

// The PDF, downloaded once. Its size is checked here; the binary itself is never logged.
let pdfBytes = 0, pdf = null;
try { pdf = $input.first().binary.data; pdfBytes = (await this.helpers.getBinaryDataBuffer(0, 'data')).length; } catch (e) {}

const queue = [], skipped = [];
for (const r of rows) {
  const name = str(r['Startup name']);
  if (S.TEST_MODE && !testRows.includes(name)) continue;
  const status = str(r['Status']);
  if (status !== 'Ready') { skipped.push(name + ' (' + (status || 'empty') + ')'); continue; }
  if (str(r['Sent at'])) { skipped.push(name + ' (Sent at already set)'); continue; }
  if (S.TEST_MODE && testLog.some(t => str(t['Startup name']) === name && str(t['Sent at']))) {
    skipped.push(name + ' (already in Test log)'); continue;
  }
  const realTo = splitList(r['To']), realCc = splitList(r['CC']);
  const subject = str(r['Subject']), html = str(r['Body HTML']), att = str(r['Attachment']);
  const base = { name, realTo: realTo.join(', '), realCc: realCc.join(', '), followDays, senderName, testMode: S.TEST_MODE };
  const bad = [];
  if (!realTo.length) bad.push('To empty');
  const badAddr = [...realTo, ...realCc].filter(a => !EMAIL_RE.test(a));
  if (badAddr.length) bad.push('invalid address ' + badAddr.join(', '));
  if (new Set(realTo.map(a => a.toLowerCase())).size !== realTo.length) bad.push('duplicate address in To');
  for (const [k, v] of [['Subject', subject], ['Body HTML', html], ['Follow-up subject', r['Follow-up subject']],
                        ['Follow-up body HTML', r['Follow-up body HTML']]]) {
    if (!str(v)) bad.push(k + ' empty');
    else if (PLACEHOLDER_RE.test(str(v))) bad.push('placeholder left in ' + k);
  }
  if (!/\.pdf$/i.test(att)) bad.push('Attachment name is not a .pdf');
  if (!pdf || !(pdfBytes > 0)) bad.push('PDF missing or empty on Drive');
  if (bad.length) { queue.push({ json: { ...base, subject, action: 'error', reason: bad.join('; ') } }); continue; }

  let sendTo = realTo.join(', '), cc = realCc.join(', '), subj = subject, body = html;
  if (S.TEST_MODE) {
    sendTo = S.TEST_RECIPIENT; cc = ''; subj = '[TEST] ' + subject;
    body = `<div style="border:1px dashed #999;padding:8px;margin-bottom:16px;font:12px Arial;color:#555">TEST - real To: ${esc(base.realTo)}<br>real CC: ${esc(base.realCc)}<br>attachment: ${esc(att)}</div>` + html;
  }
  // Gmail safety net: has this startup already received the Airbus email?
  const sentQuery = S.TEST_MODE ? `in:sent subject:"${subj.replace(/"/g, '')}" newer_than:7d`
                                : `in:sent to:${realTo[0]} subject:"Airbus Defence and Space" newer_than:90d`;
  queue.push({ json: { ...base, action: 'send', to: sendTo, cc, subject: subj, html: body, attachmentName: att, sentQuery },
               binary: { pdf: { ...pdf, fileName: att, mimeType: 'application/pdf' } } });
}
if (!queue.length) queue.push({ json: { action: 'nothing' } });
queue[0].json.skippedList = skipped;
queue[0].json.pdfBytes = pdfBytes;
return queue;
"""

already_js = r"""const e = $('Loop Over Startups').first();
const res = $input.first().json;
const n = (res.messages || []).length;
const ok = !res.error && n === 0;
return [{ json: { ...e.json, okToSend: ok,
  blockReason: res.error ? 'Gmail check failed, not sent' : 'already in Gmail Sent (' + n + ' email), not sent' },
  binary: e.binary }];
"""

mark_sent_js = HELPERS + r"""const e = $('Loop Over Startups').first().json;
const g = $('Gmail - Send First Email').first().json;
const m = $input.first().json;
const hdr = n => (((m.payload || {}).headers || []).find(h => h.name.toLowerCase() === n.toLowerCase()) || {}).value || '';
const rfc = hdr('Message-ID');
const now = new Date();
let due = new Date(now.getTime() + e.followDays * 86400000);
const wd = madrid(due).wd;
if (wd === 'Sat') due = new Date(due.getTime() + 2 * 86400000);
if (wd === 'Sun') due = new Date(due.getTime() + 86400000);
const row = { 'Startup name': e.name, Status: 'Sent', 'Sent at': madrid(now).s, 'Thread ID': g.threadId || '',
              'Message ID': rfc, 'Follow-up due': madrid(due).s };
if (!rfc) row['Automation notes'] = 'Message-ID header not read after sending: follow-up will use the thread';
if (e.testMode) Object.assign(row, { 'Real To': e.realTo, 'Real CC': e.realCc, Subject: e.subject, 'Gmail IDs': g.id || '' });
return [{ json: { ...row, _sent: true } }];
"""

mark_error_js = r"""const e = $('Loop Over Startups').first().json;
const reason = $json.blockReason || e.reason || 'unknown';
const row = { 'Startup name': e.name, Status: 'Error: ' + reason };
if (e.testMode) Object.assign(row, { 'Real To': e.realTo, 'Real CC': e.realCc, Subject: e.subject });
return [{ json: { ...row, _sent: false } }];
"""

mark_send_failed_js = r"""// Never retried automatically: check Gmail Sent, then set Status back to Ready to try again.
const e = $('Loop Over Startups').first().json;
const err = $input.first().json.error;
const msg = (err && (err.message || err.description)) || JSON.stringify(err || 'unknown');
const row = { 'Startup name': e.name, Status: 'Error: send failed - ' + String(msg).slice(0, 150) };
if (e.testMode) Object.assign(row, { 'Real To': e.realTo, 'Real CC': e.realCc, Subject: e.subject });
return [{ json: { ...row, _sent: false } }];
"""

summary1_js = r"""const S = $('Settings').first().json;
const q = $('Build Queue').first().json;
const res = [];
for (let r = 0; r < 500; r++) {
  let its;
  try { its = $('Row Payload').all(0, r); } catch (e) { break; }
  if (!its || !its.length) break;
  res.push(...its.map(i => i.json));
}
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const sent = res.filter(r => r.Status === 'Sent'), err = res.filter(r => r.Status !== 'Sent');
const skipped = q.skippedList || [];
let html = `<p><b>${S.TEST_MODE ? 'TEST MODE' : 'LIVE'}</b> - inviate: ${sent.length}, saltate: ${skipped.length}, errori: ${err.length}. PDF: ${q.pdfBytes || 0} byte.</p>`;
if (sent.length) html += '<p>Inviate:</p><ul>' + sent.map(r => `<li>${esc(r['Startup name'])} - ${esc(r['Sent at'])} - follow-up dal ${esc(r['Follow-up due'])}</li>`).join('') + '</ul>';
if (err.length) html += '<p>Errori (non inviate):</p><ul>' + err.map(r => `<li>${esc(r['Startup name'])}: ${esc(r.Status)}</li>`).join('') + '</ul>';
if (skipped.length) html += '<p>Saltate:</p><ul>' + skipped.map(s => `<li>${esc(s)}</li>`).join('') + '</ul>';
return [{ json: { subject: `${S.TEST_MODE ? '[TEST] ' : ''}Airbus outreach: ${sent.length} inviate, ${err.length} errori, ${skipped.length} saltate`, html } }];
"""

L1 = "Loop Over Startups"
wf1_nodes = [
    node("Run Manually", "n8n-nodes-base.manualTrigger", 1, [0, 0], {}),
    settings([200, 0]),
    sheets_get("Sheets - Get Emails", [400, 0], "Emails"),
    sheets_get("Sheets - Get Template", [600, 0], "Template"),
    sheets_get("Sheets - Get Test log", [800, 0], "Test log"),
    node("Drive - Download PDF", "n8n-nodes-base.googleDrive", 3, [1000, 0],
         {"operation": "download", "fileId": {"__rl": True, "value": "={{ $('Settings').first().json.PDF_FILE_ID }}", "mode": "id"},
          "options": {}}, credentials=DRIVE_CRED, executeOnce=True, **RETRY),
    code("Build Queue", [1200, 0], build_queue_js),
    node(L1, "n8n-nodes-base.splitInBatches", 3, [1400, 0], {"batchSize": 1, "options": {}}),
    if_true("Send?", [1600, 100], "={{ $json.action === 'send' }}"),
    if_true("Error?", [1800, 300], "={{ $json.action === 'error' }}"),
    gmail_api("Gmail - Already Sent?", [1800, 0], f"{GAPI}/messages",
              [("q", "={{ $json.sentQuery }}"), ("maxResults", "10")], onError="continueRegularOutput"),
    code("Check Already Sent", [2000, 0], already_js),
    if_true("OK to Send?", [2200, 0], "={{ $json.okToSend }}"),
    node("Gmail - Send First Email", "n8n-nodes-base.gmail", 2.1, [2400, -100],
         {"resource": "message", "operation": "send", "sendTo": "={{ $json.to }}", "subject": "={{ $json.subject }}",
          "emailType": "html", "message": "={{ $json.html }}",
          "options": {"appendAttribution": False, "ccList": "={{ $json.cc }}", "senderName": "={{ $json.senderName }}",
                      "attachmentsUi": {"attachmentsBinary": [{"property": "pdf"}]}}},
         credentials=GMAIL_CRED, onError="continueErrorOutput"),
    gmail_api("Gmail - Read Message-ID", [2600, -200],
              f"={{{{ '{GAPI}/messages/' + $json.id + '?format=metadata&metadataHeaders=Message-ID' }}}}",
              onError="continueRegularOutput"),
    code("Mark Sent", [2800, -200], mark_sent_js),
    code("Mark Send Failed", [2600, 0], mark_send_failed_js),
    code("Mark Error", [2400, 250], mark_error_js),
    code("Row Payload", [3000, 0], "return $input.all();"),
    if_true("Test Mode?", [3200, 0], "={{ $('Settings').first().json.TEST_MODE }}"),
    sheets_write("Test log - Append Row", [3400, -100], "Test log", "append"),
    sheets_write("Emails - Update Row", [3400, 100], "Emails", "update", "Startup name"),
    if_true("Sent? (wait)", [3600, 0], "={{ $('Row Payload').first().json._sent }}"),
    wait_node("Wait 60-120 s", [3800, -100], L1),
    code("Summary", [1600, -250], summary1_js),
    send_me("Email Summary to Me", [1800, -250]),
]
wf1_conn = {
    "Run Manually": {"main": [to("Settings")]},
    "Settings": {"main": [to("Sheets - Get Emails")]},
    "Sheets - Get Emails": {"main": [to("Sheets - Get Template")]},
    "Sheets - Get Template": {"main": [to("Sheets - Get Test log")]},
    "Sheets - Get Test log": {"main": [to("Drive - Download PDF")]},
    "Drive - Download PDF": {"main": [to("Build Queue")]},
    "Build Queue": {"main": [to(L1)]},
    L1: {"main": [to("Summary"), to("Send?")]},
    "Summary": {"main": [to("Email Summary to Me")]},
    "Send?": {"main": [to("Gmail - Already Sent?"), to("Error?")]},
    "Error?": {"main": [to("Mark Error"), to(L1)]},
    "Gmail - Already Sent?": {"main": [to("Check Already Sent")]},
    "Check Already Sent": {"main": [to("OK to Send?")]},
    "OK to Send?": {"main": [to("Gmail - Send First Email"), to("Mark Error")]},
    "Gmail - Send First Email": {"main": [to("Gmail - Read Message-ID"), to("Mark Send Failed")]},
    "Gmail - Read Message-ID": {"main": [to("Mark Sent")]},
    "Mark Sent": {"main": [to("Row Payload")]},
    "Mark Send Failed": {"main": [to("Row Payload")]},
    "Mark Error": {"main": [to("Row Payload")]},
    "Row Payload": {"main": [to("Test Mode?")]},
    "Test Mode?": {"main": [to("Test log - Append Row"), to("Emails - Update Row")]},
    "Test log - Append Row": {"main": [to("Sent? (wait)")]},
    "Emails - Update Row": {"main": [to("Sent? (wait)")]},
    "Sent? (wait)": {"main": [to("Wait 60-120 s"), to(L1)]},
    "Wait 60-120 s": {"main": [to(L1)]},
}

# ---------------------------------------------------------------- WF2: replies + follow-up
select2_js = HELPERS + r"""const S = $('Settings').first().json;
const emails = $('Sheets - Get Emails').all().map(i => i.json).filter(r => str(r['Startup name']));
const testLog = $('Sheets - Get Test log').all().map(i => i.json).filter(r => str(r['Startup name']));
const src = S.TEST_MODE ? testLog : emails;
const out = [];
for (const r of src) {
  const status = str(r['Status']);
  if (!['Sent', 'Follow-up sent'].includes(status) || !str(r['Thread ID'])) continue;
  const name = str(r['Startup name']);
  const er = emails.find(x => str(x['Startup name']) === name) || {};
  const realTo = splitList(S.TEST_MODE ? r['Real To'] : r['To']);
  const realCc = splitList(S.TEST_MODE ? r['Real CC'] : r['CC']);
  // Test rows never look at the real startups' mail.
  const domains = S.TEST_MODE ? [] : [...new Set(realTo.map(a => a.split('@')[1].toLowerCase()))]
    .filter(d => !str(S.OWN_DOMAINS).split(',').map(x => x.trim()).includes(d));
  const sendTo = S.TEST_MODE ? [S.TEST_RECIPIENT] : realTo;
  const subject = S.TEST_MODE ? 'Re: ' + str(r['Subject']) : str(er['Follow-up subject']);
  let html = str(er['Follow-up body HTML']);
  if (S.TEST_MODE) html = `<div style="border:1px dashed #999;padding:8px;margin-bottom:16px;font:12px Arial;color:#555">TEST follow-up - real To: ${esc(realTo.join(', '))}<br>real CC: ${esc(realCc.join(', '))}</div>` + html;
  out.push({ json: {
    key: S.TEST_MODE ? { row_number: r.row_number } : { 'Startup name': name },
    name, status, threadId: str(r['Thread ID']), messageId: str(r['Message ID']), sentAt: str(r['Sent at']),
    due: str(r['Follow-up due']), notes: str(r['Automation notes']), ourIds: splitList(r['Gmail IDs']),
    domains, sendTo: sendTo.join(', '), cc: S.TEST_MODE ? '' : realCc.join(', '), subject, html,
    // Placeholder check runs on the sheet text, before the [TEST] label / banner are added.
    checkText: str(er['Follow-up subject']) + ' ' + str(er['Follow-up body HTML']),
    testMode: S.TEST_MODE } });
}
return out;
"""

# Gmail queries per candidate (after = first message of the thread).
AFTER = ("(() => { try { const ms = Number($('Gmail - Get Thread').item.json.messages[0].internalDate);"
         " return ms > 0 ? ' after:' + Math.floor(ms / 1000) : ''; } catch (e) { return ''; } })()")
q_inbox = ("={{ (() => { const c = $('Select Rows').item.json;"
           " if (!c.domains.length) return 'from:nobody@invalid.invalid';"
           " return '-in:sent' + " + AFTER + " + ' {' + c.domains.map(d => 'from:@' + d).join(' ') + '}'; })() }}")
q_bounce = ("={{ (() => { const c = $('Select Rows').item.json;"
            " const addrs = c.testMode ? c.sendTo.split(', ') : c.sendTo.split(', ').concat(c.cc ? c.cc.split(', ') : []);"
            " return '{from:mailer-daemon from:postmaster}' + " + AFTER + " + ' {' + addrs.map(a => '\"' + a + '\"').join(' ') + '}'; })() }}")

expand_js = r"""// One item per inbox / bounce message to read (max 5 + 5 per startup).
const out = [];
const inbox = $('Gmail - Startup Inbox').all(), bounces = $('Gmail - Bounces').all();
$('Select Rows').all().forEach((it, k) => {
  for (const m of ((inbox[k] || {}).json || {}).messages?.slice(0, 5) || []) out.push({ json: { k, id: m.id, kind: 'inbox' } });
  for (const m of ((bounces[k] || {}).json || {}).messages?.slice(0, 5) || []) out.push({ json: { k, id: m.id, kind: 'bounce' } });
});
return out.length ? out : [{ json: { k: -1, id: 'none', kind: 'none' } }];
"""

evaluate2_js = HELPERS + r"""const S = $('Settings').first().json;
const ME = str(S.ME).toLowerCase();
const OWN = str(S.OWN_DOMAINS).split(',').map(x => x.trim().toLowerCase()).filter(Boolean);
const cands = $('Select Rows').all(), threads = $('Gmail - Get Thread').all();
const extra = $('Expand Messages').all().map((it, i) => ({ ...it.json, msg: ($('Gmail - Read Message').all()[i] || {}).json || {} }));
const hdr = (m, n) => (((m.payload || {}).headers || []).find(h => h.name.toLowerCase() === n.toLowerCase()) || {}).value || '';
const fromAddr = m => { const f = hdr(m, 'From'); const x = f.match(/<([^>]+)>/); return (x ? x[1] : f).trim().toLowerCase(); };
const isBounce = m => /mailer-daemon|postmaster/i.test(hdr(m, 'From')) || /delivery status notification|undeliverable|delivery failure|returned mail/i.test(hdr(m, 'Subject'));
const isAuto = m => { const as = hdr(m, 'Auto-Submitted'); return (as && !/^no$/i.test(as)) || !!hdr(m, 'X-Autoreply') || !!hdr(m, 'X-Autorespond')
  || /auto-?reply|automatic reply|out of (the )?office|abwesenheit|absence|automatische antwort|r[ée]ponse automatique|respuesta autom[áa]tica|risposta automatica/i.test(hdr(m, 'Subject')); };
const b64 = s => Buffer.from(s, 'utf8').toString('base64');
const b64url = s => b64(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const wrap = s => s.replace(/(.{76})/g, '$1\r\n');
const today = madrid(new Date()).date;

const out = [];
cands.forEach((it, k) => {
  const c = it.json;
  const t = (threads[k] || {}).json || {};
  const notes = new Set(c.notes ? c.notes.split(' | ') : []);
  const before = notes.size;
  const row = { ...c.key };
  if (t.error || !(t.messages || []).length) {
    notes.add('Thread not readable in Gmail (' + today + ')');
    row['Automation notes'] = [...notes].join(' | ');
    return out.push({ json: { action: 'note', row } });
  }
  const msgs = t.messages, orig = msgs[0];
  const ours = m => c.testMode ? c.ourIds.includes(m.id) : (fromAddr(m) === ME || OWN.includes(fromAddr(m).split('@')[1]));
  let reply = null;
  for (const m of msgs.slice(1)) {
    if (ours(m)) continue;
    if (isBounce(m)) { notes.add('Bounce in thread: ' + (m.snippet || '').slice(0, 80)); continue; }
    if (isAuto(m)) { notes.add('Auto-reply: ' + fromAddr(m)); continue; }
    if (!reply) reply = m;
  }
  for (const x of extra.filter(x => x.k === k)) {
    const m = x.msg;
    if (!m || m.error || !m.id) continue;
    if (x.kind === 'bounce') {
      const addr = c.sendTo.split(', ').concat(c.cc ? c.cc.split(', ') : []).find(a => (m.snippet || '').toLowerCase().includes(a.toLowerCase()));
      notes.add('Bounce: ' + (addr || (m.snippet || '').slice(0, 80)));
      continue;
    }
    if (isBounce(m)) continue;
    if (isAuto(m)) { notes.add('Auto-reply: ' + fromAddr(m)); continue; }
    if (!reply) reply = m;
  }
  if (notes.size !== before) row['Automation notes'] = [...notes].join(' | ');
  if (reply) {
    row.Status = 'Replied';
    row['Replied at'] = madrid(new Date(Number(reply.internalDate) || Date.now())).s;
    return out.push({ json: { action: 'replied', row, name: c.name, from: fromAddr(reply) } });
  }
  if (c.status !== 'Sent' || !c.due || today < c.due.slice(0, 10)) {
    return notes.size !== before ? out.push({ json: { action: 'note', row } }) : null;
  }
  if (msgs.filter(ours).length > 1) {
    notes.add('Follow-up not sent: the thread already holds a second email from us');
    row['Automation notes'] = [...notes].join(' | ');
    return out.push({ json: { action: 'note', row } });
  }
  const rfc = hdr(orig, 'Message-ID') || c.messageId;
  const bad = [];
  if (!rfc) bad.push('no Message-ID for the original email');
  if (!c.subject || !c.html) bad.push('Follow-up subject or body empty');
  if (!c.checkText.trim() || PLACEHOLDER_RE.test(c.checkText)) bad.push('placeholder left or follow-up text missing');
  const addrs = c.sendTo.split(', ').concat(c.cc ? c.cc.split(', ') : []);
  if (addrs.some(a => !EMAIL_RE.test(a))) bad.push('invalid address');
  if (bad.length) { row.Status = 'Error: follow-up not sent - ' + bad.join('; '); return out.push({ json: { action: 'note', row } }); }
  const boundary = 'b' + Math.random().toString(36).slice(2) + Date.now();
  const text = c.html.replace(/<br\s*\/?>/gi, '\n').replace(/<\/p>/gi, '\n\n').replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').trim();
  const mime = [
    'From: ' + $('Template Values').first().json.senderName + ' <' + S.ME + '>',
    'To: ' + c.sendTo, ...(c.cc ? ['Cc: ' + c.cc] : []),
    'Subject: =?UTF-8?B?' + b64(c.subject) + '?=', 'In-Reply-To: ' + rfc, 'References: ' + rfc, 'MIME-Version: 1.0',
    'Content-Type: multipart/alternative; boundary="' + boundary + '"', '',
    '--' + boundary, 'Content-Type: text/plain; charset="UTF-8"', 'Content-Transfer-Encoding: base64', '', wrap(b64(text)),
    '--' + boundary, 'Content-Type: text/html; charset="UTF-8"', 'Content-Transfer-Encoding: base64', '', wrap(b64(c.html)),
    '--' + boundary + '--', '',
  ].join('\r\n');
  out.push({ json: { action: 'send', row, name: c.name, ourIds: c.ourIds, testMode: c.testMode,
                     sendBody: { raw: b64url(mime), threadId: c.threadId } } });
});
return out;
"""

template_js = HELPERS + r"""const tpl = Object.fromEntries($('Sheets - Get Template').all().map(i => [str(i.json['Field']), str(i.json['Value'])]));
if (!tpl['Sender name']) throw new Error('Template tab: Sender name missing');
return [{ json: { senderName: tpl['Sender name'] } }];
"""

fu_sent_js = HELPERS + r"""const e = $('Loop Over Rows').first().json;
const g = $input.first().json;
const row = { ...e.row, Status: 'Follow-up sent', 'Follow-up sent at': madrid(new Date()).s };
if (e.testMode) row['Gmail IDs'] = [...e.ourIds, g.id].filter(Boolean).join(', ');
return [{ json: { ...row, _sent: true } }];
"""
fu_failed_js = r"""// Not retried automatically: check the thread in Gmail, then set Status back to Sent to try again.
const e = $('Loop Over Rows').first().json;
const err = $input.first().json.error;
const msg = (err && (err.message || err.description)) || JSON.stringify(err || 'unknown');
return [{ json: { ...e.row, Status: 'Error: follow-up send failed - ' + String(msg).slice(0, 150), _sent: false } }];
"""
other_js = r"""const e = $('Loop Over Rows').first().json;
return [{ json: { ...e.row, _sent: false } }];
"""

summary2_js = r"""const S = $('Settings').first().json;
const res = [];
for (let r = 0; r < 500; r++) {
  let its;
  try { its = $('Row Payload').all(0, r); } catch (e) { break; }
  if (!its || !its.length) break;
  res.push(...its.map(i => i.json));
}
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const rows = res.filter(r => r.Status || r['Automation notes']);
if (!rows.length) return [];
const label = r => esc(r['Startup name'] || ('Test log row ' + r.row_number));
const html = '<ul>' + rows.map(r => `<li>${label(r)}: ${esc(r.Status || 'note')}${r['Automation notes'] ? ' - ' + esc(r['Automation notes']) : ''}</li>`).join('') + '</ul>';
const fu = rows.filter(r => r.Status === 'Follow-up sent').length, rep = rows.filter(r => r.Status === 'Replied').length;
return [{ json: { subject: `${S.TEST_MODE ? '[TEST] ' : ''}Airbus outreach: ${rep} risposte, ${fu} follow-up inviati`, html } }];
"""

L2 = "Loop Over Rows"
wf2_nodes = [
    node("Mon-Fri 09:30", "n8n-nodes-base.scheduleTrigger", 1.2, [0, -100],
         {"rule": {"interval": [{"field": "cronExpression", "expression": "30 9 * * 1-5"}]}}),
    node("Run Manually", "n8n-nodes-base.manualTrigger", 1, [0, 100], {}),
    settings([200, 0]),
    sheets_get("Sheets - Get Emails", [400, 0], "Emails"),
    sheets_get("Sheets - Get Test log", [600, 0], "Test log"),
    sheets_get("Sheets - Get Template", [800, 0], "Template"),
    code("Template Values", [1000, 0], template_js),
    code("Select Rows", [1200, 0], select2_js),
    gmail_api("Gmail - Get Thread", [1400, 0],
              f"={{{{ '{GAPI}/threads/' + $json.threadId + '?format=metadata&metadataHeaders=From&metadataHeaders=To"
              "&metadataHeaders=Subject&metadataHeaders=Message-ID&metadataHeaders=Auto-Submitted"
              "&metadataHeaders=X-Autoreply&metadataHeaders=X-Autorespond' }}}}", onError="continueRegularOutput"),
    gmail_api("Gmail - Startup Inbox", [1600, 0], f"{GAPI}/messages", [("q", q_inbox), ("maxResults", "5")],
              onError="continueRegularOutput"),
    gmail_api("Gmail - Bounces", [1800, 0], f"{GAPI}/messages", [("q", q_bounce), ("maxResults", "5")],
              onError="continueRegularOutput"),
    code("Expand Messages", [2000, 0], expand_js),
    gmail_api("Gmail - Read Message", [2200, 0],
              f"={{{{ '{GAPI}/messages/' + $json.id + '?format=metadata&metadataHeaders=From&metadataHeaders=Subject"
              "&metadataHeaders=Auto-Submitted&metadataHeaders=X-Autoreply&metadataHeaders=X-Autorespond' }}}}",
              onError="continueRegularOutput"),
    code("Evaluate", [2400, 0], evaluate2_js),
    node(L2, "n8n-nodes-base.splitInBatches", 3, [2600, 0], {"batchSize": 1, "options": {}}),
    if_true("Follow-up?", [2800, 100], "={{ $json.action === 'send' }}"),
    gmail_api("Gmail - Send Follow-up", [3000, 0], f"{GAPI}/messages/send", method="POST",
              body="={{ JSON.stringify($json.sendBody) }}", retry=False, onError="continueErrorOutput"),
    code("Mark Follow-up Sent", [3200, -100], fu_sent_js),
    code("Mark Follow-up Failed", [3200, 50], fu_failed_js),
    code("Mark Other", [3000, 250], other_js),
    code("Row Payload", [3400, 0], "return $input.all();"),
    if_true("Test Mode?", [3600, 0], "={{ $('Settings').first().json.TEST_MODE }}"),
    sheets_write("Test log - Update Row", [3800, -100], "Test log", "update", "row_number"),
    sheets_write("Emails - Update Row", [3800, 100], "Emails", "update", "Startup name"),
    if_true("Sent? (wait)", [4000, 0], "={{ $('Row Payload').first().json._sent }}"),
    wait_node("Wait 60-120 s", [4200, -100], L2),
    code("Summary", [2800, -250], summary2_js),
    send_me("Email Summary to Me", [3000, -250]),
]
straight2 = ["Settings", "Sheets - Get Emails", "Sheets - Get Test log", "Sheets - Get Template", "Template Values",
             "Select Rows", "Gmail - Get Thread", "Gmail - Startup Inbox", "Gmail - Bounces", "Expand Messages",
             "Gmail - Read Message", "Evaluate", L2]
wf2_conn = {a: {"main": [to(b)]} for a, b in zip(straight2, straight2[1:])}
wf2_conn.update({
    "Mon-Fri 09:30": {"main": [to("Settings")]},
    "Run Manually": {"main": [to("Settings")]},
    L2: {"main": [to("Summary"), to("Follow-up?")]},
    "Summary": {"main": [to("Email Summary to Me")]},
    "Follow-up?": {"main": [to("Gmail - Send Follow-up"), to("Mark Other")]},
    "Gmail - Send Follow-up": {"main": [to("Mark Follow-up Sent"), to("Mark Follow-up Failed")]},
    "Mark Follow-up Sent": {"main": [to("Row Payload")]},
    "Mark Follow-up Failed": {"main": [to("Row Payload")]},
    "Mark Other": {"main": [to("Row Payload")]},
    "Row Payload": {"main": [to("Test Mode?")]},
    "Test Mode?": {"main": [to("Test log - Update Row"), to("Emails - Update Row")]},
    "Test log - Update Row": {"main": [to("Sent? (wait)")]},
    "Emails - Update Row": {"main": [to("Sent? (wait)")]},
    "Sent? (wait)": {"main": [to("Wait 60-120 s"), to(L2)]},
    "Wait 60-120 s": {"main": [to(L2)]},
})

# ---------------------------------------------------------------- WF3: errors
error_js = r"""const e = $input.first().json;
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const ex = e.execution || {}, wf = e.workflow || {};
const err = ex.error || e.trigger?.error || {};
const html = `<p><b>${esc(wf.name)}</b> si e' fermato.</p><ul>`
  + `<li>Nodo: ${esc(ex.lastNodeExecuted || err.node?.name || '?')}</li>`
  + `<li>Errore: ${esc(err.message || JSON.stringify(err).slice(0, 300))}</li>`
  + `<li>Esecuzione: ${esc(ex.url || ex.id || '')}</li></ul>`
  + '<p>Le righe gia\' scritte nel foglio sono corrette; quelle non ancora scritte non sono state inviate, '
  + 'oppure lo sono ma il controllo su Gmail Inviati le blocca al prossimo giro. Controlla la colonna Status.</p>';
return [{ json: { subject: 'Airbus outreach: errore in ' + (wf.name || 'workflow'), html } }];
"""
wf3_nodes = [
    node("Error Trigger", "n8n-nodes-base.errorTrigger", 1, [0, 0], {}),
    node("Settings", "n8n-nodes-base.set", 3.4, [200, 0], {"assignments": {"assignments": [
        {"id": str(uuid.uuid4()), "name": "ME", "value": ME, "type": "string"}]}, "options": {"includeOtherFields": True}}),
    code("Build Error Email", [400, 0], error_js),
    send_me("Email Error to Me", [600, 0]),
]
wf3_conn = {"Error Trigger": {"main": [to("Settings")]}, "Settings": {"main": [to("Build Error Email")]},
            "Build Error Email": {"main": [to("Email Error to Me")]}}

SETTINGS = {"executionOrder": "v1", "timezone": TZ, "saveManualExecutions": True}
wfs = {
    NAME3: {"name": NAME3, "nodes": wf3_nodes, "connections": wf3_conn, "settings": dict(SETTINGS)},
    NAME1: {"name": NAME1, "nodes": wf1_nodes, "connections": wf1_conn, "settings": dict(SETTINGS)},
    NAME2: {"name": NAME2, "nodes": wf2_nodes, "connections": wf2_conn, "settings": dict(SETTINGS)},
}
for n, wf in wfs.items():
    fn = n.replace("|", "-").replace(" ", "_").replace(".", "")
    json.dump(wf, open(os.path.join(out_dir, fn + ".json"), "w"), indent=1)
print("generated", "TEST_MODE" if TEST_MODE else "LIVE", "->", out_dir)

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
    by_name = {w["name"]: w for w in all_wf}
    for n in (NAME1, NAME2):
        if n in by_name and by_name[n]["active"]:
            raise SystemExit(f"{n} is ACTIVE on n8n - refusing to overwrite a live sender. Deactivate it first.")
    backups = os.path.join(ROOT, "Sourcing - N8N Cloud Rebuild", "workflow_backups")
    ids = {}
    for n in (NAME3, NAME1, NAME2):
        wf = wfs[n]
        if n != NAME3 and NAME3 in ids:
            wf["settings"]["errorWorkflow"] = ids[NAME3]
        ex = by_name.get(n)
        res = call("PUT", f"/api/v1/workflows/{ex['id']}", wf) if ex else call("POST", "/api/v1/workflows", wf)
        ids[n] = res["id"]
        print(f"{n}: {res['id']} | active: {res['active']} | nodes: {len(res['nodes'])}")
        json.dump(res, open(os.path.join(backups, n.replace("|", "-") + ".json"), "w"), indent=2)
