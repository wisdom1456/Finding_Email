/**
 * Progress Store for SSE-based real-time progress tracking
 * 
 * Manages progress state for analysis and import operations
 */

import { writable, derived } from 'svelte/store';
import { SSEClient, type ProgressEvent } from '$lib/utils/sseClient';
import { PollingClient } from '$lib/utils/pollingClient';

export interface ProgressState<T = unknown> {
	message: string;
	phase: string;
	percent: number;
	docs_processed: string[];
	current_doc: {
		name: string;
		index: number;
		total: number;
	} | null;
	sub_step: string | null;
	status: 'idle' | 'connecting' | 'active' | 'completed' | 'error';
	error: string | null;
	timestamp: string | null;
	data: T | null;
}

const initialState: ProgressState<unknown> = {
	message: '',
	phase: '',
	percent: 0,
	docs_processed: [],
	current_doc: null,
	sub_step: null,
	status: 'idle',
	error: null,
	timestamp: null,
	data: null
};

function createProgressStore() {
	const { subscribe, set, update } = writable<ProgressState<unknown>>(initialState);
	let sseClient: SSEClient | null = null;
	let pollingClient: PollingClient | null = null;
	let currentStatusUrl: string = '';
	let currentToken: string = '';

	return {
		subscribe,

		/**
		 * Connect to an SSE progress stream with automatic polling fallback
		 */
		connect: (url: string, onComplete?: (data?: unknown) => void, statusUrl?: string, token?: string): boolean => {
			// Disconnect existing connections
			if (sseClient) {
				sseClient.disconnect();
			}
			if (pollingClient) {
				pollingClient.stopPolling();
			}

			update(state => ({
				...initialState,
				status: 'connecting',
				message: 'Connecting to progress stream...'
			}));

			// Store status URL and token for polling fallback
			if (statusUrl) currentStatusUrl = statusUrl;
			if (token) currentToken = token;

			let finalData: unknown = null;

			// Try SSE first
			sseClient = new SSEClient();

			const messageHandler = (event: ProgressEvent) => {
				if (event.data) finalData = event.data;
				
				update(state => ({
					...state,
					message: event.message,
					phase: event.phase,
					percent: event.percent,
					docs_processed: event.docs_processed || state.docs_processed,
					current_doc: event.current_doc || state.current_doc,
					sub_step: event.sub_step || state.sub_step,
					status: event.type === 'completed' ? 'completed' : 
					        event.type === 'error' || event.type === 'failed' ? 'error' : 'active',
					error: event.error || null,
					timestamp: event.timestamp || new Date().toISOString(),
					data: event.data || state.data
				}));
			};

			const errorHandler = (error: Error) => {
				const errorMessage = error.message;
				
				// If SSE times out or fails, try polling fallback
				if ((errorMessage.includes('SSE_TIMEOUT') || errorMessage.includes('SSE_CONNECTION_FAILED')) 
				    && currentStatusUrl && currentToken) {
					update(state => ({
						...state,
						message: 'Stream timeout, switching to polling mode...',
						status: 'active'
					}));

					// Start polling
					pollingClient = new PollingClient();
					pollingClient.startPolling(
						currentStatusUrl,
						currentToken,
						messageHandler,
						(pollError: Error) => {
							update(state => ({
								...state,
								status: 'error',
								error: pollError.message
							}));
						},
						() => {
							if (onComplete) {
								onComplete(finalData);
							}
						}
					);
				} else {
					// Non-recoverable error
					update(state => ({
						...state,
						status: 'error',
						error: errorMessage
					}));
				}
			};

			const completeHandler = () => {
				if (onComplete) {
					onComplete(finalData);
				}
			};

			const connected = sseClient.connect(url, messageHandler, errorHandler, completeHandler);

			if (!connected) {
				// SSE not supported, try polling immediately if available
				if (currentStatusUrl && currentToken) {
					update(state => ({
						...state,
						message: 'Using polling mode...',
						status: 'active'
					}));

					pollingClient = new PollingClient();
					pollingClient.startPolling(
						currentStatusUrl,
						currentToken,
						messageHandler,
						(pollError: Error) => {
							update(state => ({
								...state,
								status: 'error',
								error: pollError.message
							}));
						},
						completeHandler
					);
					return true;
				}

				update(state => ({
					...state,
					status: 'error',
					error: 'SSE_NOT_SUPPORTED'
				}));
				return false;
			}

			return true;
		},

		/**
		 * Disconnect from the SSE stream or polling
		 */
		disconnect: () => {
			if (sseClient) {
				sseClient.disconnect();
				sseClient = null;
			}
			if (pollingClient) {
				pollingClient.stopPolling();
				pollingClient = null;
			}
			set(initialState);
		},

		/**
		 * Reset the store to initial state
		 */
		reset: () => {
			if (sseClient) {
				sseClient.disconnect();
				sseClient = null;
			}
			if (pollingClient) {
				pollingClient.stopPolling();
				pollingClient = null;
			}
			set(initialState);
		},

		/**
		 * Manually update progress (for polling fallback)
		 */
		updateProgress: (event: Partial<ProgressEvent>) => {
			update(state => ({
				...state,
				message: event.message || state.message,
				phase: event.phase || state.phase,
				percent: event.percent !== undefined ? event.percent : state.percent,
				docs_processed: event.docs_processed || state.docs_processed,
				current_doc: event.current_doc || state.current_doc,
				sub_step: event.sub_step || state.sub_step,
				status: event.type === 'completed' ? 'completed' : 
				        event.type === 'error' || event.type === 'failed' ? 'error' : 'active',
				error: event.error || state.error,
				timestamp: event.timestamp || new Date().toISOString(),
				data: event.data || state.data
			}));
		},

		/**
		 * Check if SSE is supported
		 */
		isSupported: (): boolean => {
			return SSEClient.isSupported();
		}
	};
}

export const progressStore = createProgressStore();

// Derived stores for convenience
export const isProcessing = derived(
	progressStore,
	$progress => $progress.status === 'active' || $progress.status === 'connecting'
);

export const isComplete = derived(
	progressStore,
	$progress => $progress.status === 'completed'
);

export const hasError = derived(
	progressStore,
	$progress => $progress.status === 'error'
);

