/**
 * SSE (Server-Sent Events) Client Utility
 *
 * Uses fetch() + ReadableStream instead of native EventSource so that
 * auth tokens can be sent via Authorization header (not in the URL).
 * Falls back to polling when SSE is not supported or fails.
 */

export interface ProgressEvent<T = unknown> {
	type: 'progress' | 'completed' | 'error' | 'failed' | 'stalled';
	message: string;
	phase: string;
	percent: number;
	docs_processed?: string[];
	current_doc?: {
		name: string;
		index: number;
		total: number;
	};
	sub_step?: string;
	error?: string;
	timestamp?: string;
	data?: T; // Generic payload for results
	document?: {
		status?: string;
		[key: string]: unknown;
	};
}

export type SSEMessageHandler<T = unknown> = (event: ProgressEvent<T>) => void;
export type SSEErrorHandler = (error: Error) => void;
export type SSECompleteHandler = () => void;

export class SSEClient<T = unknown> {
	private abortController: AbortController | null = null;
	private reconnectAttempts = 0;
	private maxReconnectAttempts = 3;
	private reconnectDelay = 1000; // Start with 1 second
	private isManuallyDisconnected = false;
	private url: string = '';
	private token: string = '';
	private onMessageHandler: SSEMessageHandler<T> | null = null;
	private onErrorHandler: SSEErrorHandler | null = null;
	private onCompleteHandler: SSECompleteHandler | null = null;
	private inactivityTimer: NodeJS.Timeout | null = null;
	private inactivityTimeout = 300000; // 5 minutes of no messages = timeout
	private lastMessageTime: number = 0;

	/**
	 * Check if fetch streaming is supported by the browser.
	 * (ReadableStream is available in all modern browsers.)
	 */
	static isSupported(): boolean {
		return typeof ReadableStream !== 'undefined' && typeof fetch !== 'undefined';
	}

	/**
	 * Connect to an SSE stream using fetch + ReadableStream.
	 * Auth token is sent via Authorization header — never in the URL.
	 *
	 * @param url - The SSE endpoint URL (without token query param)
	 * @param token - Bearer token for Authorization header
	 * @param onMessage - Called for each parsed SSE event
	 * @param onError - Called on connection or parse errors
	 * @param onComplete - Called when stream ends (terminal event or EOF)
	 */
	connect(
		url: string,
		token: string,
		onMessage: SSEMessageHandler<T>,
		onError: SSEErrorHandler,
		onComplete: SSECompleteHandler
	): boolean {
		if (!SSEClient.isSupported()) {
			onError(new Error('SSE_NOT_SUPPORTED'));
			return false;
		}

		this.url = url;
		this.token = token;
		this.onMessageHandler = onMessage;
		this.onErrorHandler = onError;
		this.onCompleteHandler = onComplete;
		this.isManuallyDisconnected = false;

		this._startStream();
		return true;
	}

	/**
	 * Internal: start or restart the fetch-based SSE stream.
	 */
	private async _startStream(): Promise<void> {
		this.abortController = new AbortController();
		this.lastMessageTime = Date.now();
		this.startInactivityTimer();

		try {
			const response = await fetch(this.url, {
				method: 'GET',
				headers: {
					Authorization: `Bearer ${this.token}`,
					Accept: 'text/event-stream',
				},
				signal: this.abortController.signal,
			});

			if (!response.ok) {
				throw new Error(`SSE connection failed: HTTP ${response.status}`);
			}

			if (!response.body) {
				throw new Error('SSE_NO_BODY: No response body');
			}

			// Reset reconnect counter on successful connection
			this.reconnectAttempts = 0;

			const reader = response.body.getReader();
			const decoder = new TextDecoder();
			let buffer = '';

			while (true) {
				if (this.isManuallyDisconnected) break;

				const { done, value } = await reader.read();
				if (done) break;

				buffer += decoder.decode(value, { stream: true });
				const lines = buffer.split('\n');
				buffer = lines.pop() || '';

				for (const line of lines) {
					this.processLine(line);
				}
			}

			// Stream ended without terminal event (e.g., network disconnect).
			// Notify via error so progressStore can attempt recovery (check backend status).
			if (!this.isManuallyDisconnected) {
				this.onErrorHandler?.(new Error('SSE_STREAM_ENDED'));
				this.onCompleteHandler?.();
			}
		} catch (err) {
			if (this.isManuallyDisconnected) return;

			// AbortError is expected during disconnect
			if (err instanceof Error && err.name === 'AbortError') return;

			this.clearInactivityTimer();

			// Attempt reconnection with exponential backoff
			if (this.reconnectAttempts < this.maxReconnectAttempts) {
				this.reconnectAttempts++;
				const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);

				setTimeout(() => {
					if (!this.isManuallyDisconnected) {
						this._startStream();
					}
				}, delay);
			} else {
				// Max reconnect attempts reached
				this.onErrorHandler?.(new Error('SSE_CONNECTION_FAILED'));
				this.onCompleteHandler?.();
			}
		}
	}

	/**
	 * Parse a single SSE line and dispatch to handlers.
	 */
	private processLine(line: string): void {
		// Skip empty lines and SSE comments (keep-alive pings)
		const trimmed = line.trim();
		if (!trimmed || trimmed.startsWith(':')) {
			this.resetInactivityTimer();
			return;
		}

		if (!trimmed.startsWith('data: ')) return;

		try {
			const data: ProgressEvent<T> = JSON.parse(trimmed.slice(6));

			// Update last message time and reset inactivity timer
			this.lastMessageTime = Date.now();
			this.resetInactivityTimer();

			this.onMessageHandler?.(data);

			// Check if this is a terminal event
			if (data.type === 'completed' || data.type === 'failed' || data.type === 'error') {
				this.disconnect();
				this.onCompleteHandler?.();
			}

			// Reset reconnect attempts on successful message
			this.reconnectAttempts = 0;
		} catch (err) {
			console.error('Failed to parse SSE message:', err);
			this.onErrorHandler?.(
				new Error(`Failed to parse message: ${err instanceof Error ? err.message : String(err)}`)
			);
		}
	}

	/**
	 * Disconnect from the SSE stream
	 */
	disconnect(): void {
		this.isManuallyDisconnected = true;
		this.clearInactivityTimer();
		if (this.abortController) {
			this.abortController.abort();
			this.abortController = null;
		}
		this.reconnectAttempts = 0;
	}

	/**
	 * Check if currently connected
	 */
	isConnected(): boolean {
		return this.abortController !== null && !this.isManuallyDisconnected;
	}

	/**
	 * Start inactivity timer - triggers timeout if no messages received
	 */
	private startInactivityTimer(): void {
		this.clearInactivityTimer();
		this.inactivityTimer = setTimeout(() => {
			const timeSinceLastMessage = Date.now() - this.lastMessageTime;
			if (timeSinceLastMessage >= this.inactivityTimeout) {
				console.warn('SSE stream inactive for too long, timing out');
				this.onErrorHandler?.(new Error('SSE_TIMEOUT: No updates received for 5 minutes'));
				this.disconnect();
				this.onCompleteHandler?.();
			}
		}, this.inactivityTimeout);
	}

	/**
	 * Reset inactivity timer
	 */
	private resetInactivityTimer(): void {
		this.startInactivityTimer();
	}

	/**
	 * Clear inactivity timer
	 */
	private clearInactivityTimer(): void {
		if (this.inactivityTimer) {
			clearTimeout(this.inactivityTimer);
			this.inactivityTimer = null;
		}
	}
}
