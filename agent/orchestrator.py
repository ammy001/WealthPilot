"""Agent orchestrator: route a turn to the right lane and compose the answer.

Routing = ONE tool_choice="auto" LLM call (gpt-4o-mini auto-calls; if it declines,
we default to general_knowledge). The model picks one tool — router + argument extraction
in one step.
Tool outputs are formatted deterministically (no fabricated numbers) then guardrailed;
`general_knowledge` falls through to the cited RAG pipeline (rag.answer).

respond(query, user) -> {answer, route, trace}
"""
import json
import re

import memory
from guardrails.rules import DISCLAIMER, classify_input, enforce
from llm import chat
from rag.answer import answer as rag_answer
from tools.get_index import get_index
from tools.get_quote import get_quote
from tools.portfolio_calc import portfolio_calc
from tools.portfolio_summary import summarize

# risk-profile model allocation baseline for rebalance questions
import json as _json
import os as _os
_RP = _json.load(open(_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                                    "data", "reference", "risk_profiles.json"), encoding="utf-8"))

ROUTER_TOOLS = [
    {"type": "function", "function": {
        "name": "get_quote", "description": "Live price of ONE stock. Use for 'price of X', 'what is X trading at'.",
        "parameters": {"type": "object", "properties": {"ticker": {"type": "string", "description": "NSE symbol e.g. RELIANCE, TCS"}}, "required": ["ticker"]}}},
    {"type": "function", "function": {
        "name": "get_index", "description": "Live level of an index or sector. Use for 'where is the Nifty', 'Nifty Bank level'.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "e.g. NIFTY 50, Nifty IT, India VIX"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "portfolio_summary", "description": "Summarise the CURRENT user's own portfolio (value, P&L, holdings). Use for 'how is my portfolio', 'my holdings', 'my returns'.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "rebalance", "description": "Compute a new asset allocation after moving money between asset classes. Use for 'move X from bonds to equities'.",
        "parameters": {"type": "object", "properties": {"from_asset": {"type": "string"}, "to_asset": {"type": "string"}, "amount_inr": {"type": "number"}}, "required": ["from_asset", "to_asset", "amount_inr"]}}},
    {"type": "function", "function": {
        "name": "update_preference",
        "description": "The user is STATING or CHANGING their own risk tolerance or a preference (e.g. "
                       "'my risk tolerance is aggressive', 'set my crypto cap to 10%', 'I don't want more "
                       "than 10% in crypto'). NOT for asking what their profile currently is — that's "
                       "general_knowledge.",
        "parameters": {"type": "object", "properties": {
            "risk_tolerance": {"type": "string", "description": "conservative | moderate | aggressive, only if stated"},
            "crypto_cap_pct": {"type": "number", "description": "max % of portfolio in crypto, only if stated"}}}}},
    {"type": "function", "function": {
        "name": "general_knowledge", "description": "EVERYTHING ELSE: concepts, company/fund info, education, risk, sector performance, and any advice-type question. This is the default.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
]

ROUTER_SYS = ("You route a user's finance question to exactly one tool for WealthPilot. "
              "Pick get_quote/get_index only for live price/level lookups; portfolio_summary for "
              "the user's own holdings; rebalance for moving money between asset classes; "
              "update_preference only when the user is STATING a new risk tolerance/preference "
              "(not asking what it is); otherwise general_knowledge. Always choose one tool.")


def _route(query):
    # Auto tool-calling picks the lane; if the model declines OR the provider rejects a
    # malformed tool call (small models on Groq occasionally emit bad function syntax ->
    # HTTP 400), we retry once then default to general_knowledge rather than fail the turn.
    for _attempt in range(2):
        try:
            resp = chat(messages=[{"role": "system", "content": ROUTER_SYS},
                                  {"role": "user", "content": query}],
                        tools=ROUTER_TOOLS, tool_choice="auto", temperature=0, max_tokens=1024)
        except Exception:
            continue
        calls = resp.choices[0].message.tool_calls or []
        if not calls:
            return "general_knowledge", {"query": query}
        fn = calls[0].function
        try:
            args = json.loads(fn.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        return fn.name, args
    return "general_knowledge", {"query": query}


def _fmt_quote(q):
    return (f"{q['ticker']} is trading at ₹{q['price']:,} {q['currency']} "
            f"(delayed; source {q['source']}, as of {q['timestamp'][:16]}Z). "
            f"{'Cache hit.' if q.get('cache_hit') else 'Live fetch.'}")


def _fmt_index(d):
    arrow = "▲" if d["change"] >= 0 else "▼"
    return (f"{d['name']} is at {d['level']:,} ({arrow} {d['change']:+,} / {d['change_pct']:+.2f}%) "
            f"(delayed). ")


def _fmt_portfolio(s):
    lines = [f"Portfolio for {s['user']} (risk: {s['risk_tolerance']}):",
             f"- Invested: ₹{s['invested']:,.0f} · Current: ₹{s['current_value']:,.0f} · "
             f"P&L: ₹{s['pnl']:,.0f} ({s['pnl_pct']:+.1f}%)"]
    lines.append("- Holdings:")
    for p in s["positions"]:
        if p["price"] is None:
            lines.append(f"   • {p['symbol']}: {p['quantity']} @ ₹{p['buy_price']} — live price unavailable")
        else:
            lines.append(f"   • {p['symbol']}: {p['quantity']} @ ₹{p['buy_price']} → ₹{p['price']:,} "
                         f"(P&L {p['pnl_pct']:+.1f}%)")
    top = next(iter(s["sector_pct"].items()), None)
    if top:
        lines.append(f"- Sector mix (by value): " + ", ".join(f"{k} {v}%" for k, v in s["sector_pct"].items()))
        if top[1] >= 40:
            lines.append(f"- Note: {top[0]} is {top[1]}% of the portfolio — relatively concentrated.")
    return "\n".join(lines)


def _rebalance_answer(args, user):
    """Use the user's risk-profile model allocation × invested value as the baseline."""
    if not user:
        return "I need your profile to estimate a current allocation for a rebalance."
    rp = _RP["profiles"].get(user.get("risk_tolerance", "moderate"), _RP["profiles"]["moderate"])
    total = sum(h["quantity"] * h["buy_price"] for h in user.get("holdings", [])) or 100000
    mid = rp["midpoint"]
    alloc = {"equity": total * mid["equity"] / 100, "debt": total * mid["debt"] / 100,
             "gold": total * mid["gold_cash"] / 100}
    amt = float(args.get("amount_inr", 0))
    fa = args.get("from_asset", "debt").lower()
    ta = args.get("to_asset", "equity").lower()
    key = lambda a: "debt" if "bond" in a or "debt" in a else ("gold" if "gold" in a else "equity")
    res = portfolio_calc(alloc, {key(fa): -amt, key(ta): amt})
    if "error" in res:
        return f"That rebalance isn't possible: {res['error']}."
    b, a = res["before_pct"], res["after_pct"]
    return ("Using a typical " + user["risk_tolerance"] + f" allocation on your ₹{total:,.0f} portfolio "
            f"as a baseline, moving ₹{amt:,.0f} from {fa} to {ta} shifts the mix:\n"
            f"- Before: equity {b.get('equity',0)}%, debt {b.get('debt',0)}%, gold {b.get('gold',0)}%\n"
            f"- After:  equity {a.get('equity',0)}%, debt {a.get('debt',0)}%, gold {a.get('gold',0)}%\n"
            "Rebalancing simply realigns to a target; this is illustrative, not a suggestion to act.")


def _finish(result, query, user):
    """Persist one observability record per turn, then return the result unchanged."""
    try:
        from obs.trace import log_turn
        log_turn(user, query, result)
    except Exception:
        pass
    return result


def respond(query, user=None, history=None):
    # Multi-turn coreference: rewrite a follow-up into a standalone query using history.
    original = query
    if history:
        from rag.query_ops import rewrite_with_history
        query = rewrite_with_history(query, history)
    rewritten = query if query != original else None
    flags = classify_input(query)
    # Risky/directive asks always go through the guarded RAG safety path.
    if flags["directive"] or flags["risky"]:
        out = rag_answer(query, user=user)
        return _finish({"answer": out["answer"], "route": "general_knowledge(safety)",
                "sources": out.get("sources", []),
                "trace": {"flags": flags, "route": "general_knowledge(safety)", "cache_hit": None,
                          "rewritten": rewritten, "retrieval": out.get("retrieval_trace"),
                          "guardrail": {"blocked": out.get("guardrail_blocked", False),
                                        "violations": out.get("guardrail_violations", [])}}},
                       query, user)

    route, args = _route(query)
    trace = {"flags": flags, "route": route, "args": args, "cache_hit": None, "rewritten": rewritten}
    cache_hit = None

    if route == "get_quote":
        try:
            q = get_quote(args["ticker"])
            cache_hit = q.get("cache_hit")
            text = _fmt_quote(q)
        except Exception as e:
            text = f"I couldn't fetch a live price for {args.get('ticker')!r} ({type(e).__name__})."
    elif route == "get_index":
        try:
            d = get_index(args["name"])
            cache_hit = d.get("cache_hit")
            text = _fmt_index(d)
        except Exception as e:
            text = f"I couldn't fetch {args.get('name')!r} ({type(e).__name__})."
    elif route == "portfolio_summary":
        text = _fmt_portfolio(summarize(user)) if user else "I don't have your profile loaded."
    elif route == "rebalance":
        text = _rebalance_answer(args, user)
    elif route == "update_preference":
        fields = {k: v for k, v in args.items()
                  if k in ("risk_tolerance", "crypto_cap_pct") and v not in (None, "")}
        if not user:
            text = "I don't have your profile loaded, so I can't save that."
        elif not fields:
            text = ("I heard a preference update but couldn't tell exactly what to change — "
                    "could you rephrase (e.g. 'set my risk tolerance to aggressive')?")
        else:
            memory.update_preferences(user["user_id"], **fields)
            said = ", ".join(f"{k.replace('_', ' ')} = {v}" for k, v in fields.items())
            text = f"Got it — I've updated your profile ({said}). I'll remember this next time."
    else:  # general_knowledge -> cited RAG (has its own guardrails)
        out = rag_answer(args.get("query", query), user=user)
        trace["guardrail"] = {"blocked": out.get("guardrail_blocked", False),
                              "violations": out.get("guardrail_violations", [])}
        trace["retrieval"] = out.get("retrieval_trace")
        return _finish({"answer": out["answer"], "route": route,
                        "sources": out.get("sources", []), "trace": trace}, query, user)

    g = enforce(text)
    trace["guardrail"] = {"blocked": g["blocked"], "violations": g["violations"]}
    trace["cache_hit"] = cache_hit
    return _finish({"answer": g["text"], "route": route, "sources": [], "trace": trace}, query, user)


if __name__ == "__main__":
    import sys
    u = memory.get_user("U001")
    q = sys.argv[1] if len(sys.argv) > 1 else "how is my portfolio doing?"
    r = respond(q, user=u)
    print(f"[route: {r['route']}]\n{r['answer']}")
