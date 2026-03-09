import { describe, it, expect } from 'vitest';
import { computeAttentionScore, getAttentionNeeds, sortByAttention } from './documentSorting';

describe('computeAttentionScore', () => {
    it('returns 0 for fully enriched, signed, high-quality document', () => {
        const doc = {
            signature_expected: true,
            signed_status: 'signed',
            document_type_label: 'Contract',
            metadata: {
                quality_score: 8,
                registry: {
                    quick_facts_raw: { dates: ['2024-01-01'], amounts: [] },
                },
                attorney_enrichment: {
                    key_facts: { date: '2024-01-01' },
                },
            },
        };
        expect(computeAttentionScore(doc)).toBe(0);
    });

    it('scores +50 for missing expected signature', () => {
        const doc = {
            signature_expected: true,
            signed_status: 'not_detected',
            document_type_label: 'Contract',
            metadata: {
                quality_score: 8,
                registry: {
                    quick_facts_raw: { dates: ['2024-01-01'], amounts: [] },
                },
                attorney_enrichment: {
                    key_facts: { date: '2024-01-01' },
                },
            },
        };
        expect(computeAttentionScore(doc)).toBe(50);
    });

    it('scores +40 for low OCR quality', () => {
        const doc = {
            signature_expected: true,
            signed_status: 'signed',
            document_type_label: 'Contract',
            metadata: {
                quality_score: 3,  // < 5
                registry: {
                    quick_facts_raw: { dates: ['2024-01-01'], amounts: [] },
                },
                attorney_enrichment: {
                    key_facts: { date: '2024-01-01' },
                },
            },
        };
        expect(computeAttentionScore(doc)).toBe(40);
    });

    it('scores +30 for missing document type label', () => {
        const doc = {
            signature_expected: true,
            signed_status: 'signed',
            // document_type_label intentionally missing
            metadata: {
                quality_score: 8,
                registry: {
                    quick_facts_raw: { dates: ['2024-01-01'], amounts: [] },
                },
                attorney_enrichment: {
                    key_facts: { date: '2024-01-01' },
                },
            },
        };
        expect(computeAttentionScore(doc)).toBe(30);
    });

    it('scores +20 for missing key facts (no raw, no ai, no attorney)', () => {
        const doc = {
            signature_expected: true,
            signed_status: 'signed',
            document_type_label: 'Contract',
            metadata: {
                quality_score: 8,
                registry: {},
                attorney_enrichment: {},
            },
        };
        expect(computeAttentionScore(doc)).toBe(20);
    });

    it('does NOT score +10 for missing attorney notes (notes penalty removed)', () => {
        const doc = {
            signature_expected: true,
            signed_status: 'signed',
            document_type_label: 'Contract',
            metadata: {
                quality_score: 8,
                registry: {
                    quick_facts_raw: { dates: ['2024-01-01'], amounts: [] },
                },
                attorney_enrichment: {
                    key_facts: { date: '2024-01-01' },
                    // attorney_notes intentionally missing — should NOT add penalty
                },
            },
        };
        expect(computeAttentionScore(doc)).toBe(0);
    });

    it('considers quick_facts_raw as having facts (no +20)', () => {
        const doc = {
            signed_status: 'signed',
            document_type_label: 'Contract',
            metadata: {
                quality_score: 8,
                registry: {
                    quick_facts_raw: { dates: ['03/15/2025'], amounts: ['$50,000'] },
                },
                attorney_enrichment: {},
            },
        };
        expect(computeAttentionScore(doc)).toBe(0);
    });

    it('accumulates multiple needs (no type + no facts = 50)', () => {
        const doc = {
            signed_status: 'signed',
            metadata: { quality_score: 8, registry: {}, attorney_enrichment: {} }
        };
        expect(computeAttentionScore(doc)).toBe(50); // +30 type + +20 facts
    });

    it('handles doc with no metadata gracefully', () => {
        const doc = { metadata: {} };
        // No sig expected (0) + no type (30) + no facts (20) = 50
        expect(computeAttentionScore(doc)).toBe(50);
    });
});

describe('getAttentionNeeds', () => {
    it('returns empty array for fully enriched doc', () => {
        const doc = {
            signature_expected: true,
            signed_status: 'signed',
            document_type_label: 'Contract',
            metadata: {
                quality_score: 8,
                registry: { quick_facts_raw: { dates: ['2024-01-01'], amounts: [] } },
                attorney_enrichment: { key_facts: { date: '2024-01-01' } },
            },
        };
        expect(getAttentionNeeds(doc)).toEqual([]);
    });

    it('returns "signature" for missing expected signature', () => {
        const doc = {
            signature_expected: true,
            signed_status: 'not_detected',
            document_type_label: 'Contract',
            metadata: {
                quality_score: 8,
                registry: { quick_facts_raw: { dates: ['2024-01-01'], amounts: [] } },
                attorney_enrichment: { key_facts: { date: '2024-01-01' } },
            },
        };
        expect(getAttentionNeeds(doc)).toContain('signature');
    });

    it('does NOT return "notes" (notes penalty removed)', () => {
        const doc = {
            document_type_label: 'Contract',
            metadata: {
                quality_score: 8,
                registry: { quick_facts_raw: { dates: ['2024-01-01'], amounts: [] } },
                attorney_enrichment: {},
            },
        };
        expect(getAttentionNeeds(doc)).not.toContain('notes');
    });
});

describe('getAttentionNeeds - additional coverage', () => {
    it('returns "ocr quality" for quality score below 5', () => {
        const doc = {
            document_type_label: 'Contract',
            metadata: {
                quality_score: 2,
                registry: { quick_facts_raw: { dates: ['2024-01-01'], amounts: [] } },
                attorney_enrichment: { key_facts: { a: '1' } },
            },
        };
        expect(getAttentionNeeds(doc)).toContain('ocr quality');
    });

    it('returns "type" for missing document type', () => {
        const doc = {
            signed_status: 'signed',
            metadata: {
                quality_score: 9,
                registry: { quick_facts_raw: { dates: ['2024-01-01'], amounts: [] } },
                attorney_enrichment: { key_facts: { a: '1' } },
            },
        };
        expect(getAttentionNeeds(doc)).toContain('type');
    });

    it('returns "key facts" when no facts from any source', () => {
        const doc = {
            signed_status: 'signed',
            document_type_label: 'Contract',
            metadata: { quality_score: 9, registry: {}, attorney_enrichment: {} },
        };
        expect(getAttentionNeeds(doc)).toContain('key facts');
    });

    it('returns multiple needs when multiple issues exist', () => {
        const doc = {
            signature_expected: true,
            signed_status: 'not_detected',
            metadata: { quality_score: 2, registry: {}, attorney_enrichment: {} },
        };
        const needs = getAttentionNeeds(doc);
        expect(needs).toContain('signature');
        expect(needs).toContain('ocr quality');
        expect(needs).toContain('type');
        expect(needs).toContain('key facts');
        expect(needs).toHaveLength(4);
    });
});

describe('computeAttentionScore - edge cases', () => {
    it('uses registry.signature_expected when column is not set', () => {
        const doc = {
            signed_status: 'not_detected',
            document_type_label: 'Contract',
            metadata: {
                quality_score: 8,
                registry: {
                    signature_expected: true,
                    quick_facts_raw: { dates: ['2024-01-01'], amounts: [] },
                },
                attorney_enrichment: { key_facts: { a: '1' } },
            },
        };
        expect(computeAttentionScore(doc)).toBe(50);
    });

    it('considers attorney signature verification as satisfied', () => {
        const doc = {
            signature_expected: true,
            signed_status: 'not_detected',
            document_type_label: 'Contract',
            metadata: {
                quality_score: 8,
                registry: { quick_facts_raw: { dates: ['2024-01-01'], amounts: [] } },
                attorney_enrichment: {
                    key_facts: { a: '1' },
                    signature_verification: 'signed',
                },
            },
        };
        expect(computeAttentionScore(doc)).toBe(0);
    });

    it('considers attorney type override as having type', () => {
        const doc = {
            signed_status: 'signed',
            metadata: {
                quality_score: 8,
                registry: { quick_facts_raw: { dates: ['2024-01-01'], amounts: [] } },
                attorney_enrichment: {
                    key_facts: { a: '1' },
                    document_type_override: 'Medical Records',
                },
            },
        };
        expect(computeAttentionScore(doc)).toBe(0);
    });

    it('considers AI facts as having facts', () => {
        const doc = {
            signed_status: 'signed',
            document_type_label: 'Contract',
            metadata: {
                quality_score: 8,
                registry: {
                    quick_facts_ai: { dates: ['2024-01-01'], amounts: [], parties: [] },
                },
                attorney_enrichment: {},
            },
        };
        expect(computeAttentionScore(doc)).toBe(0);
    });

    it('uses extraction_quality_score when quality_score not set', () => {
        const doc = {
            signed_status: 'signed',
            document_type_label: 'Contract',
            metadata: {
                extraction_quality_score: 3,
                registry: { quick_facts_raw: { dates: ['2024-01-01'], amounts: [] } },
                attorney_enrichment: { key_facts: { a: '1' } },
            },
        };
        expect(computeAttentionScore(doc)).toBe(40);
    });

    it('accumulates all penalties for worst-case doc', () => {
        const doc = {
            signature_expected: true,
            signed_status: 'not_detected',
            metadata: { quality_score: 1, registry: {}, attorney_enrichment: {} },
        };
        // +50 (sig) + +40 (quality) + +30 (type) + +20 (facts) = 140
        expect(computeAttentionScore(doc)).toBe(140);
    });
});

describe('sortByAttention', () => {
    it('sorts highest attention score first', () => {
        const docs = [
            {
                id: '1',
                signed_status: 'signed',
                document_type_label: 'Contract',
                metadata: {
                    quality_score: 9,
                    registry: { quick_facts_raw: { dates: ['2024-01-01'], amounts: [] } },
                    attorney_enrichment: { key_facts: { a: '1' } },
                },
            },
            {
                id: '2',
                metadata: {}  // Missing everything = high attention score
            },
        ];
        const sorted = sortByAttention(docs);
        expect(sorted[0].id).toBe('2');
    });

    it('does not mutate the input array', () => {
        const docs = [{ id: '1', metadata: {} }, { id: '2', metadata: {} }];
        const original = [...docs];
        sortByAttention(docs);
        expect(docs).toEqual(original);
    });

    it('handles empty array', () => {
        expect(sortByAttention([])).toEqual([]);
    });

    it('handles single element array', () => {
        const docs = [{ id: '1', metadata: {} }];
        expect(sortByAttention(docs)).toHaveLength(1);
    });
});
