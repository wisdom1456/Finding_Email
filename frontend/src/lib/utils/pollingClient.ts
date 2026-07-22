/**
 * Polling Client for Progress Updates
 *
 * Fallback mechanism when SSE is not available or times out.
 * Supports token refresh for long-running operations where JWTs expire.
 */

import type { ProgressEvent } from './sseClient';

export type PollingMessageHandler = (event: ProgressEvent) => void;
export type PollingErrorHandler = (error: Error) => void;
export type PollingCompleteHandler = () => void;
/** Returns a fresh access token, or null if refresh failed. */
export type TokenRefresher = () => Promise<string | null>;

/**
 * Options for tuning polling behavior. Used to support durable analysis
 * jobs that can run far longer than the legacy 20-minute default.
 */
export interface PollingOptions {
	/** Hard cap on poll iterations. Default 400 (20 min @ 3s). For durable
	 * worker jobs, pass 1200 (60 min) or higher. */
	maxPollAttempts?: number;
	/**
	 * When true, declare "stalled" based on response field `heartbeat_age`
	 * (seconds since worker last beat) rather than progress.percent
	 * stagnation. Long stages (fact_extraction, synthesis) can sit at the
	 * same percent for many minutes while the worker is still alive — the
	 * percent-based stall produced false positives in that case.
	 */
	useHeartbeatStall?: boolean;
	/** Threshold for the heartbeat-stall check. Default 180s (3x the
	 * worker's typical 30s heartbeat cadence; well below the 120s
	 * stale-job recovery threshold + safety margin). */
	maxHeartbeatStaleSeconds?: number;
	/** Poll frequency override (ms). Default 3000. */
	pollFrequencyMs?: number;
}

export class PollingClient {
	private pollInterval: NodeJS.Timeout | null = null;
	private pollFrequency = 3000; // Poll every 3 seconds
	private maxPollAttempts = 400; // 20 minutes max (400 * 3 seconds = 1200s)
	private pollAttempts = 0;
	private isActive = false;
	private url: string = '';
	private token: string = '';
	private tokenRefresher: TokenRefresher | null = null;
	private onMessageHandler: PollingMessageHandler | null = null;
	private onErrorHandler: PollingErrorHandler | null = null;
	private onCompleteHandler: PollingCompleteHandler | null = null;
	private lastProgressPercent = -1;
	private stallCount = 0;
	private maxStallCount = 30; // 30 polls * 3s = 90 seconds (earlier warning)
	private lastEventFingerprint = ''; // Track last event to prevent duplicate processing
	private consecutiveAuthFailures = 0;
	private maxConsecutiveAuthFailures = 2; // Stop after 2 consecutive 401s
	// Heartbeat-mode stall detection (durable worker jobs)
	private useHeartbeatStall = false;
	private maxHeartbeatStaleSeconds = 180;

	/**
	 * Start polling for progress updates
	 */
	startPolling(
		statusUrl: string,
		token: string,
		onMessage: PollingMessageHandler,
		onError: PollingErrorHandler,
		onComplete: PollingCompleteHandler,
		tokenRefresher?: TokenRefresher,
		options?: PollingOptions
	): void {
		this.url = statusUrl;
		this.token = token;
		this.onMessageHandler = onMessage;
		this.onErrorHandler = onError;
		this.onCompleteHandler = onComplete;
		this.tokenRefresher = tokenRefresher ?? null;
		this.isActive = true;
		this.pollAttempts = 0;
		this.lastProgressPercent = -1;
		this.stallCount = 0;
		this.consecutiveAuthFailures = 0;

		// Apply options (each falls back to the default if omitted)
		if (options?.maxPollAttempts !== undefined) {
			this.maxPollAttempts = options.maxPollAttempts;
		}
		if (options?.pollFrequencyMs !== undefined) {
			this.pollFrequency = options.pollFrequencyMs;
		}
		this.useHeartbeatStall = options?.useHeartbeatStall === true;
		if (options?.maxHeartbeatStaleSeconds !== undefined) {
			this.maxHeartbeatStaleSeconds = options.maxHeartbeatStaleSeconds;
		}

		// Start immediate poll
		this.poll();
	}

	/**
	 * Stop polling
	 */
	stopPolling(): void {
		this.isActive = false;
		if (this.pollInterval) {
			clearTimeout(this.pollInterval);
			this.pollInterval = null;
		}
	}

	/**
	 * Generate fingerprint for an event to detect duplicates
	 */
	private getEventFingerprint(data: ProgressEvent): string {
		const status = (data as any).status || data.type || '';
		return `${status}|${data.percent}|${data.phase}|${data.timestamp}|${data.document?.status}`;
	}

	/**
	 * Handle a 401/403 auth failure: attempt token refresh once,
	 * then stop if still failing.
	 * Returns true if we should retry with a new token.
	 */
	private async handleAuthFailure(status: number): Promise<boolean> {
		this.consecutiveAuthFailures++;
		console.warn(`[PollingClient] Auth failure (${status}), attempt ${this.consecutiveAuthFailures}/${this.maxConsecutiveAuthFailures}`);

		if (this.consecutiveAuthFailures > this.maxConsecutiveAuthFailures) {
			// Exhausted auth retries — terminal auth error
			if (this.onErrorHandler) {
				this.onErrorHandler(new Error(`AUTH_EXPIRED: Session expired after ${this.consecutiveAuthFailures} failed attempts (HTTP ${status})`));
			}
			this.stopPolling();
			if (this.onCompleteHandler) {
				this.onCompleteHandler();
			}
			return false;
		}

		// Try to refresh the token
		if (this.tokenRefresher) {
			try {
				const newToken = await this.tokenRefresher();
				if (newToken) {
					this.token = newToken;
					console.log('[PollingClient] Token refreshed successfully');
					return true; // Retry with new token
				}
			} catch (e) {
				console.error('[PollingClient] Token refresh failed:', e);
			}
		}

		// No refresher or refresh failed — report auth error
		if (this.onErrorHandler) {
			this.onErrorHandler(new Error(`AUTH_EXPIRED: Unable to refresh session (HTTP ${status})`));
		}
		this.stopPolling();
		if (this.onCompleteHandler) {
			this.onCompleteHandler();
		}
		return false;
	}

	/**
	 * Perform a single poll
	 */
	private async poll(): Promise<void> {
		if (!this.isActive) return;

		this.pollAttempts++;

		if (this.pollAttempts > this.maxPollAttempts) {
			if (this.onErrorHandler) {
				this.onErrorHandler(new Error('POLLING_TIMEOUT: Maximum polling duration exceeded'));
			}
			this.stopPolling();
			if (this.onCompleteHandler) {
				this.onCompleteHandler();
			}
			return;
		}

		try {
			const response = await fetch(this.url, {
				headers: {
					Authorization: `Bearer ${this.token}`
				}
			});

			// Handle auth failures with refresh attempt
			if (response.status === 401 || response.status === 403) {
				const shouldRetry = await this.handleAuthFailure(response.status);
				if (shouldRetry && this.isActive) {
					// Retry immediately with refreshed token
					this.pollInterval = setTimeout(() => this.poll(), 500);
				}
				return;
			}

			if (!response.ok) {
				throw new Error(`Polling request failed: ${response.status} ${response.statusText}`);
			}

			// Successful response — reset auth failure counter
			this.consecutiveAuthFailures = 0;

			const data: ProgressEvent = await response.json();

		// Check for duplicate events to prevent console spam
		const fingerprint = this.getEventFingerprint(data);
		if (fingerprint === this.lastEventFingerprint) {
			// Duplicate event, skip processing but continue polling
			if (this.isActive) {
				this.pollInterval = setTimeout(() => this.poll(), this.pollFrequency);
			}
			return;
		}
		this.lastEventFingerprint = fingerprint;

			const currentPercent = data.percent ?? 0;

			if (this.onMessageHandler) {
				this.onMessageHandler(data);
			}

			// Check if terminal state (job endpoint returns 'status', SSE returns 'type')
			const terminalStatus = (data as any).status || data.type;
			if (terminalStatus === 'completed' || terminalStatus === 'failed' || terminalStatus === 'error') {
				this.stopPolling();
				if (this.onCompleteHandler) {
					this.onCompleteHandler();
				}
				return;
			}

			// Stall detection — two modes:
			//   Durable mode (useHeartbeatStall=true): check the backend-provided
			//     `heartbeat_age` field on each response. The worker writes
			//     heartbeat_at every ~30s even during long stages (fact_extraction
			//     can stay at the same percent for 20+ minutes while the worker
			//     is actively running — the old percent-based check produced
			//     false positives there).
			//   Legacy mode: track percent stagnation across polls.
			if (this.useHeartbeatStall) {
				// The jobs status endpoint returns `heartbeat_age_seconds`; older
				// callers used `heartbeat_age`. Accept either — without this the
				// dead-worker check silently never fired (the UI spun forever).
				const heartbeatAge = (data as any).heartbeat_age_seconds ?? (data as any).heartbeat_age;
				if (typeof heartbeatAge === 'number' && heartbeatAge >= this.maxHeartbeatStaleSeconds) {
					console.warn(`Worker heartbeat stale (${heartbeatAge}s) at ${currentPercent}%. Treating as stalled.`);
					if (this.onMessageHandler) {
						this.onMessageHandler({
							type: 'stalled',
							message: `Worker appears unresponsive (last heartbeat ${heartbeatAge}s ago at ${currentPercent}%).`,
							phase: 'stalled',
							percent: currentPercent,
							error: 'WORKER_STALLED'
						});
					}
					this.stopPolling();
					if (this.onCompleteHandler) {
						this.onCompleteHandler();
					}
					return;
				}
			} else {
				// Legacy percent-stagnation stall (kept for non-durable callers)
				if (currentPercent > this.lastProgressPercent) {
					this.lastProgressPercent = currentPercent;
					this.stallCount = 0;
				} else {
					this.stallCount++;
				}

				if (this.stallCount === this.maxStallCount) {
					console.warn(`Processing paused at ${currentPercent}% - server may be working on a large document`);
					if (this.onMessageHandler) {
						this.onMessageHandler({
							type: 'progress',
							message: `Processing large document... (${currentPercent}% complete)`,
							phase: data.phase,
							percent: currentPercent,
						});
					}
				}

				if (this.stallCount >= this.maxStallCount && this.stallCount % 20 === 0) {
					console.warn(`Import appears stalled at ${currentPercent}% for ${Math.round(this.stallCount * this.pollFrequency / 1000)}s`);
				}

				const maxStallBeforeGracefulExit = 100; // 5 minutes
				if (this.stallCount >= maxStallBeforeGracefulExit) {
					console.warn(`Import stalled for 5+ minutes at ${currentPercent}%. Treating as partial completion.`);
					if (this.onMessageHandler) {
						this.onMessageHandler({
							type: 'stalled',
							message: `Import may have stopped at ${currentPercent}%. Some documents may have been imported.`,
							phase: 'stalled',
							percent: currentPercent,
							error: 'IMPORT_STALLED'
						});
					}
					this.stopPolling();
					if (this.onCompleteHandler) {
						this.onCompleteHandler();
					}
					return;
				}
			}

			// Schedule next poll
			if (this.isActive) {
				this.pollInterval = setTimeout(() => this.poll(), this.pollFrequency);
			}
		} catch (err) {
			console.error('Polling error:', err);

			// Don't fail immediately, retry on next poll
			if (this.isActive && this.pollAttempts < this.maxPollAttempts) {
				this.pollInterval = setTimeout(() => this.poll(), this.pollFrequency);
			} else {
				if (this.onErrorHandler) {
					this.onErrorHandler(
						new Error(`Polling failed: ${err instanceof Error ? err.message : String(err)}`)
					);
				}
				this.stopPolling();
				if (this.onCompleteHandler) {
					this.onCompleteHandler();
				}
			}
		}
	}

	/**
	 * Check if currently polling
	 */
	isPolling(): boolean {
		return this.isActive;
	}
}
