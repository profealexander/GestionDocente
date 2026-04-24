# Guía de desarrollo — SchoolAI

## Correr los servicios en WSL

Los servicios están configurados como unidades systemd de usuario. El script `sai.sh` (en la raíz del proyecto) los gestiona.

```bash
cd ~/schoolai
./sai.sh start    # arranca API + 3 bots en background
./sai.sh status   # verifica que estén verdes
./sai.sh stop     # detiene todos
./sai.sh restart  # detiene y vuelve a arrancar
```

### Logs en tiempo real

```bash
./sai.sh logs api      # FastAPI
./sai.sh logs bot      # Bot Modo Libre
./sai.sh logs jornada  # Bot Modo Jornada
./sai.sh logs agente   # Bot Agente GLM
```

Los archivos de log están en `/tmp/schoolai-*.log`.

### Inicio automático al abrir WSL

```bash
./sai.sh enable   # activa arranque automático
./sai.sh disable  # lo desactiva
```

---

## Diferencia entre sai.sh y los scripts de dev

| Script | Modo | Hot-reload | Uso |
|---|---|---|---|
| `./sai.sh start` | Producción estable | No | Dejar corriendo en background |
| `./start.sh` | Desarrollo | Sí (watchfiles) | Bot Libre + API con recarga automática |
| `./dev-bot.sh` | Desarrollo | Sí | Solo Bot Libre |
| `./dev-bot-jornada.sh` | Desarrollo | Sí | Solo Bot Jornada |
| `./dev-bot-agente.sh` | Desarrollo | Sí | Solo Bot Agente |

Para desarrollo activo usa los scripts `dev-*.sh`. Para dejarlo corriendo de fondo usa `sai.sh`.

---

## PostgreSQL (Docker)

La base de datos corre como contenedor Docker independiente:

```bash
docker ps                        # verificar que schoolai-db esté activo
docker compose up -d             # levantarlo si está caído
docker compose down              # detenerlo
```

El contenedor tiene volumen nombrado (`schoolai_db`) — los datos persisten aunque se detenga.

---

## Migraciones Alembic

```bash
uv run alembic upgrade head      # aplicar migraciones pendientes
uv run alembic revision --autogenerate -m "descripcion"  # nueva migración
```
