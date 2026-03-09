/**
 * Tests for extracted VerificationHub handler logic.
 *
 * Validates:
 * - Optimistic updates roll back on API failure
 * - Error toasts appear on failure
 * - Document status doesn't falsely advance
 * - Double-submit prevention for extract operations
 * - Processing IDs are cleaned up on failure
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
	applyOptimistic,
	handleTypeOverride,
	handleRelevanceChange,
	handleNotesUpdate,
	handleReExtract,
	handleBulkExtract,
	type HandlerDeps,
} from './verificationHandlers';

// ── Helpers ──

function makeDoc(overrides: Record<string, any> = {}) {
	return {
		id: 'doc-001',
		file_name: 'contract.pdf',
		status: 'needs_review',
		metadata: {},
		...overrides,
	};
}

function makeDeps(overrides: Partial<HandlerDeps> = {}): HandlerDeps {
	return {
		getSecureSession: vi.fn().mockResolvedValue({
			session: { access_token: 'test-token' },
			user: { id: 'user-1' },
		}),
		getApiUrl: () => 'http://localhost:8000',
		toastStore: {
			success: vi.fn(),
			error: vi.fn(),
			info: vi.fn(),
			warning: vi.fn(),
		},
		onDocumentsUpdated: vi.fn().mockResolvedValue(undefined),
		fetchFn: vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) }),
		...overrides,
	};
}

// ── applyOptimistic ──

describe('applyOptimistic', () => {
	it('applies update and returns rollback snapshot', () => {
		const docs = [makeDoc({ id: 'doc-1' }), makeDoc({ id: 'doc-2' })];
		const { newDocs, rollback, idx } = applyOptimistic(docs, 'doc-1', (d) => ({
			...d,
			status: 'ready',
		}));

		expect(idx).toBe(0);
		expect(newDocs[0].status).toBe('ready');
		expect(newDocs[1].status).toBe('needs_review');
		// Rollback is original snapshot
		expect(rollback![0].status).toBe('needs_review');
	});

	it('returns original docs when document not found', () => {
		const docs = [makeDoc({ id: 'doc-1' })];
		const { newDocs, rollback, idx } = applyOptimistic(docs, 'nonexistent', (d) => d);

		expect(idx).toBe(-1);
		expect(rollback).toBeNull();
		expect(newDocs).toBe(docs); // Same reference
	});

	it('does not mutate original array', () => {
		const docs = [makeDoc({ id: 'doc-1' })];
		const original = [...docs];
		applyOptimistic(docs, 'doc-1', (d) => ({ ...d, status: 'ready' }));
		expect(docs[0].status).toBe('needs_review');
	});
});

// ── handleTypeOverride ──

describe('handleTypeOverride', () => {
	it('applies optimistic update and returns new docs on success', async () => {
		const docs = [makeDoc({ id: 'doc-1', metadata: {} })];
		const deps = makeDeps();

		const result = await handleTypeOverride('doc-1', 'Contract', docs, deps);

		expect(result.success).toBe(true);
		expect(result.documents[0].metadata.attorney_enrichment.document_type_override).toBe('Contract');
		expect(deps.fetchFn).toHaveBeenCalledWith(
			'http://localhost:8000/api/documents/doc-1/verify',
			expect.objectContaining({ method: 'PATCH' })
		);
	});

	it('rolls back optimistic update on API failure', async () => {
		const docs = [makeDoc({ id: 'doc-1', metadata: { attorney_enrichment: { document_type_override: 'Letter' } } })];
		const deps = makeDeps({
			fetchFn: vi.fn().mockResolvedValue({ ok: false, status: 500 }),
		});

		const result = await handleTypeOverride('doc-1', 'Contract', docs, deps);

		expect(result.success).toBe(false);
		// Rolled back to original
		expect(result.documents[0].metadata.attorney_enrichment.document_type_override).toBe('Letter');
		expect(deps.toastStore.error).toHaveBeenCalledWith('Failed to save document type');
	});

	it('rolls back on auth failure', async () => {
		const docs = [makeDoc({ id: 'doc-1' })];
		const deps = makeDeps({
			getSecureSession: vi.fn().mockResolvedValue({ session: null, user: null }),
		});

		const result = await handleTypeOverride('doc-1', 'Contract', docs, deps);

		expect(result.success).toBe(false);
		expect(deps.toastStore.error).toHaveBeenCalledWith('Failed to save document type');
	});

	it('rolls back on network error', async () => {
		const docs = [makeDoc({ id: 'doc-1' })];
		const deps = makeDeps({
			fetchFn: vi.fn().mockRejectedValue(new Error('Network error')),
		});

		const result = await handleTypeOverride('doc-1', 'Contract', docs, deps);

		expect(result.success).toBe(false);
		expect(deps.toastStore.error).toHaveBeenCalled();
	});

	it('returns original docs when document not found', async () => {
		const docs = [makeDoc({ id: 'doc-1' })];
		const deps = makeDeps();

		const result = await handleTypeOverride('nonexistent', 'Contract', docs, deps);

		// Should still try the API call but no optimistic change
		expect(result.documents).toEqual(docs);
	});
});

// ── handleRelevanceChange ──

describe('handleRelevanceChange', () => {
	it('applies optimistic update on success', async () => {
		const docs = [makeDoc({ id: 'doc-1' })];
		const deps = makeDeps();

		const result = await handleRelevanceChange('doc-1', 'high', docs, deps);

		expect(result.success).toBe(true);
		expect(result.documents[0].metadata.attorney_enrichment.relevance_level).toBe('high');
	});

	it('rolls back on failure', async () => {
		const docs = [makeDoc({ id: 'doc-1', metadata: { attorney_enrichment: { relevance_level: 'low' } } })];
		const deps = makeDeps({
			fetchFn: vi.fn().mockResolvedValue({ ok: false }),
		});

		const result = await handleRelevanceChange('doc-1', 'high', docs, deps);

		expect(result.success).toBe(false);
		expect(result.documents[0].metadata.attorney_enrichment.relevance_level).toBe('low');
		expect(deps.toastStore.error).toHaveBeenCalledWith('Failed to save relevance');
	});
});

// ── handleNotesUpdate ──

describe('handleNotesUpdate', () => {
	it('applies optimistic update on success', async () => {
		const docs = [makeDoc({ id: 'doc-1' })];
		const deps = makeDeps();

		const result = await handleNotesUpdate('doc-1', 'Important note', docs, deps);

		expect(result.success).toBe(true);
		expect(result.documents[0].metadata.attorney_enrichment.attorney_notes).toBe('Important note');
	});

	it('rolls back on failure and shows error toast', async () => {
		const docs = [makeDoc({ id: 'doc-1', metadata: { attorney_enrichment: { attorney_notes: 'Old note' } } })];
		const deps = makeDeps({
			fetchFn: vi.fn().mockResolvedValue({ ok: false }),
		});

		const result = await handleNotesUpdate('doc-1', 'New note', docs, deps);

		expect(result.success).toBe(false);
		expect(result.documents[0].metadata.attorney_enrichment.attorney_notes).toBe('Old note');
		expect(deps.toastStore.error).toHaveBeenCalledWith('Failed to save notes');
	});
});

// ── handleReExtract ──

describe('handleReExtract', () => {
	it('extracts successfully and cleans up processing ids', async () => {
		const deps = makeDeps();
		const processingIds = new Set<string>();

		const result = await handleReExtract('doc-1', processingIds, deps);

		expect(result.attempted).toBe(true);
		expect(result.success).toBe(true);
		expect(result.newProcessingIds.has('doc-1')).toBe(false);
		expect(deps.toastStore.success).toHaveBeenCalledWith('Extraction complete');
		expect(deps.onDocumentsUpdated).toHaveBeenCalled();
	});

	it('prevents double-submit when doc already processing', async () => {
		const deps = makeDeps();
		const processingIds = new Set(['doc-1']);

		const result = await handleReExtract('doc-1', processingIds, deps);

		expect(result.attempted).toBe(false);
		expect(result.success).toBe(false);
		expect(deps.fetchFn).not.toHaveBeenCalled();
	});

	it('cleans up processing ids on failure', async () => {
		const deps = makeDeps({
			fetchFn: vi.fn().mockResolvedValue({
				ok: false,
				status: 500,
				json: () => Promise.resolve({ detail: 'OCR_SERVICE_TOKEN must be set' }),
			}),
		});
		const processingIds = new Set<string>();

		const result = await handleReExtract('doc-1', processingIds, deps);

		expect(result.attempted).toBe(true);
		expect(result.success).toBe(false);
		expect(result.newProcessingIds.has('doc-1')).toBe(false);
		expect(deps.toastStore.error).toHaveBeenCalledWith('OCR_SERVICE_TOKEN must be set');
	});

	it('cleans up processing ids on auth failure', async () => {
		const deps = makeDeps({
			getSecureSession: vi.fn().mockResolvedValue({ session: null, user: null }),
		});
		const processingIds = new Set<string>();

		const result = await handleReExtract('doc-1', processingIds, deps);

		expect(result.success).toBe(false);
		expect(result.newProcessingIds.has('doc-1')).toBe(false);
		expect(deps.toastStore.error).toHaveBeenCalledWith('Not authenticated');
	});

	it('cleans up processing ids on network error', async () => {
		const deps = makeDeps({
			fetchFn: vi.fn().mockRejectedValue(new Error('Network error')),
		});

		const result = await handleReExtract('doc-1', new Set(), deps);

		expect(result.success).toBe(false);
		expect(result.newProcessingIds.has('doc-1')).toBe(false);
	});

	it('shows extraction failed status code when response is not JSON', async () => {
		const deps = makeDeps({
			fetchFn: vi.fn().mockResolvedValue({
				ok: false,
				status: 502,
				json: () => Promise.reject(new Error('not json')),
			}),
		});

		const result = await handleReExtract('doc-1', new Set(), deps);

		expect(result.success).toBe(false);
		expect(deps.toastStore.error).toHaveBeenCalledWith('Extraction failed (502)');
	});
});

// ── handleBulkExtract ──

describe('handleBulkExtract', () => {
	it('processes all documents and reports success', async () => {
		const docs = [
			makeDoc({ id: 'doc-1' }),
			makeDoc({ id: 'doc-2' }),
			makeDoc({ id: 'doc-3' }),
		];
		const deps = makeDeps();

		const result = await handleBulkExtract(docs, new Set(), false, deps);

		expect(result.success).toBe(true);
		expect(result.extractedCount).toBe(3);
		expect(result.failedCount).toBe(0);
		expect(result.newProcessingIds.size).toBe(0);
		expect(deps.toastStore.success).toHaveBeenCalledWith('Successfully extracted all 3 documents');
	});

	it('prevents double-submit when already loading', async () => {
		const docs = [makeDoc({ id: 'doc-1' })];
		const deps = makeDeps();

		const result = await handleBulkExtract(docs, new Set(), true, deps);

		expect(result.success).toBe(false);
		expect(deps.fetchFn).not.toHaveBeenCalled();
	});

	it('does nothing with empty docs array', async () => {
		const deps = makeDeps();

		const result = await handleBulkExtract([], new Set(), false, deps);

		expect(result.success).toBe(false);
		expect(deps.fetchFn).not.toHaveBeenCalled();
	});

	it('reports partial failure with correct counts', async () => {
		const docs = [
			makeDoc({ id: 'doc-1' }),
			makeDoc({ id: 'doc-2' }),
			makeDoc({ id: 'doc-3' }),
		];
		let callCount = 0;
		const deps = makeDeps({
			fetchFn: vi.fn().mockImplementation(() => {
				callCount++;
				if (callCount === 2) {
					return Promise.resolve({ ok: false, status: 500 });
				}
				return Promise.resolve({ ok: true });
			}),
		});

		const result = await handleBulkExtract(docs, new Set(), false, deps);

		expect(result.success).toBe(true);
		expect(result.extractedCount).toBe(2);
		expect(result.failedCount).toBe(1);
		expect(deps.toastStore.warning).toHaveBeenCalledWith('Extracted 2 docs, but 1 failed.');
	});

	it('cleans up all processing ids on auth failure', async () => {
		const docs = [makeDoc({ id: 'doc-1' }), makeDoc({ id: 'doc-2' })];
		const deps = makeDeps({
			getSecureSession: vi.fn().mockResolvedValue({ session: null, user: null }),
		});

		const result = await handleBulkExtract(docs, new Set(), false, deps);

		expect(result.success).toBe(false);
		expect(result.newProcessingIds.size).toBe(0);
		expect(deps.toastStore.error).toHaveBeenCalledWith('Not authenticated');
	});

	it('calls onDocumentsUpdated after each batch', async () => {
		// 5 docs = 2 batches (3 + 2)
		const docs = Array.from({ length: 5 }, (_, i) => makeDoc({ id: `doc-${i}` }));
		const deps = makeDeps();

		await handleBulkExtract(docs, new Set(), false, deps);

		// Should be called once per batch
		expect(deps.onDocumentsUpdated).toHaveBeenCalledTimes(2);
	});
});
