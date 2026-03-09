/**
 * Extracted pure functions from AnalysisStreamPanel for testability.
 *
 * - formatTime: elapsed time formatting
 * - parseSSELine: SSE line parsing and event classification
 * - processSSEEvent: state transitions from parsed events
 */

export type StreamStatus = 'idle' | 'thinking' | 'streaming' | 'complete' | 'error';

export interface SSEEvent {
	type: 'token' | 'thinking' | 'streaming_phase' | 'heartbeat' | 'done' | 'error' | 'unknown';
	token?: string;
	thinkingTime?: number;
	error?: string;
	docsInScope?: number;
	docsOmitted?: number;
	elapsed?: number;
}

/**
 * Format elapsed time in seconds to a human-readable string.
 */
export function formatTime(seconds: number): string {
	const mins = Math.floor(seconds / 60);
	const secs = seconds % 60;
	if (mins > 0) {
		return `${mins}m ${secs}s`;
	}
	return `${secs}s`;
}

/**
 * Parse a single SSE line (starting with "data: ") into a classified event.
 * Returns null for non-data lines or unparseable JSON.
 */
export function parseSSELine(line: string): SSEEvent | null {
	if (!line.startsWith('data: ')) return null;

	const jsonStr = line.slice(6).trim();
	if (!jsonStr) return null;

	let data: any;
	try {
		data = JSON.parse(jsonStr);
	} catch {
		return null;
	}

	if (data.error) {
		return { type: 'error', error: data.error };
	}

	if (data.done) {
		return {
			type: 'done',
			docsInScope: data.docs_in_scope,
			docsOmitted: data.docs_omitted,
		};
	}

	if (data.heartbeat !== undefined) {
		return { type: 'heartbeat' };
	}

	if (data.phase === 'thinking') {
		return { type: 'thinking', elapsed: data.elapsed };
	}

	if (data.phase === 'streaming') {
		return { type: 'streaming_phase', thinkingTime: data.thinking_time };
	}

	if (data.token) {
		return { type: 'token', token: data.token };
	}

	return { type: 'unknown' };
}

/**
 * Given a parsed SSE event and current status, return the next status.
 * Returns null if status should not change.
 */
export function nextStatus(event: SSEEvent, currentStatus: StreamStatus): StreamStatus | null {
	switch (event.type) {
		case 'thinking':
			return currentStatus !== 'thinking' ? 'thinking' : null;
		case 'streaming_phase':
			return 'streaming';
		case 'token':
			// If still in thinking when tokens arrive, transition to streaming
			return currentStatus === 'thinking' ? 'streaming' : null;
		case 'done':
			return 'complete';
		case 'error':
			return 'error';
		default:
			return null;
	}
}
