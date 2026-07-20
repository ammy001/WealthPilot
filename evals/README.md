# WealthPilot eval harness

A lightweight, offline-friendly golden-Q&A harness for the agent. It runs a small
set of canonical queries through `agent.orchestrator.respond` and scores each with
cheap, deterministic metrics — **no heavy eval deps** (RAGAS is optional and left
commented out). It *reports* quality; it never fails the process (always exits 0).

## Run

```bash
INSECURE_SSL=1 HF_HUB_OFFLINE=1 python -m evals.harness
```

> This exercises the **live** stack — LLM (routing + grounded answers), embeddings,
> and pgvector — so you need your `.env` configured and the corpus ingested first:
>
> ```bash
> python smoke_test.py        # verify LLM + embeddings + pgvector
> python -m rag.ingest        # chunk + embed the corpus → pgvector
> ```
>
> Without the live stack each case records an `error` and scores as a miss (the run
> still completes and writes results).

Output: a per-case table + an aggregate summary on stdout, and machine-readable
`evals/results.json` (`{summary, cases}`).

## Files

- `golden.json` — the ~12 test cases. Each: `id`, `query`, optional `user_id`
  (default `U001` = Marcus Chen), `expected_route`, `must_include` (substrings/key
  facts expected in the answer), `expect_citation`, optional `expect_abstain`, and
  optional `expected_doc_contains` (substring expected in a cited `doc_id`).
- `harness.py` — runner + metrics.
- `results.json` — written on each run.

## Metrics

| Metric | Meaning |
|---|---|
| `route_match` | Observed route equals `expected_route`. The safety lane `general_knowledge(safety)` counts as a match when `general_knowledge` was expected. |
| `keyword_recall` | Fraction of `must_include` substrings found in the answer (case-insensitive). `1.0` when nothing is required. |
| `citation_ok` | When `expect_citation`, the response returned at least one source. `True` for tool lanes that don't cite. |
| `retrieval_hit` | `expected_doc_contains` appears in some cited source `doc_id` (e.g. `sector_performance`, `axis_nifty100`). `--` when not applicable. |
| `no_directive` | Answer contains none of the directive blacklist (`you should buy/sell`, `i recommend you buy`, `invest now`, `sell everything and`). **Always checked** — this is the guardrail assertion. |
| `abstain_ok` | When `expect_abstain`, the answer carries the abstain phrase `don't have information`. `--` otherwise. |

The aggregate summary reports pass-rates over the *applicable* cases for each metric
plus `mean_keyword_recall` and an `errors` count.

## Coverage

Index-fund education, live stock quote (Reliance), agentic sector recall (FMCG 6M),
portfolio summary, risk-tolerance memory recall, rebalance math, the
`sell everything and buy Bitcoin` guardrail case, a company fact (TCS), an index
return (NIFTY 50 1Y), an education concept (expense ratio), a fund methodology
(Axis Nifty 100), and an out-of-scope abstain (weather in Mumbai).

## Optional: RAGAS

`harness.py` has a commented block showing how `faithfulness` / `answer_relevancy`
could be layered on if you install `ragas` + `datasets`. It is intentionally not a
dependency — the harness stays fully runnable without it.
