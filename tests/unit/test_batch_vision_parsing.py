"""Tests for identity-matched batch vision response parsing."""

from legal_portal.services.documents.file_processors.batch_vision_processor import (
    _parse_batch_response,
)

FILES = ["roof_damage.jpg", "water_stain.png", "invoice_scan.jpg"]


def _response(sections):
    return "\n\n".join(
        f"## IMAGE {i + 1}: {name}\n{body}" for i, (name, body) in enumerate(sections)
    )


class TestParseBatchResponse:
    def test_in_order_response(self):
        text = _response([
            ("roof_damage.jpg", "Shingle damage visible."),
            ("water_stain.png", "Ceiling stain, brown discoloration."),
            ("invoice_scan.jpg", "Invoice dated 2026-01-05."),
        ])
        result = _parse_batch_response(text, FILES)
        assert result == {
            "roof_damage.jpg": "Shingle damage visible.",
            "water_stain.png": "Ceiling stain, brown discoloration.",
            "invoice_scan.jpg": "Invoice dated 2026-01-05.",
        }

    def test_reordered_response_binds_by_filename_not_position(self):
        """The model swapping section order must not swap attributions."""
        text = _response([
            ("water_stain.png", "Ceiling stain."),
            ("roof_damage.jpg", "Shingle damage."),
            ("invoice_scan.jpg", "Invoice."),
        ])
        result = _parse_batch_response(text, FILES)
        assert result["roof_damage.jpg"] == "Shingle damage."
        assert result["water_stain.png"] == "Ceiling stain."

    def test_missing_section_reported_as_missing(self):
        text = _response([
            ("roof_damage.jpg", "Shingle damage."),
            ("invoice_scan.jpg", "Invoice."),
        ])
        result = _parse_batch_response(text, FILES)
        assert "water_stain.png" not in result
        assert len(result) == 2

    def test_unknown_filename_dropped(self):
        text = _response([
            ("roof_damage.jpg", "Shingle damage."),
            ("some_other_file.jpg", "Mystery content."),
        ])
        result = _parse_batch_response(text, FILES)
        assert result == {"roof_damage.jpg": "Shingle damage."}

    def test_decorated_filename_still_matches(self):
        text = '## IMAGE 1: **"roof_damage.jpg"**\nShingle damage.'
        result = _parse_batch_response(text, FILES)
        assert result == {"roof_damage.jpg": "Shingle damage."}

    def test_case_insensitive_match(self):
        text = "## IMAGE 1: ROOF_DAMAGE.JPG\nShingle damage."
        result = _parse_batch_response(text, FILES)
        assert result == {"roof_damage.jpg": "Shingle damage."}

    def test_duplicate_sections_keep_first(self):
        text = _response([
            ("roof_damage.jpg", "First description."),
            ("roof_damage.jpg", "Second description."),
        ])
        result = _parse_batch_response(text, FILES)
        assert result == {"roof_damage.jpg": "First description."}

    def test_wrong_numbering_is_irrelevant(self):
        """Renumbered markers still bind by echoed filename."""
        text = (
            "## IMAGE 7: water_stain.png\nCeiling stain.\n\n"
            "## IMAGE 2: roof_damage.jpg\nShingle damage."
        )
        result = _parse_batch_response(text, FILES)
        assert result["water_stain.png"] == "Ceiling stain."
        assert result["roof_damage.jpg"] == "Shingle damage."

    def test_empty_response(self):
        assert _parse_batch_response("", FILES) == {}
        assert _parse_batch_response("no markers here", FILES) == {}
