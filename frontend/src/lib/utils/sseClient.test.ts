import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SSEClient } from './sseClient';

// ── fetch + ReadableStream Mock ──

/**
 * Creates a controllable ReadableStream for testing SSE parsing.
 * Returns the stream and a controller to push data / close it.
 */
function createMockStream() {
	let controller!: ReadableStreamDefaultController<Uint8Array>;
	const stream = new ReadableStream<Uint8Array>({
		start(c) {
			controller = c;
		},
	});
	const encoder = new TextEncoder();
	return {
		stream,
		push(text: string) {
			controller.enqueue(encoder.encode(text));
		},
		close() {
			controller.close();
		},
		error(e: Error) {
			controller.error(e);
		},
	};
}

/** SSE-format a JSON payload as a `data: ...\n\n` line */
function sseData(obj: Record<string, unknown>): string {
	return `data: ${JSON.stringify(obj)}\n\n`;
}

describe('SSEClient', () => {
	let client: SSEClient;
	let onMessage: ReturnType<typeof vi.fn>;
	let onError: ReturnType<typeof vi.fn>;
	let onComplete: ReturnType<typeof vi.fn>;
	let mockStream: ReturnType<typeof createMockStream>;

	beforeEach(() => {
		vi.useFakeTimers();
		client = new SSEClient();
		onMessage = vi.fn();
		onError = vi.fn();
		onComplete = vi.fn();
		mockStream = createMockStream();

		// Default: successful fetch returning our controllable stream
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: true,
				body: mockStream.stream,
			})
		);
	});

	afterEach(() => {
		client.disconnect();
		vi.useRealTimers();
		vi.restoreAllMocks();
	});

	// ── isSupported ──

	it('reports SSE as supported when ReadableStream exists', () => {
		expect(SSEClient.isSupported()).toBe(true);
	});

	// ── connect ──

	it('returns true on successful connect', () => {
		const result = client.connect(
			'http://localhost/stream',
			'test-token',
			onMessage,
			onError,
			onComplete
		);
		expect(result).toBe(true);
	});

	it('sends Authorization header, not token in URL', async () => {
		client.connect('http://localhost/stream', 'my-secret-jwt', onMessage, onError, onComplete);

		// Let fetch resolve
		await vi.advanceTimersByTimeAsync(0);

		expect(fetch).toHaveBeenCalledWith(
			'http://localhost/stream',
			expect.objectContaining({
				headers: expect.objectContaining({
					Authorization: 'Bearer my-secret-jwt',
				}),
			})
		);
	});

	it('returns false and fires error when ReadableStream not supported', () => {
		const saved = globalThis.ReadableStream;
		// @ts-ignore
		delete globalThis.ReadableStream;
		try {
			const localClient = new SSEClient();
			const result = localClient.connect(
				'http://localhost/stream',
				'tok',
				onMessage,
				onError,
				onComplete
			);
			expect(result).toBe(false);
			expect(onError).toHaveBeenCalledWith(
				expect.objectContaining({ message: 'SSE_NOT_SUPPORTED' })
			);
		} finally {
			globalThis.ReadableStream = saved;
		}
	});

	// ── message handling ──

	it('parses and forwards progress messages', async () => {
		client.connect('http://localhost/stream', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		mockStream.push(
			sseData({ type: 'progress', message: 'Working', phase: 'doc_summary', percent: 42 })
		);
		await vi.advanceTimersByTimeAsync(0);

		expect(onMessage).toHaveBeenCalledWith(
			expect.objectContaining({
				type: 'progress',
				message: 'Working',
				percent: 42,
			})
		);
	});

	it('skips empty and comment lines (keep-alive)', async () => {
		client.connect('http://localhost/stream', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		mockStream.push('   \n');
		mockStream.push(': ping\n');
		await vi.advanceTimersByTimeAsync(0);

		expect(onMessage).not.toHaveBeenCalled();
	});

	it('handles incomplete lines across chunks', async () => {
		client.connect('http://localhost/stream', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		// Split a single SSE message across two chunks
		mockStream.push('data: {"type":"pro');
		await vi.advanceTimersByTimeAsync(0);
		expect(onMessage).not.toHaveBeenCalled();

		mockStream.push('gress","message":"OK","phase":"p","percent":10}\n\n');
		await vi.advanceTimersByTimeAsync(0);
		expect(onMessage).toHaveBeenCalledWith(
			expect.objectContaining({ type: 'progress', percent: 10 })
		);
	});

	// ── terminal events ──

	it('disconnects and calls onComplete on "completed" event', async () => {
		client.connect('http://localhost/stream', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		mockStream.push(
			sseData({ type: 'completed', message: 'Done', phase: 'done', percent: 100 })
		);
		await vi.advanceTimersByTimeAsync(0);

		expect(onMessage).toHaveBeenCalled();
		expect(onComplete).toHaveBeenCalled();
		expect(client.isConnected()).toBe(false);
	});

	it('disconnects and calls onComplete on "failed" event', async () => {
		client.connect('http://localhost/stream', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		mockStream.push(
			sseData({ type: 'failed', message: 'Error', phase: 'error', percent: 50, error: 'boom' })
		);
		await vi.advanceTimersByTimeAsync(0);

		expect(onComplete).toHaveBeenCalled();
	});

	it('disconnects and calls onComplete on "error" event', async () => {
		client.connect('http://localhost/stream', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		mockStream.push(sseData({ type: 'error', message: 'Bad', phase: 'error', percent: 0 }));
		await vi.advanceTimersByTimeAsync(0);

		expect(onComplete).toHaveBeenCalled();
	});

	// ── stream end ──

	it('calls onComplete when stream closes without terminal event', async () => {
		client.connect('http://localhost/stream', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		mockStream.push(sseData({ type: 'progress', message: 'OK', phase: 'p', percent: 50 }));
		await vi.advanceTimersByTimeAsync(0);

		mockStream.close();
		await vi.advanceTimersByTimeAsync(0);

		expect(onComplete).toHaveBeenCalled();
	});

	// ── reconnection ──

	it('reconnects with exponential backoff on fetch failure', async () => {
		let fetchCount = 0;
		vi.stubGlobal(
			'fetch',
			vi.fn().mockImplementation(() => {
				fetchCount++;
				if (fetchCount <= 3) {
					return Promise.reject(new Error('Network error'));
				}
				// 4th attempt succeeds
				return Promise.resolve({ ok: true, body: mockStream.stream });
			})
		);

		client.connect('http://localhost/stream', 'tok', onMessage, onError, onComplete);

		// 1st attempt fails immediately
		await vi.advanceTimersByTimeAsync(0);
		expect(fetchCount).toBe(1);

		// 2nd attempt after 1s backoff
		await vi.advanceTimersByTimeAsync(1000);
		expect(fetchCount).toBe(2);

		// 3rd attempt after 2s backoff
		await vi.advanceTimersByTimeAsync(2000);
		expect(fetchCount).toBe(3);

		// 4th attempt after 4s backoff — succeeds
		await vi.advanceTimersByTimeAsync(4000);
		expect(fetchCount).toBe(4);

		// Should NOT have fired SSE_CONNECTION_FAILED
		expect(onError).not.toHaveBeenCalledWith(
			expect.objectContaining({ message: 'SSE_CONNECTION_FAILED' })
		);
	});

	it('fires SSE_CONNECTION_FAILED after max reconnect attempts', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockRejectedValue(new Error('Network error'))
		);

		client.connect('http://localhost/stream', 'tok', onMessage, onError, onComplete);

		// Attempt 1 fails
		await vi.advanceTimersByTimeAsync(0);
		// Attempt 2 after 1s
		await vi.advanceTimersByTimeAsync(1000);
		await vi.advanceTimersByTimeAsync(0);
		// Attempt 3 after 2s
		await vi.advanceTimersByTimeAsync(2000);
		await vi.advanceTimersByTimeAsync(0);
		// Attempt 4 after 4s — exceeds maxReconnectAttempts (3)
		await vi.advanceTimersByTimeAsync(4000);
		await vi.advanceTimersByTimeAsync(0);

		expect(onError).toHaveBeenCalledWith(
			expect.objectContaining({ message: 'SSE_CONNECTION_FAILED' })
		);
		expect(onComplete).toHaveBeenCalled();
	});

	it('does not reconnect after manual disconnect', async () => {
		client.connect('http://localhost/stream', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		client.disconnect();
		expect(client.isConnected()).toBe(false);
	});

	// ── inactivity timeout ──

	it('fires SSE_TIMEOUT after 5 minutes of inactivity', async () => {
		client.connect('http://localhost/stream', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		// Advance past inactivity timeout (5 minutes = 300000ms)
		vi.advanceTimersByTime(300001);

		expect(onError).toHaveBeenCalledWith(
			expect.objectContaining({
				message: expect.stringContaining('SSE_TIMEOUT'),
			})
		);
		expect(onComplete).toHaveBeenCalled();
	});

	it('resets inactivity timer on message', async () => {
		client.connect('http://localhost/stream', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		// Advance 4 minutes
		vi.advanceTimersByTime(240000);

		// Send a message — should reset timer
		mockStream.push(
			sseData({ type: 'progress', message: 'Still alive', phase: 'working', percent: 50 })
		);
		await vi.advanceTimersByTimeAsync(0);

		// Advance another 4 minutes (total 8 since start, but only 4 since last message)
		vi.advanceTimersByTime(240000);

		// Should NOT have timed out (only 4 min since last message)
		expect(onError).not.toHaveBeenCalled();

		// Advance past full timeout from last message
		vi.advanceTimersByTime(60001);

		expect(onError).toHaveBeenCalledWith(
			expect.objectContaining({
				message: expect.stringContaining('SSE_TIMEOUT'),
			})
		);
	});

	it('resets inactivity timer on keep-alive', async () => {
		client.connect('http://localhost/stream', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		// Advance 4.5 minutes
		vi.advanceTimersByTime(270000);

		// Send keep-alive (SSE comment line)
		mockStream.push(': ping\n');
		await vi.advanceTimersByTimeAsync(0);

		// Advance another 4.5 minutes
		vi.advanceTimersByTime(270000);

		// Should NOT have timed out
		expect(onError).not.toHaveBeenCalled();
	});

	// ── disconnect ──

	it('disconnect clears all state', async () => {
		client.connect('http://localhost/stream', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		client.disconnect();
		expect(client.isConnected()).toBe(false);
	});

	// ── HTTP error handling ──

	it('retries on non-ok HTTP response', async () => {
		let fetchCount = 0;
		vi.stubGlobal(
			'fetch',
			vi.fn().mockImplementation(() => {
				fetchCount++;
				if (fetchCount === 1) {
					return Promise.resolve({ ok: false, status: 502, body: null });
				}
				return Promise.resolve({ ok: true, body: mockStream.stream });
			})
		);

		client.connect('http://localhost/stream', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		// First attempt fails with 502, reconnect after 1s
		await vi.advanceTimersByTimeAsync(1000);
		await vi.advanceTimersByTimeAsync(0);

		expect(fetchCount).toBe(2);
		expect(client.isConnected()).toBe(true);
	});
});
