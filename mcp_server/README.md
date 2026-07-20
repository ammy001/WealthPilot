# WealthPilot MCP server

Exposes WealthPilot's tools over the **Model Context Protocol (MCP)** so external
agents (e.g. Claude Desktop) can call them over a stdio transport.

> **Educational only.** These tools return descriptive market/portfolio data and
> simple rebalance math. They give **no investment advice** and are intentionally
> non-directive.

## Tools exposed

| Tool | Signature | What it returns |
|------|-----------|-----------------|
| `get_quote` | `get_quote(ticker: str)` | Live/last NSE quote `{ticker, price, currency, timestamp, source, cache_hit}` |
| `get_index` | `get_index(name: str)` | Index level `{name, ticker, level, change, change_pct, timestamp, cache_hit}` |
| `portfolio_summary` | `portfolio_summary(user_id: str)` | Value / P&L / sector mix for a known user |
| `rebalance` | `rebalance(user_id, from_asset, to_asset, amount_inr)` | Illustrative before/after allocation |
| `list_users` | `list_users()` | `[[user_id, name, risk_tolerance], ...]` |

Unknown tickers / indices / users return `{"error": "..."}` rather than fabricated data.

## Requirements

The `mcp` package (>= 1.0) must be installed — it is already in `requirements.txt`:

```bash
pip install -r requirements.txt
```

## Run it

From the project root:

```bash
python mcp_server/server.py
```

The server speaks MCP over **stdio** and blocks waiting for a client; it is meant
to be launched by an MCP client (like Claude Desktop), not run interactively.

The server does the same TLS / offline setup as `app.py` at startup
(`INSECURE_SSL=1`, `HF_HUB_OFFLINE=1`) so it works behind a corporate
SSL-inspection proxy, and it inserts the project root on `sys.path` so it runs
correctly from this subfolder.

## Claude Desktop configuration

Add an entry to your `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`,
Windows: `%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "wealthpilot": {
      "command": "python",
      "args": [
        "C:\\Users\\Pavan13.Kumar\\notes\\wealthpilot\\mcp_server\\server.py"
      ],
      "env": {
        "INSECURE_SSL": "1",
        "HF_HUB_OFFLINE": "1",
        "LLM_PROVIDER": "azure",
        "OPENAI_API_VERSION": "2024-08-01-preview",
        "AZURE_OPENAI_ENDPOINT": "https://hcmp-aiml-oai.openai.azure.com",
        "DEPLOYMENT_NAME": "hcmp-aiml-oai-gpt4o-mini",
        "OPENAI_AIML_KEY": "<your-azure-openai-key>",
        "EMBED_BASE_URL": "http://10.169.88.182:30704",
        "EMBED_PATH": "/api/cloudxp/embeddings",
        "EMBED_MODEL": "mxbai-embed-large:latest",
        "EMBED_DIM": "1024",
        "PG_DSN": "postgresql://postgres:password@10.169.88.180:30003/hcmp_aiml_dev",
        "PG_SCHEMA": "hcmp_aiml"
      }
    }
  }
}
```

Notes:

- Use an **absolute path** to `server.py` (double-backslashes on Windows JSON).
- If `python` is not on Claude Desktop's PATH, use the absolute interpreter path
  (e.g. `C:\\Users\\Pavan13.Kumar\\...\\python.exe`) as `command`.
- The `env` block mirrors the `.env` values the app relies on. The quote/index
  tools only need network access (plus `INSECURE_SSL` behind a proxy); the LLM /
  embeddings / Postgres settings are included for parity with the app and are not
  strictly required by the five tools above.
- Restart Claude Desktop after editing the config so it re-reads `mcpServers`.
