/**
 * Determines whether to auto-run gap analysis
 *
 * Multi-stage support is required; then auto-run when explicitly requested
 * OR when no gap analysis exists yet.
 */
export function shouldAutoRunGapAnalysis(opts: {
	hasMultiStageSupport: boolean;
	hasGapAnalysis: boolean;
	autoRunEnabled: boolean;
}): boolean {
	return opts.hasMultiStageSupport && (opts.autoRunEnabled || !opts.hasGapAnalysis);
}
