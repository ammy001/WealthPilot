# WealthPilot — Memory Schema (Week 2, task 14)

Lane C (user memory). Currently backed by a JSON file, not Postgres — see "Future
store" below for why that's a deliberate, documented choice rather than an oversight.

## Schema — one record per user, `data/profiles/users.json`

```json
{
  "user_id": "U001",
  "name": "Marcus Chen",
  "age": 34,
  "risk_tolerance": "moderate",
  "goals": ["retirement", "house down-payment"],
  "preferences": {
    "crypto_cap_pct": 5,
    "base_currency": "INR"
  },
  "monthly_investment_inr": 60000,
  "created": "2023-08-17",
  "holdings": [
    {"symbol": "HCLTECH", "sector": "Information Technology",
     "buy_date": "2023-03-03", "quantity": 106, "buy_price": 959.54}
  ]
}
```

| Field | Type | Written by |
|---|---|---|
| `user_id`, `name`, `age`, `created` | str/int | seed data only (identity, not user-stated) |
| `risk_tolerance` | str | seed data **or** `update_preferences()` |
| `goals` | list[str] | seed data **or** `update_preferences()` |
| `monthly_investment_inr` | number | seed data **or** `update_preferences()` |
| `preferences.*` (e.g. `crypto_cap_pct`, `base_currency`) | any | seed data **or** `update_preferences()` — any key not in the top-level set above is written into this nested dict |
| `holdings` | list[dict] | seed data only — buying/selling isn't in scope (no brokerage integration) |

## API — `memory.py`

```python
get_user(user_id: str) -> dict | None          # lookup by user_id or name, case-insensitive
list_users() -> list[(user_id, name, risk_tolerance)]
update_preferences(user_id: str, **fields) -> dict | None
```

`update_preferences` routes each kwarg to the right place (top-level field vs. nested
`preferences`), then rewrites the whole `users.json` to disk — so a stated preference
survives an app restart, not just the current process.

## Read/write round trip (evidence for task 14's DoD)

Recorded 2026-07-20, run against a backed-up copy of `users.json` and restored afterward
so the seed persona data wasn't disturbed by the test itself:

```
>>> memory.get_user('U001')['risk_tolerance']
'moderate'
>>> memory.get_user('U001')['preferences']
{'crypto_cap_pct': 5, 'base_currency': 'INR'}

>>> memory.update_preferences('U001', risk_tolerance='aggressive', crypto_cap_pct=10)
{'risk_tolerance': 'aggressive', 'preferences': {'crypto_cap_pct': 10, 'base_currency': 'INR'}, ...}

>>> memory.get_user('U001')['risk_tolerance']      # re-read from disk, fresh process
'aggressive'
>>> memory.get_user('U001')['preferences']
{'crypto_cap_pct': 10, 'base_currency': 'INR'}
```

## Wired into the conversation (task 15's DoD)

`agent/orchestrator.py` adds a 6th router lane, `update_preference`, alongside
`get_quote`/`get_index`/`portfolio_summary`/`rebalance`/`general_knowledge`. The router
LLM picks it when the user is **stating** a new risk tolerance or preference (not asking
what it currently is — that stays on `general_knowledge`, which already injects the
user's profile into the RAG system prompt for recall).

```
User (session 1): "my risk tolerance is aggressive now"
  -> route: update_preference  -> memory.update_preferences('U001', risk_tolerance='aggressive')
  -> "Got it — I've updated your profile (risk tolerance = aggressive). I'll remember this next time."

User (session 2, new process): "remind me what my risk tolerance is"
  -> route: general_knowledge -> rag.answer(user=get_user('U001'))   # profile already reflects 'aggressive'
  -> "You told me your risk tolerance is aggressive..."
```

Verified end-to-end (`agent.orchestrator.respond`) with the same backup/restore
discipline as above — see git history / session transcript for the run.

## Future store (unchanged from the original plan)

Postgres tables `user_profile` / `user_holding` (already sketched in
`docs/data-architecture.md §5`) can back this same `get_user` / `update_preferences`
API later without changing any caller — only `memory.py`'s internals would change from
file I/O to SQL. Not needed to satisfy Week 2's DoD, which only requires that *a* record
can be written and read back correctly.
