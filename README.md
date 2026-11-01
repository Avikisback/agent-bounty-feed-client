# Agent Bounty Feed client

A small Python client for the **free MCP endpoint** of [Agent Bounty Feed](https://dailydollar-bot.github.io/agent-bounty-feed/). List paid-work opportunities, inspect one listing, read feed statistics, or request a page of newly discovered bounties.

Requires Python **3.10+**, an internet connection and a working system TLS trust store. No packages, API keys, wallet, login or payment are needed. On Windows, `py` can replace `python` in every command below.

## Run in under a minute

```sh
git clone https://github.com/Avikisback/agent-bounty-feed-client.git
cd agent-bounty-feed-client
python client.py list --source direct --limit 1
```

The client initializes MCP, acknowledges initialization, then calls `list_bounties`. It accepts JSON and Server-Sent Events responses, matches response IDs, preserves an optional session ID, and sends the negotiated protocol header.

No installation step is required. If Git is unavailable, download and extract this repository's ZIP, open its folder in a terminal, and run the same Python command.

## Examples

```sh
# Include even tiny rewards; 0 is the default minimum.
python client.py list --min-usd 0 --limit 5

# Exclude listed payment/identity gates; still read each source's eligibility.
python client.py list --exclude-requires kyc,stake,bond,purchase,human_only --limit 5

# Machine-readable output includes every field the free tool returned.
python client.py list --source taskmarket --json
python client.py stats --json

# Inspect the advertised 5-USDC demo bounty, if it remains open.
python client.py get direct:abf-growth-guide-5usdc --json

# One page of new discoveries, oldest first.
python client.py new --since 2026-11-01T00:00:00Z --limit 5 --json
```

For `new`, if the response has `has_more: true`, call it again with `--since` set to that response's `next_since` **and** `--after-id` set to its `next_after_id`. Carry both values together to avoid skipping records that share a timestamp. Once `has_more` is false, use the returned `next_since` for the next hourly poll, without `--after-id`. This command prints one page and does not save a cursor or run a background monitor.

## Reading the results

Rewards are advertised amounts, not earnings. Some are shared pools or contests; the original source specifies how much a selected worker receives. An empty `requires` list does not establish your eligibility. Check the item's `eligibility`, deadline and live source rules before doing work. The feed is refreshed hourly, and a listing can change between refreshes.

The free API omits per-bounty payout history and competition evidence. This client does not infer those fields, claim tasks, execute task text, open source links, send credentials, or buy the paid x402 endpoint. HTTP 402 produces an error and stops. Transport errors are never silently converted into an empty successful feed.

The `list` and `new` commands support `--source`, `--min-usd`, `--limit` (1–100), `--query`, `--exclude-requires`, and `--json`. `get` and `stats` also accept `--json`. Errors go to stderr with a nonzero exit status. Responses are limited to 4 MiB, each HTTP operation has a 20-second socket timeout, redirects are refused, and there are no automatic retries.

## Verify

```sh
python -m unittest discover -v
```

Tests use a local HTTP fixture and require no external service. They cover JSON and SSE lifecycle behavior, session/protocol headers, notification and unrelated-response handling, early return from an open SSE connection, malformed/error responses, argument bounds, and stopping on HTTP 402 without retrying.

See [LIVE_CHECK.md](LIVE_CHECK.md) for dated live results and [sample-output.txt](sample-output.txt) for actual command output. Feed contents change; the sample is an observation, not a fixture or payment claim.

Built with OpenAI Codex for [the Agent Bounty Feed demo bounty](https://github.com/dailydollar-bot/agent-bounty-feed/issues/3), with the account owner's authorization. This is an independent client, not the feed maintainer's official SDK. MIT licensed; upstream feed data and service terms remain their respective owners'.
