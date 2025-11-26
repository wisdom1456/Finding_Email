/**
 * Polling Client for Progress Updates
 * 
 * Fallback mechanism when SSE is not available or times out
 */

import type { ProgressEvent } from './sseClient';

export type PollingMessageHandler = (event: ProgressEvent) => void;
export type PollingErrorHandler = (error: Error) => void;
export type PollingCompleteHandler = () => void;

export class PollingClient {
	private pollInterval: NodeJS.Timeout | null = null;
	private pollFrequency = 3000; // Poll every 3 seconds
	private maxPollAttempts = 120; // 6 minutes max (120 * 3 seconds)
	private pollAttempts = 0;
	private isActive = false;
	private url: string = '';
	private token: string = '';
	private onMessageHandler: PollingMessageHandler | null = null;
	private onErrorHandler: PollingErrorHandler | null = null;
	private onCompleteHandler: PollingCompleteHandler | null = null;

	/**
	 * Start polling for progress updates
	 */
	startPolling(
		statusUrl: string,
		token: string,
		onMessage: PollingMessageHandler,
		onError: PollingErrorHandler,
		onComplete: PollingCompleteHandler
	): void {
		this.url = statusUrl;
		this.token = token;
		this.onMessageHandler = onMessage;
		this.onErrorHandler = onError;
		this.onCompleteHandler = onComplete;
		this.isActive = true;
		this.pollAttempts = 0;

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

			if (!response.ok) {
				throw new Error(`Polling request failed: ${response.status} ${response.statusText}`);
			}

			const data: ProgressEvent = await response.json();

			if (this.onMessageHandler) {
				this.onMessageHandler(data);
			}

			// Check if terminal state
			if (data.type === 'completed' || data.type === 'failed' || data.type === 'error') {
				this.stopPolling();
				if (this.onCompleteHandler) {
					this.onCompleteHandler();
				}
				return;
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

