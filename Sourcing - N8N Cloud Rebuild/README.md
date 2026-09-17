# Sourcing - N8N Cloud Rebuild

Ricostruzione da zero (non migrazione) della pipeline di sourcing+outreach startup sul **nuovo account n8n aziendale**, separata dalla vecchia pipeline locale che gira ancora sul Mac (script Python + n8n locale, cartella root del repo). Le due pipeline sono indipendenti: questa cartella riguarda **solo** la nuova.

Non toccare/cancellare la vecchia pipeline finché questa non è confermata funzionante al 100%.

## Dove vive cosa

| Cosa | Dove |
|---|---|
| Workflow n8n (live) | `https://agentflow.pnptc.com` — self-hosted, non n8n.cloud ufficiale |
| Dati (startup, pipeline contatti) | Airtable, base "Sourcing - N8N" (id `appKs6UmJX4w6GEp0`) |
| Chiavi/token | `.env` nella root del repo (condiviso con la vecchia pipeline, mai committato) |
| Piano tecnico completo | `/Users/iacopobon/.claude/plans/ok-allora-non-voglio-clever-horizon.md` |
| Backup dei workflow costruiti | `workflow_backups/` in questa cartella (JSON esportati via API n8n — nessun segreto dentro, le credenziali sono referenziate solo per ID) |

## Perché Airtable invece di Google Sheets

L'organizzazione ha disabilitato Google Cloud Platform per l'account aziendale, quindi Google Sheets/Gmail via OAuth2 erano irraggiungibili. Airtable fa lo stesso lavoro (tabella online) autenticandosi con un semplice token, senza dipendenze da Google Cloud. Per lo stesso motivo l'email non usa il nodo Gmail nativo di n8n ma SMTP/IMAP con la password per app già in uso nella vecchia pipeline (indicazione dell'IT).

## Stato attuale (aggiornato 2026-09-17)

**Costruito e testato:**
- `Util - Claude Messages API` — sotto-workflow condiviso per le chiamate a Claude.
- `Sourcing - Daily Harvest` (cron giornaliero 12:00) — 3 fonti: BetaList (25 righe), tech.eu (8 righe), Wamda (8 righe), tutte deduplicate e verificate su run ripetuti. Il ramo Apollo è costruito correttamente ma produce 0 risultati perché **la chiave Apollo non ha crediti di ricerca residui**.

**Non ancora costruito** (vedi il piano per i dettagli):
- Scoring settimanale AI (valutazione startup con Claude)
- Ciclo Pipeline ogni 15 min (spostamento in pipeline, arricchimento contatti, invio outreach, invito Playbook)
- Controllo risposte + follow-up giornaliero
- Gestione bounce (email rimbalzate)
- Harvest settimanale Harmonic (**bloccato**: la chiave Harmonic è valida ma l'account non ha i permessi per cercare aziende — serve il manager)

**Tutti i workflow sono lasciati INATTIVI** — nessun invio automatico reale finché non li attivi esplicitamente tu.

## Credenziali create su n8n (solo riferimento ID, i valori restano nel `.env`)

| Nome | Tipo | ID |
|---|---|---|
| Apollo Header Auth | httpHeaderAuth | `tsTg37ICmuv8HBpC` |
| Harmonic Header Auth | httpHeaderAuth | `YsZim9PzaFellWqP` (bloccata sui permessi) |
| Anthropic Custom Auth | httpCustomAuth | `5Nk0gwk1gXo8HRaS` |
| Gmail SMTP | smtp | `TLNLg8fonUK1hOD8` |
| Gmail IMAP | imap | `nNSAuErjynXHLMa8` |
| Airtable Token | airtableTokenApi | `QbFL5zfsc0H2Pcs5` |
