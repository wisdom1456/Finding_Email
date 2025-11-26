/**
 * SSE (Server-Sent Events) Client Utility
 * 
 * Handles EventSource connections with automatic fallback to polling
 * when SSE is not supported or fails.
 */

export interface ProgressEvent {
	type: 'progress' | 'completed' | 'error' | 'failed';
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
	data?: any; // Arbitrary payload for results
}

export type SSEMessageHandler = (event: ProgressEvent) => void;
export type SSEErrorHandler = (error: Error) => void;
export type SSECompleteHandler = () => void;

export class SSEClient {
	private eventSource: EventSource | null = null;
	private reconnectAttempts = 0;
	private maxReconnectAttempts = 3;
	private reconnectDelay = 1000; // Start with 1 second
	private isManuallyDisconnected = false;
	private url: string = '';
	private onMessageHandler: SSEMessageHandler | null = null;
	private onErrorHandler: SSEErrorHandler | null = null;
	private onCompleteHandler: SSECompleteHandler | null = null;
	private inactivityTimer: NodeJS.Timeout | null = null;
	private inactivityTimeout = 300000; // 5 minutes of no messages = timeout
	private lastMessageTime: number = 0;

	/**
	 * Check if EventSource is supported by the browser
	 */
	static isSupported(): boolean {
		return typeof EventSource !== 'undefined';
	}

	/**
	 * Connect to an SSE stream
	 */
	connect(
		url: string,
		onMessage: SSEMessageHandler,
		onError: SSEErrorHandler,
		onComplete: SSECompleteHandler
	): boolean {
		if (!SSEClient.isSupported()) {
			onError(new Error('SSE_NOT_SUPPORTED'));
			return false;
		}

		this.url = url;
		this.onMessageHandler = onMessage;
		this.onErrorHandler = onError;
		this.onCompleteHandler = onComplete;
		this.isManuallyDisconnected = false;

		try {
			this.eventSource = new EventSource(url);
			this.lastMessageTime = Date.now();
			this.startInactivityTimer();

			this.eventSource.onmessage = (event) => {
				try {
					// Skip ping/keep-alive messages
					if (event.data.trim() === '' || event.data.trim().startsWith(':')) {
						// Reset inactivity timer even for keep-alive
						this.resetInactivityTimer();
						return;
					}

					const data: ProgressEvent = JSON.parse(event.data);
					
					// Update last message time and reset inactivity timer
					this.lastMessageTime = Date.now();
					this.resetInactivityTimer();
					
					if (this.onMessageHandler) {
						this.onMessageHandler(data);
					}

					// Check if this is a terminal event
					if (data.type === 'completed' || data.type === 'failed' || data.type === 'error') {
						this.disconnect();
						if (this.onCompleteHandler) {
							this.onCompleteHandler();
						}
					}

					// Reset reconnect attempts on successful message
					this.reconnectAttempts = 0;
				} catch (err) {
					console.error('Failed to parse SSE message:', err);
					if (this.onErrorHandler) {
						this.onErrorHandler(
							new Error(`Failed to parse message: ${err instanceof Error ? err.message : String(err)}`)
						);
					}
				}
			};

			this.eventSource.onerror = () => {
				// Don't reconnect if manually disconnected
				if (this.isManuallyDisconnected) {
					return;
				}

				// Close the current connection
				if (this.eventSource) {
					this.eventSource.close();
					this.eventSource = null;
				}

				// Attempt reconnection with exponential backoff
				if (this.reconnectAttempts < this.maxReconnectAttempts) {
					this.reconnectAttempts++;
					const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
					
					setTimeout(() => {
						if (!this.isManuallyDisconnected) {
							this.connect(this.url, this.onMessageHandler!, this.onErrorHandler!, this.onCompleteHandler!);
						}
					}, delay);
				} else {
					// Max reconnect attempts reached, trigger error and complete
					if (this.onErrorHandler) {
						this.onErrorHandler(new Error('SSE_CONNECTION_FAILED'));
					}
					if (this.onCompleteHandler) {
						this.onCompleteHandler();
					}
				}
			};

			this.eventSource.onopen = () => {
				this.reconnectAttempts = 0;
			};

			return true;
		} catch (err) {
			if (this.onErrorHandler) {
				this.onErrorHandler(
					new Error(`Failed to connect: ${err instanceof Error ? err.message : String(err)}`)
				);
			}
			return false;
		}
	}

	/**
	 * Disconnect from the SSE stream
	 */
	disconnect(): void {
		this.isManuallyDisconnected = true;
		this.clearInactivityTimer();
		if (this.eventSource) {
			this.eventSource.close();
			this.eventSource = null;
		}
		this.reconnectAttempts = 0;
	}

	/**
	 * Check if currently connected
	 */
	isConnected(): boolean {
		return this.eventSource !== null && this.eventSource.readyState === EventSource.OPEN;
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
				if (this.onErrorHandler) {
					this.onErrorHandler(new Error('SSE_TIMEOUT: No updates received for 5 minutes'));
				}
				this.disconnect();
				if (this.onCompleteHandler) {
					this.onCompleteHandler();
				}
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

