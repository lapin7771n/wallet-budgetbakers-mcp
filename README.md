# Wallet by BudgetBakers — MCP Server

Read-only MCP server for accessing [Wallet by BudgetBakers](https://budgetbakers.com/) financial data from Claude.

## Prerequisites

- **Wallet Premium** subscription (API access requires Premium)
- **API token** from <https://web.budgetbakers.com/settings/apiTokens>
- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** package manager

## Setup

### 1. Set your API token

```bash
export WALLET_API_TOKEN=your_token_here
```

### 2. Claude Code (recommended)

The project includes `.mcp.json` — Claude Code auto-discovers the server. Just open the project directory:

```bash
cd wallet-bb-mcp
claude
# /mcp should show "wallet-bb" connected
```

### 3. Claude Desktop / Cowork

1. Open **Claude Desktop** → **Settings** (gear icon) → **Developer** → **Edit Config**
2. This opens `claude_desktop_config.json` in your editor. Add the `mcpServers` block:

```json
{
  "mcpServers": {
    "wallet-bb": {
      "command": "/Users/YOUR_USERNAME/.local/bin/uv",
      "args": ["--directory", "/path/to/wallet-bb-mcp", "run", "server.py"],
      "env": {
        "WALLET_API_TOKEN": "your_token_here"
      }
    }
  }
}
```

3. Replace the values:
   - `command` — full path to `uv` (run `which uv` in terminal to get it)
   - `--directory` argument — full path to this project
   - `WALLET_API_TOKEN` — your actual token (env var interpolation doesn't work here)
4. Save the file and **restart Claude Desktop**
5. You should see an MCP tools indicator (hammer icon) in the chat input area

## Available Tools

| Tool | Description |
|---|---|
| `get_accounts` | List financial accounts (bank, cash, cards). **Start here.** |
| `get_records` | Get transactions for an account (requires account ID) |
| `get_records_by_id` | Get specific records by IDs (max 30) |
| `get_categories` | List spending/income categories |
| `get_budgets` | List budgets with limits and spent amounts |
| `get_goals` | List savings goals with progress |
| `get_labels` | List custom labels/tags |
| `get_standing_orders` | List recurring payments |
| `get_record_rules` | List auto-categorization rules |
| `get_api_usage` | Check API usage quota |

## Filter Syntax

All text fields support filter prefixes:

| Prefix | Example | Meaning |
|---|---|---|
| `eq.` | `eq.Groceries` | Exact match |
| `contains.` | `contains.bank` | Contains (case-sensitive) |
| `contains-i.` | `contains-i.amazon` | Contains (case-insensitive) |

Range filters for dates, amounts, and timestamps:

| Prefix | Example | Meaning |
|---|---|---|
| `gte.` | `gte.2025-01-01` | Greater than or equal |
| `lte.` | `lte.2025-12-31` | Less than or equal |
| Combined | `gte.100,lte.500` | Between 100 and 500 |

## Rate Limits

- **500 requests per hour**
- Use `get_api_usage()` to check remaining quota
- Server returns structured error with `Retry-After` on HTTP 429
