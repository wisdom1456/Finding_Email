"""Legal corpus documentation endpoints.

Serves markdown content from florida_legal_corpus and new_mexico_legal_corpus
for in-app viewing. Project root is resolved relative to this file; override
with CORPUS_BASE_PATH env var if needed (e.g. on Vercel).
"""

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

# Primary doc to serve per jurisdiction
DEFAULT_DOC = "README.md"


def _get_base_path() -> Path:
    base = os.getenv("CORPUS_BASE_PATH")
    if base:
        return Path(base)
    return _REPO_ROOT


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
