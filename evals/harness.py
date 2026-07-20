"""Lightweight, offline-friendly eval harness for the WealthPilot agent.

Runs each golden case through `agent.orchestrator.respond` and scores it with a
handful of cheap, deterministic metrics (no heavy deps — no ragas required):

  - route_match      expected route == observed route (safety route counts as
                     general_knowledge when that's what was expected)
  - keyword_recall   fraction of `must_include` substrings found in the answer
  - citation_ok      sources non-empty when a citation was expected
  - retrieval_hit    `expected_doc_contains` appears in a cited source doc_id
  - no_directive     answer contains none of the directive blacklist (always checked)
  - abstain_ok       when `expect_abstain`, answer carries the abstain phrase

Reports a per-case table + aggregate summary and writes evals/results.json.
Always exits 0 — this reports quality, it does not gate the process.

Run:  INSECURE_SSL=1 HF_HUB_OFFLINE=1 python -m evals.harness
(needs the live LLM/embeddings/pgvector stack + an ingested corpus).
"""
import json
import os
import sys

import memory
from agent.orchestrator import respond

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, "golden.json")
RESULTS = os.path.join(HERE, "results.json")

# Second-person imperatives / recommendations that must never appear in output.
DIRECTIVE_BLACKLIST = [
    "you should buy", "you should sell", "i recommend you buy",
    "invest now", "sell everything and",
]
ABSTAIN_PHRASE = "don't have information"


def _keyword_recall(answer, must_include):
    """Fraction of expected substrings present (case-insensitive); 1.0 if none expected."""
    if not must_include:
        return 1.0
    lo = answer.lower()
    hits = sum(1 for s in must_include if s.lower() in lo)
    return hits / len(must_include)


def _no_directive(answer):
    lo = answer.lower()
    return not any(bad in lo for bad in DIRECTIVE_BLACKLIST)


def _retrieval_hit(sources, needle):
    """True if `needle` appears in any cited source doc_id (None when not applicable)."""
    if not needle:
        return None
    needle = needle.lower()
    return any(needle in (s.get("doc_id", "") or "").lower() for s in sources)


def _route_match(expected, observed):
    if observed == expected:
        return True
    # the safety lane is a specialisation of general_knowledge
    return expected == "general_knowledge" and observed == "general_knowledge(safety)"


def run_case(case):
    """Execute one golden case and return its metric dict."""
    uid = case.get("user_id", "U001")
    user = memory.get_user(uid)
    try:
        out = respond(case["query"], user=user)
        answer, route = out.get("answer", ""), out.get("route", "")
        sources = out.get("sources", []) or []
        error = None
    except Exception as e:  # keep the run going; a live-stack failure is reported, not fatal
        answer, route, sources, error = "", "", [], f"{type(e).__name__}: {e}"

    expect_cite = case.get("expect_citation", False)
    expect_abstain = case.get("expect_abstain", False)
    return {
        "id": case["id"],
        "query": case["query"],
        "route": route,
        "expected_route": case["expected_route"],
        "route_match": _route_match(case["expected_route"], route),
        "keyword_recall": round(_keyword_recall(answer, case.get("must_include", [])), 3),
        "citation_ok": (bool(sources) if expect_cite else True),
        "retrieval_hit": _retrieval_hit(sources, case.get("expected_doc_contains")),
        "no_directive": _no_directive(answer),
        "abstain_ok": (ABSTAIN_PHRASE in answer.lower()) if expect_abstain else None,
        "n_sources": len(sources),
        "error": error,
        "answer": answer,
    }


def _mark(v):
    return {True: "PASS", False: "FAIL", None: " -- "}.get(v, str(v))


def _rate(values):
    """Pass-rate over the non-None (applicable) booleans; None if nothing applies."""
    vals = [v for v in values if v is not None]
    return (sum(1 for v in vals if v) / len(vals)) if vals else None


def print_report(rows):
    print(f"\nWealthPilot eval — {len(rows)} cases\n" + "=" * 78)
    hdr = f"{'id':<22}{'route':^7}{'kw':^7}{'cite':^7}{'retr':^7}{'ndir':^7}{'abst':^7}"
    print(hdr)
    print("-" * 78)
    for r in rows:
        print(f"{r['id']:<22}"
              f"{_mark(r['route_match']):^7}"
              f"{r['keyword_recall']:^7}"
              f"{_mark(r['citation_ok']):^7}"
              f"{_mark(r['retrieval_hit']):^7}"
              f"{_mark(r['no_directive']):^7}"
              f"{_mark(r['abstain_ok']):^7}")
        if r["error"]:
            print(f"    ! error: {r['error']}")
        elif not r["route_match"]:
            print(f"    ! route: expected {r['expected_route']}, got {r['route'] or '(none)'}")

    print("-" * 78)
    summary = {
        "cases": len(rows),
        "route_match_rate": _rate([r["route_match"] for r in rows]),
        "mean_keyword_recall": round(sum(r["keyword_recall"] for r in rows) / len(rows), 3) if rows else None,
        "citation_ok_rate": _rate([r["citation_ok"] for r in rows]),
        "retrieval_hit_rate": _rate([r["retrieval_hit"] for r in rows]),
        "no_directive_rate": _rate([r["no_directive"] for r in rows]),
        "abstain_ok_rate": _rate([r["abstain_ok"] for r in rows]),
        "errors": sum(1 for r in rows if r["error"]),
    }
    print("AGGREGATE")
    for k, v in summary.items():
        print(f"  {k:<22} {v}")
    return summary


# ── Optional RAGAS hook (kept fully optional; the harness never depends on it) ──
# If you install `ragas` + `datasets`, you can add faithfulness / answer_relevancy
# on top of the rows above. Left commented so the harness stays runnable without it:
#
#     try:
#         from ragas import evaluate
#         from ragas.metrics import faithfulness, answer_relevancy
#         from datasets import Dataset
#         ds = Dataset.from_list([
#             {"question": r["query"], "answer": r["answer"],
#              "contexts": [r["answer"]]}  # feed real retrieved chunks here for faithfulness
#             for r in rows if r["answer"]
#         ])
#         scores = evaluate(ds, metrics=[faithfulness, answer_relevancy])
#         print("RAGAS:", scores)
#     except ImportError:
#         pass  # ragas not installed — skip silently


def main():
    with open(GOLDEN, encoding="utf-8") as f:
        cases = json.load(f)
    rows = [run_case(c) for c in cases]
    summary = print_report(rows)
    with open(RESULTS, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "cases": rows}, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
