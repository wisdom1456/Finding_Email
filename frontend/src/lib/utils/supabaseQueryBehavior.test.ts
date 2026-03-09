/**
 * Supabase query behavior tests — .single() vs .maybeSingle()
 *
 * Documents the exact behavior difference that caused the 406 bug:
 * - .single() throws PGRST116 when 0 or >1 rows match
 * - .maybeSingle() returns null when 0 rows match
 *
 * These tests use a mock Supabase client to verify the app handles
 * each case intentionally rather than accidentally.
 */
import { describe, it, expect, vi } from 'vitest';
import { loadCaseGracefully, type CaseLoadResult } from './streamRecovery';

// ── Mock Supabase query builder ──

/**
 * Simulates Supabase PostgREST query behavior.
 * This mirrors how the real client behaves.
 */
function mockSupabaseQuery(rows: Record<string, any>[]) {
	return {
		/** .single() — PGRST116 error on 0 or >1 rows */
		single() {
			if (rows.length === 0) {
				return {
					data: null,
					error: {
						message: 'JSON object requested, multiple (or no) rows returned',
						code: 'PGRST116',
						details: 'The result contains 0 rows',
						hint: null,
					},
					status: 406,
				};
			}
			if (rows.length > 1) {
				return {
					data: null,
					error: {
						message: 'JSON object requested, multiple (or no) rows returned',
						code: 'PGRST116',
						details: `The result contains ${rows.length} rows`,
						hint: null,
					},
					status: 406,
				};
			}
			return { data: rows[0], error: null, status: 200 };
		},

		/** .maybeSingle() — returns null on 0 rows, error on >1 */
		maybeSingle() {
			if (rows.length === 0) {
				return { data: null, error: null, status: 200 };
			}
			if (rows.length > 1) {
				return {
					data: null,
					error: {
						message: 'JSON object requested, multiple (or no) rows returned',
						code: 'PGRST116',
						details: `The result contains ${rows.length} rows`,
						hint: null,
					},
					status: 406,
				};
			}
			return { data: rows[0], error: null, status: 200 };
		},
	};
}

describe('Supabase .single() vs .maybeSingle() behavior', () => {
	const sampleCase = { id: 'case-001', client_name: 'Test Client', status: 'active' };

	// ── .single() ──

	describe('.single()', () => {
		it('returns data when exactly 1 row matches', () => {
			const result = mockSupabaseQuery([sampleCase]).single();
			expect(result.data).toEqual(sampleCase);
			expect(result.error).toBeNull();
		});

		it('returns PGRST116 error when 0 rows match (the 406 bug)', () => {
			const result = mockSupabaseQuery([]).single();
			expect(result.data).toBeNull();
			expect(result.error).not.toBeNull();
			expect(result.error!.code).toBe('PGRST116');
			expect(result.status).toBe(406);
		});

		it('returns PGRST116 error when >1 rows match', () => {
			const result = mockSupabaseQuery([sampleCase, { ...sampleCase, id: 'case-002' }]).single();
			expect(result.data).toBeNull();
			expect(result.error!.code).toBe('PGRST116');
		});
	});

	// ── .maybeSingle() ──

	describe('.maybeSingle()', () => {
		it('returns data when exactly 1 row matches', () => {
			const result = mockSupabaseQuery([sampleCase]).maybeSingle();
			expect(result.data).toEqual(sampleCase);
			expect(result.error).toBeNull();
		});

		it('returns null data and NO error when 0 rows match', () => {
			const result = mockSupabaseQuery([]).maybeSingle();
			expect(result.data).toBeNull();
			expect(result.error).toBeNull();
			expect(result.status).toBe(200);
		});

		it('still errors when >1 rows match', () => {
			const result = mockSupabaseQuery([sampleCase, { ...sampleCase, id: 'case-002' }]).maybeSingle();
			expect(result.error!.code).toBe('PGRST116');
		});
	});

	// ── How the app should handle each case ──

	describe('app-level handling via loadCaseGracefully', () => {
		it('single row → found', async () => {
			const result = await loadCaseGracefully(async () =>
				mockSupabaseQuery([sampleCase]).maybeSingle()
			);
			expect(result.type).toBe('found');
		});

		it('zero rows → not_found (not error!)', async () => {
			const result = await loadCaseGracefully(async () =>
				mockSupabaseQuery([]).maybeSingle()
			);
			expect(result.type).toBe('not_found');
		});

		it('zero rows with .single() → error (the bug we fixed)', async () => {
			// This demonstrates what USED TO HAPPEN before the fix:
			// .single() returns an error object, which loadCaseGracefully classifies as error
			const result = await loadCaseGracefully(async () =>
				mockSupabaseQuery([]).single()
			);
			expect(result.type).toBe('error');
			if (result.type === 'error') {
				expect(result.message).toContain('multiple (or no) rows returned');
			}
		});

		it('>1 rows → error (both .single and .maybeSingle)', async () => {
			const result = await loadCaseGracefully(async () =>
				mockSupabaseQuery([sampleCase, { ...sampleCase, id: 'case-002' }]).maybeSingle()
			);
			expect(result.type).toBe('error');
		});
	});

	// ── Race condition: case not persisted yet ──

	describe('persistence race conditions', () => {
		it('handles "case not yet persisted" as not_found (retryable)', async () => {
			// During Clio import, the case may not be in the DB yet.
			// With maybeSingle, this is a clean not_found, not a 406 crash.
			const result = await loadCaseGracefully(async () =>
				mockSupabaseQuery([]).maybeSingle()
			);
			expect(result.type).toBe('not_found');
			// The caller can decide to retry
		});

		it('handles "case deleted during view" as not_found', async () => {
			// User is viewing a case that gets deleted by another process.
			const result = await loadCaseGracefully(async () =>
				mockSupabaseQuery([]).maybeSingle()
			);
			expect(result.type).toBe('not_found');
		});

		it('handles "permission denied" as error (not not_found)', async () => {
			const result = await loadCaseGracefully(async () => ({
				data: null,
				error: { message: 'permission denied for table cases', code: '42501' },
			}));
			expect(result.type).toBe('error');
			if (result.type === 'error') {
				expect(result.message).toContain('permission denied');
			}
		});
	});
});
