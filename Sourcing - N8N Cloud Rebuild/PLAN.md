> Piano tecnico originale della ricostruzione. Era in `~/.claude/plans/ok-allora-non-voglio-clever-horizon.md`, cancellato dalla pulizia automatica di Claude Code il 2026-10-19 e ripristinato qui il 2026-10-20. È il documento storico: lo stato attuale è nel `README.md` di questa cartella.

# Piano: ricostruzione da zero della pipeline sourcing+outreach su n8n cloud aziendale

## Contesto
La pipeline attuale (sourcing startup B2B + outreach) gira interamente in locale sul Mac di Iacopo: n8n locale (LaunchAgent) che lancia script Python via nodi Execute Command, contro un file Excel locale (bug noto con Apple Numbers). L'azienda ha reso disponibile un piano n8n cloud gratuito già collegato ai tool interni (`https://agentflow.pnptc.com`, Salesforce/CRM incluso). Obiettivo: ricostruire la stessa logica **da zero** su questa nuova istanza, con un nuovo Google Sheet al posto dell'Excel, **senza toccare/cancellare la pipeline vecchia per ora** (verrà spenta solo a fine progetto, a nuova pipeline confermata funzionante). Aggiunta richiesta: nuova fonte di sourcing **Harmonic**, usabile solo 1 volta a settimana per limiti di crediti.

Decisione architetturale chiave (confermata dall'utente): dato che il server n8n cloud non ha accesso al Mac locale, **niente Execute Command / niente script Python** — si ricostruisce **nativo in n8n** (nodi Google Sheets, Gmail via OAuth2, HTTP Request per Apollo/Harmonic/Anthropic).

## Stato attuale verificato
- Chiave API n8n cloud verificata funzionante (dopo correzione di un carattere in eccesso nel copia-incolla) — salvata in `.env` come `N8N_CLOUD_API_KEY` / `N8N_CLOUD_BASE_URL`.
- Inventario completo della pipeline attuale raccolto (script, cron, credenziali, schema Excel, subject email, LaunchAgent) — vedi dettagli sotto.
- **Nota di sicurezza (non bloccante, promemoria):** nella cronologia git locale (commit `fe06034`, non ancora pushato su `origin/main`) è presente una vecchia chiave Apollo hardcoded. Da ruotare comunque prima del prossimo `git push` su questo repo. Non impatta la nuova build (che userà una credenziale Apollo nuova su n8n). *(Risolto il 2026-09-29: cronologia ripulita prima del push.)*

## Architettura: 7 workflow n8n separati (non uno solo)
Ogni workflow copre un "concern" della pipeline, collegati dove serve via Execute Workflow. Motivazione: leggibilità, log separati, possibilità di testare/attivare ogni pezzo in isolamento (utile per il build incrementale richiesto).

| # | Workflow | Trigger | Sostituisce |
|---|---|---|---|
| 1 | Sourcing - Daily Harvest | `0 12 * * *` | BetaList + Apollo + tech.eu/Wamda |
| 2 | Sourcing - Harmonic Weekly Harvest | settimanale (default `0 6 * * 1`, da confermare) | Nuovo, additivo, gated |
| 3 | Sourcing - Weekly AI Scoring | `0 12 * * 1` | select_leads.py |
| 4 | Pipeline - 15min Cycle | `*/15 * * * *` | move_to_pipeline.py → enrich_apollo_pipeline.py → send_outreach.py → send_playbook_invite.py |
| 5 | Pipeline - Daily Replies & Follow-ups | `0 16 * * *` | check_replies.py → send_followup.py → send_playbook_followup.py |
| 6 | Pipeline - Bounce Handling | nuovo trigger (cadenza da confermare) | Nuovo — mancava anche nel setup attuale |
| 7 | Util - Claude Messages API | Execute Workflow Trigger (sub-workflow condiviso) | Chiamata Anthropic duplicata nei 3 script originali |

## Nuovo Google Sheet (da creare per primo)
Due tab:
- **`Sourcing`**: `Organization Name | Organization Name URL | Headquarters Location | Description | Website | Move to Pipeline? | Source | AI Moat Score | AI Notes` (+ eventuale `Funding USD (parsed)`, vedi decisioni sotto)
- **`Pipeline`**: `Startup name | Website | Salesforce | Job title | Email | Contacted | Meeting | Playbook | Full Name | Date Contacted | Followed Up | Playbook Invite Sent | Date Playbook Invite Sent | Playbook Followup Sent | Bounced Emails | Outreach Count | Playbook Message ID | Message ID | Date Followed Up | Final Followup Sent`

Le colonne booleane diventano vere checkbox di Google Sheets (non testo "TRUE"/"FALSE" come nel vecchio Excel). Niente più spazi finali nei nomi colonna (bug del vecchio file, corretto qui).

## Credenziali da creare su n8n (prima di costruire i workflow)
- **Google OAuth2** (account `i.bon@pnptc.com`) — per Sheets + Gmail. Da verificare se n8n cloud richiede una credenziale unica o due separate (Sheets/Gmail).
- **Apollo** — HTTP Header Auth, header `x-api-key`. Chiave da rigenerare/ruotare (vedi nota sicurezza).
- **Harmonic** — HTTP Header Auth, dettagli bloccati in attesa di documentazione API (vedi Aperti).
- **Anthropic** — riusa il valore di `ANTHROPIC_API_KEY` già presente in `.env` locale. Servono gli header `x-api-key`, `anthropic-version: 2023-06-01`, `content-type: application/json`.

## Decisioni prese per la ricostruzione (deviazioni deliberate, non replicazione ingenua)
1. **Dedup permanente**: il vecchio sistema usava una cache JSON locale mai svuotata. Nel nuovo sistema, l'harvest dedupe controllando sia la tab `Sourcing` sia la colonna `Website` di `Pipeline`; le righe scartate dallo scoring restano in `Sourcing` con `AI Moat Score` valorizzato (anche a 0) così non vengono mai riproposte.
2. **Aggiornamento in-place allo scoring**: l'harvest fa append, lo scoring settimanale aggiorna le stesse righe (match by row number), non ne crea di nuove.
3. **Threading email nativo Gmail**: invece di ricostruire header MIME `Message-ID`/`In-Reply-To` a mano, si usa l'`id`/`threadId` nativo del nodo Gmail e l'operazione "Reply".
4. **Tracking "già processato" via etichette Gmail**: sostituisce le cache JSON locali (`seen_replies.json`, `seen_bounces.json`) con label Gmail dedicate (`Automation/Processed-Reply`, `Automation/Processed-Bounce`).
5. **Enrichment Apollo**: si chiama `people/match` per tutti i candidati restituiti (pattern nativo n8n, più semplice da costruire) invece dello short-circuit sul primo match valido dello script originale — leggero aumento di chiamate Apollo, da tenere presente per i costi.
6. **Colonna funding**: aggiunta `Funding USD (parsed)` a `Sourcing` per replicare il filtro di scoring a costo zero (Claude non viene chiamato se il funding supera il tetto).

## Logica che richiede nodi Code (JavaScript) vs nodi standard
Richiedono Code node: parsing Atom/RSS, regex importo funding + conversione valuta, ranking candidati Apollo per job title, costruzione prompt Claude + parsing JSON, template HTML email con firma condivisa, calcolo date a 7 giorni per i follow-up in due fasi, regex di rilevamento bounce, scraping title/meta homepage, normalizzazione dominio per dedup.
Bastano nodi standard (Filter/IF/Set/Merge): controlli cap `Outreach Count`, flag `Contacted`/`Salesforce`/`Playbook`/`Meeting`, filtro checkbox `Move to Pipeline?`.

## Ordine di build consigliato
1. Google Sheet (entrambe le tab, checkbox formattate)
2. Credenziali (Google, Apollo dopo rotazione, Anthropic; shell per Harmonic)
3. Workflow 1 (Harvest) — testare i 3 rami singolarmente
4. Workflow 7 (Util Claude) — testabile in isolamento
5. Workflow 3 (Scoring) — qui si convalida il pattern update-by-row-number
6. Workflow 4, step "Move to Pipeline" da solo
7. Workflow 4, step "Enrich" — testare con poche righe reali prima di consumare crediti Apollo veri
8. Workflow 4, step "Send outreach" — ispezionare l'email renderizzata nel Code node prima di collegare l'invio Gmail reale; poi Playbook invite allo stesso modo
9. Workflow 5 (Replies & follow-up) — prima la classificazione (sola lettura, sicura), poi l'invio follow-up (più rischioso, verificare bene il calcolo giorni)
10. Workflow 6 (Bounce handling) — per ultimo tra i pipeline-workflow, perché modifica righe usate dagli altri
11. Workflow 2 (Harmonic) — deliberatamente ultimo, è additivo e bloccato in attesa di info API

## Aperti — richiedono decisione/informazione dell'utente prima di costruire quella parte
1. **API Harmonic** (blocco vero) — serve: URL base, metodo, schema di autenticazione/header, forma della richiesta e un esempio di risposta.
2. Modello credenziali Google su questa istanza n8n cloud (unica o separata Sheets/Gmail) — verifica rapida in UI, non blocca il resto.
3. Cadenza controllo bounce (default proposto: dentro il workflow delle 16:00 insieme alle reply, oppure ogni ora — dipende da quanto velocemente vuoi che un contatto rimbalzato venga sostituito).
4. Timing esatto di Harmonic (default proposto: lunedì 06:00, prima dello scoring delle 12:00).

## Aggiornamento architetturale (durante la build)
- **Google Sheets → Airtable**: l'organizzazione ha disabilitato Google Cloud Platform per l'account aziendale, quindi Google Sheets/Gmail OAuth2 sono irraggiungibili. Sostituito Google Sheets con **Airtable** (stesso concetto di tabella online, autenticazione con Personal Access Token, nessuna dipendenza da Google Cloud).
- **Gmail OAuth2 → SMTP/IMAP**: su indicazione dell'IT, l'email si collega con lo stesso metodo già in uso (utente + password per app di Gmail), non con OAuth2. Questo significa: niente threading nativo Gmail (id/threadId) né label Gmail per il tracking "già processato" — si torna a ricostruire header `Message-ID`/`In-Reply-To`/`References` a mano (come nello script originale) e si usa lo static data di n8n (`$getWorkflowStaticData('global')`) al posto delle cache JSON locali per tracciare cosa è già stato processato.
- Con questo pivot, **nessuna parte della pipeline dipende più da Google Cloud** — si può costruire tutto senza aspettare l'IT.
- *(2026-09-24: le credenziali Google OAuth2 sono poi diventate disponibili sull'istanza; i dati sono tornati su Google Sheets e l'invio usa il nodo Gmail nativo. Vedi `README.md`.)*

### Riferimenti build (id creati)
- Base Airtable: `appKs6UmJX4w6GEp0` ("Sourcing - N8N") — tabella `Sourcing` id `tblFzRunGJHbNHoyf`, tabella `Pipeline` id `tbllX1ySWqUyTTjzk`. (Rimane anche "Table 1" di default, cancellabile solo a mano dalla UI Airtable, l'API non supporta la cancellazione tabelle.)
- Credenziali n8n: Apollo Header Auth (`tsTg37ICmuv8HBpC`), Harmonic Header Auth (`YsZim9PzaFellWqP`, bloccata su permessi lato Harmonic), Anthropic Custom Auth (`5Nk0gwk1gXo8HRaS`), Gmail SMTP (`TLNLg8fonUK1hOD8`), Gmail IMAP (`nNSAuErjynXHLMa8`), Airtable Token (`QbFL5zfsc0H2Pcs5`).
- Workflow 7 "Util - Claude Messages API" costruito e testato con successo, id `V5wGQ55LdYLhSCmf`.

## Verifica end-to-end
Per ogni workflow, prima di attivarlo: eseguirlo manualmente da n8n ("Test workflow") con dati reali/di prova, controllare l'output di ogni nodo Code, e solo dopo attivare il trigger schedulato. Per gli step che inviano email, ispezionare il corpo renderizzato prima di collegare il nodo Gmail Send/Reply. La pipeline vecchia resta attiva e intoccata come riferimento/fallback fino a conferma completa della nuova.
