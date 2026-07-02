"""Tests for the letter HTML sanitizer chokepoint."""

from legal_portal.services.shared.html_sanitizer import sanitize_letter_html


class TestSanitizeLetterHtml:
    def test_empty_input(self):
        assert sanitize_letter_html("") == ""
        assert sanitize_letter_html(None) == ""

    def test_plain_letter_markup_passes_through(self):
        html = (
            "<h2>Findings</h2>"
            "<p>Dear <strong>Client</strong>,</p>"
            "<ul><li>Fact one</li><li>Fact two</li></ul>"
            "<table><thead><tr><th>Date</th></tr></thead>"
            "<tbody><tr><td>2026-01-01</td></tr></tbody></table>"
        )
        assert sanitize_letter_html(html) == html

    def test_script_tags_stripped(self):
        html = "<p>hello</p><script>alert(1)</script>"
        cleaned = sanitize_letter_html(html)
        assert "<script" not in cleaned
        assert "alert(1)" not in cleaned
        assert "<p>hello</p>" in cleaned

    def test_event_handlers_stripped(self):
        cleaned = sanitize_letter_html('<p onclick="steal()">hi</p>')
        assert "onclick" not in cleaned
        assert "hi" in cleaned

    def test_img_onerror_stripped(self):
        cleaned = sanitize_letter_html('<p><img src=x onerror="alert(1)">text</p>')
        assert "onerror" not in cleaned
        assert "<img" not in cleaned
        assert "text" in cleaned

    def test_javascript_urls_stripped(self):
        cleaned = sanitize_letter_html('<a href="javascript:alert(1)">link</a>')
        assert "javascript:" not in cleaned
        assert "link" in cleaned

    def test_safe_links_keep_href_and_gain_rel(self):
        cleaned = sanitize_letter_html('<a href="https://example.com">statute</a>')
        assert 'href="https://example.com"' in cleaned
        assert "noopener" in cleaned

    def test_semantic_classes_survive(self):
        html = '<div class="legal-letter"><p class="disclaimer">note</p></div>'
        cleaned = sanitize_letter_html(html)
        assert 'class="legal-letter"' in cleaned
        assert 'class="disclaimer"' in cleaned

    def test_citation_sup_marker_survives(self):
        html = 'Fla. Stat. § 501.204<sup class="citation-unverified">U</sup>'
        cleaned = sanitize_letter_html(html)
        assert '<sup class="citation-unverified">U</sup>' in cleaned

    def test_style_tags_stripped(self):
        cleaned = sanitize_letter_html("<style>body{display:none}</style><p>x</p>")
        assert "<style" not in cleaned
        assert "<p>x</p>" in cleaned

    def test_iframe_stripped(self):
        cleaned = sanitize_letter_html('<iframe src="https://evil.example"></iframe><p>x</p>')
        assert "<iframe" not in cleaned
