import { describe, it, expect, vi, beforeEach } from 'vitest';
import { dedupCaseDocuments, syncClioMatter } from './cases';
import { makeAuthenticatedSession } from '../../tests/componentHelpers';

// Mock dependencies
vi.mock('$lib/config', () => ({
	getApiUrl: () => 'http://localhost:8000',
}));

vi.mock('$lib/supabase', () => ({
	getSecureSession: vi.fn(),
}));

import { getSecureSession } from '$lib/supabase';

const mockSession = makeAuthenticatedSession();

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
		const [url, init] = vi.mocked(fetch).mock.calls[0];
		expect(url).toBe('http://localhost:8000/api/cases/case-1/dedup');
		expect(init?.method).toBe('POST');
		expect((init?.headers as Headers).get('Authorization')).toBe('Bearer test-token');
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
			status: 500,
			json: () => Promise.reject(new Error('not json')),
		} as Response);

		await expect(dedupCaseDocuments('case-1')).rejects.toThrow('Request failed (500)');
	});

	it('uses the normalized message field when detail is absent', async () => {
		vi.mocked(getSecureSession).mockResolvedValue(mockSession);
		vi.mocked(fetch).mockResolvedValue({
			ok: false,
			status: 500,
			json: () => Promise.resolve({ message: 'Internal Server Error' }),
		} as Response);

		await expect(dedupCaseDocuments('case-1')).rejects.toThrow('Internal Server Error');
	});

	it('handles 401 unauthorized', async () => {
		vi.mocked(getSecureSession).mockResolvedValue(mockSession);
		vi.mocked(fetch).mockResolvedValue({
			ok: false,
			status: 401,
			json: () => Promise.resolve({ detail: 'Token expired' }),
		} as Response);

		await expect(dedupCaseDocuments('case-1')).rejects.toThrow('Token expired');
	});

	it('handles 403 forbidden', async () => {
		vi.mocked(getSecureSession).mockResolvedValue(mockSession);
		vi.mocked(fetch).mockResolvedValue({
			ok: false,
			status: 403,
			json: () => Promise.resolve({ detail: 'Not authorized for this case' }),
		} as Response);

		await expect(dedupCaseDocuments('case-1')).rejects.toThrow('Not authorized for this case');
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

	it('throws generic message when error response is not JSON', async () => {
		vi.mocked(getSecureSession).mockResolvedValue(mockSession);
		vi.mocked(fetch).mockResolvedValue({
			ok: false,
			status: 502,
			json: () => Promise.reject(new Error('not json')),
		} as Response);

		await expect(syncClioMatter('case-1')).rejects.toThrow('Request failed (502)');
	});

	it('handles 500 server error', async () => {
		vi.mocked(getSecureSession).mockResolvedValue(mockSession);
		vi.mocked(fetch).mockResolvedValue({
			ok: false,
			status: 500,
			json: () => Promise.resolve({ detail: 'Internal server error' }),
		} as Response);

		await expect(syncClioMatter('case-1')).rejects.toThrow('Internal server error');
	});

	it('handles 401 unauthorized', async () => {
		vi.mocked(getSecureSession).mockResolvedValue(mockSession);
		vi.mocked(fetch).mockResolvedValue({
			ok: false,
			status: 401,
			json: () => Promise.resolve({ detail: 'Invalid token' }),
		} as Response);

		await expect(syncClioMatter('case-1')).rejects.toThrow('Invalid token');
	});
});
