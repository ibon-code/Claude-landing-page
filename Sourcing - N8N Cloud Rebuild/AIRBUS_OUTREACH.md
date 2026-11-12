# Airbus DS outreach (invio una tantum, 30 startup)

Email a 30 startup per la challenge Data Management di Airbus Defence and Space: una email per startup (tutti i contatti in To, CC dal foglio, PDF allegato), un solo follow-up nello stesso thread dopo 7 giorni se nessuno risponde.

## Dove sta cosa

| Cosa | Dove |
|---|---|
| Foglio (fonte dei testi e dello stato) | Google Sheet "Airbus_DS_Data_Mgmt_outreach_30_startups" (id `1IR6rO48OiW0dnJNBpMDbxl85QGGdbuFoqewyCWYinzw`), cartella Drive "Claude automation". L'xlsx originale resta lì ma non viene usato. |
| PDF allegato | Drive, stessa cartella, id `1Se0tZT4Bc7BfVnrLXjeqNuFoJr7Frth9`; parte col nome della colonna Attachment |
| Workflow | `Airbus outreach \| 1. Invio iniziale` (`9LzbzoQlA70SRdpX`), `Airbus outreach \| 2. Risposte e follow-up` (`ew3T35qp6U4qWkij`), `Airbus outreach \| Errori` (`x9NFxOpa4CT3unBl`) |
| Generatore | `scripts/build_airbus_outreach.py` |
| Credenziali n8n (solo per ID) | Google Sheets, Gmail, Google Drive (Iacopo Bon) |

## Come funziona

- I testi si cambiano nel tab **Template** (B2-B7): il tab Emails li riprende con formule, per tutte le 30 righe. Mai modificare le colonne con formule nel tab Emails.
- WF1 (manuale) manda solo le righe con Status = Ready e Sent at vuoto, poi scrive Status, Sent at, Thread ID, Message ID, Follow-up due (+7 giorni, sabato/domenica → lunedì). 60-120 s tra un'email e l'altra. Prima di ogni invio controlla Gmail Inviati: se la startup ha già ricevuto l'email non la rimanda.
- WF2 (lun-ven 9:30 ora di Madrid): risposta vera → Replied (mai più email); bounce e risposte automatiche → colonna Automation notes; nessuna risposta e data passata → un solo follow-up nello stesso thread, Status = Follow-up sent.
- Prima di ogni invio WF1 rilegge la riga dal foglio: se non è più Ready (Hold) o è cambiata, non invia. Se un invio fallisce, WF1 si ferma subito (Stop Run) e arriva la mail di errore.
- Errori di invio → Status = `Error: ...`, mai ritentati da soli. WF3 manda un'email con l'errore.

## Test (11-11-2026, tutti superati)

1. Dati: 30 righe Ready, 67 destinatari, nessun segnaposto, indirizzo duplicato o nome di un'altra startup.
2. Invio test (SPREAD AI, eccenca, Agon → solo a me): PDF col nome giusto, grassetti, nessuna attribuzione n8n.
3. Risposte: le 3 email a cui ho risposto → Replied, nessun follow-up. Follow-up (Squirro, data forzata a ieri): arrivato nello stesso thread, senza allegato, col link Calendly.
4. Idempotenza: rilanciando WF1 non parte nulla.

## Go live (solo dopo "OK, vai")

1. `python3 scripts/build_airbus_outreach.py <dir> --live --deploy`
2. Lanci WF1 a mano (Execute workflow): circa 45 minuti per 30 email, riepilogo finale via email.
3. Pubblichi/attivi WF2.

## Come fermare tutto

- Disattiva WF2 (niente più follow-up), oppure metti `Hold` nello Status di una riga.
- Per rimandare una riga in errore: controlla Gmail Inviati, poi rimetti Status = Ready (WF1) o Sent (WF2).
