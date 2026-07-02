"""Choose the best intake document among multiple 'intake'-labeled candidates.

One LLM call comparing extracted-text snippets. Any failure returns None and
the caller falls back to the mechanical pick — selection must never block or
break an analysis.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

SNIPPET_CHARS = 3500

PROMPT_TEMPLATE = """You are selecting the OFFICIAL CLIENT INTAKE DOCUMENT for a legal case.
Below are {n} candidate documents, each with a snippet of its extracted text.
Judge each on: client identity detail, case narrative, key dates, damages/amounts,
contact information, and overall completeness as an intake record.

{candidate_blocks}

Respond with ONLY a JSON object:
{{"chosen_doc_id": "<id>", "reasoning": "<1-2 sentences>",
  "scores": [{{"doc_id": "<id>", "score": <0-100>, "note": "<short>"}}]}}"""


@dataclass
class IntakeSelection:
    chosen_doc_id: str
    reasoning: str
    scores: list = field(default_factory=list)


def select_intake_document(candidates, supabase, openai_client) -> Optional[IntakeSelection]:
    if not candidates or len(candidates) < 2:
        return None
    try:
        ids = [c["id"] for c in candidates]
        rows = (
            supabase.table("documents")
            .select("id, extracted_text")
            .in_("id", ids)
            .execute()
        )
        text_by_id = {r["id"]: (r.get("extracted_text") or "") for r in (rows.data or [])}

        blocks = []
        for c in candidates:
            snippet = text_by_id.get(c["id"], "").strip()[:SNIPPET_CHARS]
            blocks.append(
                f"--- doc_id: {c['id']}\nfilename: {c.get('file_name', '?')}\n"
                f"type: {c.get('file_type', '?')}\ntext snippet:\n{snippet or '(no extracted text)'}\n"
            )
        prompt = PROMPT_TEMPLATE.format(n=len(candidates), candidate_blocks="\n".join(blocks))

        model = openai_client.get_preferred_model("document_analysis", "gpt-5.4-mini")

        # NOTE: adapted to the real OpenAIClient contract, which differs from
        # a naive OpenAI-SDK-shaped reference:
        #   - create_chat_completion(...) returns a dict {"content", "usage",
        #     "model"} (not a `.choices[0].message` object), and it RAISES on
        #     failure instead of returning a success=False envelope — the
        #     surrounding try/except here is what turns that into None.
        #   - parse_json_response(content) returns
        #     {"success": bool, "data": ..., "error": ...}, not the raw
        #     parsed payload — we must unwrap it and check "success".
        response = openai_client.create_chat_completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        content = response["content"]

        parsed = openai_client.parse_json_response(content)
        if not parsed.get("success"):
            logger.warning(f"[INTAKE-SELECT] LLM response was not valid JSON: {parsed.get('error')}")
            return None
        payload: dict[str, Any] = parsed.get("data") or {}

        chosen = payload.get("chosen_doc_id")
        if chosen not in set(ids):
            logger.warning(f"[INTAKE-SELECT] LLM chose unknown doc id {chosen!r}; falling back")
            return None
        return IntakeSelection(
            chosen_doc_id=chosen,
            reasoning=str(payload.get("reasoning", ""))[:500],
            scores=payload.get("scores") or [],
        )
    except Exception as e:
        logger.warning(f"[INTAKE-SELECT] selection failed, falling back to mechanical pick: {e}")
        return None
