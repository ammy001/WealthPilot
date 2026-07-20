"""Query pre-processing for multi-turn + multi-hop questions.

- rewrite_with_history(query, history) : coreference resolution — turn a follow-up like
  "what about its P/E?" into a standalone query using the recent conversation.
- decompose(query)                     : split a comparison / multi-part question into
  standalone sub-questions ("compare TCS and Infosys" -> two queries).

Both use the cheap/fast helper model and degrade gracefully (return the original query)
on any failure, so they never break the main path.
"""
import json
import re

from llm import chat_fast

_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def _json_from(text):
    if not text:
        return None
    text = _THINK.sub("", text)
    text = re.sub(r"```(?:json)?|```", "", text)
    for oc, cc in (("{", "}"), ("[", "]")):
        i, j = text.find(oc), text.rfind(cc)
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except json.JSONDecodeError:
                continue
    return None


def rewrite_with_history(query, history, max_turns=4):
    """Resolve references in `query` against recent history -> standalone query.
    `history` is a list of {role, content}. Returns the (possibly) rewritten query."""
    if not history:
        return query
    turns = [h for h in history if h.get("role") in ("user", "assistant")][-max_turns * 2:]
    if not turns:
        return query
    convo = "\n".join(f"{h['role']}: {h['content']}" for h in turns)
    sys = ("Rewrite the user's LATEST message as a standalone, self-contained finance search "
           "query, resolving any pronouns or references (it/that/its/the company) using the "
           "conversation. If it is already standalone, return it unchanged. "
           "Return ONLY the rewritten query, no quotes, no explanation.")
    try:
        resp = chat_fast(messages=[{"role": "system", "content": sys},
                                   {"role": "user",
                                    "content": f"Conversation:\n{convo}\n\nLatest message: {query}"}],
                         temperature=0, max_tokens=400)
        out = _THINK.sub("", resp.choices[0].message.content or "").strip().strip('"')
        # sanity: keep it short and non-empty, else fall back
        return out if out and len(out) <= 300 else query
    except Exception:
        return query


def decompose(query, max_parts=3):
    """Split a comparison / multi-part question into standalone sub-questions.
    Returns a list (>=1); [query] when it's already a single question."""
    sys = ("Decide if the finance question asks to COMPARE multiple entities or has multiple "
           "DISTINCT parts that need separate lookups. If so, split it into standalone "
           "sub-questions (one entity/topic each). If it is a single question, do not split. "
           f'Return ONLY JSON: {{"subqueries": ["...", ...]}} (max {max_parts} items).')
    try:
        resp = chat_fast(messages=[{"role": "system", "content": sys},
                                   {"role": "user", "content": query}],
                         temperature=0, max_tokens=500)
        data = _json_from(resp.choices[0].message.content) or {}
        subs = [s.strip() for s in data.get("subqueries", []) if isinstance(s, str) and s.strip()]
    except Exception:
        subs = []
    # dedup, cap; fall back to the original when the model didn't split
    seen, out = set(), []
    for s in subs:
        if s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out[:max_parts] if len(out) > 1 else [query]
