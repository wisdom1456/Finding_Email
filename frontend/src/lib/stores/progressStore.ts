/**
 * Progress Store for SSE-based real-time progress tracking
 * 
 * Manages progress state for analysis and import operations
 */

import { writable, derived } from 'svelte/store';
import { SSEClient, type ProgressEvent } from '$lib/utils/sseClient';
import { PollingClient } from '$lib/utils/pollingClient';
import { getApiUrl } from '$lib/config';
import { supabase } from '$lib/supabase';

export interface StageState {
	id: string;
	name: string;
	status: 'pending' | 'active' | 'completed' | 'error';
	progress: number;
	startedAt?: string;
	completedAt?: string;
	extracted?: { type: string; count: number; preview?: string[] };
}

export interface DocumentState {
	id: string;
	name: string;
	status: 'pending' | 'processing' | 'completed' | 'error';
}

export interface StatsState {
	elapsedSeconds: number;
	estimatedRemaining?: number;
	tokens_used: number;
	model: string;
}

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

export interface EnhancedProgressState<T = unknown> extends ProgressState<T> {
	stages: StageState[];
	documents: DocumentState[];
	stats: StatsState;
	streamingText: string;
	isStreaming: boolean;
}

const DEFAULT_STAGES: StageState[] = [
	{ id: 'doc_summary', name: 'Document Analysis', status: 'pending', progress: 0 },
	{ id: 'fact_matrix', name: 'Extracting Facts', status: 'pending', progress: 0 },
	{ id: 'issue_mapping', name: 'Legal Issues', status: 'pending', progress: 0 },
	{ id: 'deep_analysis', name: 'Deep Analysis', status: 'pending', progress: 0 },
	{ id: 'letter_structure', name: 'Letter Structure', status: 'pending', progress: 0 },
];

const initialState: EnhancedProgressState<unknown> = {
	message: '',
	phase: '',
	percent: 0,
	docs_processed: [],
	current_doc: null,
	sub_step: null,
	status: 'idle',
	error: null,
	timestamp: null,
	data: null,
	stages: [...DEFAULT_STAGES],
	documents: [],
	stats: {
		elapsedSeconds: 0,
		tokens_used: 0,
		model: 'gpt-4o'
	},
	streamingText: '',
	isStreaming: false
};

function createProgressStore() {
	const { subscribe, set, update } = writable<EnhancedProgressState<unknown>>(initialState);
	let sseClient: SSEClient | null = null;
	let pollingClient: PollingClient | null = null;
	let currentStatusUrl: string = '';
	let currentToken: string = '';

	return {
		subscribe,

		/**
		 * Start listening to a specialized analysis progress stream
		 */
		startListening: async (analysisId: string) => {
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) return;

			const apiUrl = getApiUrl();
			const streamUrl = `${apiUrl}/api/analysis/progress/${analysisId}`;
			const statusUrl = `${apiUrl}/api/analysis/status/${analysisId}`;

			// Use existing connect method
			createProgressStore().connect(streamUrl, undefined, statusUrl, session.access_token);
		},

		/**
		 * Stop listening and reset
		 */
		stopListening: () => {
			if (sseClient) sseClient.disconnect();
			if (pollingClient) pollingClient.stopPolling();
			set(initialState);
		},

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

			const messageHandler = (event: ProgressEvent | any) => {
				if (event.data) finalData = event.data;
				
				// Determine status based on event type
				let newStatus: ProgressState['status'] = 'active';
				if (event.type === 'completed') newStatus = 'completed';
				else if (event.type === 'error' || event.type === 'failed') newStatus = 'error';
				
				update(state => {
					// 1. Update Stages
					let newStages = [...state.stages];
					if (event.stage) {
						const stageIdx = newStages.findIndex(s => s.id === event.stage.id);
						if (stageIdx !== -1) {
							newStages[stageIdx] = { ...newStages[stageIdx], ...event.stage };
						}
					}

					// 2. Update Documents
					let newDocs = [...state.documents];
					if (event.document) {
						const docIdx = newDocs.findIndex(d => d.id === event.document.id);
						if (docIdx !== -1) {
							newDocs[docIdx] = { ...newDocs[docIdx], ...event.document };
						} else {
							newDocs.push(event.document);
						}
					}

					// 3. Update Stats
					const newStats = event.stats ? { ...state.stats, ...event.stats } : state.stats;

					return {
						...state,
						message: event.message || state.message,
						phase: event.phase || state.phase,
						percent: event.percent !== undefined ? event.percent : state.percent,
						docs_processed: event.docs_processed || state.docs_processed,
						current_doc: event.current_doc || state.current_doc,
						sub_step: event.sub_step || state.sub_step,
						status: newStatus,
						error: event.error || null,
						timestamp: event.timestamp || new Date().toISOString(),
						data: event.data || state.data,
						stages: newStages,
						documents: newDocs,
						stats: newStats
					};
				});
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
		updateProgress: (event: Partial<ProgressEvent> | any) => {
			update(state => {
				// Stages update
				let newStages = [...state.stages];
				if (event.stage) {
					const stageIdx = newStages.findIndex(s => s.id === event.stage.id);
					if (stageIdx !== -1) {
						newStages[stageIdx] = { ...newStages[stageIdx], ...event.stage };
					}
				}

				// Documents update
				let newDocs = [...state.documents];
				if (event.document) {
					const docIdx = newDocs.findIndex(d => d.id === event.document.id);
					if (docIdx !== -1) {
						newDocs[docIdx] = { ...newDocs[docIdx], ...event.document };
					} else {
						newDocs.push(event.document);
					}
				}

				return {
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
					data: event.data || state.data,
					stages: newStages,
					documents: newDocs,
					stats: event.stats ? { ...state.stats, ...event.stats } : state.stats
				};
			});
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

