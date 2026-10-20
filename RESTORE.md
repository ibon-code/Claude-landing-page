# Ripristino su un nuovo Mac

Guida per rimettere in piedi questo progetto (landing page, design system, pipeline di sourcing, memoria di Claude) su un computer nuovo. Non contiene segreti: chiavi e dati personali sono solo nell'archivio cifrato.

## Cosa sta dove

| Cosa | Dove | Azione sul nuovo Mac |
|---|---|---|
| Codice, script, backup workflow n8n, skill `email-one-time` | Questo repo GitHub | `git clone` |
| Chiavi API (`.env`), design system, sorgenti landing, dati startup, memoria di Claude | `Backup-cambio-Mac-2026-10.dmg` (cifrato) su Google Drive aziendale | Scaricare e copiare (passo 3) |
| Workflow n8n, Google Sheet, Gmail, GitHub Pages | Cloud | Niente: girano da soli |

## Passi

1. **Installa gli strumenti**: Claude Code, l'estensione Claude in Chrome e Python 3 (`xcode-select --install`).

2. **Clona il repo nello STESSO percorso** (la memoria di Claude è legata al percorso):
   ```bash
   cd ~/Desktop
   git clone https://github.com/ibon-code/Claude-landing-page.git "Claude code experiment"
   ```

3. **Apri l'archivio cifrato**: scarica il `.dmg` da Google Drive, fai doppio clic e inserisci la password, che è nel tuo password manager. Poi:
   ```bash
   B="/Volumes/Backup cambio Mac 2026-10"
   R=~/Desktop/"Claude code experiment"
   rsync -a "$B/repo-privato/" "$R/"            # .env, design system, landing, cartelle dati, permessi Claude
   mkdir -p ~/.claude
   rsync -a "$B/claude-home/.claude/" ~/.claude/  # memoria, trascrizioni, piani, comandi, impostazioni
   cp -n "$B/claude-home/.claude.json" ~/ 2>/dev/null || true
   rsync -a "$B/Documents/" ~/Documents/
   ```
   La vecchia n8n locale (`n8n-locale/`) resta solo nell'archivio come riferimento. **Non va ripristinata né avviata**: è spenta per sempre.

4. **Se il nome utente o il percorso sono diversi** (ad esempio non sei più `iacopobon`), la cartella della memoria va rinominata. Il nome si ottiene dal percorso completo del progetto, sostituendo `/` e gli spazi con `-`:
   ```bash
   ls ~/.claude/projects/        # vecchio nome: -Users-iacopobon-Desktop-Claude-code-experiment
   mv ~/.claude/projects/-Users-iacopobon-Desktop-Claude-code-experiment \
      ~/.claude/projects/-Users-<nuovoutente>-Desktop-Claude-code-experiment
   ```

5. **Rifai il login a GitHub, una volta sola**: al primo `git push` macOS chiede le credenziali. Usa un token GitHub classic con scope `repo`, che verrà salvato nel Portachiavi.

6. **Controlli finali**:
   - `cd ~/Desktop/"Claude code experiment" && git status`: deve risultare pulito.
   - `ls -a` deve mostrare `.env` e `Plug and Play Design System (1)/`.
   - `open index.html`: la landing page si apre.
   - Apri Claude Code nella cartella e chiedi "cosa sai della pipeline n8n?". Deve rispondere con gli ID e lo stato dei workflow (segno che la memoria è stata caricata).

## Non dimenticare
- Il `.dmg` e la cartella di appoggio contengono chiavi in chiaro: **non metterli mai su GitHub**, perché questo repo è pubblico.
- La password dell'app Gmail nel `.env` scade a ogni rotazione delle password aziendali. Se va rinnovata, leggi prima la memoria `credential_fix_triggers_automations`.
