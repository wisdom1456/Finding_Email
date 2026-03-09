import { describe, it, expect } from 'vitest';
import { groupDocuments, filterDocuments } from './triageGrouping';

function makeDoc(overrides: Record<string, any> = {}) {
	return {
		id: overrides.id ?? 'doc-1',
		file_name: overrides.file_name ?? 'test.pdf',
		status: overrides.status ?? 'ready',
		extracted_at: overrides.extracted_at ?? '2025-01-01T00:00:00Z',
		metadata: overrides.metadata ?? {},
		signature_expected: overrides.signature_expected ?? false,
		signed_status: overrides.signed_status ?? null,
		document_type_label: overrides.document_type_label ?? null,
		...overrides,
	};
}

// ── groupDocuments ──

describe('groupDocuments', () => {
	it('places download_failed docs in critical', () => {
		const docs = [makeDoc({ status: 'download_failed' })];
		const groups = groupDocuments(docs);
		expect(groups.critical).toHaveLength(1);
		expect(groups.needs_attention).toHaveLength(0);
	});

	it('places corrupted docs in critical', () => {
		const docs = [makeDoc({ status: 'corrupted' })];
		const groups = groupDocuments(docs);
		expect(groups.critical).toHaveLength(1);
	});

	it('places extraction_failed docs in needs_attention', () => {
		const docs = [makeDoc({ status: 'extraction_failed' })];
		const groups = groupDocuments(docs);
		expect(groups.needs_attention).toHaveLength(1);
	});

	it('places needs_review docs in needs_attention', () => {
		const docs = [makeDoc({ status: 'needs_review' })];
		const groups = groupDocuments(docs);
		expect(groups.needs_attention).toHaveLength(1);
	});

	it('places pending docs in needs_attention', () => {
		const docs = [makeDoc({ status: 'pending' })];
		const groups = groupDocuments(docs);
		expect(groups.needs_attention).toHaveLength(1);
	});

	it('places ready docs without extracted_at in needs_attention', () => {
		const docs = [makeDoc({ status: 'ready', extracted_at: null })];
		const groups = groupDocuments(docs);
		expect(groups.needs_attention).toHaveLength(1);
	});

	it('places ready docs with extracted_at in ready', () => {
		const docs = [makeDoc({ status: 'ready', extracted_at: '2025-01-01' })];
		const groups = groupDocuments(docs);
		expect(groups.ready).toHaveLength(1);
	});

	it('places duplicate docs in duplicates', () => {
		const docs = [makeDoc({ status: 'duplicate' })];
		const groups = groupDocuments(docs);
		expect(groups.duplicates).toHaveLength(1);
	});

	it('places docs with is_duplicate metadata in duplicates', () => {
		const docs = [makeDoc({ metadata: { is_duplicate: true } })];
		const groups = groupDocuments(docs);
		expect(groups.duplicates).toHaveLength(1);
	});

	it('places excluded docs in excluded', () => {
		const docs = [makeDoc({ metadata: { excluded: true } })];
		const groups = groupDocuments(docs);
		expect(groups.excluded).toHaveLength(1);
	});

	it('excluded takes priority over duplicate', () => {
		const docs = [makeDoc({ metadata: { excluded: true, is_duplicate: true } })];
		const groups = groupDocuments(docs);
		expect(groups.excluded).toHaveLength(1);
		expect(groups.duplicates).toHaveLength(0);
	});

	it('duplicate takes priority over status-based grouping', () => {
		const docs = [makeDoc({ status: 'needs_review', metadata: { is_duplicate: true } })];
		const groups = groupDocuments(docs);
		expect(groups.duplicates).toHaveLength(1);
		expect(groups.needs_attention).toHaveLength(0);
	});

	it('handles empty array', () => {
		const groups = groupDocuments([]);
		expect(groups.critical).toHaveLength(0);
		expect(groups.needs_attention).toHaveLength(0);
		expect(groups.ready).toHaveLength(0);
		expect(groups.duplicates).toHaveLength(0);
		expect(groups.excluded).toHaveLength(0);
	});

	it('distributes mixed documents correctly', () => {
		const docs = [
			makeDoc({ id: '1', status: 'corrupted' }),
			makeDoc({ id: '2', status: 'needs_review' }),
			makeDoc({ id: '3', status: 'ready', extracted_at: '2025-01-01' }),
			makeDoc({ id: '4', status: 'duplicate' }),
			makeDoc({ id: '5', metadata: { excluded: true } }),
			makeDoc({ id: '6', status: 'extraction_failed' }),
			makeDoc({ id: '7', status: 'download_failed' }),
		];
		const groups = groupDocuments(docs);
		expect(groups.critical).toHaveLength(2); // corrupted + download_failed
		expect(groups.needs_attention).toHaveLength(2); // needs_review + extraction_failed
		expect(groups.ready).toHaveLength(1);
		expect(groups.duplicates).toHaveLength(1);
		expect(groups.excluded).toHaveLength(1);
	});

	it('sorts each group by attention score', () => {
		const docs = [
			makeDoc({
				id: 'low-attention',
				status: 'needs_review',
				document_type_label: 'Contract',
				metadata: { quality_score: 9 },
			}),
			makeDoc({
				id: 'high-attention',
				status: 'needs_review',
				signature_expected: true,
				signed_status: 'not_detected',
				metadata: { quality_score: 2 },
			}),
		];
		const groups = groupDocuments(docs);
		expect(groups.needs_attention[0].id).toBe('high-attention');
		expect(groups.needs_attention[1].id).toBe('low-attention');
	});
});

// ── filterDocuments ──

describe('filterDocuments', () => {
	it('returns all documents when no filters active', () => {
		const docs = [makeDoc(), makeDoc({ id: '2' })];
		const result = filterDocuments(docs, new Set());
		expect(result).toHaveLength(2);
	});

	it('filters by missing-signatures', () => {
		const docs = [
			makeDoc({ id: 'needs-sig', signature_expected: true, signed_status: 'not_detected' }),
			makeDoc({ id: 'signed', signature_expected: true, signed_status: 'signed' }),
			makeDoc({ id: 'no-sig-expected', signature_expected: false }),
		];
		const result = filterDocuments(docs, new Set(['missing-signatures']));
		expect(result).toHaveLength(1);
		expect(result[0].id).toBe('needs-sig');
	});

	it('filters by missing-signatures using registry metadata', () => {
		const docs = [
			makeDoc({
				id: 'registry-sig',
				metadata: { registry: { signature_expected: true } },
			}),
		];
		const result = filterDocuments(docs, new Set(['missing-signatures']));
		expect(result).toHaveLength(1);
	});

	it('considers attorney verification as satisfied signature', () => {
		const docs = [
			makeDoc({
				id: 'attorney-verified',
				signature_expected: true,
				metadata: { attorney_enrichment: { signature_verification: 'signed' } },
			}),
		];
		const result = filterDocuments(docs, new Set(['missing-signatures']));
		expect(result).toHaveLength(0);
	});

	it('filters by low-ocr quality', () => {
		const docs = [
			makeDoc({ id: 'low', metadata: { quality_score: 3 } }),
			makeDoc({ id: 'high', metadata: { quality_score: 8 } }),
		];
		const result = filterDocuments(docs, new Set(['low-ocr']));
		expect(result).toHaveLength(1);
		expect(result[0].id).toBe('low');
	});

	it('defaults quality to 10 when not set', () => {
		const docs = [makeDoc({ id: 'no-score' })];
		const result = filterDocuments(docs, new Set(['low-ocr']));
		expect(result).toHaveLength(0);
	});

	it('filters by needs-type', () => {
		const docs = [
			makeDoc({ id: 'no-type', document_type_label: null }),
			makeDoc({ id: 'has-type', document_type_label: 'Contract' }),
			makeDoc({
				id: 'attorney-type',
				document_type_label: null,
				metadata: { attorney_enrichment: { document_type_override: 'Letter' } },
			}),
		];
		const result = filterDocuments(docs, new Set(['needs-type']));
		expect(result).toHaveLength(1);
		expect(result[0].id).toBe('no-type');
	});

	it('filters by ready status', () => {
		const docs = [
			makeDoc({ id: 'ready', status: 'ready' }),
			makeDoc({ id: 'review', status: 'needs_review' }),
		];
		const result = filterDocuments(docs, new Set(['ready']));
		expect(result).toHaveLength(1);
		expect(result[0].id).toBe('ready');
	});

	it('combines multiple filters with OR logic', () => {
		const docs = [
			makeDoc({ id: 'low-ocr', metadata: { quality_score: 2 }, document_type_label: 'Contract' }),
			makeDoc({ id: 'no-type', document_type_label: null, metadata: { quality_score: 9 } }),
			makeDoc({ id: 'fine', document_type_label: 'Contract', metadata: { quality_score: 9 } }),
		];
		const result = filterDocuments(docs, new Set(['low-ocr', 'needs-type']));
		expect(result).toHaveLength(2);
		expect(result.map(d => d.id).sort()).toEqual(['low-ocr', 'no-type']);
	});
});
