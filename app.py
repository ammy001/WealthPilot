"""WealthPilot — Gradio UI.

Tabs:
  💬 Chat        — streaming chat + expandable agent-trace + guardrail/cache badges
  📊 Portfolio   — descriptive charts (sector mix pie + per-holding P&L bar) for the user
  🔎 Observability — recent per-turn traces (route, sources) from the obs sink

Run:  python app.py    (add share=True on Colab)
"""
import os

# TLS / offline setup BEFORE importing anything that makes network calls.
os.environ.setdefault("INSECURE_SSL", "1")        # corporate SSL-inspection proxy
os.environ.setdefault("HF_HUB_OFFLINE", "1")      # reranker loads from local cache

import insecure_ssl  # noqa: E402
insecure_ssl.maybe_disable_tls_verification()

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import gradio as gr  # noqa: E402

import memory  # noqa: E402
from agent.orchestrator import respond  # noqa: E402
from tools.portfolio_summary import summarize  # noqa: E402

USERS = [f"{uid} — {name} ({risk})" for uid, name, risk in memory.list_users()]
DEFAULT_USER = USERS[0]

INTRO = ("**WealthPilot** — educational finance assistant (NIFTY 100). "
         "Ask about companies, funds, your portfolio, live prices, or concepts. "
         "_Educational only — not investment advice._")


def _uid(user_label):
    return user_label.split(" — ")[0] if user_label else None


def _badges(trace):
    g = trace.get("guardrail") or {}
    if g.get("blocked"):
        gb = "🛡️ Guardrail: **blocked**"
    elif trace.get("flags", {}).get("directive") or trace.get("flags", {}).get("risky"):
        gb = "🛡️ Guardrail: **caution (risky/directive)**"
    else:
        gb = "🛡️ Guardrail: clean"
    ch = trace.get("cache_hit")
    cb = "⚡ Cache: hit" if ch is True else ("🐢 Cache: miss" if ch is False else "")
    nf = "📰 news-fallback" if (trace.get("retrieval") or {}).get("news_fallback") else ""
    extra = "   ·   ".join(x for x in (cb, nf) if x)
    return f"{gb}   ·   Route: `{trace.get('route')}`" + (f"   ·   {extra}" if extra else "")


def _trace_md(trace, sources):
    lines = ["#### Agent trace",
             f"- **Route:** `{trace.get('route')}`",
             f"- **Args:** `{trace.get('args', {})}`"]
    if trace.get("rewritten"):
        lines.append(f"- **Rewritten query (coreference):** {trace['rewritten']}")
    ret = trace.get("retrieval") or {}
    if ret:
        if ret.get("strategy"):
            lines.append(f"- **Retrieval strategy:** `{ret['strategy']}`")
        if ret.get("subqueries"):
            lines.append(f"    - sub-queries: `{ret['subqueries']}`")
        if ret.get("news_fallback"):
            lines.append(f"    - 📰 **news fallback:** `{ret['news_fallback']}`")
    lines.append(f"- **Input flags:** directive={trace.get('flags',{}).get('directive')}, "
                 f"risky={trace.get('flags',{}).get('risky')}")
    g = trace.get("guardrail") or {}
    lines.append(f"- **Output guardrail:** blocked={g.get('blocked', False)}, "
                 f"violations={g.get('violations', [])}")
    if trace.get("cache_hit") is not None:
        lines.append(f"- **Cache hit:** {trace.get('cache_hit')}")
    if sources:
        lines.append("- **Sources cited:**")
        for s in sources:
            asof = f" (as of {s['as_of']})" if s.get("as_of") else ""
            lines.append(f"    - `{s.get('doc_id')}` — {s.get('section','')}{asof}")
    return "\n".join(lines)


def chat_fn(message, history, user_label):
    """Streaming generator: shows a thinking state, then progressively reveals the answer."""
    if not message or not message.strip():
        yield history or [], "", "", ""
        return
    user = memory.get_user(_uid(user_label)) if user_label else None
    prior = history or []
    working = prior + [{"role": "user", "content": message},
                       {"role": "assistant", "content": "⏳ thinking…"}]
    yield working, "", "", "⏳ working…"
    try:
        r = respond(message, user=user, history=prior)   # prior = turns before this one
    except Exception as e:
        working[-1]["content"] = f"⚠️ Error: {type(e).__name__}: {e}"
        yield working, "", "", "⚠️ error"
        return
    trace = r.get("trace", {})
    tm, bd = _trace_md(trace, r.get("sources")), _badges(trace)
    words = (r.get("answer") or "").split(" ")
    acc = ""
    for i, w in enumerate(words):
        acc += ("" if i == 0 else " ") + w
        working[-1]["content"] = acc
        if i % 5 == 0 or i == len(words) - 1:
            yield working, "", tm, bd
    yield working, "", tm, bd


def portfolio_view(user_label):
    """Descriptive portfolio charts (never signals): sector mix + per-holding return."""
    user = memory.get_user(_uid(user_label)) if user_label else None
    if not user:
        return None, None, "_Select a user._"
    try:
        s = summarize(user)
    except Exception as e:
        return None, None, f"⚠️ Couldn't compute portfolio ({type(e).__name__}: {e})."
    sec = s.get("sector_pct") or {}
    fig1, ax1 = plt.subplots(figsize=(4.3, 4.3))
    if sec:
        ax1.pie(list(sec.values()), labels=list(sec.keys()), autopct="%1.0f%%",
                startangle=90, colors=plt.cm.tab20.colors)
        ax1.set_title("Sector mix (by value)")
    fig1.tight_layout()
    pos = [p for p in s.get("positions", []) if p.get("price") is not None]
    fig2, ax2 = plt.subplots(figsize=(5.6, 4.3))
    if pos:
        names = [p["symbol"] for p in pos]
        pnls = [p["pnl_pct"] for p in pos]
        colors = ["#10B981" if x >= 0 else "#E11D48" for x in pnls]
        ax2.bar(names, pnls, color=colors)
        ax2.axhline(0, color="#333", linewidth=0.8)
        ax2.set_ylabel("P&L %"); ax2.set_title("Per-holding return (delayed)")
        for t in ax2.get_xticklabels():
            t.set_rotation(45); t.set_ha("right")
    fig2.tight_layout()
    md = (f"**{s['user']}** · risk **{s['risk_tolerance']}** — invested ₹{s['invested']:,.0f} · "
          f"current ₹{s['current_value']:,.0f} · P&L ₹{s['pnl']:,.0f} ({s['pnl_pct']:+.1f}%)  \n"
          "_Descriptive only — not a recommendation to trade._")
    return fig1, fig2, md


def load_traces():
    from obs.trace import recent_traces
    rows = recent_traces(40)
    if not rows:
        return "_No traces yet — ask something in the Chat tab._"
    out = ["| time (UTC) | user | route | query | sources |", "|---|---|---|---|---|"]
    for r in rows:
        q = (r.get("query") or "").replace("|", "/")[:48]
        srcs = ", ".join((r.get("sources") or [])[:3]).replace("|", "/")
        out.append(f"| {r.get('ts','')[:19]} | {r.get('user') or '-'} | "
                   f"`{r.get('route','')}` | {q} | {srcs} |")
    return "\n".join(out)


with gr.Blocks(title="WealthPilot", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 💹 WealthPilot")
    gr.Markdown(INTRO)
    user_dd = gr.Dropdown(USERS, value=DEFAULT_USER,
                          label="User (memory / personalisation)", scale=3)

    with gr.Tabs():
        with gr.Tab("💬 Chat"):
            badges = gr.Markdown("")
            chatbot = gr.Chatbot(height=430)   # Gradio 6: messages-format by default
            with gr.Row():
                msg = gr.Textbox(
                    placeholder="e.g. How did the FMCG sector perform in the last 6 months?",
                    show_label=False, scale=8)
                send = gr.Button("Send", variant="primary", scale=1)
            with gr.Accordion("🔎 Agent trace (explainability)", open=False):
                trace_md = gr.Markdown("")
            gr.Examples(
                ["What's a good low-cost index fund for a moderate-risk investor?",
                 "What's the current price of Reliance?",
                 "How did the FMCG sector perform in the last 6 months?",
                 "How is my portfolio doing?",
                 "Remind me what my risk tolerance is.",
                 "If I move ₹5,000 from bonds to equities, what's my new allocation?",
                 "Should I sell everything and buy Bitcoin?",
                 "Compare TCS and Infosys."],
                inputs=msg)

        with gr.Tab("📊 Portfolio"):
            gr.Markdown("Descriptive view of the selected user's holdings.")
            pf_refresh = gr.Button("Load / refresh portfolio", variant="primary")
            pf_summary = gr.Markdown("")
            with gr.Row():
                pf_pie = gr.Plot(label="Sector mix")
                pf_bar = gr.Plot(label="Per-holding P&L %")

        with gr.Tab("🔎 Observability"):
            gr.Markdown("Recent turns logged by the observability sink (one row per request).")
            obs_refresh = gr.Button("Refresh traces")
            obs_md = gr.Markdown("_No traces yet — ask something in the Chat tab._")

    for trigger in (msg.submit, send.click):
        trigger(chat_fn, [msg, chatbot, user_dd], [chatbot, msg, trace_md, badges])
    pf_refresh.click(portfolio_view, [user_dd], [pf_pie, pf_bar, pf_summary])
    obs_refresh.click(load_traces, None, obs_md)

demo.queue()   # module-scope so streaming works via `import app; app.demo.launch(...)` too


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, share=False, inbrowser=False)
