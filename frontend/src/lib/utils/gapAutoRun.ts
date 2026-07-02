/**
 * Determines whether to auto-run gap analysis
 *
 * Only auto-runs when:
 * - Multi-stage support is available for the case
 * - Gap analysis hasn't been run yet
 * - Auto-run is explicitly enabled
 */
export function shouldAutoRunGapAnalysis(opts: {
	hasMultiStageSupport: boolean;
	hasGapAnalysis: boolean;
	autoRunEnabled: boolean;
}): boolean {
	return opts.hasMultiStageSupport && !opts.hasGapAnalysis && opts.autoRunEnabled;
}
