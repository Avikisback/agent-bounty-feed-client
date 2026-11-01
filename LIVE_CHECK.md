# Live check

Checked: 2026-11-01T15:09:08.454958+00:00.

Runtime: Python 3.10.0 on Windows. No packages installed.

All commands below completed with exit status 0 using the free MCP endpoint:

```sh
python client.py list --source direct --limit 1
python client.py list --min-usd 0 --limit 5
python client.py list --exclude-requires kyc,stake,bond,purchase,human_only --limit 5
python client.py list --source taskmarket --json
python client.py stats --json
python client.py get direct:abf-growth-guide-5usdc --json
python client.py new --since 2026-11-01T00:00:00Z --limit 5 --json
```

The JSON commands returned parseable JSON objects. The direct-source example listed the advertised 5-USDC bounty; no reward was claimed or paid during these checks.

The client completed initialization, sent the initialized notification and used the negotiated 2025-06-18 protocol. The live service returned JSON. SSE behavior was verified with the offline HTTP fixture, not claimed as an observed live SSE response.

All 12 offline tests passed. Commands are read-only feed queries and do not pay the x402 endpoint or submit to any bounty. The repository clone/publish steps still require a live public repository and are verified separately after publication.
