#!/bin/bash
# Mata todo al cerrar la ventana (X, Ctrl+C, etc.)
cleanup() {
    echo ""
    echo "Cerrando SchoolAI..."
    kill $API_PID $BOT_PID 2>/dev/null
    wait $API_PID $BOT_PID 2>/dev/null
    exit 0
}
trap cleanup EXIT INT TERM HUP

clear
echo "=========================================="
echo " SchoolAI Dev - Bot + API (hot-reload)"
echo " API:      http://localhost:8000/docs"
echo " Frontend: https://schoolai-web.pages.dev"
echo "=========================================="
echo ""

echo "Iniciando PostgreSQL..."
sudo service postgresql start > /dev/null 2>&1

echo "Matando bot anterior si existe..."
pkill -f schoolai-bot 2>/dev/null
sleep 1

echo "Liberando sesion Telegram..."
source /home/edwin8600/schoolai/.env
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates?offset=-1&timeout=1" > /dev/null
sleep 2

echo "Iniciando API con hot-reload..."
DEBUG=true uv run schoolai-api > /tmp/schoolai-api.log 2>&1 &
API_PID=$!

echo "Esperando que la API levante..."
sleep 4

echo ""
echo "=== Bot Telegram - hot-reload al cambiar src/ ==="
echo ""

# watchfiles reinicia el bot automáticamente al detectar cambios en src/
uv run watchfiles --filter python --target-type command "uv run schoolai-bot" src/schoolai/
