import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { withRetry } from './supabaseRetry';

describe('withRetry', () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('returns immediately on success', async () => {
		const queryFn = vi.fn().mockResolvedValue({ data: [{ id: 1 }], error: null, status: 200 });
		const result = await withRetry(queryFn);
		expect(queryFn).toHaveBeenCalledTimes(1);
		expect(result.data).toEqual([{ id: 1 }]);
	});

	it('returns immediately on non-503 error', async () => {
		const queryFn = vi.fn().mockResolvedValue({
			data: null,
			error: { message: 'Row not found', code: 'PGRST116' },
			status: 406
		});
		const result = await withRetry(queryFn);
		expect(queryFn).toHaveBeenCalledTimes(1);
		expect(result.error?.code).toBe('PGRST116');
	});

	it('retries on 503 status and succeeds', async () => {
		const queryFn = vi
			.fn()
			.mockResolvedValueOnce({ data: null, error: { message: 'unavailable' }, status: 503 })
			.mockResolvedValueOnce({ data: [{ id: 1 }], error: null, status: 200 });

		const promise = withRetry(queryFn);
		await vi.advanceTimersByTimeAsync(1000);
		const result = await promise;

		expect(queryFn).toHaveBeenCalledTimes(2);
		expect(result.data).toEqual([{ id: 1 }]);
	});

	it('retries on PGRST002 error code', async () => {
		const queryFn = vi
			.fn()
			.mockResolvedValueOnce({
				data: null,
				error: { message: 'Could not query', code: 'PGRST002' },
				status: 500
			})
			.mockResolvedValueOnce({ data: [], error: null, status: 200 });

		const promise = withRetry(queryFn);
		await vi.advanceTimersByTimeAsync(1000);
		const result = await promise;

		expect(queryFn).toHaveBeenCalledTimes(2);
		expect(result.error).toBeNull();
	});

	it('retries on "schema cache" in error message', async () => {
		const queryFn = vi
			.fn()
			.mockResolvedValueOnce({
				data: null,
				error: { message: 'schema cache is being rebuilt' },
				status: 500
			})
			.mockResolvedValueOnce({ data: [{ id: 2 }], error: null, status: 200 });

		const promise = withRetry(queryFn);
		await vi.advanceTimersByTimeAsync(1000);
		const result = await promise;

		expect(queryFn).toHaveBeenCalledTimes(2);
		expect(result.data).toEqual([{ id: 2 }]);
	});

	it('gives up after maxRetries', async () => {
		const queryFn = vi.fn().mockResolvedValue({
			data: null,
			error: { message: 'unavailable' },
			status: 503
		});

		const promise = withRetry(queryFn, 2);
		// Need to advance through all retry delays: 1000ms + 2000ms
		await vi.advanceTimersByTimeAsync(1000);
		await vi.advanceTimersByTimeAsync(2000);
		const result = await promise;

		expect(queryFn).toHaveBeenCalledTimes(3); // attempt 0, 1, 2
		expect(result.status).toBe(503);
	});

	it('respects custom maxRetries', async () => {
		const queryFn = vi.fn().mockResolvedValue({
			data: null,
			error: { message: 'down' },
			status: 503
		});

		const promise = withRetry(queryFn, 1);
		await vi.advanceTimersByTimeAsync(1000);
		await promise;

		expect(queryFn).toHaveBeenCalledTimes(2); // attempt 0 + 1
	});

	it('does not retry non-503 errors', async () => {
		const queryFn = vi.fn().mockResolvedValue({
			data: null,
			error: { message: 'permission denied', code: '42501' },
			status: 403
		});
		const result = await withRetry(queryFn);
		expect(queryFn).toHaveBeenCalledTimes(1);
		expect(result.status).toBe(403);
	});
});
