/**
 * Pure reducer for the recommendation-letter SSE stream.
 *
 * Mirrors the backend event shapes emitted by
 * `letter_routes.py` (`recommendation-letter/stream`, schema_version=2):
 *   - `phase`  : { phase, message?, percent? }
 *   - `token`  : { token }
 *   - `final`  : { content: { format, html?, markdown? }, quality_report?, generation_metrics? }
 *   - `done`   : { done: true }
 *   - `error`  : { error, code?, recoverable? }
 *
 * The backend also emits `error` events with `recoverable: true` mid-stream
 * (e.g. a draft that hit its time budget but has enough content to finish
 * linting/finalizing) — the generator keeps running afterward and still
 * sends a proper `final` event. Those are NOT terminal: mirroring
 * `DemandLetterSection.svelte`'s `!Boolean(data.recoverable)` check (around
 * line 301), the reducer ignores them and waits for the real outcome.
 *
 * A non-recoverable `error` (or an omitted `recoverable` flag) IS terminal.
 * If tokens have already accumulated in the buffer, the reducer salvages
 * them as the letter content (`recovered: true`) instead of discarding the
 * draft — mirroring the fallback-buffer flush in `DemandLetterSection.svelte`
 * (around lines 323-332), which shows whatever was streamed so far rather
 * than losing it when the stream ends without ever reaching a terminal
 * state.
 */

export interface RecommendationLetterContent {
	format?: string;
	html?: string;
	markdown?: string;
}

export interface RecommendationStreamState {
	/** Human-readable label for the current phase (from the `message` field). */
	phaseLabel: string;
	/** Progress percent for the current phase, if the backend supplied one. */
	percent: number | null;
	/** Accumulated markdown tokens streamed so far. */
	markdownBuffer: string;
	/** Final (or salvaged) letter content, once available. */
	content: RecommendationLetterContent | null;
	/** Whether the stream has reached a terminal state. */
	done: boolean;
	/** Non-recoverable error message, if the stream failed with no usable draft. */
	error: string | null;
	/** True when `content` was salvaged from the token buffer after an error. */
	recovered: boolean;
}

/** Minimal shape of a parsed SSE event from the recommendation-letter stream. */
export interface RecommendationStreamEvent {
	event?: string;
	type?: string;
	phase?: string;
	message?: string;
	percent?: number;
	token?: string;
	content?: RecommendationLetterContent;
	error?: string;
	code?: string;
	recoverable?: boolean;
	done?: boolean;
	[key: string]: unknown;
}

export function initialRecommendationStreamState(): RecommendationStreamState {
	return {
		phaseLabel: '',
		percent: null,
		markdownBuffer: '',
		content: null,
		done: false,
		error: null,
		recovered: false
	};
}

function eventType(event: RecommendationStreamEvent): string {
	if (typeof event.event === 'string' && event.event) return event.event;
	if (typeof event.type === 'string' && event.type) return event.type;
	if (typeof event.token === 'string') return 'token';
	if (event.done) return 'done';
	if (typeof event.error === 'string') return 'error';
	return '';
}

export type TerminalOutcome = 'recovered' | 'error' | 'final';

/**
 * Classifies a terminal (`done: true`) state into its outcome. The reducer's
 * error case sets `done: true` for BOTH the salvage and plain-error outcomes,
 * so callers must branch on this classification — not on `done` vs `error` —
 * or the error branch is unreachable.
 */
export function resolveTerminalOutcome(state: RecommendationStreamState): TerminalOutcome {
	if (state.recovered) return 'recovered';
	if (state.error) return 'error';
	return 'final';
}

export function reduceRecommendationStreamEvent(
	state: RecommendationStreamState,
	event: RecommendationStreamEvent
): RecommendationStreamState {
	switch (eventType(event)) {
		case 'phase': {
			return {
				...state,
				phaseLabel: typeof event.message === 'string' ? event.message : state.phaseLabel,
				percent: typeof event.percent === 'number' ? event.percent : state.percent
			};
		}
		case 'token': {
			if (typeof event.token !== 'string') return state;
			return {
				...state,
				markdownBuffer: state.markdownBuffer + event.token
			};
		}
		case 'final': {
			return {
				...state,
				content: event.content ?? state.content,
				done: true,
				error: null,
				recovered: false
			};
		}
		case 'done': {
			return {
				...state,
				done: true
			};
		}
		case 'error': {
			if (event.recoverable) {
				// Soft/recoverable error — the backend is still going to finish the
				// stream (lint/repair/finalize -> final). Don't terminate; ignore it.
				return state;
			}
			const salvaged = state.markdownBuffer.trim();
			if (salvaged) {
				return {
					...state,
					content: { format: 'markdown', markdown: salvaged },
					done: true,
					error: null,
					recovered: true
				};
			}
			return {
				...state,
				error: typeof event.error === 'string' ? event.error : 'Recommendation letter generation failed',
				done: true,
				recovered: false
			};
		}
		default:
			return state;
	}
}
