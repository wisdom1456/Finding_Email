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
});
