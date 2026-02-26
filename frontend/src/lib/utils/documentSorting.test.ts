import { describe, it, expect } from 'vitest';
import { computeAttentionScore, getAttentionNeeds, sortByAttention } from './documentSorting';

describe('computeAttentionScore', () => {
    it('returns 0 for fully enriched, signed, high-quality document', () => {
        const doc = {
            metadata: {
                signature_detection: { status: 'signed', signature_expected: true },
                document_type: 'contract',
                quality_score: 8,
                attorney_enrichment: {
                    key_facts: { date: '2024-01-01' },
                    attorney_notes: 'Reviewed',
                },
            },
        };
        expect(computeAttentionScore(doc)).toBe(0);
    });

    it('scores +50 for missing expected signature', () => {
        const doc = {
            metadata: {
                signature_detection: { status: 'not_detected', signature_expected: true },
                document_type: 'contract',
                quality_score: 8,
                attorney_enrichment: {
                    key_facts: { date: '2024-01-01' },
                    attorney_notes: 'Reviewed',
                },
            },
        };
        expect(computeAttentionScore(doc)).toBe(50);
    });

    it('scores +40 for low OCR quality', () => {
        const doc = {
            metadata: {
                signature_detection: { status: 'signed', signature_expected: true },
                document_type: 'contract',
                quality_score: 3,  // < 5
                attorney_enrichment: {
                    key_facts: { date: '2024-01-01' },
                    attorney_notes: 'Reviewed',
                },
            },
        };
        expect(computeAttentionScore(doc)).toBe(40);
    });

    it('scores +30 for missing document type', () => {
        const doc = {
            metadata: {
                signature_detection: { status: 'signed', signature_expected: true },
                quality_score: 8,
                attorney_enrichment: {
                    key_facts: { date: '2024-01-01' },
                    attorney_notes: 'Reviewed',
                },
            },
        };
        expect(computeAttentionScore(doc)).toBe(30);
    });

    it('scores +20 for missing key facts', () => {
        const doc = {
            metadata: {
                signature_detection: { status: 'signed', signature_expected: true },
                document_type: 'contract',
                quality_score: 8,
                attorney_enrichment: {
                    attorney_notes: 'Reviewed',
                },
            },
        };
        expect(computeAttentionScore(doc)).toBe(20);
    });

    it('scores +10 for missing attorney notes', () => {
        const doc = {
            metadata: {
                signature_detection: { status: 'signed', signature_expected: true },
                document_type: 'contract',
                quality_score: 8,
                attorney_enrichment: {
                    key_facts: { date: '2024-01-01' },
                },
            },
        };
        expect(computeAttentionScore(doc)).toBe(10);
    });

    it('accumulates multiple needs (no type + no facts + no notes = 60)', () => {
        const doc = { metadata: { signature_detection: { status: 'signed' }, quality_score: 8 } };
        expect(computeAttentionScore(doc)).toBe(60); // +30 +20 +10
    });

    it('handles doc with no metadata gracefully', () => {
        const doc = { metadata: {} };
        // No sig expected (0) + no type (30) + no facts (20) + no notes (10) = 60
        expect(computeAttentionScore(doc)).toBe(60);
    });
});

describe('getAttentionNeeds', () => {
    it('returns empty array for fully enriched doc', () => {
        const doc = {
            metadata: {
                signature_detection: { status: 'signed', signature_expected: true },
                document_type: 'contract',
                quality_score: 8,
                attorney_enrichment: { key_facts: { date: '2024-01-01' }, attorney_notes: 'ok' },
            },
        };
        expect(getAttentionNeeds(doc)).toEqual([]);
    });

    it('returns "signature" for missing expected signature', () => {
        const doc = {
            metadata: {
                signature_detection: { status: 'not_detected', signature_expected: true },
                document_type: 'contract',
                quality_score: 8,
                attorney_enrichment: { key_facts: { date: '2024-01-01' }, attorney_notes: 'ok' },
            },
        };
        expect(getAttentionNeeds(doc)).toContain('signature');
    });
});

describe('sortByAttention', () => {
    it('sorts highest attention score first', () => {
        const docs = [
            {
                id: '1',
                metadata: {
                    signature_detection: { status: 'signed', signature_expected: true },
                    document_type: 'contract',
                    quality_score: 9,
                    attorney_enrichment: { key_facts: { a: '1' }, attorney_notes: 'ok' }
                }
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
