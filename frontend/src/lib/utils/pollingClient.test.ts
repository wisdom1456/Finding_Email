import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { PollingClient } from './pollingClient';

describe('PollingClient', () => {
	let client: PollingClient;
	let onMessage: ReturnType<typeof vi.fn>;
	let onError: ReturnType<typeof vi.fn>;
	let onComplete: ReturnType<typeof vi.fn>;
	let mockFetch: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		vi.useFakeTimers();
		client = new PollingClient();
		onMessage = vi.fn();
		onError = vi.fn();
		onComplete = vi.fn();
		mockFetch = vi.fn();
		vi.stubGlobal('fetch', mockFetch);
	});

	afterEach(() => {
		client.stopPolling();
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	function makeResponse(data: any, ok = true, status = 200) {
		return Promise.resolve({
			ok,
			status,
			statusText: ok ? 'OK' : 'Error',
			json: () => Promise.resolve(data),
		} as Response);
	}

	function makeProgressEvent(overrides: Record<string, any> = {}) {
		return {
			type: 'progress',
			message: 'Working',
			phase: 'doc_summary',
			percent: 50,
			timestamp: new Date().toISOString(),
			...overrides,
		};
	}

	// ── basic polling ──

	it('sends first poll immediately on start', async () => {
		mockFetch.mockReturnValue(makeResponse(makeProgressEvent()));

		client.startPolling('http://localhost/status', 'token-123', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		expect(mockFetch).toHaveBeenCalledWith('http://localhost/status', {
			headers: { Authorization: 'Bearer token-123' },
		});
	});

	it('delivers progress events to onMessage', async () => {
		const event = makeProgressEvent({ percent: 30 });
		mockFetch.mockReturnValue(makeResponse(event));

		client.startPolling('http://localhost/status', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		expect(onMessage).toHaveBeenCalledWith(expect.objectContaining({ percent: 30 }));
	});

	it('polls every 3 seconds', async () => {
		let callCount = 0;
		mockFetch.mockImplementation(() => {
			callCount++;
			return makeResponse(makeProgressEvent({ percent: callCount * 10, timestamp: `t${callCount}` }));
		});

		client.startPolling('http://localhost/status', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0); // first poll
		expect(mockFetch).toHaveBeenCalledTimes(1);

		await vi.advanceTimersByTimeAsync(3000); // second poll
		expect(mockFetch).toHaveBeenCalledTimes(2);

		await vi.advanceTimersByTimeAsync(3000); // third poll
		expect(mockFetch).toHaveBeenCalledTimes(3);
	});

	// ── terminal events ──

	it('stops polling on completed event', async () => {
		mockFetch.mockReturnValue(makeResponse(makeProgressEvent({ type: 'completed', percent: 100 })));

		client.startPolling('http://localhost/status', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		expect(onComplete).toHaveBeenCalled();
		expect(client.isPolling()).toBe(false);
	});

	it('stops polling on failed event', async () => {
		mockFetch.mockReturnValue(makeResponse(makeProgressEvent({ type: 'failed' })));

		client.startPolling('http://localhost/status', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		expect(onComplete).toHaveBeenCalled();
		expect(client.isPolling()).toBe(false);
	});

	it('stops polling on error event', async () => {
		mockFetch.mockReturnValue(makeResponse(makeProgressEvent({ type: 'error' })));

		client.startPolling('http://localhost/status', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);

		expect(onComplete).toHaveBeenCalled();
	});

	// ── duplicate event filtering ──

	it('skips duplicate events with same fingerprint', async () => {
		const event = makeProgressEvent({ percent: 50, phase: 'p1', timestamp: 't1' });
		mockFetch.mockReturnValue(makeResponse(event));

		client.startPolling('http://localhost/status', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0); // first poll — delivers
		await vi.advanceTimersByTimeAsync(3000); // second poll — same data, skipped

		expect(onMessage).toHaveBeenCalledTimes(1);
	});

	// ── stall detection ──

	it('sends stall warning at 90 seconds of no progress change', async () => {
		const event = makeProgressEvent({ percent: 30, timestamp: 't1' });
		let callIdx = 0;
		mockFetch.mockImplementation(() => {
			callIdx++;
			// Each call returns same percent but different timestamp to avoid duplicate filtering
			return makeResponse({ ...event, timestamp: `t${callIdx}` });
		});

		client.startPolling('http://localhost/status', 'tok', onMessage, onError, onComplete);

		// Need 31 polls for stall warning (first + 30 stalls)
		// Poll 0 is immediate, then every 3s
		for (let i = 0; i <= 30; i++) {
			await vi.advanceTimersByTimeAsync(i === 0 ? 0 : 3000);
		}

		// Should have sent a stall warning message
		const stallMessage = onMessage.mock.calls.find(
			(call: any[]) => call[0].message?.includes('Processing large document')
		);
		expect(stallMessage).toBeTruthy();
	});

	it('sends stalled event after 5 minutes of no progress', async () => {
		let callIdx = 0;
		mockFetch.mockImplementation(() => {
			callIdx++;
			return makeResponse(makeProgressEvent({ percent: 20, timestamp: `t${callIdx}` }));
		});

		client.startPolling('http://localhost/status', 'tok', onMessage, onError, onComplete);

		// 101 polls (first + 100 stalls) to trigger graceful exit
		for (let i = 0; i <= 100; i++) {
			await vi.advanceTimersByTimeAsync(i === 0 ? 0 : 3000);
		}

		// Should have sent a "stalled" event
		const stalledEvent = onMessage.mock.calls.find(
			(call: any[]) => call[0].type === 'stalled'
		);
		expect(stalledEvent).toBeTruthy();
		expect(onComplete).toHaveBeenCalled();
		expect(client.isPolling()).toBe(false);
	});

	// ── max poll timeout ──

	it('fires POLLING_TIMEOUT after maxPollAttempts', async () => {
		let callIdx = 0;
		mockFetch.mockImplementation(() => {
			callIdx++;
			return makeResponse(makeProgressEvent({ percent: callIdx, timestamp: `t${callIdx}` }));
		});

		client.startPolling('http://localhost/status', 'tok', onMessage, onError, onComplete);

		// Exhaust all 400 poll attempts (but stall detection may fire first)
		// For this test, set maxPollAttempts via private field
		(client as any).maxPollAttempts = 3;

		await vi.advanceTimersByTimeAsync(0); // poll 1
		await vi.advanceTimersByTimeAsync(3000); // poll 2
		await vi.advanceTimersByTimeAsync(3000); // poll 3
		await vi.advanceTimersByTimeAsync(3000); // poll 4 — exceeds max

		expect(onError).toHaveBeenCalledWith(expect.objectContaining({
			message: expect.stringContaining('POLLING_TIMEOUT'),
		}));
		expect(onComplete).toHaveBeenCalled();
	});

	// ── fetch error resilience ──

	it('retries after fetch error instead of failing immediately', async () => {
		mockFetch
			.mockRejectedValueOnce(new Error('Network error'))
			.mockReturnValue(makeResponse(makeProgressEvent({ percent: 10, timestamp: 't2' })));

		client.startPolling('http://localhost/status', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0); // first poll — error

		// Should NOT have fired onError (retries instead)
		expect(onError).not.toHaveBeenCalled();

		await vi.advanceTimersByTimeAsync(3000); // second poll — succeeds
		expect(onMessage).toHaveBeenCalledWith(expect.objectContaining({ percent: 10 }));
	});

	it('fires error after fetch failure when max attempts exceeded', async () => {
		mockFetch.mockRejectedValue(new Error('Persistent network error'));
		(client as any).maxPollAttempts = 2;

		client.startPolling('http://localhost/status', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0); // poll 1 — error
		await vi.advanceTimersByTimeAsync(3000); // poll 2 — error
		await vi.advanceTimersByTimeAsync(3000); // poll 3 — exceeds max

		expect(onError).toHaveBeenCalledWith(expect.objectContaining({
			message: expect.stringContaining('Persistent network error'),
		}));
		expect(onComplete).toHaveBeenCalled();
	});

	it('fires error on non-ok HTTP response', async () => {
		mockFetch
			.mockReturnValueOnce(makeResponse({}, false, 500))
			.mockReturnValue(makeResponse(makeProgressEvent({ percent: 10, timestamp: 't2' })));

		client.startPolling('http://localhost/status', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0); // poll 1 — 500 error

		// Retries on next poll instead of giving up
		expect(onError).not.toHaveBeenCalled();

		await vi.advanceTimersByTimeAsync(3000); // poll 2 — succeeds
		expect(onMessage).toHaveBeenCalled();
	});

	// ── stopPolling ──

	it('stopPolling prevents further polls', async () => {
		mockFetch.mockReturnValue(makeResponse(makeProgressEvent()));

		client.startPolling('http://localhost/status', 'tok', onMessage, onError, onComplete);
		await vi.advanceTimersByTimeAsync(0);
		expect(mockFetch).toHaveBeenCalledTimes(1);

		client.stopPolling();
		await vi.advanceTimersByTimeAsync(10000);
		expect(mockFetch).toHaveBeenCalledTimes(1); // no more calls
	});

	it('isPolling returns correct state', async () => {
		expect(client.isPolling()).toBe(false);

		mockFetch.mockReturnValue(makeResponse(makeProgressEvent()));
		client.startPolling('http://localhost/status', 'tok', onMessage, onError, onComplete);
		expect(client.isPolling()).toBe(true);

		client.stopPolling();
		expect(client.isPolling()).toBe(false);
	});

	// ── stall counter reset on progress ──

	it('resets stall counter when progress increases', async () => {
		let callIdx = 0;
		mockFetch.mockImplementation(() => {
			callIdx++;
			// First 10 calls: stuck at 20%, then jump to 50%
			const percent = callIdx <= 10 ? 20 : 50;
			return makeResponse(makeProgressEvent({ percent, timestamp: `t${callIdx}` }));
		});

		client.startPolling('http://localhost/status', 'tok', onMessage, onError, onComplete);

		// 10 polls at same percent
		for (let i = 0; i <= 10; i++) {
			await vi.advanceTimersByTimeAsync(i === 0 ? 0 : 3000);
		}

		// Poll 11 jumps to 50% — should reset stall counter
		await vi.advanceTimersByTimeAsync(3000);

		// Another 10 polls at 50% should NOT trigger stall warning (counter was reset)
		for (let i = 0; i < 10; i++) {
			await vi.advanceTimersByTimeAsync(3000);
		}

		// Stall count should be around 10, not 20+ (it was reset)
		const stallMessages = onMessage.mock.calls.filter(
			(call: any[]) => call[0].message?.includes('Processing large document')
		);
		expect(stallMessages.length).toBe(0);
	});
});
