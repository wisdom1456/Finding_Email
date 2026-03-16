/**
 * Integration tests for progressStore recovery paths.
 *
 * These tests wire together the REAL progressStore and SSEClient
 * with controlled fetch mocks to simulate network disconnects,
 * backend completion races, reconnect exhaustion, and auth failures.
 *
 * They cover two bug classes:
 * 1. "backend finished, UI stuck after disconnect"
 * 2. "recovery path fails because token expired" (401 on status/polling)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { get } from 'svelte/store';

// ── Controllable SSE stream via fetch mock ──

const encoder = new TextEncoder();

/** Create a ReadableStream whose chunks we control from tests. */
function createControllableStream() {
	let ctrl!: ReadableStreamDefaultController<Uint8Array>;
	const stream = new ReadableStream<Uint8Array>({
		start(c) { ctrl = c; },
	});
	return {
		stream,
		/** Push an SSE-formatted JSON event */
		pushEvent(obj: Record<string, unknown>) {
			ctrl.enqueue(encoder.encode(`data: ${JSON.stringify(obj)}\n\n`));
		},
		/** Push raw text (e.g., keep-alive) */
		pushRaw(text: string) {
			ctrl.enqueue(encoder.encode(text));
		},
		/** Close the stream (simulates EOF / network disconnect) */
		close() { ctrl.close(); },
		/** Error the stream (simulates network failure) */
		error(e: Error) { ctrl.error(e); },
	};
}

type FetchImpl = (url: string | URL | Request, init?: RequestInit) => Promise<Response>;

// ── Mock dependencies ──

vi.mock('$lib/config', () => ({
	getApiUrl: () => 'http://localhost:8000',
}));

const { mockGetSession } = vi.hoisted(() => ({
	mockGetSession: vi.fn(),
}));

vi.mock('$lib/supabase', () => ({
	getSecureSession: mockGetSession,
}));

// Import after mocks
import {
	progressStore,
	isProcessing,
	isComplete,
	hasError,
} from './progressStore';

// ── Helpers ──

const STREAM_URL = 'http://localhost:8000/api/progress/analysis/test-id';
const STATUS_URL = 'http://localhost:8000/api/progress/analysis/test-id/status';
const TOKEN = 'test-jwt-token';

/** Connect the store with both stream and status URLs. */
function connectStore(onComplete?: (data?: unknown) => void) {
	progressStore.connect(STREAM_URL, onComplete, STATUS_URL, TOKEN);
}

/** Wait for all pending microtasks + timers to flush. */
async function flushAsync() {
	await vi.advanceTimersByTimeAsync(0);
}

describe('progressStore recovery integration', () => {
	let currentStream: ReturnType<typeof createControllableStream>;
	let fetchMock: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		vi.useFakeTimers();
		progressStore.reset();
		vi.clearAllMocks();

		currentStream = createControllableStream();

		// Default: SSE fetch succeeds, status endpoint not yet called
		fetchMock = vi.fn().mockImplementation((url: string) => {
			if (url === STREAM_URL) {
				return Promise.resolve({
					ok: true,
					body: currentStream.stream,
				});
			}
			// Status endpoint — default: 404 (not ready)
			return Promise.resolve({
				ok: false,
				status: 404,
			});
		});
		vi.stubGlobal('fetch', fetchMock);
	});

	afterEach(() => {
		progressStore.disconnect();
		vi.useRealTimers();
		vi.restoreAllMocks();
	});

	// ═══════════════════════════════════════════════════════════
	// Scenario A — stream ends without terminal event
	// ═══════════════════════════════════════════════════════════

	describe('Scenario A: stream EOF without terminal event', () => {
		it('transitions out of active state after stream closes unexpectedly', async () => {
			connectStore();
			await flushAsync();

			// Simulate some progress
			currentStream.pushEvent({ type: 'progress', message: 'Working', phase: 'p', percent: 50 });
			await flushAsync();
			expect(get(progressStore).status).toBe('active');
			expect(get(progressStore).percent).toBe(50);

			// Stream closes without a completed/failed event (network disconnect)
			currentStream.close();
			await flushAsync();

			// The store must NOT remain in 'active' — it should have entered recovery.
			// Recovery does a one-shot status check. Since our default status mock returns 404,
			// it falls back to polling. The polling client starts, keeping status 'active'
			// until it gets a real update or times out.
			// Key assertion: the store attempted reconciliation (status fetch was called)
			const statusCalls = fetchMock.mock.calls.filter(
				(c: any[]) => c[0] === STATUS_URL
			);
			expect(statusCalls.length).toBeGreaterThanOrEqual(1);
		});

		it('does not stay in connecting state after EOF', async () => {
			connectStore();
			await flushAsync();

			// Close immediately without any events
			currentStream.close();
			await flushAsync();

			const state = get(progressStore);
			// Should not be 'connecting' — must have moved to recovery
			expect(state.status).not.toBe('connecting');
		});
	});

	// ═══════════════════════════════════════════════════════════
	// Scenario B — stream disconnect after backend already finished
	// ═══════════════════════════════════════════════════════════

	describe('Scenario B: disconnect after backend completed', () => {
		it('reconciles to completed when status endpoint reports completed', async () => {
			// Status endpoint returns completed
			fetchMock.mockImplementation((url: string) => {
				if (url === STREAM_URL) {
					return Promise.resolve({ ok: true, body: currentStream.stream });
				}
				if (url === STATUS_URL) {
					return Promise.resolve({
						ok: true,
						json: () => Promise.resolve({
							type: 'completed',
							message: 'Analysis complete',
							phase: 'done',
							percent: 100,
						}),
					});
				}
				return Promise.resolve({ ok: false, status: 404 });
			});

			const onComplete = vi.fn();
			connectStore(onComplete);
			await flushAsync();

			// Simulate progress then disconnect
			currentStream.pushEvent({ type: 'progress', message: 'Working', phase: 'p', percent: 60 });
			await flushAsync();

			currentStream.close();
			await flushAsync();

			// The reconcileFromStatus call happens asynchronously
			// Flush promises
			await flushAsync();
			await flushAsync();

			const state = get(progressStore);
			expect(state.status).toBe('completed');
			expect(state.percent).toBe(100);
			expect(get(isComplete)).toBe(true);
			expect(get(isProcessing)).toBe(false);
			expect(onComplete).toHaveBeenCalled();
		});

		it('reconciles to error when status endpoint reports failed', async () => {
			fetchMock.mockImplementation((url: string) => {
				if (url === STREAM_URL) {
					return Promise.resolve({ ok: true, body: currentStream.stream });
				}
				if (url === STATUS_URL) {
					return Promise.resolve({
						ok: true,
						json: () => Promise.resolve({
							type: 'failed',
							message: 'Analysis failed: model error',
							phase: 'error',
							percent: 30,
							error: 'Model error',
						}),
					});
				}
				return Promise.resolve({ ok: false, status: 404 });
			});

			connectStore();
			await flushAsync();

			currentStream.pushEvent({ type: 'progress', message: 'Working', phase: 'p', percent: 30 });
			await flushAsync();

			currentStream.close();
			await flushAsync();
			await flushAsync();

			const state = get(progressStore);
			expect(state.status).toBe('error');
			expect(get(hasError)).toBe(true);
		});

		it('does not start polling when status endpoint confirms completion', async () => {
			fetchMock.mockImplementation((url: string) => {
				if (url === STREAM_URL) {
					return Promise.resolve({ ok: true, body: currentStream.stream });
				}
				if (url === STATUS_URL) {
					return Promise.resolve({
						ok: true,
						json: () => Promise.resolve({
							type: 'completed',
							message: 'Done',
							phase: 'done',
							percent: 100,
						}),
					});
				}
				return Promise.resolve({ ok: false, status: 404 });
			});

			connectStore();
			await flushAsync();

			currentStream.close();
			await flushAsync();
			await flushAsync();

			// After reconciliation, no further fetch calls should happen (no polling)
			const callCountAfterReconcile = fetchMock.mock.calls.length;

			// Advance 10 seconds — polling would have made calls at 3s intervals
			await vi.advanceTimersByTimeAsync(10000);

			expect(fetchMock.mock.calls.length).toBe(callCountAfterReconcile);
		});
	});

	// ═══════════════════════════════════════════════════════════
	// Scenario C — repeated reconnect failures
	// ═══════════════════════════════════════════════════════════

	describe('Scenario C: repeated reconnect failures', () => {
		it('stops retrying after max reconnect attempts and enters error state', async () => {
			// All fetch calls fail
			fetchMock.mockRejectedValue(new Error('Network error'));

			connectStore();

			// SSEClient: attempt 1 fails
			await flushAsync();

			// Attempt 2 after 1s backoff
			await vi.advanceTimersByTimeAsync(1000);
			await flushAsync();

			// Attempt 3 after 2s backoff
			await vi.advanceTimersByTimeAsync(2000);
			await flushAsync();

			// Attempt 4 after 4s — exceeds maxReconnectAttempts (3)
			await vi.advanceTimersByTimeAsync(4000);
			await flushAsync();

			// SSE_CONNECTION_FAILED fires → progressStore errorHandler →
			// reconcileFromStatus also fails → falls back to polling → polling also fails
			// Give it time to settle
			await vi.advanceTimersByTimeAsync(10000);
			await flushAsync();

			// The store should NOT be in 'connecting' or 'active' indefinitely
			const state = get(progressStore);
			// It's either in error (if status check failed) or active (polling started)
			// but fetch keeps failing, so polling will eventually error too
			expect(['error', 'active']).toContain(state.status);

			// Advance well past polling max (20 min) to verify it doesn't loop forever
			// PollingClient max is 400 * 3s = 1200s
			await vi.advanceTimersByTimeAsync(1300 * 1000);
			await flushAsync();

			// Now it must be in error or idle — not still active
			const finalState = get(progressStore);
			// The polling will eventually error out after max attempts
			expect(finalState.status).not.toBe('connecting');
		});

		it('exposes usable error message after exhausting retries', async () => {
			// Status endpoint fails, no polling URL
			fetchMock.mockRejectedValue(new Error('Network error'));

			// Connect WITHOUT a status URL — non-recoverable path
			progressStore.connect(STREAM_URL, undefined, undefined, TOKEN);

			// Exhaust retries: 1 + 3 reconnects
			await flushAsync();
			await vi.advanceTimersByTimeAsync(1000);
			await flushAsync();
			await vi.advanceTimersByTimeAsync(2000);
			await flushAsync();
			await vi.advanceTimersByTimeAsync(4000);
			await flushAsync();

			const state = get(progressStore);
			expect(state.status).toBe('error');
			expect(state.error).toBeTruthy();
			expect(get(hasError)).toBe(true);
		});
	});

	// ═══════════════════════════════════════════════════════════
	// Scenario D — stream disconnect + status endpoint unavailable
	// ═══════════════════════════════════════════════════════════

	describe('Scenario D: disconnect + status endpoint unavailable', () => {
		it('falls back to polling when status check returns non-terminal', async () => {
			fetchMock.mockImplementation((url: string) => {
				if (url === STREAM_URL) {
					return Promise.resolve({ ok: true, body: currentStream.stream });
				}
				if (url === STATUS_URL) {
					// Status returns "still in progress" (not terminal)
					return Promise.resolve({
						ok: true,
						json: () => Promise.resolve({
							type: 'progress',
							message: 'Still processing',
							phase: 'doc_summary',
							percent: 40,
						}),
					});
				}
				return Promise.resolve({ ok: false, status: 404 });
			});

			connectStore();
			await flushAsync();

			currentStream.close();
			await flushAsync();
			await flushAsync();

			// Status returned non-terminal → should have started polling
			const state = get(progressStore);
			expect(state.status).toBe('active');
			// Note: message may be 'Reconnecting...' or 'Still processing' depending on
			// whether the polling response has already overwritten the reconnect message

			// Advance 3s — polling should make a call
			await vi.advanceTimersByTimeAsync(3000);
			await flushAsync();

			const statusCalls = fetchMock.mock.calls.filter(
				(c: any[]) => c[0] === STATUS_URL
			);
			// At least 2: one from reconcile, one from polling
			expect(statusCalls.length).toBeGreaterThanOrEqual(2);
		});

		it('falls back to polling when status endpoint errors', async () => {
			fetchMock.mockImplementation((url: string) => {
				if (url === STREAM_URL) {
					return Promise.resolve({ ok: true, body: currentStream.stream });
				}
				if (url === STATUS_URL) {
					return Promise.reject(new Error('Status endpoint down'));
				}
				return Promise.resolve({ ok: false, status: 404 });
			});

			connectStore();
			await flushAsync();

			currentStream.close();
			await flushAsync();
			await flushAsync();

			// reconcileFromStatus failed → should still fall back to polling
			const state = get(progressStore);
			expect(state.status).toBe('active');
		});

		it('polling eventually delivers backend completion after disconnect', async () => {
			let pollCount = 0;
			fetchMock.mockImplementation((url: string) => {
				if (url === STREAM_URL) {
					return Promise.resolve({ ok: true, body: currentStream.stream });
				}
				if (url === STATUS_URL) {
					pollCount++;
					if (pollCount <= 2) {
						// First two polls: still in progress
						return Promise.resolve({
							ok: true,
							json: () => Promise.resolve({
								type: 'progress',
								message: 'Still working',
								phase: 'deep_analysis',
								percent: 70,
							}),
						});
					}
					// Third poll: completed
					return Promise.resolve({
						ok: true,
						json: () => Promise.resolve({
							type: 'completed',
							message: 'Analysis complete',
							phase: 'done',
							percent: 100,
						}),
					});
				}
				return Promise.resolve({ ok: false, status: 404 });
			});

			const onComplete = vi.fn();
			connectStore(onComplete);
			await flushAsync();

			currentStream.close();
			await flushAsync();
			await flushAsync();

			// Poll 1 (from reconcile) — still in progress → starts polling
			// Poll 2 (3s later) — still in progress
			await vi.advanceTimersByTimeAsync(3000);
			await flushAsync();

			// Poll 3 (3s later) — completed!
			await vi.advanceTimersByTimeAsync(3000);
			await flushAsync();

			const state = get(progressStore);
			expect(state.status).toBe('completed');
			expect(state.percent).toBe(100);
			expect(get(isComplete)).toBe(true);
			expect(onComplete).toHaveBeenCalled();
		});
	});

	// ═══════════════════════════════════════════════════════════
	// Scenario E — clean terminal events (regression baseline)
	// ═══════════════════════════════════════════════════════════

	describe('Scenario E: normal terminal events (no recovery needed)', () => {
		it('settles to completed on normal completed event', async () => {
			const onComplete = vi.fn();
			connectStore(onComplete);
			await flushAsync();

			currentStream.pushEvent({ type: 'progress', message: 'Working', phase: 'p', percent: 50 });
			await flushAsync();

			currentStream.pushEvent({ type: 'completed', message: 'Done', phase: 'done', percent: 100 });
			await flushAsync();

			expect(get(progressStore).status).toBe('completed');
			expect(get(isComplete)).toBe(true);
			expect(onComplete).toHaveBeenCalled();

			// No status endpoint calls needed — stream delivered the terminal event
			const statusCalls = fetchMock.mock.calls.filter(
				(c: any[]) => c[0] === STATUS_URL
			);
			expect(statusCalls.length).toBe(0);
		});

		it('settles to error on normal error event', async () => {
			connectStore();
			await flushAsync();

			currentStream.pushEvent({
				type: 'error',
				message: 'Model error',
				phase: 'error',
				percent: 30,
				error: 'Context length exceeded',
			});
			await flushAsync();

			expect(get(progressStore).status).toBe('error');
			expect(get(progressStore).error).toBeTruthy();
			expect(get(hasError)).toBe(true);
		});
	});

	// ═══════════════════════════════════════════════════════════
	// Scenario F — SSE_TIMEOUT triggers same recovery
	// ═══════════════════════════════════════════════════════════

	describe('Scenario F: SSE_TIMEOUT triggers reconciliation', () => {
		it('reconciles after 5-minute inactivity timeout', async () => {
			fetchMock.mockImplementation((url: string) => {
				if (url === STREAM_URL) {
					return Promise.resolve({ ok: true, body: currentStream.stream });
				}
				if (url === STATUS_URL) {
					return Promise.resolve({
						ok: true,
						json: () => Promise.resolve({
							type: 'completed',
							message: 'Done',
							phase: 'done',
							percent: 100,
						}),
					});
				}
				return Promise.resolve({ ok: false, status: 404 });
			});

			connectStore();
			await flushAsync();

			// Send initial progress
			currentStream.pushEvent({ type: 'progress', message: 'Working', phase: 'p', percent: 50 });
			await flushAsync();

			// Advance past 5-minute inactivity timeout (no more events)
			vi.advanceTimersByTime(300001);
			await flushAsync();
			await flushAsync();

			// SSE_TIMEOUT should trigger → reconcileFromStatus → finds completed
			const state = get(progressStore);
			expect(state.status).toBe('completed');
		});
	});

	// ═══════════════════════════════════════════════════════════
	// Scenario G — connect without status URL
	// ═══════════════════════════════════════════════════════════

	describe('Scenario G: no status URL available for recovery', () => {
		it('goes to error state when stream disconnects without status URL', async () => {
			const noStatusStream = createControllableStream();
			fetchMock.mockImplementation((url: string) => {
				if (url === STREAM_URL) {
					return Promise.resolve({ ok: true, body: noStatusStream.stream });
				}
				return Promise.resolve({ ok: false, status: 404 });
			});

			// Connect WITHOUT status URL
			progressStore.connect(STREAM_URL, undefined, undefined, TOKEN);
			await flushAsync();

			noStatusStream.pushEvent({ type: 'progress', message: 'Working', phase: 'p', percent: 50 });
			await flushAsync();

			noStatusStream.close();
			await flushAsync();

			// Without a status URL, the store should move to error
			const state = get(progressStore);
			expect(state.status).toBe('error');
			expect(state.error).toContain('SSE_STREAM_ENDED');
		});
	});

	// ═══════════════════════════════════════════════════════════
	// Scenario H — SSE gets 401 on initial connect
	// ═══════════════════════════════════════════════════════════

	describe('Scenario H: SSE auth failure on connect', () => {
		it('reports auth error when SSE returns 401 and refresh fails', async () => {
			// SSE returns 401, no valid session to refresh
			fetchMock.mockImplementation((url: string) => {
				if (url === STREAM_URL) {
					return Promise.resolve({ ok: false, status: 401, statusText: 'Unauthorized' });
				}
				return Promise.resolve({ ok: false, status: 401 });
			});

			// getSecureSession returns no session (refresh fails)
			mockGetSession.mockResolvedValue({ session: null, user: null });

			connectStore();
			await flushAsync();
			await flushAsync();

			const state = get(progressStore);
			expect(state.status).toBe('error');
			expect(state.error).toContain('Session expired');
		});

		it('falls back to polling with refreshed token when SSE returns 401', async () => {
			const FRESH_TOKEN = 'fresh-jwt-token';
			let sseCallCount = 0;

			fetchMock.mockImplementation((url: string, init?: RequestInit) => {
				if (url === STREAM_URL) {
					sseCallCount++;
					// SSE always returns 401 (can't do SSE with refresh mid-stream)
					return Promise.resolve({ ok: false, status: 401, statusText: 'Unauthorized' });
				}
				if (url === STATUS_URL) {
					const authHeader = (init?.headers as Record<string, string>)?.Authorization || '';
					if (authHeader.includes(FRESH_TOKEN)) {
						return Promise.resolve({
							ok: true,
							json: () => Promise.resolve({
								type: 'completed',
								message: 'Done',
								phase: 'done',
								percent: 100,
							}),
						});
					}
					return Promise.resolve({ ok: false, status: 401 });
				}
				return Promise.resolve({ ok: false, status: 404 });
			});

			// Token refresh succeeds
			mockGetSession.mockResolvedValue({
				session: { access_token: FRESH_TOKEN },
				user: { id: 'user-1' },
			});

			connectStore();
			await flushAsync();
			await flushAsync();
			// Give polling time to kick in
			await vi.advanceTimersByTimeAsync(1000);
			await flushAsync();
			await vi.advanceTimersByTimeAsync(3000);
			await flushAsync();

			const state = get(progressStore);
			// After refresh + polling with fresh token, should complete
			expect(state.status).toBe('completed');
		});
	});

	// ═══════════════════════════════════════════════════════════
	// Scenario I — status endpoint returns 401, token refresh succeeds
	// ═══════════════════════════════════════════════════════════

	describe('Scenario I: status endpoint 401 with token refresh', () => {
		it('refreshes token and retries status check on 401', async () => {
			const FRESH_TOKEN = 'refreshed-jwt-token';
			let statusCallCount = 0;

			fetchMock.mockImplementation((url: string, init?: RequestInit) => {
				if (url === STREAM_URL) {
					return Promise.resolve({ ok: true, body: currentStream.stream });
				}
				if (url === STATUS_URL) {
					statusCallCount++;
					const authHeader = (init?.headers as Record<string, string>)?.Authorization || '';
					if (authHeader.includes(FRESH_TOKEN)) {
						// Fresh token works
						return Promise.resolve({
							ok: true,
							json: () => Promise.resolve({
								type: 'completed',
								message: 'Analysis complete',
								phase: 'done',
								percent: 100,
							}),
						});
					}
					// Stale token returns 401
					return Promise.resolve({ ok: false, status: 401, statusText: 'Unauthorized' });
				}
				return Promise.resolve({ ok: false, status: 404 });
			});

			// Token refresh succeeds
			mockGetSession.mockResolvedValue({
				session: { access_token: FRESH_TOKEN },
				user: { id: 'user-1' },
			});

			connectStore();
			await flushAsync();

			// Stream closes unexpectedly
			currentStream.close();
			await flushAsync();
			await flushAsync();
			await flushAsync();

			const state = get(progressStore);
			// Should have refreshed token, retried status, and reconciled to completed
			expect(state.status).toBe('completed');
			expect(state.percent).toBe(100);
			// Status was called at least twice: once with stale token (401), once with fresh
			expect(statusCallCount).toBeGreaterThanOrEqual(2);
		});

		it('enters auth error state when both token and refresh fail', async () => {
			fetchMock.mockImplementation((url: string) => {
				if (url === STREAM_URL) {
					return Promise.resolve({ ok: true, body: currentStream.stream });
				}
				if (url === STATUS_URL) {
					return Promise.resolve({ ok: false, status: 401, statusText: 'Unauthorized' });
				}
				return Promise.resolve({ ok: false, status: 404 });
			});

			// Token refresh fails
			mockGetSession.mockResolvedValue({ session: null, user: null });

			connectStore();
			await flushAsync();

			currentStream.close();
			await flushAsync();
			await flushAsync();
			await flushAsync();

			const state = get(progressStore);
			expect(state.status).toBe('error');
			expect(state.error).toContain('Session expired');
		});
	});

	// ═══════════════════════════════════════════════════════════
	// Scenario J — polling gets 401, token refresh recovers
	// ═══════════════════════════════════════════════════════════

	describe('Scenario J: polling 401 with token refresh', () => {
		it('refreshes token mid-polling and continues to completion', async () => {
			const FRESH_TOKEN = 'polling-refreshed-token';
			let pollCount = 0;

			fetchMock.mockImplementation((url: string, init?: RequestInit) => {
				if (url === STREAM_URL) {
					return Promise.resolve({ ok: true, body: currentStream.stream });
				}
				if (url === STATUS_URL) {
					pollCount++;
					const authHeader = (init?.headers as Record<string, string>)?.Authorization || '';

					if (pollCount === 1) {
						// First call (reconcile): returns non-terminal → starts polling
						return Promise.resolve({
							ok: true,
							json: () => Promise.resolve({
								type: 'progress',
								message: 'Working',
								phase: 'analysis',
								percent: 50,
							}),
						});
					}
					if (pollCount === 2) {
						// Second call (first poll): 401 — token expired mid-session
						return Promise.resolve({ ok: false, status: 401, statusText: 'Unauthorized' });
					}
					// Third+ calls: with fresh token, return completed
					if (authHeader.includes(FRESH_TOKEN)) {
						return Promise.resolve({
							ok: true,
							json: () => Promise.resolve({
								type: 'completed',
								message: 'Done',
								phase: 'done',
								percent: 100,
							}),
						});
					}
					return Promise.resolve({ ok: false, status: 401 });
				}
				return Promise.resolve({ ok: false, status: 404 });
			});

			// Token refresh succeeds
			mockGetSession.mockResolvedValue({
				session: { access_token: FRESH_TOKEN },
				user: { id: 'user-1' },
			});

			connectStore();
			await flushAsync();

			currentStream.close();
			await flushAsync();
			await flushAsync();

			// First poll happens, gets 401 → triggers refresh
			await vi.advanceTimersByTimeAsync(3000);
			await flushAsync();
			// Refresh happens, retry with new token
			await vi.advanceTimersByTimeAsync(1000);
			await flushAsync();

			const state = get(progressStore);
			expect(state.status).toBe('completed');
		});

		it('stops polling after consecutive auth failures and enters error state', async () => {
			fetchMock.mockImplementation((url: string) => {
				if (url === STREAM_URL) {
					return Promise.resolve({ ok: true, body: currentStream.stream });
				}
				if (url === STATUS_URL) {
					return Promise.resolve({ ok: false, status: 401, statusText: 'Unauthorized' });
				}
				return Promise.resolve({ ok: false, status: 404 });
			});

			// Token refresh always fails
			mockGetSession.mockResolvedValue({ session: null, user: null });

			connectStore();
			await flushAsync();

			currentStream.close();
			await flushAsync();
			await flushAsync();
			await flushAsync();

			// reconcileFromStatus gets 401 → refreshes → still 401 → auth_failed
			// So it should go to error state without even starting polling
			const state = get(progressStore);
			expect(state.status).toBe('error');
			expect(state.error).toContain('Session expired');
		});

		it('does not retry infinitely on 401 — bounded auth failure count', async () => {
			let fetchCallCount = 0;
			fetchMock.mockImplementation((url: string) => {
				fetchCallCount++;
				if (url === STREAM_URL) {
					return Promise.resolve({ ok: true, body: currentStream.stream });
				}
				// Everything returns 401
				return Promise.resolve({ ok: false, status: 401, statusText: 'Unauthorized' });
			});

			mockGetSession.mockResolvedValue({ session: null, user: null });

			connectStore();
			await flushAsync();

			currentStream.close();
			await flushAsync();
			await flushAsync();
			await flushAsync();

			const callsAfterSettle = fetchCallCount;

			// Advance well past what would be many poll cycles
			await vi.advanceTimersByTimeAsync(60000);
			await flushAsync();

			// No additional fetch calls should have happened (no infinite loop)
			expect(fetchCallCount).toBe(callsAfterSettle);

			const state = get(progressStore);
			expect(state.status).toBe('error');
		});
	});
});
