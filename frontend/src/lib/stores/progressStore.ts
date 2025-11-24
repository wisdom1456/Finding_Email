/**
 * Progress Store for SSE-based real-time progress tracking
 * 
 * Manages progress state for analysis and import operations
 */

import { writable, derived } from 'svelte/store';
import { SSEClient, type ProgressEvent } from '$lib/utils/sseClient';

export interface ProgressState {
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
	data: any | null;
}

const initialState: ProgressState = {
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
	const { subscribe, set, update } = writable<ProgressState>(initialState);
	let sseClient: SSEClient | null = null;

	return {
		subscribe,

		/**
		 * Connect to an SSE progress stream
		 */
		connect: (url: string, onComplete?: (data?: any) => void): boolean => {
			// Disconnect existing connection if any
			if (sseClient) {
				sseClient.disconnect();
			}

			update(state => ({
				...initialState,
				status: 'connecting',
				message: 'Connecting to progress stream...'
			}));

			let finalData: any = null;

			sseClient = new SSEClient();

			const connected = sseClient.connect(
				url,
				// onMessage
				(event: ProgressEvent) => {
					console.log('📊 Progress event received:', event);
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
				},
				// onError
				(error: Error) => {
					console.error('SSE Progress error:', error);
					update(state => ({
						...state,
						status: 'error',
						error: error.message
					}));
				},
				// onComplete
				() => {
					if (onComplete) {
						onComplete(finalData);
					}
				}
			);

			if (!connected) {
				// SSE not supported, update status
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
		 * Disconnect from the SSE stream
		 */
		disconnect: () => {
			if (sseClient) {
				sseClient.disconnect();
				sseClient = null;
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
		isSuppported: (): boolean => {
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

