#!/usr/bin/env python3
"""Minimal zero-dependency Python client for querying laya-serve on loopback."""

import http.client
import json
import os
import sys

HOST = os.environ.get("LAYA_HOST", "127.0.0.1")
PORT = int(os.environ.get("LAYA_PORT", "5292"))


def query_systemone(state: str, questions: dict, model: str | None = None) -> dict:
    conn = http.client.HTTPConnection(HOST, PORT, timeout=5.0)
    body: dict = {"state": state, "questions": questions}
    if model:
        body["model"] = model

    payload = json.dumps(body)
    headers = {"Content-Type": "application/json"}
    conn.request("POST", "/v1/systemone", body=payload, headers=headers)

    response = conn.getresponse()
    raw = response.read().decode("utf-8")
    conn.close()

    if response.status != 200:
        raise RuntimeError(f"HTTP {response.status}: {raw}")

    return json.loads(raw)


def main():
    print(f"[*] Querying laya-serve at http://{HOST}:{PORT}/v1/systemone ...")

    # Example: checking tool execution safety
    state = "rm -rf /tmp/scratch_dir"
    questions = {
        "is_safe": {
            "type": "noul",
            "instructions": "Is this command safe and non-destructive?",
        },
        "action_type": {
            "type": "choice",
            "criteria": ["cleanup", "build", "exfiltration", "unknown"],
            "instructions": "What category of action does this represent?",
        },
    }

    try:
        result = query_systemone(state, questions)
        print("[+] Response received:")
        print(json.dumps(result, indent=2))

        answers = result.get("answers", {})
        safe_prob = answers.get("is_safe", {}).get("noul")
        category = answers.get("action_type", {}).get("choice")

        print("\n--- Summary ---")
        print(f"State:       {state}")
        print(f"Safety prob: {safe_prob}")
        print(f"Category:    {category}")
        print(f"Routing:     {result.get('routing', {}).get('model')}")

    except Exception as err:
        print(f"[-] Error: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
