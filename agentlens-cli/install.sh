#!/usr/bin/env bash
set -e

echo "==================================================="
echo "  Installing AgentLens CLI (Pure Standalone)"
echo "==================================================="

python3 -m pip install -e .

echo ""
echo "==================================================="
echo "  Verifying Installation..."
echo "==================================================="
agentlens --help

echo ""
echo "==================================================="
echo "  SUCCESS! AgentLens CLI is installed and ready."
echo "==================================================="
