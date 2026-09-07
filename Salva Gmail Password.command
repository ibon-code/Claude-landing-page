#!/bin/zsh
cd "$(dirname "$0")"

echo "Incolla qui l'App Password Gmail (16 caratteri, senza spazi) e premi Invio:"
read -s GMAIL_APP_PASSWORD
echo

# strip whitespace defensively
GMAIL_APP_PASSWORD="${GMAIL_APP_PASSWORD//[[:space:]]/}"

if [ ${#GMAIL_APP_PASSWORD} -ne 16 ]; then
    echo "ATTENZIONE: la password ha ${#GMAIL_APP_PASSWORD} caratteri, dovrebbe averne 16."
    echo "Probabile paste doppio o errore di copia — riprova (Ctrl+C per uscire e ricominciare)."
    echo
fi

# remove any previous entries for these keys, then append fresh ones
if [ -f .env ]; then
    grep -v "^GMAIL_APP_PASSWORD=" .env | grep -v "^GMAIL_USER=" > .env.tmp
    mv .env.tmp .env
fi
echo "GMAIL_APP_PASSWORD=$GMAIL_APP_PASSWORD" >> .env
echo "GMAIL_USER=i.bon@pnptc.com" >> .env
chmod 600 .env

echo "Salvata correttamente in .env."
echo
echo "Premi Invio per chiudere questa finestra."
read
