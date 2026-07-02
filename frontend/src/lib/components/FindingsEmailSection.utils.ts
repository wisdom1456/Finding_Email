/**
 * Extracted pure constants from FindingsEmailSection for testability.
 */

export type FindingsGenerationState =
	| 'idle'
	| 'connecting'
	| 'strategy'
	| 'context_build'
	| 'draft_generation'
	| 'lint_validation'
	| 'repair'
	| 'polishing'
	| 'finalizing'
	| 'complete'
	| 'error'
	| 'cancelled';

/**
 * Ordered list of phases the findings-letter SSE stream can emit, used to drive the
 * phase progress bar (`indexOf(currentPhase)` determines how many steps are "done").
 *
 * Must match the backend emission order in
 * src/legal_portal/api/routes/letter_routes.py::stream_letter (search "_emit(\"phase\"...)"):
 * strategy -> context_build -> draft_generation -> lint_validation -> repair (conditional)
 * -> polishing -> finalizing. Omitting any phase here makes `indexOf` return -1 for that
 * phase, which resets the progress bar to all-gray mid-generation.
 */
export const FINDINGS_PHASE_ORDER: FindingsGenerationState[] = [
	'strategy', 'context_build', 'draft_generation',
	'lint_validation', 'repair', 'polishing', 'finalizing'
];

export const FINDINGS_PHASE_LABELS: Record<string, string> = {
	strategy: 'Preparing strategy',
	context_build: 'Prioritizing key documents',
	draft_generation: 'Drafting letter',
	lint_validation: 'Reviewing for accuracy',
	repair: 'Fixing issues',
	polishing: 'Final polish',
	finalizing: 'Saving'
};
