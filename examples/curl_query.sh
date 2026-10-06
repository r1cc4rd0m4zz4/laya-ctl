#!/usr/bin/env bash
# Minimal curl query to laya-serve (TypeSafe Jev System 1)

HOST="${LAYA_HOST:-127.0.0.1}"
PORT="${LAYA_PORT:-5292}"

echo "[*] Sending System 1 query to http://${HOST}:${PORT}/v1/systemone ..."

curl -s -X POST "http://${HOST}:${PORT}/v1/systemone" \
  -H "Content-Type: application/json" \
  -d '{
    "state": "git push --force origin main",
    "questions": {
      "is_safe_operation": {
        "type": "noul",
        "instructions": "Is this git operation safe without team coordination?"
      },
      "risk_level": {
        "type": "choice",
        "criteria": ["low", "medium", "high", "critical"],
        "instructions": "What is the operational risk level?"
      }
    }
  }' | (command -v jq >/dev/null 2>&1 && jq . || cat)
