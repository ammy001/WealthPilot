"""Turn the corpus into retrieval chunks with citation metadata.

Chunking strategy (per doc type):
  - markdown → split on `## ` sections; the doc title (+ ticker for companies) is
    prepended to every chunk so each metric stays tied to its entity (numerical fidelity).
  - PDF → grouped ~1500-char windows with page-range locators; large reference PDFs capped.

Each chunk dict: doc_id, doc_type, entity, title, section, chunk_text, source, url, as_of, locator.
"""
import datetime
import glob
import os
import re

from pypdf import PdfReader

CORPUS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "corpus")
TODAY = datetime.date.today().isoformat()
MAX_CHARS = 2000  # split a section if longer

# Big reference PDFs: cap pages to the useful front matter.
PDF_MAX_PAGES = {"nifty_index_methodology": 40}

MD_DIRS = [("companies", "company"), ("education", "education"),
           ("market", "market"), ("reports", "report")]
PDF_DIRS = [("funds", "fund"), ("reports", "report")]


def _asof(text):
    m = re.search(r"As of:\*{0,2}\s*(\d{4}-\d{2}-\d{2})", text)
    return m.group(1) if m else TODAY


def _h1(text, fallback):
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else fallback


def _split_sections(text):
    """Yield (section_title, body) splitting markdown on '## ' headings."""
    title, buf = "Overview", []
    for ln in text.splitlines():
        if ln.startswith("## "):
            if buf:
                yield title, "\n".join(buf).strip()
            title, buf = ln[3:].strip(), []
        elif ln.startswith("# "):
            continue
        else:
            buf.append(ln)
    if buf:
        yield title, "\n".join(buf).strip()


def _wrap(body, limit=MAX_CHARS):
    """Split an over-long body on blank lines into <=limit pieces."""
    if len(body) <= limit:
        return [body]
    out, cur = [], ""
    for para in body.split("\n"):
        if len(cur) + len(para) + 1 > limit and cur:
            out.append(cur.strip())
            cur = ""
        cur += para + "\n"
    if cur.strip():
        out.append(cur.strip())
    return out


def _markdown_chunks():
    for sub, dtype in MD_DIRS:
        for path in sorted(glob.glob(os.path.join(CORPUS, sub, "*.md"))):
            text = open(path, encoding="utf-8").read()
            stem = os.path.splitext(os.path.basename(path))[0]
            title = _h1(text, stem)
            entity = stem if dtype == "company" else None
            asof = _asof(text)
            src = "Screener.in, Yahoo Finance, NSE" if dtype == "company" else "WealthPilot corpus"
            for sect, body in _split_sections(text):
                if not body:
                    continue
                prefix = (f"Company: {title} — {sect}" if dtype == "company"
                          else f"{title} — {sect}")
                for piece in _wrap(body):
                    yield dict(doc_id=f"{dtype}:{stem}", doc_type=dtype, entity=entity,
                               title=title, section=sect,
                               chunk_text=f"{prefix}\n\n{piece}",
                               source=src, url=None, as_of=asof, locator=sect)


def _pdf_chunks():
    seen = set()
    for sub, dtype in PDF_DIRS:
        for path in sorted(glob.glob(os.path.join(CORPUS, sub, "*.pdf"))):
            stem = os.path.splitext(os.path.basename(path))[0]
            if stem in seen:
                continue
            seen.add(stem)
            reader = PdfReader(path)
            maxp = PDF_MAX_PAGES.get(stem, len(reader.pages))
            buf, start = "", 1
            for i, page in enumerate(reader.pages[:maxp], 1):
                t = (page.extract_text() or "").strip()
                if not t:
                    continue
                buf += "\n" + t
                if len(buf) >= 1500:
                    loc = f"p{start}-{i}"
                    yield dict(doc_id=f"{dtype}:{stem}", doc_type=dtype, entity=None,
                               title=stem, section=loc,
                               chunk_text=f"{stem} ({loc})\n\n{buf.strip()[:2200]}",
                               source=stem, url=None, as_of=TODAY, locator=loc)
                    buf, start = "", i + 1
            if buf.strip():
                loc = f"p{start}-{maxp}"
                yield dict(doc_id=f"{dtype}:{stem}", doc_type=dtype, entity=None,
                           title=stem, section=loc,
                           chunk_text=f"{stem} ({loc})\n\n{buf.strip()[:2200]}",
                           source=stem, url=None, as_of=TODAY, locator=loc)


def build_all():
    return list(_markdown_chunks()) + list(_pdf_chunks())


if __name__ == "__main__":
    chunks = build_all()
    from collections import Counter
    print("total chunks:", len(chunks))
    print("by type:", dict(Counter(c["doc_type"] for c in chunks)))
    print("sample:", chunks[0]["chunk_text"][:160].replace("\n", " "))
