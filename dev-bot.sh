#!/bin/bash
cd /home/edwin8600/schoolai
uv run watchfiles --filter python --target-type command "uv run schoolai-bot" src/schoolai/
