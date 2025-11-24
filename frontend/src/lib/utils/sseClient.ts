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
			console.warn('SSE not supported, falling back to polling');
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

			this.eventSource.onmessage = (event) => {
				try {
					console.log('📡 Raw SSE message received:', event.data);
					
					// Skip ping/keep-alive messages
					if (event.data.trim() === '' || event.data.trim().startsWith(':')) {
						console.log('Skipping ping/keep-alive message');
						return;
					}

					const data: ProgressEvent = JSON.parse(event.data);
					console.log('✅ Parsed SSE data:', data);
					
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

			this.eventSource.onerror = (event) => {
				console.error('SSE connection error:', event);

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
					
					console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
					
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
				console.log('SSE connection established');
				this.reconnectAttempts = 0;
			};

			return true;
		} catch (err) {
			console.error('Failed to create EventSource:', err);
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
}

