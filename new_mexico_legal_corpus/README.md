# New Mexico Legal Corpus

This directory contains the expanded legal corpus for New Mexico, structured similarly to the Florida legal corpus.

## Files

- `statutes.jsonl`: Contains 42 key New Mexico statutes covering consumer protection, landlord-tenant law, construction defects, liens, foreclosure, insurance, and torts.
- `statute_aliases.jsonl`: Contains 42 alias entries for the statutes, facilitating pattern matching for various citation formats (e.g., NMSA 1978, N.M. Stat. Ann.).
- `nm_rules.jsonl`: Contains 8 key rules of civil procedure and court-specific rules.
- `COVERAGE_TARGETS.md`: A detailed list of equivalent NM statutes mapped to Florida practice areas.
- `SOURCES.md`: Official source links and citation guidance for New Mexico legal research.
- `validate_corpus.py`: Integrity validation script for the New Mexico corpus.

## Content Coverage

### Statutes
- **Consumer Protection**: Unfair Practices Act (Ch. 57, Art. 12)
- **Landlord-Tenant**: Uniform Owner-Resident Relations Act (Ch. 47, Art. 8)
- **Construction & Liens**: Indemnification (Ch. 56, Art. 7) and Mechanic's Liens (Ch. 48, Art. 2)
- **Foreclosure**: Mortgages and Redemption (Ch. 48, Art. 7 and Ch. 39, Art. 5)
- **Insurance & Torts**: Unfair Claims Practices (Ch. 59A, Art. 16) and Several Liability (Ch. 41, Art. 3A)
- **Statutes of Limitation**: Notes, Contracts, and Personal Injury (Ch. 37, Art. 1)

### Rules
- **Civil Procedure**: Rules 1-004, 1-009, 1-011, 1-012, 1-055, 1-056 NMRA
- **Magistrate Court**: Rule 2-401 NMRA
- **Metropolitan Court**: Rule 3-401 NMRA

## Data Format

Each file follows the JSONL (JSON Lines) format, where each line is a valid JSON object. This structure is designed for efficient line-by-line processing.

## Sources

The data was gathered from official New Mexico sources, including the New Mexico Supreme Court, the New Mexico Compilation Commission (NMOneSource), and authorized legal repositories (e.g., Justia, FindLaw).

**Last Verified**: December 24, 2025
