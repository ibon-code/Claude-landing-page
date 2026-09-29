"""One-off: builds an n8n workflow that appends a Harmonic Excel export to the Sourcing tab
and then runs 'Sourcing - Weekly AI Scoring' straight away (via its Execute Workflow trigger).
Usage: build_import_harmonic_xlsx.py <file.xlsx> <out.json> <source label>
"""
import json, sys, datetime
import openpyxl

xlsx, out_path, source = sys.argv[1], sys.argv[2], sys.argv[3]
rows = list(openpyxl.load_workbook(xlsx, read_only=True, data_only=True).worksheets[0].iter_rows(values_only=True))
header, data = rows[0], [dict(zip(rows[0], r)) for r in rows[1:] if any(r)]


def year(v):
    return v.year if isinstance(v, (datetime.date, datetime.datetime)) else (str(v)[:4] if v else None)


def num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


records = []
for r in data:
    extras = [f"Category: {r['category']}"] if r.get("category") else []
    if year(r.get("founding_date")):
        extras.append(f"Founded: {year(r['founding_date'])}")
    if num(r.get("headcount")):
        extras.append(f"Headcount: {num(r['headcount'])}")
    if r.get("funding_last_type") and r["funding_last_type"] != "UNKNOWN":
        when = r["funding_last_at"].strftime("%Y-%m") if hasattr(r.get("funding_last_at"), "strftime") else ""
        extras.append(f"Last round: {r['funding_last_type'].replace('_', ' ').title()} {when}".strip())
    site = (r.get("website_url") or "").strip()
    records.append({
        "Organization Name": r["name"].strip(),
        "Organization Name URL": site,
        "Headquarters Location": ", ".join(x for x in (r.get("location_city"), r.get("location_country")) if x),
        "Description": (r.get("description") or "").strip() + (" | " + " | ".join(extras) if extras else ""),
        "Website": site,
        "Move to Pipeline?": False,
        "Source": source,
        "Funding USD (parsed)": num(r.get("funding_total")),
    })

DOC = {"__rl": True, "value": "1LpPqSKXOvB2FdqNGNnlVBpPDvnfDrYml7npHJEZpKxc", "mode": "list",
       "cachedResultName": "Sourcing - N8N Cloud",
       "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1LpPqSKXOvB2FdqNGNnlVBpPDvnfDrYml7npHJEZpKxc/edit?usp=drivesdk"}
GS_CRED = {"googleSheetsOAuth2Api": {"id": "gRSPd8YEw5iadWsy", "name": "Google Sheets (Iacopo Bon)"}}
nodes = [
    {"name": "Manual Trigger", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [0, 0], "parameters": {}},
    {"name": "Leads from Excel", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [220, 0],
     "parameters": {"jsCode": "const ROWS = " + json.dumps(records, ensure_ascii=False) + ";\nreturn ROWS.map(r => ({ json: r }));"}},
    {"name": "Sourcing - Append", "type": "n8n-nodes-base.googleSheets", "typeVersion": 4.5, "position": [440, 0],
     "credentials": GS_CRED,
     "parameters": {"operation": "append", "documentId": DOC, "sheetName": {"__rl": True, "value": "0", "mode": "id"},
                    "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": []},
                    "options": {}}},
    {"name": "Run AI Scoring Now", "type": "n8n-nodes-base.executeWorkflow", "typeVersion": 1.2, "position": [660, 0],
     "executeOnce": True,
     "parameters": {"workflowId": {"__rl": True, "value": "1YSwWkL3cCakhvxs", "mode": "list",
                                   "cachedResultName": "Sourcing - Weekly AI Scoring"},
                    "workflowInputs": {"mappingMode": "defineBelow", "value": {}, "matchingColumns": [], "schema": []},
                    "mode": "once", "options": {}}},
]
names = [n["name"] for n in nodes]
conn = {a: {"main": [[{"node": b, "type": "main", "index": 0}]]} for a, b in zip(names, names[1:])}
json.dump({"name": "TEMP - Import New Leads (Harmonic xlsx)", "nodes": nodes, "connections": conn,
           "settings": {"executionOrder": "v1"}}, open(out_path, "w"), ensure_ascii=False)
print(len(records), "rows")
