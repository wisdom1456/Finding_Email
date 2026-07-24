/**
 * Pure mapping from a case's `ui_state` to which controls the page may render.
 *
 * This is the G1 guarantee: no control set below permits both an active-run
 * state (queued/running/stalled) and a Start/Re-run button at the same time.
 * Callers must render Start/Re-run ONLY when the corresponding flag is true —
 * never derive "can I restart?" from anything else (loading flags, timers).
 */
export interface Controls {
	start: boolean;
	cancel: boolean;
	startOver: boolean;
	rerun: boolean;
	viewResults: boolean;
}

export function controlsFor(uiState: string): Controls {
	switch (uiState) {
		case 'queued':
		case 'running':
			return { start: false, cancel: true, startOver: false, rerun: false, viewResults: false };
		case 'stalled':
			return { start: false, cancel: false, startOver: true, rerun: false, viewResults: false };
		case 'completed':
			return { start: false, cancel: false, startOver: false, rerun: true, viewResults: true };
		case 'failed':
			return { start: false, cancel: false, startOver: true, rerun: false, viewResults: false };
		case 'idle':
		case 'cancelled':
		default:
			return { start: true, cancel: false, startOver: false, rerun: false, viewResults: false };
	}
}
