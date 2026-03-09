import { describe, it, expect, vi, beforeEach } from 'vitest';
import { dedupCaseDocuments, syncClioMatter } from './cases';

// Mock dependencies
vi.mock('$lib/config', () => ({
	getApiUrl: () => 'http://localhost:8000',
}));

vi.mock('$lib/supabase', () => ({
	getSecureSession: vi.fn(),
}));

import { getSecureSession } from '$lib/supabase';

const mockSession = {
	session: { access_token: 'test-token' },
	user: { id: 'user-1' },
};

describe('dedupCaseDocuments', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('throws when not authenticated', async () => {
		vi.mocked(getSecureSession).mockResolvedValue({ session: null, user: null });
		await expect(dedupCaseDocuments('case-1')).rejects.toThrow('Not authenticated');
	});

	it('sends POST with auth header and returns response', async () => {
		vi.mocked(getSecureSession).mockResolvedValue(mockSession);
		const mockResponse = {
			success: true,
			duplicates_found: 2,
			documents_checked: 10,
			message: '2 duplicates found',
		};
		vi.mocked(fetch).mockResolvedValue({
			ok: true,
			json: () => Promise.resolve(mockResponse),
		} as Response);

		const result = await dedupCaseDocuments('case-1');
		expect(result).toEqual(mockResponse);
		expect(fetch).toHaveBeenCalledWith(
			'http://localhost:8000/api/cases/case-1/dedup',
			expect.objectContaining({
				method: 'POST',
				headers: { Authorization: 'Bearer test-token' },
			})
		);
	});

	it('throws with backend error detail on failure', async () => {
		vi.mocked(getSecureSession).mockResolvedValue(mockSession);
		vi.mocked(fetch).mockResolvedValue({
			ok: false,
			json: () => Promise.resolve({ detail: 'Case not found' }),
		} as Response);

		await expect(dedupCaseDocuments('case-1')).rejects.toThrow('Case not found');
	});

	it('throws generic message when error response is not JSON', async () => {
		vi.mocked(getSecureSession).mockResolvedValue(mockSession);
		vi.mocked(fetch).mockResolvedValue({
			ok: false,
			json: () => Promise.reject(new Error('not json')),
		} as Response);

		await expect(dedupCaseDocuments('case-1')).rejects.toThrow('Failed to deduplicate documents');
	});
});

describe('syncClioMatter', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('throws when not authenticated', async () => {
		vi.mocked(getSecureSession).mockResolvedValue({ session: null, user: null });
		await expect(syncClioMatter('case-1')).rejects.toThrow('Not authenticated');
	});

	it('sends POST to correct endpoint and returns response', async () => {
		vi.mocked(getSecureSession).mockResolvedValue(mockSession);
		const mockResponse = {
			success: true,
			case_id: 'case-1',
			synced_at: '2025-01-01T00:00:00Z',
			summary: { new_items: 3, updated_items: 1, total_processed: 4 },
			details: { new: [], updated: [] },
			needs_reanalysis: true,
		};
		vi.mocked(fetch).mockResolvedValue({
			ok: true,
			json: () => Promise.resolve(mockResponse),
		} as Response);

		const result = await syncClioMatter('case-1');
		expect(result).toEqual(mockResponse);
		expect(fetch).toHaveBeenCalledWith(
			'http://localhost:8000/api/clio/sync/case-1',
			expect.objectContaining({ method: 'POST' })
		);
	});

	it('throws with backend error detail on failure', async () => {
		vi.mocked(getSecureSession).mockResolvedValue(mockSession);
		vi.mocked(fetch).mockResolvedValue({
			ok: false,
			json: () => Promise.resolve({ detail: 'Clio token expired' }),
		} as Response);

		await expect(syncClioMatter('case-1')).rejects.toThrow('Clio token expired');
	});
});
