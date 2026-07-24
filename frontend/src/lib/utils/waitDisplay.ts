/**
 * Pure formatters for the "trustworthy wait" progress line
 * (Step X of Y · substance · ETA · liveness) shown during active
 * analysis runs. Kept dependency-free and side-effect-free so they
 * are trivial to unit test and safe to call every render tick.
 */

export function formatEta(sec: number | null | undefined): string {
	if (sec === null || sec === undefined) return '';
	if (sec <= 0) return 'almost done';
	const mins = Math.max(1, Math.round(sec / 60));
	return `~${mins} min remaining`;
}

export function livenessLine(
	healthy: boolean | undefined,
	heartbeatAgeSec: number | null | undefined
): string {
	if (healthy === false) return 'Worker unresponsive — this may have stalled';
	const age = heartbeatAgeSec == null ? 0 : Math.round(heartbeatAgeSec);
	return `Working normally · updated ${age}s ago`;
}

export function substanceLine(
	itemsDone: number | null | undefined,
	itemsTotal: number | null | undefined,
	_stepIndex: number | undefined
): string {
	if (typeof itemsDone === 'number' && typeof itemsTotal === 'number' && itemsTotal > 0) {
		return `${itemsDone} of ${itemsTotal} documents`;
	}
	return 'This step takes several minutes on large cases';
}
