# Sourcing - N8N Cloud Rebuild

Ricostruzione da zero (non migrazione) della pipeline di sourcing+outreach startup sul **nuovo account n8n aziendale**, separata dalla vecchia pipeline locale che gira ancora sul Mac (script Python + n8n locale, cartella root del repo). Le due pipeline sono indipendenti: questa cartella riguarda **solo** la nuova.

Non toccare/cancellare la vecchia pipeline finché questa non è confermata funzionante al 100%.

## Dove vive cosa

| Cosa | Dove |
|---|---|
| Workflow n8n (live) | `https://agentflow.pnptc.com` — self-hosted, non n8n.cloud ufficiale |
| Dati (startup, pipeline contatti) | Google Sheet "Sourcing - N8N Cloud" (id `1LpPqSKXOvB2FdqNGNnlVBpPDvnfDrYml7npHJEZpKxc`), tab `Sourcing` e `Pipeline`, nella cartella Drive "Sourcing N8N - Masterfile". La vecchia base Airtable resta solo come riferimento. |
| Chiavi/token | `.env` nella root del repo (condiviso con la vecchia pipeline, mai committato) |
| Piano tecnico completo | `/Users/iacopobon/.claude/plans/ok-allora-non-voglio-clever-horizon.md` |
| Backup dei workflow costruiti | `workflow_backups/` in questa cartella (JSON esportati via API n8n — nessun segreto dentro, le credenziali sono referenziate solo per ID) |

## Google Sheets / Gmail (dal 2026-09-24)

All'inizio Google Cloud era bloccato per l'account aziendale, quindi la build partiva su Airtable + SMTP/IMAP. Dal 2026-09-24 sull'istanza esistono credenziali Google OAuth2 funzionanti (Sheets, Gmail, Drive...): i dati sono tornati su Google Sheets e l'invio email usa il nodo Gmail nativo.

## Stato attuale (aggiornato 2026-09-29)

**ATTIVI dal 2026-09-29**: Util Claude, Daily Harvest, Weekly AI Scoring, Move to Pipeline. **Ancora spento**: Salesforce Outreach (invia email vere).

| Workflow | ID | Stato |
|---|---|---|
| `Util - Claude Messages API` | `V5wGQ55LdYLhSCmf` | Testato |
| `Sourcing - Daily Harvest` (ogni giorno 12:00) | `1D0Q5agDQFAsVtFd` | Testato — BetaList, Apollo, tech.eu, Wamda |
| `Sourcing - Weekly AI Scoring` (lunedì 13:00) | `1YSwWkL3cCakhvxs` | Testato su 5 righe (scritte sulle righe giuste). Assegna un punteggio alle righe senza `AI Moat Score`: 1-5 se PASS, 0 se REJECT, motivazione in `AI Notes`. Generato da `scripts/build_scoring.py` (criteri in `scripts/criteria.txt`, identici a `select_leads.py`) |
| `Pipeline - Move to Pipeline` (ogni 15 min) | `PUsnpqT1jQFF5HXM` | Copia in `Pipeline` le righe con `Move to Pipeline?` = TRUE (solo nome + sito), salta quelle già presenti. Le righe restano in `Sourcing` (servono al dedup dell'harvest). Lo scoring spunta automaticamente `Move to Pipeline?` per ogni PASS |
| `Pipeline - Salesforce Outreach` (ogni 15 min) | `1TkdOwL5o1WWC6a8` | Testato con un'email reale a me stesso. Non incrementa ancora `Outreach Count` |

**Da costruire:** ciclo Pipeline (spostamento + arricchimento Apollo + invito Playbook), controllo risposte + follow-up giornaliero, gestione bounce, harvest settimanale Harmonic (**bloccato**: la chiave Harmonic non ha i permessi per `/companies` — serve il manager).

## Credenziali create su n8n (solo riferimento ID, i valori restano nel `.env`)

| Nome | Tipo | ID |
|---|---|---|
| Apollo Header Auth | httpHeaderAuth | `tsTg37ICmuv8HBpC` |
| Harmonic Header Auth | httpHeaderAuth | `YsZim9PzaFellWqP` (bloccata sui permessi) |
| Anthropic Custom Auth | httpCustomAuth | `5Nk0gwk1gXo8HRaS` |
| Gmail SMTP | smtp | `TLNLg8fonUK1hOD8` |
| Gmail IMAP | imap | `nNSAuErjynXHLMa8` |
| Airtable Token | airtableTokenApi | `QbFL5zfsc0H2Pcs5` (non più usata) |
| Google Sheets (Iacopo Bon) | googleSheetsOAuth2Api | `gRSPd8YEw5iadWsy` |
| Gmail (Iacopo Bon) | gmailOAuth2 | `3FF4ROo5Rl75aufp` |
