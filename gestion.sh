#!/bin/bash
# GestionDocente — dispatcher de comandos
PROJ="/home/edwin8600/gestiondocente"
CMD="${1:-}"
SUB="${2:-}"

menu() {
  echo ""
  echo "  GestionDocente — SchoolAI"
  echo "  ────────────────────────────────────────────"
  echo "  gestion start                Arrancar todo (API + Gateway + Bots)"
  echo "  gestion stop                 Detener todo"
  echo "  gestion status               Estado de servicios"
  echo ""
  echo "  gestion api                  FastAPI REST       (puerto 8000)"
  echo "  gestion gateway              Gateway v2         (puerto 8001)"
  echo "  gestion cli                  CLI interactiva"
  echo ""
  echo "  gestion logs [api|bot|jornada|agente]"
  echo "  gestion debug [api|gateway|bot|jornada]"
  echo ""
}

case "$CMD" in
  start)
    echo "Arrancando GestionDocente..."
    systemctl --user daemon-reload
    for s in schoolai-api schoolai-bot schoolai-bot-jornada schoolai-bot-agente; do
      systemctl --user start "$s" 2>/dev/null \
        && echo "  ✓ $s" \
        || echo "  ✗ $s"
    done
    if systemctl --user start schoolai-gateway 2>/dev/null; then
      echo "  ✓ schoolai-gateway"
    else
      echo "  ! schoolai-gateway sin unidad systemd — lanza con: gestion gateway"
    fi
    echo ""
    "$0" status
    ;;
  stop)
    echo "Deteniendo GestionDocente..."
    for s in schoolai-api schoolai-bot schoolai-bot-jornada schoolai-bot-agente schoolai-gateway; do
      systemctl --user stop "$s" 2>/dev/null \
        && echo "  ✗ $s" \
        || true
    done
    ;;
  status)
    echo "=== GestionDocente Status ==="
    for s in schoolai-api schoolai-bot schoolai-bot-jornada schoolai-bot-agente schoolai-gateway; do
      STATUS=$(systemctl --user is-active "$s" 2>/dev/null)
      if [ "$STATUS" = "active" ]; then
        echo "  🟢 $s"
      else
        echo "  🔴 $s ($STATUS)"
      fi
    done
    echo ""
    ;;
  api)
    cd "$PROJ" && uv run schoolaiapi
    ;;
  gateway)
    cd "$PROJ" && uv run schoolai-gateway
    ;;
  cli)
    cd "$PROJ" && uv run schoolai-cli
    ;;
  logs)
    case "$SUB" in
      api)     tail -f /tmp/schoolai-api.log ;;
      bot)     tail -f /tmp/schoolai-bot.log ;;
      jornada) tail -f /tmp/schoolai-bot-jornada.log ;;
      agente)  tail -f /tmp/schoolai-bot-agente.log ;;
      gateway) tail -f /tmp/schoolai-gateway.log ;;
      *)       echo "Uso: gestion logs [api|bot|jornada|agente|gateway]" ;;
    esac
    ;;
  debug)
    if [ -z "$SUB" ]; then
      echo ""
      echo "  ¿Qué quieres depurar?"
      echo "  1) api"
      echo "  2) gateway"
      echo "  3) bot"
      echo "  4) jornada"
      echo ""
      read -rp "  Opción [1-4]: " OPT
      case "$OPT" in
        1) SUB="api" ;;
        2) SUB="gateway" ;;
        3) SUB="bot" ;;
        4) SUB="jornada" ;;
        *) echo "Opción inválida."; exit 1 ;;
      esac
    fi
    case "$SUB" in
      api)     cd "$PROJ" && uv run python -m pudb src/schoolai/api/runner.py ;;
      gateway) cd "$PROJ" && uv run python -m pudb src/schoolai/gateway/runner.py ;;
      bot)     cd "$PROJ" && uv run python -m pudb src/schoolai/bot/main.py ;;
      jornada) cd "$PROJ" && uv run python -m pudb src/schoolai/bot/main_dev.py ;;
      *)       echo "Opciones: api | gateway | bot | jornada" ;;
    esac
    ;;
  *)
    menu
    ;;
esac
