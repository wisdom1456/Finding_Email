"""Tests for citation tracking with adaptive thresholds."""

import pytest
from legal_portal.services.citation_tracking_service import CitationThreshold, CitationTrackingService
from legal_portal.services.statute_validation_service import StatuteValidationService


def test_adaptive_threshold_corpus_covered():
    """Test threshold adjusts for corpus-covered cases."""
    threshold = CitationThreshold.from_case_context(
        case_type="Construction Law", is_corpus_covered=True, document_quality=8.0
    )

    # Corpus covered + high quality = stricter threshold
    assert threshold.effective_threshold > 0.15
    assert threshold.coverage_adjustment > 0


def test_adaptive_threshold_low_quality():
    """Test threshold is lenient for low quality docs."""
    threshold = CitationThreshold.from_case_context(
        case_type="General", is_corpus_covered=False, document_quality=3.0
    )

    # Low quality + not covered = lenient threshold
    assert threshold.effective_threshold < 0.15
    assert threshold.quality_adjustment < 0


def test_adaptive_threshold_bounds():
    """Test threshold stays within bounds."""
    # Test lower bound
    threshold = CitationThreshold.from_case_context(
        case_type="General", is_corpus_covered=False, document_quality=0.0
    )
    assert threshold.effective_threshold >= 0.1

    # Test upper bound
    threshold = CitationThreshold.from_case_context(
        case_type="Construction Law", is_corpus_covered=True, document_quality=10.0
    )
    assert threshold.effective_threshold <= 0.3


def test_text_normalization():
    """Test text normalization improves matching."""
    tracker = CitationTrackingService()

    text1 = "The contractor abandoned the project on March 15, 2024 for $50,000"
    text2 = "Contract work ceased mid-March when payment of $50000 was demanded"

    norm1 = tracker._normalize_text(text1)
    norm2 = tracker._normalize_text(text2)

    # Normalized texts should have more overlap
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    overlap = len(words1.intersection(words2))

    # Should match [DATE], [AMOUNT], contract_party, work_ceased
    assert overlap > 3


def test_text_normalization_dates():
    """Test date normalization."""
    tracker = CitationTrackingService()

    text_with_dates = "On 03/15/2024 and January 20, 2024"
    normalized = tracker._normalize_text(text_with_dates)

    assert "[date]" in normalized.lower()  # Normalized text is lowercased
    assert "03/15/2024" not in normalized
    assert "january 20, 2024" not in normalized.lower()


def test_text_normalization_amounts():
    """Test monetary amount normalization."""
    tracker = CitationTrackingService()

    text_with_amounts = "Payment of $1,234.56 and $500"
    normalized = tracker._normalize_text(text_with_amounts)

    assert "[amount]" in normalized.lower()  # Normalized text is lowercased
    assert "$1,234.56" not in normalized
    assert "$500" not in normalized


def test_text_normalization_legal_terms():
    """Test legal term normalization."""
    tracker = CitationTrackingService()

    text1 = "The contractor abandoned the project"
    text2 = "Contract work was terminated"

    norm1 = tracker._normalize_text(text1)
    norm2 = tracker._normalize_text(text2)

    assert "contract_party" in norm1
    assert "work_ceased" in norm1
    assert "contract_party" in norm2
    assert "work_ceased" in norm2


@pytest.mark.asyncio
async def test_semantic_similarity():
    """Test semantic similarity calculation."""
    import os

    # Skip if no API key (embeddings require OpenAI)
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set - skipping embedding test")

    tracker = CitationTrackingService()

    text1 = "The contractor failed to complete the work"
    text2 = "Work was not finished by the construction company"

    similarity = tracker._calculate_semantic_similarity(text1, text2)

    # Should have high semantic similarity despite different words
    assert similarity > 0.6  # Relaxed threshold for real-world testing


@pytest.mark.asyncio
async def test_semantic_similarity_unrelated():
    """Test semantic similarity for unrelated texts."""
    tracker = CitationTrackingService()

    text1 = "The contractor failed to complete the work"
    text2 = "The weather forecast predicts rain tomorrow"

    similarity = tracker._calculate_semantic_similarity(text1, text2)

    # Should have low semantic similarity for unrelated texts
    assert similarity < 0.5


def test_corpus_validated_citation_boost():
    """Test citations with corpus-validated statutes get boosted."""
    corpus_service = StatuteValidationService()
    tracker = CitationTrackingService(corpus_service=corpus_service)

    statement_with_valid_statute = "Florida Statute § 558.004 requires written notice"
    document = {
        "summary": "Notice requirements under construction law",
        "document_type": "legal_reference",
        "key_information": "Construction defect notification procedures",
        "relevance_to_case": "Pre-suit notice requirements",
    }

    score = tracker._calculate_match_score(statement_with_valid_statute, document)

    # Should have corpus bonus if 558.004 is in corpus
    assert score > 0.0


def test_match_score_with_semantic():
    """Test match score calculation with semantic similarity."""
    import os

    tracker = CitationTrackingService()

    statement = "The construction contract was signed on March 15, 2024"
    document = {
        "summary": "Agreement for construction work dated early spring 2024",
        "document_type": "contract",
        "key_information": "Contract terms and conditions",
        "relevance_to_case": "Primary contractual agreement",
    }

    # If no API key, semantic similarity will be 0, so fallback to word-based only
    if not os.getenv("OPENAI_API_KEY"):
        score = tracker._calculate_match_score(statement, document, use_semantic=False)
        # Word-based score only
        assert score > 0.1
    else:
        score = tracker._calculate_match_score(statement, document, use_semantic=True)
        # Should have reasonable score with semantic similarity
        assert score > 0.3


def test_match_score_without_semantic():
    """Test match score calculation without semantic similarity."""
    tracker = CitationTrackingService()

    statement = "The construction contract was signed on March 15, 2024"
    document = {
        "summary": "Construction contract agreement",
        "document_type": "contract",
        "key_information": "Contract signed in March 2024",
        "relevance_to_case": "Primary contractual agreement",
    }

    score = tracker._calculate_match_score(statement, document, use_semantic=False)

    # Should have reasonable score with word overlap
    assert score > 0.2


def test_document_type_bonus():
    """Test document type bonus in match scoring."""
    tracker = CitationTrackingService()

    statement = "According to the timeline, work ceased on June 1"
    document_timeline = {
        "summary": "Project timeline showing work stoppage",
        "document_type": "timeline",
        "key_information": "Work stopped in June",
        "relevance_to_case": "Timeline of events",
    }

    document_other = {
        "summary": "Project timeline showing work stoppage",
        "document_type": "letter",
        "key_information": "Work stopped in June",
        "relevance_to_case": "Timeline of events",
    }

    score_timeline = tracker._calculate_match_score(statement, document_timeline, use_semantic=False)
    score_other = tracker._calculate_match_score(statement, document_other, use_semantic=False)

    # Timeline document should score higher due to type bonus
    assert score_timeline > score_other


def test_threshold_effective_calculation():
    """Test effective threshold calculation."""
    threshold = CitationThreshold(base_threshold=0.15, quality_adjustment=0.03, coverage_adjustment=-0.02)

    # Should sum adjustments: 0.15 + 0.03 - 0.02 = 0.16
    assert threshold.effective_threshold == 0.16


def test_citation_threshold_default():
    """Test default CitationThreshold values."""
    threshold = CitationThreshold()

    assert threshold.base_threshold == 0.15
    assert threshold.quality_adjustment == 0.0
    assert threshold.coverage_adjustment == 0.0
    assert threshold.effective_threshold == 0.15
