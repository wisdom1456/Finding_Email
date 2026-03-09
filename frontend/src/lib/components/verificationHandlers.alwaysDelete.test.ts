/**
 * Tests for handleAlwaysDelete — the "Always exclude" flow.
 *
 * Validates the corrected operation order:
 *   1. Auth → 2. Fetch profile → 3. Add blacklist rule → 4. Delete docs
 *
 * Key properties tested:
 * - Blacklist rule is saved BEFORE documents are deleted
 * - Profile fetch failure blocks the entire operation (no partial deletion)
 * - Blacklist save failure blocks deletion
 * - Delete failure does NOT lose the blacklist rule
 * - Duplicate blacklist rules are not added
 * - Auth failure blocks everything
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { handleAlwaysDelete, type AlwaysDeleteDeps } from './verificationHandlers.alwaysDelete';

function makeDoc(overrides: Record<string, any> = {}) {
	return {
		id: 'doc-001',
		file_name: 'Billing Statement (1).pdf',
		status: 'needs_review',
		...overrides,
	};
}

function makeDeps(overrides: Partial<AlwaysDeleteDeps> = {}): AlwaysDeleteDeps {
	return {
		getSecureSession: vi.fn().mockResolvedValue({
			session: { access_token: 'test-token' },
			user: { id: 'user-1' },
		}),
		getApiUrl: () => 'http://localhost:8000',
		toastStore: {
			success: vi.fn(),
			error: vi.fn(),
			warning: vi.fn(),
		},
		onDocumentsUpdated: vi.fn().mockResolvedValue(undefined),
		localDocuments: [
			makeDoc({ id: 'doc-1', file_name: 'Billing Statement (1).pdf' }),
			makeDoc({ id: 'doc-2', file_name: 'Billing Statement (2).pdf' }),
			makeDoc({ id: 'doc-3', file_name: 'Contract.pdf' }),
		],
		fetchFn: vi.fn(),
		...overrides,
	};
}

function mockFetchSequence(responses: Array<{ ok: boolean; body?: any; text?: string }>) {
	let callIndex = 0;
	return vi.fn().mockImplementation(() => {
		const resp = responses[callIndex++] ?? { ok: true, body: {} };
		return Promise.resolve({
			ok: resp.ok,
			json: () => Promise.resolve(resp.body ?? {}),
			text: () => Promise.resolve(resp.text ?? ''),
		});
	});
}

describe('handleAlwaysDelete', () => {
	// ── Operation ordering ──

	it('fetches profile BEFORE attempting delete', async () => {
		const callOrder: string[] = [];
		const deps = makeDeps({
			fetchFn: vi.fn().mockImplementation((url: string, opts?: any) => {
				if (url.includes('/api/profile') && !opts?.method) {
					callOrder.push('profile-fetch');
					return Promise.resolve({
						ok: true,
						json: () => Promise.resolve({ ai_preferences: { blacklisted_documents: [] } }),
					});
				}
				if (url.includes('/api/profile') && opts?.method === 'PUT') {
					callOrder.push('blacklist-save');
					return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
				}
				if (url.includes('/bulk-delete')) {
					callOrder.push('delete');
					return Promise.resolve({
						ok: true,
						json: () => Promise.resolve({ deleted_count: 2 }),
					});
				}
				return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
			}),
		});

		await handleAlwaysDelete('Billing Statement (1).pdf', 'doc-1', deps);

		expect(callOrder).toEqual(['profile-fetch', 'blacklist-save', 'delete']);
	});

	// ── Profile fetch failure ──

	it('blocks entire operation when profile fetch fails', async () => {
		const deps = makeDeps({
			fetchFn: mockFetchSequence([
				{ ok: false, text: 'Profile not found' }, // profile GET
			]),
		});

		const result = await handleAlwaysDelete('Billing Statement.pdf', 'doc-1', deps);

		expect(result.success).toBe(false);
		expect(result.error).toBe('Failed to fetch profile');
		expect(result.documentsDeleted).toBe(0);
		expect(result.blacklistRuleAdded).toBe(false);
		expect(deps.toastStore.error).toHaveBeenCalledWith('Blacklist error: Failed to fetch profile');
	});

	// ── Blacklist save failure ──

	it('blocks deletion when blacklist save fails', async () => {
		const deps = makeDeps({
			fetchFn: vi.fn().mockImplementation((url: string, opts?: any) => {
				if (url.includes('/api/profile') && !opts?.method) {
					return Promise.resolve({
						ok: true,
						json: () => Promise.resolve({ ai_preferences: { blacklisted_documents: [] } }),
					});
				}
				if (url.includes('/api/profile') && opts?.method === 'PUT') {
					return Promise.resolve({ ok: false });
				}
				if (url.includes('/bulk-delete')) {
					// This should NOT be reached
					throw new Error('Delete was called — this is a bug');
				}
				return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
			}),
		});

		const result = await handleAlwaysDelete('Billing Statement.pdf', 'doc-1', deps);

		expect(result.success).toBe(false);
		expect(result.error).toBe('Failed to update blacklist');
		expect(result.documentsDeleted).toBe(0);
	});

	// ── Delete failure preserves blacklist rule ──

	it('preserves blacklist rule when delete fails', async () => {
		let blacklistSaved = false;
		const deps = makeDeps({
			fetchFn: vi.fn().mockImplementation((url: string, opts?: any) => {
				if (url.includes('/api/profile') && !opts?.method) {
					return Promise.resolve({
						ok: true,
						json: () => Promise.resolve({ ai_preferences: { blacklisted_documents: [] } }),
					});
				}
				if (url.includes('/api/profile') && opts?.method === 'PUT') {
					blacklistSaved = true;
					return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
				}
				if (url.includes('/bulk-delete')) {
					return Promise.resolve({ ok: false });
				}
				return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
			}),
		});

		const result = await handleAlwaysDelete('Billing Statement.pdf', 'doc-1', deps);

		// Blacklist was saved (idempotent, non-destructive) — good
		expect(blacklistSaved).toBe(true);
		// But overall operation failed because delete failed
		expect(result.success).toBe(false);
		expect(result.error).toBe('Failed to delete selected documents');
	});

	// ── Auth failure ──

	it('blocks everything when not authenticated', async () => {
		const deps = makeDeps({
			getSecureSession: vi.fn().mockResolvedValue({ session: null, user: null }),
		});

		const result = await handleAlwaysDelete('Billing Statement.pdf', 'doc-1', deps);

		expect(result.success).toBe(false);
		expect(result.error).toBe('Not authenticated');
		expect(deps.fetchFn).not.toHaveBeenCalled();
	});

	// ── Duplicate rule detection ──

	it('skips blacklist save when equivalent rule already exists', async () => {
		let blacklistSaveAttempted = false;
		const deps = makeDeps({
			fetchFn: vi.fn().mockImplementation((url: string, opts?: any) => {
				if (url.includes('/api/profile') && !opts?.method) {
					return Promise.resolve({
						ok: true,
						json: () => Promise.resolve({
							ai_preferences: {
								blacklisted_documents: ['billing statement'],
							},
						}),
					});
				}
				if (url.includes('/api/profile') && opts?.method === 'PUT') {
					blacklistSaveAttempted = true;
					return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
				}
				if (url.includes('/bulk-delete')) {
					return Promise.resolve({
						ok: true,
						json: () => Promise.resolve({ deleted_count: 2 }),
					});
				}
				return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
			}),
		});

		const result = await handleAlwaysDelete('Billing Statement (1).pdf', 'doc-1', deps);

		expect(result.success).toBe(true);
		expect(blacklistSaveAttempted).toBe(false); // No duplicate write
	});

	// ── No docId — blacklist only ──

	it('only adds blacklist rule when docId is undefined (no deletion)', async () => {
		let deleteAttempted = false;
		const deps = makeDeps({
			fetchFn: vi.fn().mockImplementation((url: string, opts?: any) => {
				if (url.includes('/api/profile') && !opts?.method) {
					return Promise.resolve({
						ok: true,
						json: () => Promise.resolve({ ai_preferences: { blacklisted_documents: [] } }),
					});
				}
				if (url.includes('/api/profile') && opts?.method === 'PUT') {
					return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
				}
				if (url.includes('/bulk-delete')) {
					deleteAttempted = true;
					return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
				}
				return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
			}),
		});

		const result = await handleAlwaysDelete('Billing Statement.pdf', undefined, deps);

		expect(result.success).toBe(true);
		expect(result.blacklistRuleAdded).toBe(true);
		expect(result.documentsDeleted).toBe(0);
		expect(deleteAttempted).toBe(false);
	});

	// ── Happy path ──

	it('adds rule and deletes matching docs on success', async () => {
		const deps = makeDeps({
			fetchFn: vi.fn().mockImplementation((url: string, opts?: any) => {
				if (url.includes('/api/profile') && !opts?.method) {
					return Promise.resolve({
						ok: true,
						json: () => Promise.resolve({ ai_preferences: { blacklisted_documents: [] } }),
					});
				}
				if (url.includes('/api/profile') && opts?.method === 'PUT') {
					return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
				}
				if (url.includes('/bulk-delete')) {
					return Promise.resolve({
						ok: true,
						json: () => Promise.resolve({ deleted_count: 2, failed_ids: [] }),
					});
				}
				return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
			}),
		});

		const result = await handleAlwaysDelete('Billing Statement (1).pdf', 'doc-1', deps);

		expect(result.success).toBe(true);
		expect(result.blacklistRuleAdded).toBe(true);
		expect(result.documentsDeleted).toBe(2);
		expect(deps.toastStore.success).toHaveBeenCalled();
		expect(deps.onDocumentsUpdated).toHaveBeenCalled();
	});

	// ── Partial delete ──

	it('shows warning when some documents fail to delete', async () => {
		const deps = makeDeps({
			fetchFn: vi.fn().mockImplementation((url: string, opts?: any) => {
				if (url.includes('/api/profile') && !opts?.method) {
					return Promise.resolve({
						ok: true,
						json: () => Promise.resolve({ ai_preferences: { blacklisted_documents: [] } }),
					});
				}
				if (url.includes('/api/profile') && opts?.method === 'PUT') {
					return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
				}
				if (url.includes('/bulk-delete')) {
					return Promise.resolve({
						ok: true,
						json: () => Promise.resolve({ deleted_count: 1, failed_ids: ['doc-2'] }),
					});
				}
				return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
			}),
		});

		const result = await handleAlwaysDelete('Billing Statement (1).pdf', 'doc-1', deps);

		expect(result.success).toBe(true);
		expect(deps.toastStore.warning).toHaveBeenCalledWith(
			expect.stringContaining('1 could not be deleted'),
		);
	});

	// ── Network error during profile fetch ──

	it('handles network error during profile fetch', async () => {
		const deps = makeDeps({
			fetchFn: vi.fn().mockImplementation((url: string) => {
				if (url.includes('/api/profile')) {
					return Promise.reject(new Error('Network error'));
				}
				return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
			}),
		});

		const result = await handleAlwaysDelete('Test.pdf', 'doc-1', deps);

		expect(result.success).toBe(false);
		expect(result.error).toBe('Network error');
		expect(result.documentsDeleted).toBe(0);
	});
});
