/**
 * Tests for stream recovery / post-stream reconciliation logic.
 *
 * Covers the exact bug class: "backend finished analyzing, but the UI
 * failed to settle after stream disconnect because sub-steps threw."
 */
import { describe, it, expect, vi } from 'vitest';
import {
	reconcileAfterStream,
	loadCaseGracefully,
	type ReconciliationDeps,
} from './streamRecovery';

// ── Helpers ──

function makeDeps(overrides: Partial<ReconciliationDeps> = {}): ReconciliationDeps {
	return {
		loadAnalysisStatus: vi.fn().mockResolvedValue(undefined),
		loadEmbeddedResults: vi.fn().mockResolvedValue(undefined),
		onSuccess: vi.fn(),
		onError: vi.fn(),
		...overrides,
	};
}

// ═══════════════════════════════════════════════════════════
// reconcileAfterStream
// ═══════════════════════════════════════════════════════════

describe('reconcileAfterStream', () => {
	// ── Happy path ──

	it('settles successfully when all sub-steps pass', async () => {
		const deps = makeDeps();
		const result = await reconcileAfterStream(deps);

		expect(result.settled).toBe(true);
		expect(result.statusLoaded).toBe(true);
		expect(result.resultsLoaded).toBe(true);
		expect(result.errors).toEqual([]);
		expect(deps.onSuccess).toHaveBeenCalledWith(expect.stringContaining('Analysis complete'));
		expect(deps.onError).not.toHaveBeenCalled();
	});

	// ── loadAnalysisStatus fails ──

	it('still settles when loadAnalysisStatus throws', async () => {
		const deps = makeDeps({
			loadAnalysisStatus: vi.fn().mockRejectedValue(new Error('DB timeout')),
		});
		const result = await reconcileAfterStream(deps);

		expect(result.settled).toBe(true);
		expect(result.statusLoaded).toBe(false);
		expect(result.resultsLoaded).toBe(true);
		expect(result.errors).toHaveLength(1);
		expect(result.errors[0]).toContain('DB timeout');
		// loadEmbeddedResults should still have been called
		expect(deps.loadEmbeddedResults).toHaveBeenCalledWith(true);
	});

	// ── loadEmbeddedResults fails ──

	it('still settles when loadEmbeddedResults throws', async () => {
		const deps = makeDeps({
			loadEmbeddedResults: vi.fn().mockRejectedValue(new Error('Network error')),
		});
		const result = await reconcileAfterStream(deps);

		expect(result.settled).toBe(true);
		expect(result.statusLoaded).toBe(true);
		expect(result.resultsLoaded).toBe(false);
		expect(result.errors).toHaveLength(1);
		expect(result.errors[0]).toContain('Network error');
		expect(deps.onError).toHaveBeenCalledWith(expect.stringContaining('failed to load'));
	});

	// ── Both sub-steps fail ──

	it('still settles when ALL sub-steps throw', async () => {
		const deps = makeDeps({
			loadAnalysisStatus: vi.fn().mockRejectedValue(new Error('Status failed')),
			loadEmbeddedResults: vi.fn().mockRejectedValue(new Error('Results failed')),
		});
		const result = await reconcileAfterStream(deps);

		expect(result.settled).toBe(true);
		expect(result.statusLoaded).toBe(false);
		expect(result.resultsLoaded).toBe(false);
		expect(result.errors).toHaveLength(2);
		// Should NOT have called onSuccess
		expect(deps.onSuccess).not.toHaveBeenCalled();
		// Should have called onError for results failure
		expect(deps.onError).toHaveBeenCalledTimes(1);
	});

	// ── Never throws ──

	it('never throws regardless of sub-step failures', async () => {
		const deps = makeDeps({
			loadAnalysisStatus: vi.fn().mockRejectedValue(new Error('Catastrophe 1')),
			loadEmbeddedResults: vi.fn().mockRejectedValue(new Error('Catastrophe 2')),
		});

		// This must not throw
		const result = await reconcileAfterStream(deps);
		expect(result.settled).toBe(true);
	});

	// ── Execution order ──

	it('calls loadAnalysisStatus before loadEmbeddedResults', async () => {
		const callOrder: string[] = [];
		const deps = makeDeps({
			loadAnalysisStatus: vi.fn().mockImplementation(async () => {
				callOrder.push('status');
			}),
			loadEmbeddedResults: vi.fn().mockImplementation(async () => {
				callOrder.push('results');
			}),
		});

		await reconcileAfterStream(deps);
		expect(callOrder).toEqual(['status', 'results']);
	});

	// ── Stream interrupted but backend saved ──

	it('handles scenario: stream interrupted, backend result exists', async () => {
		// This simulates: streaming was interrupted, but saveAnalysis succeeded
		// on the backend. loadAnalysisStatus works, loadEmbeddedResults works.
		const deps = makeDeps();
		const result = await reconcileAfterStream(deps);

		expect(result.settled).toBe(true);
		expect(result.statusLoaded).toBe(true);
		expect(result.resultsLoaded).toBe(true);
		expect(result.errors).toEqual([]);
	});
});

// ═══════════════════════════════════════════════════════════
// loadCaseGracefully
// ═══════════════════════════════════════════════════════════

describe('loadCaseGracefully', () => {
	// ── Found ──

	it('returns found when data exists', async () => {
		const result = await loadCaseGracefully(async () => ({
			data: { id: 'case-1', client_name: 'Test' },
			error: null,
		}));

		expect(result.type).toBe('found');
		if (result.type === 'found') {
			expect(result.data.id).toBe('case-1');
		}
	});

	// ── Not found (null data, no error) — maybeSingle() behavior ──

	it('returns not_found when data is null (maybeSingle zero rows)', async () => {
		const result = await loadCaseGracefully(async () => ({
			data: null,
			error: null,
		}));

		expect(result.type).toBe('not_found');
	});

	// ── Supabase error ──

	it('returns error when Supabase returns an error object', async () => {
		const result = await loadCaseGracefully(async () => ({
			data: null,
			error: { message: 'PGRST116: JSON object requested, multiple (or no) rows returned', code: 'PGRST116' },
		}));

		expect(result.type).toBe('error');
		if (result.type === 'error') {
			expect(result.message).toContain('PGRST116');
		}
	});

	// ── 406 simulation (what .single() does on zero rows) ──

	it('returns error when query function throws (simulating 406)', async () => {
		const result = await loadCaseGracefully(async () => {
			throw new Error('JSON object requested, multiple (or no) rows returned');
		});

		expect(result.type).toBe('error');
		if (result.type === 'error') {
			expect(result.message).toContain('rows returned');
		}
	});

	// ── Network error ──

	it('returns error on network failure', async () => {
		const result = await loadCaseGracefully(async () => {
			throw new Error('Failed to fetch');
		});

		expect(result.type).toBe('error');
		if (result.type === 'error') {
			expect(result.message).toContain('Failed to fetch');
		}
	});

	// ── Intentional distinction: not-found vs error ──

	it('distinguishes not-found from real errors', async () => {
		const notFound = await loadCaseGracefully(async () => ({
			data: null,
			error: null,
		}));

		const realError = await loadCaseGracefully(async () => ({
			data: null,
			error: { message: 'permission denied for table cases' },
		}));

		expect(notFound.type).toBe('not_found');
		expect(realError.type).toBe('error');
	});
});
