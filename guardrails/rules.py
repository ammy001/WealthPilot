"""Deterministic guardrails — the hard, non-bypassable safety gate.

INPUT:  classify_input(query)  -> flags {risky, directive, reasons}
OUTPUT: enforce(text, ...)     -> cleaned text (disclaimer enforced, directive
        language blocked/rewritten). The LLM prompt also forbids directives, but
        this layer is what the model cannot talk its way past.
"""
import re

DISCLAIMER = "Educational information only, not investment advice."

# ── input intent patterns ─────────────────────────────────────
_DIRECTIVE_IN = [
    r"\bshould i (buy|sell|invest|put|move|dump|hold)\b",
    r"\b(buy|sell|dump) (everything|all)\b",
    r"\bgo all[- ]in\b",
    r"\bis\b.{0,30}\b(a good|worth)\b.{0,15}\b(buy|investment|bet)\b",
    r"\bwhich stock.{0,30}(buy|best|most|pick)\b",
    r"\bwill\b.{0,30}\b(go up|make me|double|moon)\b",
    r"\bguarantee(d)?\b.{0,15}\breturn",
    r"\btell me what to (buy|invest)\b",
]
_RISKY_IN = [
    r"\bbitcoin|crypto|leverage|margin|f&o|options\b",
    r"\b(sell|dump) (everything|all)\b",
    r"\ball[- ]in\b",
    r"\bborrow.{0,20}invest\b",
]

# ── output directive violations ──────────────────────────────
# Target genuine second-person imperatives/recommendations only — NOT descriptive
# mentions (the assistant explaining "selling everything is risky" must pass).
_DIRECTIVE_OUT = [
    r"\byou should (buy|sell|invest|put|move|dump)\b",
    r"\bi (recommend|suggest|advise) (that )?you\b.{0,25}\b(buy|sell|invest)\b",
    r"\b(buy|sell) (now|immediately|today)\b",
    r"\binvest now\b",
    r"\byou (ought to|need to|must) (buy|sell|invest)\b",
    r"\bmy (recommendation|advice) (to you )?is\b",
]


def _any(patterns, text):
    t = text.lower()
    return [p for p in patterns if re.search(p, t)]


def classify_input(query: str) -> dict:
    directive = _any(_DIRECTIVE_IN, query)
    risky = _any(_RISKY_IN, query)
    return {"directive": bool(directive), "risky": bool(risky),
            "reasons": directive + risky}


def output_violations(text: str) -> list:
    return _any(_DIRECTIVE_OUT, text)


def ensure_disclaimer(text: str) -> str:
    if DISCLAIMER.lower() in text.lower():
        return text
    return text.rstrip() + "\n\n" + DISCLAIMER


def _rewrite_safe(text: str) -> str:
    """LLM pass to strip directive language while keeping the educational content."""
    from llm import chat
    resp = chat(
        messages=[
            {"role": "system", "content":
             "Rewrite the text to REMOVE any buy/sell/invest recommendation or directive. "
             "Keep it factual and educational, preserve any [S#] citations and figures, "
             "and do not add new facts. Return only the rewritten text."},
            {"role": "user", "content": text},
        ],
        temperature=0.0, max_tokens=1024,
    )
    return re.sub(r"<think>.*?</think>", "", resp.choices[0].message.content or "", flags=re.S).strip()


def enforce(text: str, rewrite: bool = True) -> dict:
    """Return {text, blocked, violations}. Blocks/rewrites directives, enforces disclaimer."""
    violations = output_violations(text)
    blocked = False
    if violations and rewrite:
        text = _rewrite_safe(text)
        violations = output_violations(text)
    if violations:  # still non-compliant after rewrite → hard fallback
        blocked = True
        text = ("I can't provide buy/sell/invest instructions — WealthPilot is an educational "
                "assistant. I can explain the relevant factors instead.")
    return {"text": ensure_disclaimer(text), "blocked": blocked, "violations": violations}
