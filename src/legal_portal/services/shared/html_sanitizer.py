"""HTML sanitization for LLM-generated letter content.

markdown2 passes raw embedded HTML through untouched, so anything the model
emits (or that prompt-injected document content smuggles into the letter)
would reach the browser and the downloaded .html file unsanitized. Every
markdown->HTML conversion of model output must pass through
``sanitize_letter_html`` BEFORE trusted post-processing (semantic class
injection, DocumentFormatter templates) is applied.
"""

from __future__ import annotations

import nh3

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)

# Everything markdown2 emits for our letter content, plus <sup> (citation
# verification markers are injected pre-conversion as raw HTML).
_ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "dd",
    "del",
    "div",
    "dl",
    "dt",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "sup",
    "sub",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}

# class survives so the letter pipeline's semantic classes (legal-letter,
# disclaimer, call-to-action, citation markers) keep their styling.
_ALLOWED_ATTRIBUTES = {
    "*": {"class"},
    "a": {"href", "title", "class"},
    "td": {"align", "colspan", "rowspan", "class"},
    "th": {"align", "colspan", "rowspan", "class"},
}

_ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


def sanitize_letter_html(html: str) -> str:
    """Strip scripts, event handlers, and unknown markup from letter HTML.

    Args:
    ----
        html: HTML produced by converting model-generated markdown.

    Returns:
    -------
        HTML containing only the allowlisted tags/attributes above.

    """
    if not html:
        return ""

    cleaned = nh3.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        url_schemes=_ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
    )

    if len(cleaned) != len(html):
        logger.info(
            "Sanitized letter HTML",
            extra={
                "original_length": len(html),
                "sanitized_length": len(cleaned),
                "method": "sanitize_letter_html",
            },
        )

    return cleaned
