#!/bin/bash
# Thin wrapper — delega al dispatcher Python (schoolai.cli.dispatcher)
PROJ="/home/edwin8600/gestiondocente"
exec uv run --project "$PROJ" gestion "$@"
