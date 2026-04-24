#!/bin/bash
cd /home/edwin8600/schoolai
pkill -f "schoolai-bot$" 2>/dev/null || true
sleep 2
uv run watchfiles --filter python --target-type command "uv run schoolai-bot" src/schoolai/
