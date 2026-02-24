"""
Wallet by BudgetBakers — MCP Server
====================================
Read-only MCP server for accessing Wallet financial data.

Endpoints covered:
  - accounts, records, categories, budgets, goals,
    labels, standing-orders, record-rules, api-usage/stats

Setup:
  1. Get API token: https://web.budgetbakers.com/settings/apiTokens (Premium required)
  2. Set env: export WALLET_API_TOKEN=your_token
  3. Run: uv run server.py
"""

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from mcp.server.fastmcp import Context, FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

# ── Config ───────────────────────────────────────────────────────────────
BASE_URL = "https://rest.budgetbakers.com/wallet/v1/api"

INSTRUCTIONS = """\
Wallet by BudgetBakers — read-only access to personal financial data.

## Workflow
1. Call get_accounts() first to discover account IDs.
2. Use an account ID with get_records() to fetch transactions.
3. Use get_categories(), get_labels() to understand record metadata.

## Filter syntax (applies to text fields like name, note, payee)
- Exact match: eq.value
- Contains (case-sensitive): contains.value
- Contains (case-insensitive): contains-i.value

## Range filters (for dates, amounts, timestamps)
- Greater/equal: gte.value
- Less/equal: lte.value
- Combine: gte.2025-01-01,lte.2025-01-31

## Record types and transfers
- recordType is either "income" or "expense"
- Transfers are identified by the presence of transferId and transferAccountId fields,
  not by recordType. A transfer appears as two linked records (one per account).

## Date constraints for records
- Max date range: 370 days per query
- Default (no date filter): last 3 months

## Rate limits
500 requests per hour. Use get_api_usage() to check remaining quota.
"""


# ── Lifespan (shared HTTP client) ────────────────────────────────────────
@dataclass
class AppContext:
    http: httpx.AsyncClient


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    token = os.environ.get("WALLET_API_TOKEN", "")
    if not token:
        raise RuntimeError(
            "WALLET_API_TOKEN is required. "
            "Get your token at https://web.budgetbakers.com/settings/apiTokens"
        )
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    ) as client:
        yield AppContext(http=client)


# ── MCP Server ───────────────────────────────────────────────────────────
mcp = FastMCP(
    "wallet-bb",
    instructions=INSTRUCTIONS,
    lifespan=app_lifespan,
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8080)),
    stateless_http=True,
)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


# ── HTTP helper ──────────────────────────────────────────────────────────
async def _fetch(
    ctx: Context,
    path: str,
    params: dict[str, str | int | None] | None = None,
) -> str:
    """Make an authenticated GET request and return formatted JSON."""
    client: httpx.AsyncClient = ctx.request_context.lifespan_context.http

    clean: dict[str, str | int] = {"agentHints": "true"}
    if params:
        for k, v in params.items():
            if v is not None and v != "":
                clean[k] = v

    try:
        resp = await client.get(path, params=clean)
        resp.raise_for_status()
        return json.dumps(resp.json(), ensure_ascii=False, default=str)
    except httpx.HTTPStatusError as e:
        body = e.response.text
        if e.response.status_code == 429:
            retry_after = e.response.headers.get("Retry-After", "unknown")
            return json.dumps(
                {
                    "error": "Rate limit exceeded (429)",
                    "retry_after": retry_after,
                    "hint": "Use get_api_usage() to check remaining quota.",
                },
                indent=2,
            )
        return json.dumps(
            {"error": f"HTTP {e.response.status_code}", "detail": body}, indent=2
        )
    except httpx.RequestError as e:
        return json.dumps({"error": f"Request failed: {e}"}, indent=2)


# ── Tools ────────────────────────────────────────────────────────────────


@mcp.tool()
async def get_accounts(
    ctx: Context,
    limit: int = 30,
    offset: int = 0,
    account_id: str | None = None,
    name: str | None = None,
    account_type: str | None = None,
    currency_code: str | None = None,
    bank_account_number: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> str:
    """
    Get all financial accounts (bank accounts, cash, cards, etc.).

    Use this first to discover account IDs — you'll need them for get_records().

    Args:
        ctx: MCP context
        limit: Items per page (1-100, default 30)
        offset: Items to skip for pagination
        account_id: Filter by exact account ID
        name: Filter by account name (use prefix: eq., contains., contains-i.)
        account_type: Filter by type (e.g. general, loan, insurance)
        currency_code: Filter by ISO currency code (e.g. UAH, USD, EUR)
        bank_account_number: Filter by bank account number
        created_at: Filter by creation date (e.g. "gte.2025-01-01")
        updated_at: Filter by last update date (e.g. "gte.2025-01-01")
    """
    return await _fetch(ctx, "/accounts", {
        "limit": limit,
        "offset": offset,
        "id": account_id,
        "name": name,
        "accountType": account_type,
        "currencyCode": currency_code,
        "bankAccountNumber": bank_account_number,
        "createdAt": created_at,
        "updatedAt": updated_at,
    })


@mcp.tool()
async def get_records(
    ctx: Context,
    account_id: str,
    record_date: str | None = None,
    limit: int = 30,
    offset: int = 0,
    category_id: str | None = None,
    label_id: str | None = None,
    note: str | None = None,
    payee: str | None = None,
    payer: str | None = None,
    amount: str | None = None,
    record_type: str | None = None,
    sort_by: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> str:
    """
    Get financial records (transactions) for a specific account.

    IMPORTANT: account_id is required. Use get_accounts() first to find it.
    Max date range is 370 days. If no date filter, returns last 3 months.

    Date filter examples:
      - "gte.2025-01-01" — from Jan 1, 2025
      - "gte.2025-01-01,lte.2025-01-31" — January 2025

    Amount filter examples:
      - "gte.100" — amount >= 100
      - "gte.100,lte.500" — between 100 and 500

    Text filter prefixes: eq., contains., contains-i.

    Args:
        ctx: MCP context
        account_id: Required. Account ID (use get_accounts to find IDs)
        record_date: Date range filter with prefix (e.g. "gte.2025-01-01")
        limit: Items per page (1-100, default 30)
        offset: Items to skip for pagination
        category_id: Filter by category ID
        label_id: Filter by label ID
        note: Filter by note text (use prefix: contains-i.grocery)
        payee: Filter expenses by payee (use prefix: contains-i.amazon)
        payer: Filter income by payer
        amount: Filter by amount (use prefix: gte.100,lte.500)
        record_type: Filter by type: income or expense. Transfers are not a
            separate type — they are identified by transferId/transferAccountId
            fields in the response
        sort_by: Sort field and direction (e.g. "recordDate,asc" or "amount,desc")
        created_at: Filter by creation date (e.g. "gte.2025-01-01")
        updated_at: Filter by last update date (e.g. "gte.2025-01-01")
    """
    return await _fetch(ctx, "/records", {
        "accountId": account_id,
        "recordDate": record_date,
        "limit": limit,
        "offset": offset,
        "categoryId": category_id,
        "labelId": label_id,
        "note": note,
        "payee": payee,
        "payer": payer,
        "amount": amount,
        "recordType": record_type,
        "sortBy": sort_by,
        "createdAt": created_at,
        "updatedAt": updated_at,
    })


@mcp.tool()
async def get_records_by_id(ctx: Context, record_ids: str) -> str:
    """
    Get specific records by their IDs (comma-separated, max 30).

    Args:
        ctx: MCP context
        record_ids: Comma-separated record IDs (e.g. "id1,id2,id3")
    """
    return await _fetch(ctx, "/records/by-id", {"id": record_ids})


@mcp.tool()
async def get_categories(
    ctx: Context,
    limit: int = 50,
    offset: int = 0,
    category_id: str | None = None,
    name: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> str:
    """
    Get spending/income categories.

    Categories are organized hierarchically (parent -> children).
    Use category IDs to filter records by category.

    Args:
        ctx: MCP context
        limit: Items per page (1-100, default 50)
        offset: Items to skip
        category_id: Filter by exact category ID
        name: Filter by name (use prefix: contains-i.food)
        created_at: Filter by creation date (e.g. "gte.2025-01-01")
        updated_at: Filter by last update date (e.g. "gte.2025-01-01")
    """
    return await _fetch(ctx, "/categories", {
        "limit": limit,
        "offset": offset,
        "id": category_id,
        "name": name,
        "createdAt": created_at,
        "updatedAt": updated_at,
    })


@mcp.tool()
async def get_budgets(
    ctx: Context,
    limit: int = 30,
    offset: int = 0,
    budget_id: str | None = None,
    name: str | None = None,
    currency_code: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> str:
    """
    Get all budgets with their limits, spent amounts, and periods.

    Args:
        ctx: MCP context
        limit: Items per page (1-100, default 30)
        offset: Items to skip
        budget_id: Filter by exact budget ID
        name: Filter by budget name (use prefix: eq., contains., contains-i.)
        currency_code: Filter by currency (e.g. UAH, USD)
        created_at: Filter by creation date (e.g. "gte.2025-01-01")
        updated_at: Filter by last update date (e.g. "gte.2025-01-01")
    """
    return await _fetch(ctx, "/budgets", {
        "limit": limit,
        "offset": offset,
        "id": budget_id,
        "name": name,
        "currencyCode": currency_code,
        "createdAt": created_at,
        "updatedAt": updated_at,
    })


@mcp.tool()
async def get_goals(
    ctx: Context,
    limit: int = 30,
    offset: int = 0,
    goal_id: str | None = None,
    name: str | None = None,
    note: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> str:
    """
    Get all savings goals with current/target amounts and deadlines.

    Args:
        ctx: MCP context
        limit: Items per page (1-100, default 30)
        offset: Items to skip
        goal_id: Filter by exact goal ID
        name: Filter by goal name (use prefix: eq., contains., contains-i.)
        note: Filter by note text (use prefix: contains-i.vacation)
        created_at: Filter by creation date (e.g. "gte.2025-01-01")
        updated_at: Filter by last update date (e.g. "gte.2025-01-01")
    """
    return await _fetch(ctx, "/goals", {
        "limit": limit,
        "offset": offset,
        "id": goal_id,
        "name": name,
        "note": note,
        "createdAt": created_at,
        "updatedAt": updated_at,
    })


@mcp.tool()
async def get_labels(
    ctx: Context,
    limit: int = 50,
    offset: int = 0,
    label_id: str | None = None,
    name: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> str:
    """
    Get custom labels (tags) used to organize records.

    Args:
        ctx: MCP context
        limit: Items per page (1-100, default 50)
        offset: Items to skip
        label_id: Filter by exact label ID
        name: Filter by label name (use prefix: eq., contains., contains-i.)
        created_at: Filter by creation date (e.g. "gte.2025-01-01")
        updated_at: Filter by last update date (e.g. "gte.2025-01-01")
    """
    return await _fetch(ctx, "/labels", {
        "limit": limit,
        "offset": offset,
        "id": label_id,
        "name": name,
        "createdAt": created_at,
        "updatedAt": updated_at,
    })


@mcp.tool()
async def get_standing_orders(
    ctx: Context,
    limit: int = 30,
    offset: int = 0,
    standing_order_id: str | None = None,
    name: str | None = None,
    currency_code: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> str:
    """
    Get recurring/scheduled payments (standing orders).

    Shows planned future transactions: bills, subscriptions, salary, etc.

    Args:
        ctx: MCP context
        limit: Items per page (1-100, default 30)
        offset: Items to skip
        standing_order_id: Filter by exact standing order ID
        name: Filter by name (use prefix: eq., contains., contains-i.)
        currency_code: Filter by ISO currency code (e.g. UAH, USD, EUR)
        created_at: Filter by creation date (e.g. "gte.2025-01-01")
        updated_at: Filter by last update date (e.g. "gte.2025-01-01")
    """
    return await _fetch(ctx, "/standing-orders", {
        "limit": limit,
        "offset": offset,
        "id": standing_order_id,
        "name": name,
        "currencyCode": currency_code,
        "createdAt": created_at,
        "updatedAt": updated_at,
    })


@mcp.tool()
async def get_record_rules(
    ctx: Context,
    limit: int = 30,
    offset: int = 0,
    rule_id: str | None = None,
    name: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> str:
    """
    Get auto-categorization rules for records.

    These rules automatically assign categories/labels to matching transactions.

    Args:
        ctx: MCP context
        limit: Items per page (1-100, default 30)
        offset: Items to skip
        rule_id: Filter by exact rule ID
        name: Filter by rule name (use prefix: eq., contains., contains-i.)
        created_at: Filter by creation date (e.g. "gte.2025-01-01")
        updated_at: Filter by last update date (e.g. "gte.2025-01-01")
    """
    return await _fetch(ctx, "/record-rules", {
        "limit": limit,
        "offset": offset,
        "id": rule_id,
        "name": name,
        "createdAt": created_at,
        "updatedAt": updated_at,
    })


@mcp.tool()
async def get_api_usage(ctx: Context, period: str = "30days") -> str:
    """
    Get API usage statistics.

    Args:
        ctx: MCP context
        period: Time period — format is Xdays, Xweeks, or Xmonths (e.g. "30days", "4weeks", "3months")
    """
    return await _fetch(ctx, "/api-usage/stats", {"period": period})


# ── Entry point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)  # type: ignore[arg-type]
