"""Legal corpus documentation endpoints.

Serves markdown content from florida_legal_corpus and new_mexico_legal_corpus
for in-app viewing. Project root is resolved relative to this file; override
with CORPUS_BASE_PATH env var if needed (e.g. on Vercel).
"""

import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter()

# Project root: from .../src/legal_portal/api/routes/corpus.py -> repo root
# parents: 0=api, 1=legal_portal, 2=src, 3=repo root
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[3]

# Allowed jurisdiction slugs and their directory names
CORPUS_DIRS = {
    "florida": "florida_legal_corpus",
    "new-mexico": "new_mexico_legal_corpus",
}

# Rules file name per jurisdiction
CORPUS_RULES_FILE = {
    "florida": "florida_refs.jsonl",
    "new-mexico": "nm_rules.jsonl",
}

# Primary doc to serve per jurisdiction
DEFAULT_DOC = "README.md"
STATUTES_FILE = "statutes.jsonl"


def _get_base_path() -> Path:
    base = os.getenv("CORPUS_BASE_PATH")
    if base:
        return Path(base)
    return _REPO_ROOT


def _load_jsonl(file_path: Path) -> list[dict]:
    """Load a JSONL file; return list of dicts. Return empty list if file missing or invalid."""
    if not file_path.is_file():
        return []
    result = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                result.append(json.loads(line))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to load JSONL %s: %s", file_path, e)
        return []
    return result


def _normalize_statute(raw: dict) -> dict:
    """Normalize a statute record for the frontend (attorney-friendly keys)."""
    citation = raw.get("citation_text") or raw.get("id", "")
    return {
        "id": raw.get("id", ""),
        "type": "statute",
        "citation": citation,
        "title": raw.get("title", ""),
        "text": raw.get("text", ""),
        "summary": raw.get("summary", ""),
        "source_urls": raw.get("source_urls") or [],
        "effective_date": raw.get("effective_date", ""),
        "source_doc_version": raw.get("source_doc_version", ""),
    }


def _normalize_rule(raw: dict) -> dict:
    """Normalize a rule record for the frontend (attorney-friendly keys)."""
    citation = raw.get("citation_key") or raw.get("citation_text") or raw.get("id", "")
    return {
        "id": raw.get("id", ""),
        "type": "rule",
        "citation": citation,
        "title": raw.get("title", ""),
        "text": raw.get("text", ""),
        "summary": raw.get("summary", ""),
        "source_urls": raw.get("source_urls") or [],
        "effective_date": raw.get("effective_date", ""),
        "source_doc_version": raw.get("source_doc_version", ""),
    }


@router.get("/{jurisdiction}/entries")
async def get_corpus_entries(jurisdiction: str) -> dict:
    """Return all statutes and rules for a jurisdiction with full text.

    Path parameter jurisdiction must be 'florida' or 'new-mexico'.
    Returns JSON: { "statutes": [...], "rules": [...] } with attorney-friendly keys.
    """
    if jurisdiction not in CORPUS_DIRS:
        raise HTTPException(status_code=404, detail="Unknown jurisdiction")

    base = _get_base_path()
    dir_name = CORPUS_DIRS[jurisdiction]
    corpus_dir = base / dir_name

    statutes_path = corpus_dir / STATUTES_FILE
    rules_path = corpus_dir / CORPUS_RULES_FILE[jurisdiction]

    statutes_raw = _load_jsonl(statutes_path)
    rules_raw = _load_jsonl(rules_path)

    statutes = [_normalize_statute(s) for s in statutes_raw]
    rules = [_normalize_rule(r) for r in rules_raw]

    # Sort by citation for stable, readable order
    statutes.sort(key=lambda x: (x["citation"], x["id"]))
    rules.sort(key=lambda x: (x["citation"], x["id"]))

    return {"statutes": statutes, "rules": rules}


@router.get("/{jurisdiction}")
async def get_corpus_doc(jurisdiction: str) -> dict:
    """Return markdown content for a jurisdiction's legal corpus README.

    Path parameter jurisdiction must be 'florida' or 'new-mexico'.
    Returns JSON: { "markdown": "<content>" }. 404 if jurisdiction unknown or file missing.
    """
    if jurisdiction not in CORPUS_DIRS:
        raise HTTPException(status_code=404, detail="Unknown jurisdiction")

    base = _get_base_path()
    dir_name = CORPUS_DIRS[jurisdiction]
    readme_path = base / dir_name / DEFAULT_DOC

    if not readme_path.is_file():
        logger.warning("Corpus file not found: %s", readme_path)
        raise HTTPException(status_code=404, detail="Corpus documentation not available")

    try:
        content = readme_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.exception("Failed to read corpus file: %s", readme_path)
        raise HTTPException(status_code=500, detail="Failed to load corpus") from e

    return {"markdown": content}
