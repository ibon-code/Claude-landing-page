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

## Layout del tab Pipeline (dal 2026-11-02)

A Startup name · B Website · **C Playbook** (tendina YES rosso / NO, la scrive Apollo Enrich) · **D Contact** (ex "Salesforce": la spunti tu, TRUE = da contattare) · E Job title · F Email · G Company LinkedIn · H Contacted · I Meeting · J Full Name · K Date Contacted · L Followed Up · M Apollo Enrich · N Playbook Check · O Playbook URL. P Outreach Status · Q Outreach Count · R Message ID · S Thread ID (scritte dall'Outreach) · **T Playbook Invite** (YES/NO) · U Meeting contact · V Meeting contact name · **W Team Added** (YES/NO, la metti tu dopo il + nel Team) · X Playbook Invite Status · Y Playbook Profile URL · Z Date Playbook Invite · AA Playbook Invite Message ID. Il Follow-up aggiunge in fondo `Follow-up Status`, `Date Followed Up`, `Follow-up Message ID`. Tendine fino alla riga 1000.

## Outreach, Follow-up e Playbook invite (dal 2026-11-02)

- **Outreach** (`Pipeline - Salesforce Outreach`, `scripts/build_outreach.py`): parte solo con Contact = TRUE e `Playbook Check` = "Not in Playbook"; blocco duro se Gmail Inviati ha già una qualsiasi email "Plug and Play <> …" a quell'indirizzo; una sola azienda una volta (dominio email e sito).
- **Follow-up** (`Pipeline - Follow-up` id `bGP5LlHKC9miEcps`, `scripts/build_followup.py`): uno solo, 7 giorni dopo, nello stesso thread, solo se il founder non ha dato segni di vita (nessuna risposta, nemmeno fuori dal thread, nessuna email in Gmail dal primo invio che citi il suo indirizzo o il dominio dell'azienda, nessuna prenotazione Calendly con il nome della startup), nessun bounce, e Gmail Inviati ha esattamente l'email originale.
- **Playbook Invite** (`Pipeline - Playbook Invite` id `HhIgZ9AEW5r0XxPB`, `scripts/build_playbook_invite.py`, semi-automatico): con `Playbook Invite` = YES n8n crea il profilo su Playbook (testo scritto da Claude dalla homepage, paese/settore dalle liste di Playbook, logo da logo.dev) e ti manda il link del Team. Tu premi + (Member Profile: nome, email, CEO) e metti `Team Added` = YES: n8n manda la nostra email di invito (blocco Gmail: mai due inviti alla stessa persona, max 20/giorno). Si ferma con 'Needs review' se la startup e' gia' su Playbook, se l'email e' personale o se la homepage non basta. Promemoria giornaliero per i profili fermi. Quando Playbook aggiunge il tool MCP richiesto (add_startup_team_member) anche il + diventa automatico.
- Entrambi: `--live` esplicito per inviare, `--test-email ADDR` per provare su un solo indirizzo; 20/giorno ciascuno, 3 per giro, lun-ven 9-18.
- **Playbook invite**: NON su n8n (la login MCP di Playbook non permette di aggiungere team member: "Authentication credentials were not provided"). Lo fa Claude in Chrome su richiesta con la skill `.claude/skills/playbook-invite` (profilo → + Team con nome/email → Playbook manda l'invito → nostra email con `send_invite_email.py` → log in T–Z). I workflow leggono/scrivono per nome di colonna e `row_number`, quindi spostare colonne non li rompe; rinominarle sì (va aggiornato il generatore).

## Stato attuale (aggiornato 2026-09-29)

**ATTIVI dal 2026-09-29**: Util Claude, Daily Harvest, Weekly AI Scoring, Move to Pipeline. **Ancora spento**: Salesforce Outreach (invia email vere).

| Workflow | ID | Stato |
|---|---|---|
| `Util - Claude Messages API` | `V5wGQ55LdYLhSCmf` | Testato |
| `Sourcing - Daily Harvest` (ogni giorno 12:00) | `1D0Q5agDQFAsVtFd` | Testato — BetaList, Apollo, tech.eu, Wamda. **Fix 19-10**: dal 5-10 (almeno) falliva ogni giorno perché BetaList partiva prima di `Sourcing - Get Existing` (ordine di esecuzione v1). Ora la catena è Trigger → Get Existing → `Existing Rows Loaded` → 4 fonti; retry x3 sui nodi Google Sheets. Script: `scripts/fix_harvest_order.py` |
| `Sourcing - Weekly AI Scoring` (lunedì 13:00) | `1YSwWkL3cCakhvxs` | Testato su 5 righe (scritte sulle righe giuste). Assegna un punteggio alle righe senza `AI Moat Score`: 1-5 se PASS, 0 se REJECT, motivazione in `AI Notes`. Scarta spazio/aerospace, droni consumer e prodotti solo militari anche via codice (`is_excluded_space_or_defence`); le startup droni/difesa DUAL-USE passano. Può essere lanciato da altri workflow (trigger "When Called by Another Workflow"). Generato da `scripts/build_scoring.py` (criteri in `scripts/criteria.txt`, identici a `select_leads.py`) |
| `Pipeline - Move to Pipeline` (ogni 15 min) | `PUsnpqT1jQFF5HXM` | Copia in `Pipeline` le righe con `Move to Pipeline?` = TRUE (solo nome + sito), salta quelle già presenti. Le righe restano in `Sourcing` (servono al dedup dell'harvest). Lo scoring spunta automaticamente `Move to Pipeline?` per ogni PASS |
| `Pipeline - Apollo Enrich` (ogni 15 min, :05/:20/:35/:50) | `YMvrsYODjU3s5Wm7` | Per le righe Pipeline senza email: trova il sito vero (ricerca aziendale Apollo, 1 credito, SOLO se Website è un link BetaList/tech.eu), sceglie la persona migliore (CEO > founder > MD > C-level > VP), rivela l'email (1 credito) anche se Apollo non segnala `has_email`; se Apollo non ha nulla, prende l'email pubblica dal sito (home o /contact, solo sul dominio della startup). Compila anche `Company LinkedIn` (colonna F): prima il link sul sito della startup, poi Apollo, solo se il nome corrisponde; altrimenti `Not found`. Il LinkedIn del CEO è stato tolto (dati poco affidabili). **Dal 23-10, prima di Apollo controlla Playbook** (MCP `search_startups`, credenziale `Playbook MCP - Iacopo Bon` id `TerVDTem462Rn6TK`): presente solo se un risultato ha esattamente lo stesso dominio → scrive `Playbook` = YES, scrive `Playbook Check`/`Playbook URL`, niente ricerca persone/email Apollo. Le righe già arricchite vengono controllate 20 per giro. Se Playbook non risponde per nessuna riga il giro si ferma e arriva l'email di Util - Error Alert (di solito: login scaduto → Reconnect sulla credenziale). Esito nella colonna `Apollo Enrich`; svuotarla per riprovare. Elabora TUTTE le righe in sospeso a ogni giro (richieste a gruppi di 5); se Apollo dà errore la riga non viene segnata e si riprova al giro dopo. Generato da `scripts/build_apollo_enrich.py` |
| `Pipeline - Salesforce Outreach` (ogni 15 min, lun-ven 9-18 ora di Roma) | `1TkdOwL5o1WWC6a8` | **Ricostruito con guardrail il 19-10, SPENTO e in DRY_RUN.** Max 20/giorno (contati da Gmail Inviati e dal foglio) e 3 per giro. Una mail alla volta: prima prenota la riga (`Outreach Status` = Sending), poi controlla in Gmail Inviati se esiste già la stessa mail (stesso destinatario e oggetto), poi invia. Se qualcosa fallisce dopo l'invio, la riga resta bloccata e non viene mai rimandata. Saluto deterministico (nome da `Full Name`, "{Startup} team" per info@/contact@). I partner devono essere nella lista PnP. Gli errori finiscono in `Outreach Status` (svuota la cella per riprovare). Firma n8n disattivata. In DRY_RUN non invia e non scrive nulla: manda solo un'anteprima a me. Generato da `scripts/build_outreach.py <dir> --deploy` (rifiuta di sovrascrivere se il workflow è attivo) |
| `Util - Error Alert` | `kWaALs0g5noG4ly4` | Error workflow dell'Outreach: mi manda un'email per ogni errore (max 1 all'ora per workflow) |

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
