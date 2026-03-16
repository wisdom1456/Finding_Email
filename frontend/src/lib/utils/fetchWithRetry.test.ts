import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fetchWithRetry } from './fetchWithRetry';

describe('fetchWithRetry', () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('returns response on success', async () => {
		const mockResponse = new Response('ok', { status: 200 });
		vi.mocked(global.fetch).mockResolvedValueOnce(mockResponse);

		const result = await fetchWithRetry('/api/test', {});
		expect(result).toBe(mockResponse);
		expect(global.fetch).toHaveBeenCalledTimes(1);
	});

	it('retries on 429', async () => {
		const retryResponse = new Response('too many requests', { status: 429 });
		const successResponse = new Response('ok', { status: 200 });
		vi.mocked(global.fetch)
			.mockResolvedValueOnce(retryResponse)
			.mockResolvedValueOnce(successResponse);

		const promise = fetchWithRetry('/api/test', {});
		await vi.advanceTimersByTimeAsync(1100);

		const result = await promise;
		expect(result.status).toBe(200);
		expect(global.fetch).toHaveBeenCalledTimes(2);
	});

	it('retries on 502', async () => {
		const retryResponse = new Response('bad gateway', { status: 502 });
		const successResponse = new Response('ok', { status: 200 });
		vi.mocked(global.fetch)
			.mockResolvedValueOnce(retryResponse)
			.mockResolvedValueOnce(successResponse);

		const promise = fetchWithRetry('/api/test', {});
		// Advance past the 1s backoff (1000 * 2^0)
		await vi.advanceTimersByTimeAsync(1100);

		const result = await promise;
		expect(result.status).toBe(200);
		expect(global.fetch).toHaveBeenCalledTimes(2);
	});

	it('retries on 503', async () => {
		const retryResponse = new Response('unavailable', { status: 503 });
		const successResponse = new Response('ok', { status: 200 });
		vi.mocked(global.fetch)
			.mockResolvedValueOnce(retryResponse)
			.mockResolvedValueOnce(successResponse);

		const promise = fetchWithRetry('/api/test', {});
		await vi.advanceTimersByTimeAsync(1100);

		const result = await promise;
		expect(result.status).toBe(200);
		expect(global.fetch).toHaveBeenCalledTimes(2);
	});

	it('retries on network error', async () => {
		const successResponse = new Response('ok', { status: 200 });
		vi.mocked(global.fetch)
			.mockRejectedValueOnce(new TypeError('fetch failed'))
			.mockResolvedValueOnce(successResponse);

		const promise = fetchWithRetry('/api/test', {});
		await vi.advanceTimersByTimeAsync(1100);

		const result = await promise;
		expect(result.status).toBe(200);
		expect(global.fetch).toHaveBeenCalledTimes(2);
	});

	it('does not retry on 400', async () => {
		const badRequest = new Response('bad request', { status: 400 });
		vi.mocked(global.fetch).mockResolvedValueOnce(badRequest);

		const result = await fetchWithRetry('/api/test', {});
		expect(result.status).toBe(400);
		expect(global.fetch).toHaveBeenCalledTimes(1);
	});

	it('does not retry on 500', async () => {
		const serverError = new Response('server error', { status: 500 });
		vi.mocked(global.fetch).mockResolvedValueOnce(serverError);

		const result = await fetchWithRetry('/api/test', {});
		expect(result.status).toBe(500);
		expect(global.fetch).toHaveBeenCalledTimes(1);
	});

	it('returns last 502 response after exhausting retries', async () => {
		const retryResponse = new Response('bad gateway', { status: 502 });
		vi.mocked(global.fetch)
			.mockResolvedValueOnce(retryResponse)
			.mockResolvedValueOnce(retryResponse)
			.mockResolvedValueOnce(retryResponse);

		const promise = fetchWithRetry('/api/test', {});
		await vi.advanceTimersByTimeAsync(1100); // attempt 1 backoff
		await vi.advanceTimersByTimeAsync(2100); // attempt 2 backoff

		const result = await promise;
		expect(result.status).toBe(502);
		expect(global.fetch).toHaveBeenCalledTimes(3);
	});

	it('throws after exhausting retries on network error', async () => {
		vi.useRealTimers();
		const error = new TypeError('fetch failed');
		vi.mocked(global.fetch).mockImplementation(() => Promise.reject(error));

		await expect(fetchWithRetry('/api/test', {}, 0)).rejects.toThrow('fetch failed');
		expect(global.fetch).toHaveBeenCalledTimes(1);
	});

	it('does not retry non-network errors', async () => {
		vi.mocked(global.fetch).mockRejectedValueOnce(new Error('some other error'));

		await expect(fetchWithRetry('/api/test', {})).rejects.toThrow('some other error');
		expect(global.fetch).toHaveBeenCalledTimes(1);
	});
});
