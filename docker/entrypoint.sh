#!/bin/sh
set -e

# AgentLens Production Container Entrypoint
echo "[agentlens] Starting service with command: $@"

# Execute requested application process
exec "$@"
