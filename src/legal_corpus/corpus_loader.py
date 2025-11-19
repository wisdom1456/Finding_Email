import json
import os
from typing import Any, Dict, List

import streamlit as st

# --- Type Definitions ---
Statute = Dict[str, Any]
Rule = Dict[str, Any]
Alias = Dict[str, Any]
Corpus = Dict[str, Dict[str, Statute | Rule]]

# --- Path Configuration ---
CORPUS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "florida_legal_corpus")
STATUTES_FILE = os.path.join(CORPUS_DIR, "statutes.jsonl")
RULES_FILE = os.path.join(CORPUS_DIR, "florida_refs.jsonl")
ALIASES_FILE = os.path.join(CORPUS_DIR, "statute_aliases.jsonl")


# --- Helper Functions ---
def _load_jsonl(file_path: str) -> List[Dict[str, Any]]:
    """Load a JSON Lines file."""
    if not os.path.exists(file_path):
        st.error(f"Corpus file not found: {file_path}")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


# --- Main Corpus Loading and Indexing ---
@st.cache_resource
def load_and_index_corpus() -> Corpus:
    """Load and index the Florida Legal Corpus from JSONL files.

    The data is indexed by citation_text for fast lookups. The entire
    corpus is cached in memory using Streamlit's cache_resource for
    high performance.

    Returns
    -------
        A dictionary containing the indexed statutes and rules.

    """
    statutes_data = _load_jsonl(STATUTES_FILE)
    rules_data = _load_jsonl(RULES_FILE)

    corpus: Corpus = {
        "statutes": {item["citation_text"]: item for item in statutes_data},
        "rules": {item["citation_key"]: item for item in rules_data},
    }

    return corpus


# --- Search and Retrieval Functions ---
def find_statute_by_keyword(corpus: Corpus, keyword: str) -> List[Statute]:
    """Find statutes that contain a keyword in their text, title, or tags.

    Args:
    ----
        corpus: The loaded legal corpus.
        keyword: The keyword to search for (case-insensitive).

    Returns:
    -------
        A list of matching statutes.

    """
    keyword = keyword.lower()
    results = []
    for statute in corpus.get("statutes", {}).values():
        in_text = keyword in statute.get("text", "").lower()
        in_title = keyword in statute.get("title", "").lower()
        in_tags = any(keyword in tag.lower() for tag in statute.get("tags", []))

        if in_text or in_title or in_tags:
            results.append(statute)

    return results


def get_statute_by_citation(corpus: Corpus, citation: str) -> Statute | None:
    """Retrieve a statute by its exact citation text.

    Args:
    ----
        corpus: The loaded legal corpus.
        citation: The exact citation (e.g., "Fla. Stat. § 83.51").

    Returns:
    -------
        The statute dictionary or None if not found.

    """
    return corpus.get("statutes", {}).get(citation)


if __name__ == "__main__":
    # --- Example Usage and Verification ---
    st.set_page_config(layout="wide")
    st.title("Florida Legal Corpus Loader")

    # Load the corpus
    legal_corpus = load_and_index_corpus()

    st.header("Corpus Overview")
    st.metric("Statutes Loaded", len(legal_corpus["statutes"]))
    st.metric("Rules Loaded", len(legal_corpus["rules"]))

    st.header("Statute Search")
    search_term = st.text_input("Enter keyword to search statutes (e.g., 'habitability', 'landlord'):")

    if search_term:
        found_statutes = find_statute_by_keyword(legal_corpus, search_term)
        st.write(f"Found {len(found_statutes)} statutes for '{search_term}':")
        for s in found_statutes:
            with st.expander(f"{s['citation_text']} - {s['title']}"):
                st.json(s)

    st.header("Direct Citation Lookup")
    citation_to_find = st.selectbox(
        "Select a statute to look up:", options=list(legal_corpus["statutes"].keys())
    )
    if citation_to_find:
        statute = get_statute_by_citation(legal_corpus, citation_to_find)
        if statute:
            st.write("Found Statute:")
            st.json(statute)
        else:
            st.warning("Statute not found.")
