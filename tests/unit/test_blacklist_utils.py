from src.legal_portal.utils.blacklist import (
    derive_blacklist_rule,
    is_name_blacklisted,
    to_canonical_blacklist_term,
)


def test_derive_blacklist_rule_removes_parenthetical_suffixes():
    value = "Attorney Representation Agreement (Metlife ELIGIBILITY ID) (Mary Ann Rivera).pdf"
    assert derive_blacklist_rule(value) == "attorney representation agreement"


def test_canonical_term_is_extension_and_case_insensitive():
    value = "What to Expect in a Demand (MC).PDF"
    assert to_canonical_blacklist_term(value) == "what to expect in a demand"


def test_is_name_blacklisted_matches_similar_parenthetical_variants():
    blacklist = [
        "Attorney Representation Agreement (Metlife ELIGIBILITY ID) (Mary Ann Rivera).pdf",
    ]
    candidate = "Attorney Representation Agreement (Metlife ELIGIBILITY ID) (Clifton Price).pdf"
    assert is_name_blacklisted(candidate, blacklist) is True


def test_is_name_blacklisted_matches_simple_prefix_rules():
    blacklist = ["Documents Needed to Proceed"]
    candidate = "Documents Needed to Proceed - Updated.pdf"
    assert is_name_blacklisted(candidate, blacklist) is True


def test_is_name_blacklisted_does_not_match_unrelated_documents():
    blacklist = ["What to Expect in a Demand"]
    candidate = "Medical Bill Summary.pdf"
    assert is_name_blacklisted(candidate, blacklist) is False
