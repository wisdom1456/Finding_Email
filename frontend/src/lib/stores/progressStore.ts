/**
 * Progress Store for SSE-based real-time progress tracking
 * 
 * Manages progress state for analysis and import operations
 */

import { writable, derived } from 'svelte/store';
import { SSEClient, type ProgressEvent } from '$lib/utils/sseClient';
import { PollingClient } from '$lib/utils/pollingClient';
import { getApiUrl } from '$lib/config';
import { getSecureSession } from '$lib/supabase';

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

export interface FailedDocument {
	id: string;
	name: string;
	error: string;
	error_type?: string;
}

export interface ChunkStatus {
	type: 'chunk_complete' | 'chunk_complete_with_errors';
	chunk?: number;
	completed?: number;
	failed?: number;
	failed_docs?: FailedDocument[];
}

export interface DocLogEntry {
	i: number;
	name: string;
	size_bytes: number;
	outcome: string;
	reason?: string;
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
	doc_log: DocLogEntry[] | null;
}

export interface EnhancedProgressState<T = unknown> extends ProgressState<T> {
	stages: StageState[];
	documents: DocumentState[];
	stats: StatsState;
	streamingText: string;
	isStreaming: boolean;
	// Chunk failure recovery
	failedDocs: FailedDocument[];
	hasRecoveryPending: boolean;
	chunkStatus: ChunkStatus | null;
	// Trustworthy-Wait fields (carried from durable job status payload)
	uiState?: string;
	stepIndex?: number;
	stepTotal?: number;
	stepLabel?: string;
	itemsDone?: number | null;
	itemsTotal?: number | null;
	etaSeconds?: number | null;
	healthy?: boolean;
	cancelReason?: string | null;
	heartbeatAgeSeconds?: number | null;
}

/**
 * Canonical 6 analysis stages, matching the backend's durable-job step order.
 */
const DEFAULT_STAGES: StageState[] = [
	{ id: 'preparing', name: 'Preparing documents', status: 'pending', progress: 0 },
	{ id: 'analyzing', name: 'Analyzing documents', status: 'pending', progress: 0 },
	{ id: 'fact_extraction', name: 'Extracting key facts', status: 'pending', progress: 0 },
	{ id: 'issue_mapping', name: 'Mapping legal issues', status: 'pending', progress: 0 },
	{ id: 'deep_analysis', name: 'Running deep analysis', status: 'pending', progress: 0 },
	{ id: 'finalizing', name: 'Finalizing results', status: 'pending', progress: 0 },
];

/**
 * Trustworthy-Wait fields carried from the job-status payload (Tasks 3-5),
 * mapped from backend snake_case to frontend camelCase.
 */
export interface UiRunFields {
	uiState?: string;
	stepIndex?: number;
	stepTotal: number;
	stepLabel?: string;
	itemsDone?: number | null;
	itemsTotal?: number | null;
	etaSeconds?: number | null;
	healthy?: boolean;
	cancelReason?: string | null;
	heartbeatAgeSeconds?: number | null;
}

/**
 * Pure mapper: job-status payload (snake_case) -> UiRunFields (camelCase).
 * Tolerates legacy payloads that lack the new fields entirely.
 */
export function mapJobStatusToUi(p: Record<string, any>): UiRunFields {
	return {
		uiState: p.ui_state,
		stepIndex: p.step_index,
		stepTotal: p.step_total ?? 6,
		stepLabel: p.step_label,
		itemsDone: p.items_done ?? null,
		itemsTotal: p.items_total ?? null,
		etaSeconds: p.eta_seconds ?? null,
		healthy: p.healthy,
		cancelReason: p.cancel_reason ?? null,
		heartbeatAgeSeconds: p.heartbeat_age_seconds ?? null,
	};
}

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
	doc_log: null,
	stages: [...DEFAULT_STAGES],
	documents: [],
	stats: {
		elapsedSeconds: 0,
		tokens_used: 0,
		model: 'gpt-5.4'
	},
	streamingText: '',
	isStreaming: false,
	// Chunk failure recovery
	failedDocs: [],
	hasRecoveryPending: false,
	chunkStatus: null
};

function createProgressStore() {
	const { subscribe, set, update } = writable<EnhancedProgressState<unknown>>(initialState);
	let sseClient: SSEClient | null = null;
	let pollingClient: PollingClient | null = null;
	let currentStatusUrl: string = '';
	let currentToken: string = '';

	// Track last logged document states to prevent console spam
	let lastLoggedDocStates: Record<string, string> = {};

	/**
	 * Refresh the auth token from Supabase session.
	 * Returns the new token, or null if refresh failed.
	 */
	async function refreshToken(): Promise<string | null> {
		try {
			const { session } = await getSecureSession();
			if (session?.access_token) {
				currentToken = session.access_token;
				console.log('[progressStore] Token refreshed');
				return currentToken;
			}
			return null;
		} catch (e) {
			console.error('[progressStore] Token refresh failed:', e);
			return null;
		}
	}

	/**
	 * Token refresher callback for PollingClient.
	 */
	const tokenRefresher = async (): Promise<string | null> => {
		return refreshToken();
	};

	/**
	 * One-shot status check: fetch the status endpoint to see if the backend
	 * already completed. If it did, dispatch the terminal event to settle the UI.
	 * Returns true if the backend reported a terminal state (completed/failed/error).
	 * Returns 'auth_failed' if authentication failed and refresh also failed.
	 */
	async function reconcileFromStatus(
		statusUrl: string,
		token: string,
		messageHandler: (event: ProgressEvent | any) => void
	): Promise<boolean | 'auth_failed'> {
		try {
			let response = await fetch(statusUrl, {
				headers: { Authorization: `Bearer ${token}` },
			});

			// If 401, try refreshing the token once
			if (response.status === 401 || response.status === 403) {
				console.log('[progressStore] Status check got', response.status, '— refreshing token');
				const newToken = await refreshToken();
				if (!newToken) return 'auth_failed';
				response = await fetch(statusUrl, {
					headers: { Authorization: `Bearer ${newToken}` },
				});
				if (response.status === 401 || response.status === 403) return 'auth_failed';
			}

			if (!response.ok) return false;
			const data = await response.json();
			const terminalTypes = ['completed', 'failed', 'error'];
			if (data && terminalTypes.includes(data.type)) {
				console.log('[progressStore] Reconciled from status endpoint:', data.type);
				messageHandler(data);
				return true;
			}
			return false;
		} catch {
			return false;
		}
	}

	// Internal connect function that can be referenced by other methods
	const connectInternal = (url: string, onComplete?: (data?: unknown) => void, statusUrl?: string, token?: string): boolean => {
		console.log('[progressStore] connectInternal called:', { url, statusUrl });

		// Reset document state tracking on new connection
		lastLoggedDocStates = {};

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

		if (!currentToken) {
			console.error('[progressStore] No auth token provided');
			update(state => ({ ...state, status: 'error', error: 'No auth token' }));
			return false;
		}

		let finalData: unknown = null;

		// Try SSE first (uses fetch + Authorization header — token never in URL)
		sseClient = new SSEClient();

		const messageHandler = (event: ProgressEvent | any) => {
			// Only log stage changes (less frequent and more meaningful)
			if (event.stage) {
				console.log('[progressStore] Stage:', event.stage.id, event.stage.status);
			}
			// Only log document updates when status actually changes
			if (event.document) {
				const key = event.document.id || event.document.name;
				if (lastLoggedDocStates[key] !== event.document.status) {
					console.log('[progressStore] Document:', event.document.name, event.document.status);
					lastLoggedDocStates[key] = event.document.status;
				}
			}
			// Log chunk status events
			if (event.chunk_status) {
				console.log('[progressStore] Chunk status:', event.chunk_status.type, event.chunk_status);
			}

			if (event.data) finalData = event.data;
			
			// Determine status based on event type
			let newStatus: ProgressState['status'] = 'active';
			if (event.type === 'completed' || event.status === 'completed') newStatus = 'completed';
			else if (event.type === 'error' || event.type === 'failed' || event.status === 'error') newStatus = 'error';
			
			// Check for chunk_complete_with_errors event
			const chunkStatus: ChunkStatus | null = event.chunk_status || null;
			const hasRecoveryPending = chunkStatus?.type === 'chunk_complete_with_errors';
			const failedDocs: FailedDocument[] = hasRecoveryPending && chunkStatus?.failed_docs 
				? chunkStatus.failed_docs 
				: [];
			
			update(state => {
				// 1. Update Stages
				let newStages = [...state.stages];
				if (event.stage) {
					const stageIdx = newStages.findIndex(s => s.id === event.stage.id);
					if (stageIdx !== -1) {
						// Update the target stage
						newStages[stageIdx] = { ...newStages[stageIdx], ...event.stage };

						// Logic: If a stage is active or completed, all previous stages should be completed
						if (event.stage.status === 'active' || event.stage.status === 'completed') {
							for (let i = 0; i < stageIdx; i++) {
								if (newStages[i].status !== 'completed') {
									newStages[i] = { ...newStages[i], status: 'completed', progress: 100 };
								}
							}
						}
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
					doc_log: event.doc_log || state.doc_log,
					sub_step: event.sub_step || state.sub_step,
					status: newStatus,
					error: event.error || null,
					timestamp: event.timestamp || new Date().toISOString(),
					data: event.data || state.data,
					stages: newStages,
					documents: newDocs,
					stats: newStats,
					// Chunk failure recovery state
					chunkStatus: chunkStatus || state.chunkStatus,
					hasRecoveryPending: hasRecoveryPending || state.hasRecoveryPending,
					failedDocs: failedDocs.length > 0 ? failedDocs : state.failedDocs
				};
			});
		};

		const errorHandler = (error: Error) => {
			const errorMessage = error.message;
			console.log('[progressStore] SSE error:', errorMessage, 'hasStatusUrl:', !!currentStatusUrl);

			// SSE_AUTH_FAILED = auth failure on initial connect — try refresh once
			if (errorMessage.includes('SSE_AUTH_FAILED')) {
				refreshToken().then((newToken) => {
					if (!newToken) {
						update(state => ({
							...state,
							status: 'error',
							error: 'Session expired. Please refresh the page to sign in again.'
						}));
						return;
					}
					// Retry with fresh token — fall through to polling with the refreshed token
					if (currentStatusUrl) {
						update(state => ({
							...state,
							message: 'Reconnecting with refreshed session...',
							status: 'active'
						}));
						pollingClient = new PollingClient();
						pollingClient.startPolling(
							currentStatusUrl,
							currentToken,
							messageHandler,
							(pollError: Error) => {
								update(state => ({ ...state, status: 'error', error: pollError.message }));
							},
							() => { if (onComplete) onComplete(finalData); },
							tokenRefresher
						);
					} else {
						update(state => ({
							...state,
							status: 'error',
							error: 'Session expired and no status endpoint available.'
						}));
					}
				});
				return;
			}

			// If SSE stream ended unexpectedly (network disconnect) or timed out,
			// try a one-shot status check first. If the backend already completed,
			// reconcile the UI immediately instead of starting a polling loop.
			const isRecoverable = errorMessage.includes('SSE_TIMEOUT')
				|| errorMessage.includes('SSE_CONNECTION_FAILED')
				|| errorMessage.includes('SSE_STREAM_ENDED');

			if (isRecoverable && currentStatusUrl && currentToken) {
				// One-shot status check — if backend already finished, settle immediately
				reconcileFromStatus(currentStatusUrl, currentToken, messageHandler)
					.then((settled) => {
						if (settled === 'auth_failed') {
							// Auth failed even after refresh — terminal
							update(state => ({
								...state,
								status: 'error',
								error: 'Session expired. Please refresh the page to sign in again.'
							}));
							return;
						}
						if (settled) {
							// Backend already completed/failed — UI is now up to date
							if (onComplete) onComplete(finalData);
							return;
						}
						// Backend still in progress — fall back to polling
						update(state => ({
							...state,
							message: 'Reconnecting to progress stream...',
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
							() => {
								if (onComplete) onComplete(finalData);
							},
							tokenRefresher
						);
					})
					.catch(() => {
						// Status check failed — fall back to polling anyway
						pollingClient = new PollingClient();
						pollingClient.startPolling(
							currentStatusUrl,
							currentToken,
							messageHandler,
							(pollError: Error) => {
								update(state => ({ ...state, status: 'error', error: pollError.message }));
							},
							() => { if (onComplete) onComplete(finalData); },
							tokenRefresher
						);
					});
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

		const connected = sseClient.connect(url, currentToken, messageHandler, errorHandler, completeHandler);

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
					completeHandler,
					tokenRefresher
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
	};

	// Internal disconnect function
	const disconnectInternal = () => {
		if (sseClient) {
			sseClient.disconnect();
			sseClient = null;
		}
		if (pollingClient) {
			pollingClient.stopPolling();
			pollingClient = null;
		}
		currentStatusUrl = '';
		currentToken = '';
		set(initialState);
	};

	return {
		subscribe,

		/**
		 * Start listening to a specialized analysis progress stream.
		 * When pollingOnly is true, skips SSE and uses PollingClient directly.
		 * When jobId is provided, polls the durable job endpoint instead of the
		 * legacy analysis progress endpoint.
		 */
		startListening: async (analysisId: string, options?: { pollingOnly?: boolean; jobId?: string }) => {
			console.log('[progressStore] startListening called:', analysisId, options);
			const { session, user } = await getSecureSession();
			if (!session || !user) return;

			const apiUrl = getApiUrl();
			const isDurable = !!options?.jobId;

			// Durable mode: poll job endpoint. Legacy: poll analysis endpoint.
			const streamUrl = isDurable ? '' : `${apiUrl}/api/progress/analysis/${analysisId}`;
			const statusUrl = isDurable
				? `${apiUrl}/api/progress/jobs/${options!.jobId}/status`
				: `${apiUrl}/api/progress/analysis/${analysisId}/status`;
			console.log('[progressStore] URLs:', { streamUrl, statusUrl, isDurable });

			if (options?.pollingOnly || isDurable) {
				// Polling-only mode: skip SSE entirely.
				// In durable mode, always use polling (no SSE for durable jobs).
				lastLoggedDocStates = {};
				if (sseClient) { sseClient.disconnect(); sseClient = null; }
				if (pollingClient) { pollingClient.stopPolling(); pollingClient = null; }

				currentStatusUrl = statusUrl;
				currentToken = session.access_token;

				update(state => ({
					...initialState,
					status: 'connecting',
					message: isDurable ? 'Analysis queued — starting shortly...' : 'Connecting to progress stream...'
				}));

				let finalData: unknown = null;

				// Job stage → frontend stage ID mapping for durable mode
				const JOB_STAGE_MAP: Record<string, string> = {
					'queued': 'preparing',
					'preparing': 'preparing',
					'summarization': 'analyzing',
					'synthesis': 'analyzing',
					'fact_extraction': 'fact_extraction',
					'issue_mapping': 'issue_mapping',
					'deep_analysis': 'deep_analysis',
					'gap_analysis': 'deep_analysis',
					'finalizing': 'finalizing',
					'completed': 'finalizing',
				};

				const messageHandler = (event: ProgressEvent | any) => {
					if (event.stage) {
						console.log('[progressStore] Stage:', event.stage.id || event.stage, event.stage.status || '');
					}
					if (event.data) finalData = event.data;

					// Determine status — handle both legacy and durable response shapes
					let newStatus: ProgressState['status'] = 'active';
					const eventStatus = event.status || event.type;
					if (eventStatus === 'completed') newStatus = 'completed';
					else if (eventStatus === 'error' || eventStatus === 'failed') newStatus = 'error';
					else if (eventStatus === 'cancelled') newStatus = 'error'; // show cancelled as error state
					else if (eventStatus === 'pending') newStatus = 'connecting'; // queued state

					// Build message for durable queued/retry states
					let message = event.message || '';
					if (isDurable && eventStatus === 'pending') {
						if (event.queue_position && event.queue_position > 1) {
							message = `Your analysis is #${event.queue_position} in the queue. The worker is currently processing another case.`;
						} else if (event.worker_busy) {
							message = 'Your analysis is next. The worker is currently finishing another case.';
						} else if (event.attempts > 0) {
							message = `Resuming analysis from last checkpoint (attempt ${event.attempts}/${event.max_attempts})...`;
						} else {
							message = 'Analysis queued — starting shortly...';
						}
					}
					// When running a retry and stages jump forward, indicate checkpoint resume
					if (isDurable && eventStatus === 'running' && event.attempts > 1 && !message) {
						message = 'Resuming from checkpoint...';
					}

					update(state => {
						let newStages = [...state.stages];

						if (isDurable && event.stage && typeof event.stage === 'string') {
							// Durable mode: event.stage is a string (job stage name).
							// Map to frontend stage ID and mark it active.
							const frontendStageId = JOB_STAGE_MAP[event.stage] || event.stage;
							const stageIdx = newStages.findIndex(s => s.id === frontendStageId);
							if (stageIdx !== -1 && eventStatus === 'running') {
								newStages[stageIdx] = { ...newStages[stageIdx], status: 'active', progress: event.percent || 0 };
								// Mark all prior stages as completed
								for (let i = 0; i < stageIdx; i++) {
									if (newStages[i].status !== 'completed') {
										newStages[i] = { ...newStages[i], status: 'completed', progress: 100 };
									}
								}
							}
							if (eventStatus === 'completed') {
								// Mark all stages completed
								newStages = newStages.map(s => ({ ...s, status: 'completed' as const, progress: 100 }));
							}
						} else if (event.stage && typeof event.stage === 'object') {
							// Legacy mode: event.stage is an object with id, status, progress
							const stageIdx = newStages.findIndex(s => s.id === event.stage.id);
							if (stageIdx !== -1) {
								newStages[stageIdx] = { ...newStages[stageIdx], ...event.stage };
								if (event.stage.status === 'active' || event.stage.status === 'completed') {
									for (let i = 0; i < stageIdx; i++) {
										if (newStages[i].status !== 'completed') {
											newStages[i] = { ...newStages[i], status: 'completed', progress: 100 };
										}
									}
								}
							}
						}

						let newDocs = [...state.documents];
						if (event.document) {
							const docIdx = newDocs.findIndex(d => d.id === event.document.id);
							if (docIdx !== -1) { newDocs[docIdx] = { ...newDocs[docIdx], ...event.document }; }
							else { newDocs.push(event.document); }
						}
						return {
							...state,
							message: message || state.message,
							phase: event.phase || (isDurable ? event.stage : '') || state.phase,
							percent: event.percent !== undefined ? event.percent : state.percent,
							docs_processed: event.docs_processed || state.docs_processed,
							current_doc: event.current_doc || state.current_doc,
							doc_log: event.doc_log || state.doc_log,
							sub_step: event.sub_step || state.sub_step,
							status: newStatus,
							error: event.error || null,
							timestamp: event.timestamp || event.server_time || new Date().toISOString(),
							data: event.data || state.data,
							stages: newStages,
							documents: newDocs,
							stats: event.stats ? { ...state.stats, ...event.stats } : state.stats,
							chunkStatus: event.chunk_status || state.chunkStatus,
							hasRecoveryPending: event.chunk_status?.type === 'chunk_complete_with_errors' || state.hasRecoveryPending,
							failedDocs: (event.chunk_status?.failed_docs?.length > 0 ? event.chunk_status.failed_docs : state.failedDocs),
							// Trustworthy-Wait fields (additive; carried straight from the job payload)
							...mapJobStatusToUi(event)
						};
					});
				};

				pollingClient = new PollingClient();
				pollingClient.startPolling(
					statusUrl,
					session.access_token,
					messageHandler,
					(pollError: Error) => {
						update(state => ({ ...state, status: 'error', error: pollError.message }));
					},
					() => {},
					tokenRefresher,
					// Durable worker jobs can run 25-60 min; the old 20-min cap
					// caused the polling client to give up while the worker was
					// still healthy and the heartbeat fresh. Use heartbeat-based
					// stall instead of percent stagnation so long stages
					// (fact_extraction in particular) don't false-fire.
					isDurable
						? {
							maxPollAttempts: 1200, // 60 minutes @ 3s
							useHeartbeatStall: true,
							maxHeartbeatStaleSeconds: 180,
						}
						: undefined
				);
				return;
			}

			connectInternal(streamUrl, undefined, statusUrl, session.access_token);
		},

		/**
		 * Stop listening and reset
		 */
		stopListening: () => {
			disconnectInternal();
		},

		/**
		 * Connect to an SSE progress stream with automatic polling fallback
		 */
		connect: connectInternal,

		/**
		 * Disconnect from the SSE stream or polling
		 */
		disconnect: disconnectInternal,

		/**
		 * Reset the store to initial state
		 */
		reset: () => {
			disconnectInternal();
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

				// Chunk status handling
				const chunkStatus: ChunkStatus | null = event.chunk_status || null;
				const hasRecoveryPending = chunkStatus?.type === 'chunk_complete_with_errors';
				const failedDocs: FailedDocument[] = hasRecoveryPending && chunkStatus?.failed_docs 
					? chunkStatus.failed_docs 
					: [];

				return {
					...state,
					message: event.message || state.message,
					phase: event.phase || state.phase,
					percent: event.percent !== undefined ? event.percent : state.percent,
					docs_processed: event.docs_processed || state.docs_processed,
					current_doc: event.current_doc || state.current_doc,
					doc_log: event.doc_log || state.doc_log,
					sub_step: event.sub_step || state.sub_step,
					status: event.type === 'completed' ? 'completed' : 
					        event.type === 'error' || event.type === 'failed' ? 'error' : 'active',
					error: event.error || state.error,
					timestamp: event.timestamp || new Date().toISOString(),
					data: event.data || state.data,
					stages: newStages,
					documents: newDocs,
					stats: event.stats ? { ...state.stats, ...event.stats } : state.stats,
					// Chunk failure recovery state
					chunkStatus: chunkStatus || state.chunkStatus,
					hasRecoveryPending: hasRecoveryPending || state.hasRecoveryPending,
					failedDocs: failedDocs.length > 0 ? failedDocs : state.failedDocs
				};
			});
		},

		/**
		 * Clear recovery state after user handles failed documents
		 */
		clearRecoveryState: () => {
			update(state => ({
				...state,
				hasRecoveryPending: false,
				failedDocs: [],
				chunkStatus: null
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

export const needsRecovery = derived(
	progressStore,
	$progress => $progress.hasRecoveryPending && $progress.failedDocs.length > 0
);

export const failedDocuments = derived(
	progressStore,
	$progress => $progress.failedDocs
);
