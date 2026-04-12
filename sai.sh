#!/bin/bash
# SchoolAI service manager
# Uso: ./sai.sh [start|stop|restart|status|logs [servicio]|backup]

SERVICES="schoolai-api schoolai-bot schoolai-bot-jornada schoolai-bot-agente"
CMD="${1:-status}"
SVC="${2:-}"

case "$CMD" in
  start)
    echo "Iniciando SchoolAI..."
    systemctl --user daemon-reload
    for s in $SERVICES; do
      systemctl --user start "$s"
      echo "  ✓ $s"
    done
    ;;
  stop)
    echo "Deteniendo SchoolAI..."
    for s in $SERVICES; do
      systemctl --user stop "$s" 2>/dev/null
      echo "  ✗ $s"
    done
    ;;
  restart)
    "$0" stop
    sleep 2
    "$0" start
    ;;
  enable)
    echo "Habilitando inicio automático..."
    systemctl --user daemon-reload
    for s in $SERVICES; do
      systemctl --user enable "$s"
    done
    loginctl enable-linger "$USER"
    echo "Listo — los servicios arrancarán solos al iniciar WSL."
    ;;
  disable)
    for s in $SERVICES; do
      systemctl --user disable "$s" 2>/dev/null
    done
    echo "Inicio automático deshabilitado."
    ;;
  status)
    echo "=== SchoolAI Status ==="
    for s in $SERVICES; do
      STATUS=$(systemctl --user is-active "$s" 2>/dev/null)
      if [ "$STATUS" = "active" ]; then
        echo "  🟢 $s"
      else
        echo "  🔴 $s ($STATUS)"
      fi
    done
    ;;
  logs)
    TARGET="${SVC:-api}"
    case "$TARGET" in
      api)     tail -f /tmp/schoolai-api.log ;;
      bot)     tail -f /tmp/schoolai-bot.log ;;
      jornada) tail -f /tmp/schoolai-bot-jornada.log ;;
      agente)  tail -f /tmp/schoolai-bot-agente.log ;;
      *)       echo "Uso: ./sai.sh logs [api|bot|jornada|agente]" ;;
    esac
    ;;
  backup)
    echo "Ejecutando backup manual..."
    systemctl --user start schoolai-backup.service
    echo "Resultado en /tmp/schoolai-backup.log"
    tail -2 /tmp/schoolai-backup.log
    ;;
  *)
    echo "Uso: ./sai.sh [start|stop|restart|enable|disable|status|backup|logs [api|bot|jornada|agente]]"
    ;;
esac
