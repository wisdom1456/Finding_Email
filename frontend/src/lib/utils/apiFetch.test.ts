import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiFetch, ApiError, parseErrorMessage } from './apiFetch';

vi.mock('$lib/supabase', () => ({
	getSecureSession: vi.fn(async () => ({
		session: { access_token: 'mock-token' },
		user: { id: 'user-1' }
	}))
}));

vi.mock('$lib/config', () => ({
	getApiUrl: () => 'http://localhost:8000'
}));

describe('parseErrorMessage', () => {
	it('reads the normalized {error, message} envelope', () => {
		expect(parseErrorMessage({ error: 'AppError', message: 'Case not found' }, 'x')).toBe(
			'Case not found'
		);
	});

	it('reads FastAPI {detail: string}', () => {
		expect(parseErrorMessage({ detail: 'Not authorized' }, 'x')).toBe('Not authorized');
	});

	it('reads nested {detail: {message}}', () => {
		expect(parseErrorMessage({ detail: { message: 'Nested' } }, 'x')).toBe('Nested');
	});

	it('falls back for unknown shapes', () => {
		expect(parseErrorMessage(null, 'fallback')).toBe('fallback');
		expect(parseErrorMessage('oops', 'fallback')).toBe('fallback');
	});
});

describe('apiFetch', () => {
	beforeEach(() => {
		global.fetch = vi.fn();
	});

	it('attaches bearer auth and parses JSON', async () => {
		(global.fetch as any).mockResolvedValueOnce({
			ok: true,
			status: 200,
			json: async () => ({ id: '123' })
		});

		const result = await apiFetch<{ id: string }>('/api/cases/123', { method: 'POST' });
		expect(result.id).toBe('123');

		const [url, init] = (global.fetch as any).mock.calls[0];
		expect(url).toBe('http://localhost:8000/api/cases/123');
		expect((init.headers as Headers).get('Authorization')).toBe('Bearer mock-token');
	});

	it('serializes json option and sets content type', async () => {
		(global.fetch as any).mockResolvedValueOnce({
			ok: true,
			status: 200,
			json: async () => ({})
		});

		await apiFetch('/api/cases', { method: 'POST', json: { client_name: 'A' } });
		const [, init] = (global.fetch as any).mock.calls[0];
		expect(init.body).toBe(JSON.stringify({ client_name: 'A' }));
		expect((init.headers as Headers).get('Content-Type')).toBe('application/json');
	});

	it('throws ApiError with normalized message on non-2xx', async () => {
		(global.fetch as any).mockResolvedValueOnce({
			ok: false,
			status: 404,
			json: async () => ({ detail: 'Case not found' })
		});

		await expect(apiFetch('/api/cases/nope', { method: 'POST' })).rejects.toMatchObject({
			name: 'ApiError',
			status: 404,
			message: 'Case not found'
		});
	});

	it('throws when not authenticated', async () => {
		const { getSecureSession } = await import('$lib/supabase');
		(getSecureSession as any).mockResolvedValueOnce({ session: null, user: null });

		await expect(apiFetch('/api/cases')).rejects.toThrow('Not authenticated');
	});

	it('retries GETs on 503 then succeeds', async () => {
		(global.fetch as any)
			.mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({}) })
			.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ ok: true }) });

		const result = await apiFetch<{ ok: boolean }>('/api/cases');
		expect(result.ok).toBe(true);
		expect((global.fetch as any).mock.calls.length).toBe(2);
	});

	it('does not retry POSTs by default', async () => {
		(global.fetch as any).mockResolvedValueOnce({
			ok: false,
			status: 503,
			json: async () => ({})
		});

		await expect(apiFetch('/api/cases', { method: 'POST' })).rejects.toBeInstanceOf(ApiError);
		expect((global.fetch as any).mock.calls.length).toBe(1);
	});
});
