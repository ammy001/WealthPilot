"""Ingest USER-PROVIDED reference material into the investor-education corpus.

This is a SCAFFOLD. It reads a manifest (data/reference/education_sources.json)
and converts local files you already have a right to use — PDF, .md, or .txt —
into cleaned markdown notes under corpus/education/, where the RAG chunker
(rag/chunk.py) will pick them up automatically (it splits on `## ` headings and
takes the title from the leading `# ` H1, so every note we write starts with an
H1 and uses `## ` sections).

Design / guardrails
-------------------
- NO live web scraping. By default the script only touches LOCAL files listed in
  the manifest. A `--allow-network` path exists but is DISABLED by default; it is
  clearly marked, prints a Terms-of-Service warning, and must be opted into. Only
  fetch URLs you are permitted to use under their ToS. Do not add scraped or
  copyrighted third-party content to the corpus.
- Descriptive only. This tool copies/normalizes text; it does not add opinions,
  ratings, or directives. Curate the source material to keep the corpus
  educational and non-directive.
- Dry-run by default. Without `--write` the script only PRINTS what it would do,
  so you can review before anything is written.
- PDFs are parsed with pypdf (already a project dependency).

Usage
-----
    # Preview what would be ingested from local files in the manifest:
    python ingest/build_education_extra.py

    # Actually write the normalized markdown notes:
    python ingest/build_education_extra.py --write

    # Opt into the (default-disabled) network path for allow-listed URLs:
    python ingest/build_education_extra.py --write --allow-network

    # Use a different manifest:
    python ingest/build_education_extra.py --manifest path/to/manifest.json
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MANIFEST = os.path.join(ROOT, "data", "reference", "education_sources.json")
OUT_DIR = os.path.join(ROOT, "corpus", "education")
FOOTER = "> Educational information only. Not investment advice."


def _resolve(path):
    """Resolve a manifest path (absolute, or relative to the repo root)."""
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


def _slugify(name):
    """Turn an arbitrary name/title into a safe filename stem."""
    stem = os.path.splitext(os.path.basename(name))[0]
    stem = re.sub(r"[^a-zA-Z0-9]+", "-", stem).strip("-").lower()
    return stem or "education-extra"


def _titleize(slug):
    """Fallback H1 title derived from a slug (strip any leading number prefix)."""
    words = re.sub(r"^\d+[-_]?", "", slug).replace("-", " ").replace("_", " ").strip()
    return words.title() or "Education Note"


def _clean_text(text):
    """Light normalization: collapse runs of blank lines and trailing spaces.

    Deliberately conservative — it does not rewrite content, only tidies
    whitespace so the chunker splits cleanly.
    """
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    out, blanks = [], 0
    for ln in lines:
        if ln.strip():
            blanks = 0
            out.append(ln)
        else:
            blanks += 1
            if blanks <= 1:
                out.append("")
    return "\n".join(out).strip()


def _read_pdf(path):
    """Extract text from a PDF using pypdf (page by page)."""
    from pypdf import PdfReader
    reader = PdfReader(path)
    parts = []
    for page in reader.pages:
        t = (page.extract_text() or "").strip()
        if t:
            parts.append(t)
    return "\n\n".join(parts)


def _read_text_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _to_markdown(raw, title):
    """Wrap normalized raw text as a corpus-style education note.

    Ensures a leading `# <title>` H1 and at least one `## ` section so the note
    chunks cleanly, and appends the standard educational footer. If the source
    already contains an H1 / `## ` sections (e.g. a .md file), it is preserved.
    """
    body = _clean_text(raw)
    has_h1 = bool(re.search(r"^#\s+", body, re.M))
    has_section = bool(re.search(r"^##\s+", body, re.M))

    parts = []
    if not has_h1:
        parts.append(f"# {title}\n")
    if not has_section:
        # Give the chunker at least one `## ` section to split on.
        parts.append("## Overview\n")
    parts.append(body)
    md = "\n".join(parts).strip()
    if FOOTER not in md:
        md += f"\n\n{FOOTER}\n"
    return md


def _load_manifest(path):
    if not os.path.exists(path):
        print(f"[!] manifest not found: {path}")
        return {"local_files": [], "urls": []}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("local_files", [])
    data.setdefault("urls", [])
    return data


def ingest_local_files(entries, write):
    """Convert each listed local file to a normalized markdown note."""
    done = 0
    for entry in entries:
        src = _resolve(entry.get("path", ""))
        if not entry.get("path"):
            print("[skip] local_files entry missing 'path'")
            continue
        if not os.path.exists(src):
            print(f"[skip] not found: {src}")
            continue
        ext = os.path.splitext(src)[1].lower()
        slug = entry.get("slug") or _slugify(src)
        title = entry.get("title") or _titleize(slug)
        dest = os.path.join(OUT_DIR, f"{slug}.md")
        try:
            if ext == ".pdf":
                raw = _read_pdf(src)
            elif ext in (".md", ".txt"):
                raw = _read_text_file(src)
            else:
                print(f"[skip] unsupported type {ext}: {src}")
                continue
        except Exception as e:
            print(f"[skip] failed to read {src}: {type(e).__name__}: {e}")
            continue

        if not raw.strip():
            print(f"[skip] no extractable text: {src}")
            continue

        md = _to_markdown(raw, title)
        if write:
            os.makedirs(OUT_DIR, exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(md)
            print(f"[write] {src}  ->  {dest}  ({len(md)} chars)")
        else:
            print(f"[dry-run] would write {src}  ->  {dest}  ({len(md)} chars)")
        done += 1
    return done


def ingest_urls(entries, write, allow_network):
    """Ingest allow-listed URLs. DISABLED BY DEFAULT.

    This path is intentionally opt-in via --allow-network. Fetching web content
    can violate a site's Terms of Service and copyright; only enable it for URLs
    you are permitted to use. When disabled (the default), this just reports what
    it *would* fetch and does nothing over the network.
    """
    if not entries:
        return 0
    if not allow_network:
        print(f"[network-disabled] {len(entries)} URL(s) in manifest were NOT fetched "
              "(pass --allow-network to opt in, and only for ToS-permitted sources):")
        for entry in entries:
            print(f"    - would consider: {entry.get('url', '<missing url>')}")
        return 0

    # --- Opt-in network path (disabled by default) ---------------------------
    print("[!] --allow-network enabled. WARNING: fetching web content may violate a "
          "source's Terms of Service or copyright. Only proceed for sources you are "
          "permitted to use. This does not perform live scraping of arbitrary sites.")
    try:
        import requests  # imported lazily so the default path has no network dep
    except ImportError:
        print("[!] 'requests' is not installed; cannot fetch URLs. Aborting network path.")
        return 0

    done = 0
    for entry in entries:
        url = entry.get("url")
        if not url:
            print("[skip] urls entry missing 'url'")
            continue
        slug = entry.get("slug") or _slugify(url)
        title = entry.get("title") or _titleize(slug)
        dest = os.path.join(OUT_DIR, f"{slug}.md")
        try:
            resp = requests.get(url, timeout=30, headers={"User-Agent": "WealthPilot-education-ingest"})
            resp.raise_for_status()
            raw = resp.text
        except Exception as e:
            print(f"[skip] fetch failed {url}: {type(e).__name__}: {e}")
            continue
        # NOTE: raw HTML is not stripped here — a curation/HTML-to-text step should
        # be added before enabling this in practice. Left as a scaffold hook.
        md = _to_markdown(raw, title)
        if write:
            os.makedirs(OUT_DIR, exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(md)
            print(f"[write] {url}  ->  {dest}  ({len(md)} chars)")
        else:
            print(f"[dry-run] would write {url}  ->  {dest}  ({len(md)} chars)")
        done += 1
    return done


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ingest user-provided reference files into corpus/education/.")
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST, help="Path to the sources manifest JSON.")
    ap.add_argument("--write", action="store_true", help="Actually write notes (default: dry-run/preview only).")
    ap.add_argument("--allow-network", action="store_true",
                    help="Opt in to fetching allow-listed URLs (DISABLED by default; respect source ToS).")
    args = ap.parse_args(argv)

    print(f"manifest : {args.manifest}")
    print(f"out dir  : {OUT_DIR}")
    print(f"mode     : {'WRITE' if args.write else 'dry-run (preview)'}")
    print(f"network  : {'ALLOWED' if args.allow_network else 'disabled (default)'}")
    print("-" * 60)

    manifest = _load_manifest(args.manifest)
    n_local = ingest_local_files(manifest.get("local_files", []), args.write)
    n_url = ingest_urls(manifest.get("urls", []), args.write, args.allow_network)

    print("-" * 60)
    action = "wrote" if args.write else "would write"
    print(f"done: {action} {n_local + n_url} note(s)  (local={n_local}, url={n_url})")
    if not manifest.get("local_files") and not manifest.get("urls"):
        print("manifest has no sources yet — add entries under 'local_files' to ingest your own docs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
