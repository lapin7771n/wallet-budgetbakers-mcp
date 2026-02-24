# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Read-only MCP server for accessing [Wallet by BudgetBakers](https://budgetbakers.com/) financial data. Single-file Python project (`server.py`, ~460 lines) using the FastMCP framework. All 10 tools are GET-only — no write operations.

## Commands

```bash
# Run the server
uv run server.py

# Install/sync dependencies
uv sync

# Type check
uv run pyright server.py
```

There are no tests configured.

## Architecture

**`server.py`** — the entire application:

1. **Lifespan** (`app_lifespan`) — creates a shared `httpx.AsyncClient` with Bearer token auth from `WALLET_API_TOKEN` env var
2. **`_fetch()`** — single HTTP helper that all tools call. Appends `agentHints=true`, handles 429 rate limits and errors, returns formatted JSON strings
3. **10 `@mcp.tool()` functions** — thin wrappers that map tool parameters to API query params and call `_fetch()`

API base: `https://rest.budgetbakers.com/wallet/v1/api`

**Tool parameter conventions:**
- `snake_case` Python params map to `camelCase` API params (e.g., `account_id` → `accountId`)
- Text filters use prefixes: `eq.`, `contains.`, `contains-i.`
- Range filters use prefixes: `gte.`, `lte.` (combinable: `gte.100,lte.500`)
- Pagination: `limit` (1-100) + `offset`
- All tools return `str` (JSON)

**Record types:** `recordType` is `income` or `expense` only. Transfers are identified by `transferId`/`transferAccountId` fields in the response, not by `recordType`.

**Date constraints (records):** Max 370-day range per query. Default (no filter): last 3 months.

**Rate limit:** 500 requests/hour. The server returns structured JSON error on 429 with `retry_after`.

## Dependencies

- `mcp[cli]>=1.2.0` — FastMCP server framework
- `httpx>=0.27.0` — async HTTP client
- Python 3.11+, managed with `uv`

## Setup

Requires `WALLET_API_TOKEN` env var (get from https://web.budgetbakers.com/settings/apiTokens, requires Premium). The `.mcp.json` file handles auto-discovery in Claude Code.
