#!/bin/bash
cd /home/edwin8600/schoolai
pkill -f "schoolai-bot-agente" 2>/dev/null || true
sleep 2
uv run watchfiles --filter python --target-type command "uv run schoolai-bot-agente" src/schoolai/
