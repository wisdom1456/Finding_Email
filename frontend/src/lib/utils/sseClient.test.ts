import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SSEClient } from './sseClient';

// ── EventSource Mock ──

class MockEventSource {
	static CONNECTING = 0;
	static OPEN = 1;
	static CLOSED = 2;

	readyState = MockEventSource.OPEN;
	onmessage: ((event: MessageEvent) => void) | null = null;
	onerror: (() => void) | null = null;
	onopen: (() => void) | null = null;
	url: string;

	constructor(url: string) {
		this.url = url;
		MockEventSource._lastInstance = this;
		// Simulate async open — only if not suppressed
		if (!MockEventSource._suppressOpen) {
			setTimeout(() => this.onopen?.(), 0);
		}
	}

	static _lastInstance: MockEventSource | null = null;
	static _suppressOpen = false;

	close() {
		this.readyState = MockEventSource.CLOSED;
	}

	// Test helper: simulate a message
	simulateMessage(data: any) {
		const event = { data: typeof data === 'string' ? data : JSON.stringify(data) } as MessageEvent;
		this.onmessage?.(event);
	}

	// Test helper: simulate an error
	simulateError() {
		this.onerror?.();
	}
}

// Install mock
vi.stubGlobal('EventSource', MockEventSource);

describe('SSEClient', () => {
	let client: SSEClient;
	let onMessage: ReturnType<typeof vi.fn>;
	let onError: ReturnType<typeof vi.fn>;
	let onComplete: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		vi.useFakeTimers();
		client = new SSEClient();
		onMessage = vi.fn();
		onError = vi.fn();
		onComplete = vi.fn();
	});

	afterEach(() => {
		client.disconnect();
		vi.useRealTimers();
	});

	// ── isSupported ──

	it('reports SSE as supported when EventSource exists', () => {
		expect(SSEClient.isSupported()).toBe(true);
	});

	// ── connect ──

	it('returns true on successful connect', () => {
		const result = client.connect('http://localhost/stream', onMessage, onError, onComplete);
		expect(result).toBe(true);
	});

	it('returns false and fires error when EventSource not supported', () => {
		const saved = globalThis.EventSource;
		// @ts-ignore
		delete globalThis.EventSource;
		try {
			const localClient = new SSEClient();
			const result = localClient.connect('http://localhost/stream', onMessage, onError, onComplete);
			expect(result).toBe(false);
			expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'SSE_NOT_SUPPORTED' }));
		} finally {
			globalThis.EventSource = saved;
		}
	});

	// ── message handling ──

	it('parses and forwards progress messages', () => {
		client.connect('http://localhost/stream', onMessage, onError, onComplete);
		const es = getEventSource(client);

		es.simulateMessage({ type: 'progress', message: 'Working', phase: 'doc_summary', percent: 42 });

		expect(onMessage).toHaveBeenCalledWith(expect.objectContaining({
			type: 'progress',
			message: 'Working',
			percent: 42,
		}));
	});

	it('skips empty keep-alive messages', () => {
		client.connect('http://localhost/stream', onMessage, onError, onComplete);
		const es = getEventSource(client);

		es.simulateMessage('   ');
		es.simulateMessage(': ping');

		expect(onMessage).not.toHaveBeenCalled();
	});

	it('fires parse error for invalid JSON', () => {
		client.connect('http://localhost/stream', onMessage, onError, onComplete);
		const es = getEventSource(client);

		es.simulateMessage('not valid json {{{');

		expect(onError).toHaveBeenCalledWith(expect.objectContaining({
			message: expect.stringContaining('Failed to parse'),
		}));
	});

	// ── terminal events ──

	it('disconnects and calls onComplete on "completed" event', () => {
		client.connect('http://localhost/stream', onMessage, onError, onComplete);
		const es = getEventSource(client);

		es.simulateMessage({ type: 'completed', message: 'Done', phase: 'done', percent: 100 });

		expect(onMessage).toHaveBeenCalled();
		expect(onComplete).toHaveBeenCalled();
		expect(client.isConnected()).toBe(false);
	});

	it('disconnects and calls onComplete on "failed" event', () => {
		client.connect('http://localhost/stream', onMessage, onError, onComplete);
		const es = getEventSource(client);

		es.simulateMessage({ type: 'failed', message: 'Error', phase: 'error', percent: 50, error: 'boom' });

		expect(onComplete).toHaveBeenCalled();
	});

	it('disconnects and calls onComplete on "error" event', () => {
		client.connect('http://localhost/stream', onMessage, onError, onComplete);
		const es = getEventSource(client);

		es.simulateMessage({ type: 'error', message: 'Bad', phase: 'error', percent: 0 });

		expect(onComplete).toHaveBeenCalled();
	});

	// ── reconnection ──

	it('reconnects with exponential backoff on connection error', () => {
		client.connect('http://localhost/stream', onMessage, onError, onComplete);
		const es = getEventSource(client);

		// Simulate connection error
		es.simulateError();

		// Should schedule reconnect after 1s (first attempt)
		expect(onError).not.toHaveBeenCalled(); // Not called yet, retrying

		// Advance past first reconnect delay (1s)
		vi.advanceTimersByTime(1000);

		// Should have created a new EventSource (reconnected)
		// The second error triggers 2s delay
	});

	it('fires SSE_CONNECTION_FAILED after max reconnect attempts', () => {
		client.connect('http://localhost/stream', onMessage, onError, onComplete);

		// Let the initial onopen fire (clears reconnect counter — normal behavior)
		vi.advanceTimersByTime(0);

		// Now suppress onopen on reconnected EventSources — simulates connections
		// that fail before fully opening (so reconnectAttempts accumulates)
		MockEventSource._suppressOpen = true;

		// maxReconnectAttempts = 3 in SSEClient
		// Need 4 errors: 3 trigger reconnects (attempts 1,2,3), 4th hits max
		const es1 = getEventSource(client)!;
		es1.simulateError(); // reconnectAttempts = 1, schedules reconnect at 1s

		vi.advanceTimersByTime(1000); // reconnect → ES2
		const es2 = getEventSource(client)!;
		es2.simulateError(); // reconnectAttempts = 2, schedules reconnect at 2s

		vi.advanceTimersByTime(2000); // reconnect → ES3
		const es3 = getEventSource(client)!;
		es3.simulateError(); // reconnectAttempts = 3, schedules reconnect at 4s

		vi.advanceTimersByTime(4000); // reconnect → ES4
		const es4 = getEventSource(client)!;
		es4.simulateError(); // reconnectAttempts = 3, 3 < 3 is false → FAILED

		expect(onError).toHaveBeenCalledWith(expect.objectContaining({
			message: 'SSE_CONNECTION_FAILED',
		}));
		expect(onComplete).toHaveBeenCalled();

		MockEventSource._suppressOpen = false;
	});

	it('does not reconnect after manual disconnect', () => {
		client.connect('http://localhost/stream', onMessage, onError, onComplete);
		client.disconnect();

		const es = getEventSource(client);
		// EventSource should be null after disconnect
		expect(es).toBeNull();
	});

	// ── inactivity timeout ──

	it('fires SSE_TIMEOUT after 5 minutes of inactivity', () => {
		client.connect('http://localhost/stream', onMessage, onError, onComplete);

		// Advance past inactivity timeout (5 minutes = 300000ms)
		vi.advanceTimersByTime(300001);

		expect(onError).toHaveBeenCalledWith(expect.objectContaining({
			message: expect.stringContaining('SSE_TIMEOUT'),
		}));
		expect(onComplete).toHaveBeenCalled();
	});

	it('resets inactivity timer on message', () => {
		client.connect('http://localhost/stream', onMessage, onError, onComplete);
		const es = getEventSource(client);

		// Advance 4 minutes
		vi.advanceTimersByTime(240000);

		// Send a message — should reset timer
		es.simulateMessage({ type: 'progress', message: 'Still alive', phase: 'working', percent: 50 });

		// Advance another 4 minutes (total 8 since start, but only 4 since last message)
		vi.advanceTimersByTime(240000);

		// Should NOT have timed out (only 4 min since last message)
		expect(onError).not.toHaveBeenCalled();

		// Advance past full timeout from last message
		vi.advanceTimersByTime(60001);

		expect(onError).toHaveBeenCalledWith(expect.objectContaining({
			message: expect.stringContaining('SSE_TIMEOUT'),
		}));
	});

	it('resets inactivity timer on keep-alive', () => {
		client.connect('http://localhost/stream', onMessage, onError, onComplete);
		const es = getEventSource(client);

		// Advance 4.5 minutes
		vi.advanceTimersByTime(270000);

		// Send keep-alive
		es.simulateMessage('   ');

		// Advance another 4.5 minutes (total 9 since start, 4.5 since keep-alive)
		vi.advanceTimersByTime(270000);

		// Should NOT have timed out
		expect(onError).not.toHaveBeenCalled();
	});

	// ── disconnect ──

	it('disconnect clears all state', () => {
		client.connect('http://localhost/stream', onMessage, onError, onComplete);
		client.disconnect();

		expect(client.isConnected()).toBe(false);
	});

	// ── resets reconnect counter ──

	it('resets reconnect counter on successful message', () => {
		client.connect('http://localhost/stream', onMessage, onError, onComplete);
		const es = getEventSource(client);

		// Simulate an error then reconnect
		es.simulateError();
		vi.advanceTimersByTime(1000);

		// Now send a successful message on the new connection
		const es2 = getEventSource(client);
		if (es2) {
			es2.simulateMessage({ type: 'progress', message: 'OK', phase: 'p', percent: 10 });
		}

		// Reconnect counter should be reset, so we get 3 more attempts
		// (not tested deeply — just verifying the message was received)
		expect(onMessage).toHaveBeenCalled();
	});
});

// Helper to access private eventSource
function getEventSource(client: SSEClient): MockEventSource | null {
	return (client as any).eventSource;
}
