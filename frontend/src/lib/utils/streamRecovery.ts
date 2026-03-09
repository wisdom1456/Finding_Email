/**
 * Stream Recovery — post-stream reconciliation logic.
 *
 * Extracted from the case detail page so it can be tested independently.
 * Handles the transition from "streaming completed" to "results loaded"
 * with resilience against sub-step failures.
 */

export interface ReconciliationDeps {
	/** Load analysis status from the database. May throw. */
	loadAnalysisStatus: () => Promise<void>;
	/** Load embedded results workspace. May throw. */
	loadEmbeddedResults: (force: boolean) => Promise<void>;
	/** Show a success toast. */
	onSuccess: (message: string) => void;
	/** Show an error toast. */
	onError: (message: string) => void;
}

export interface ReconciliationResult {
	/** Whether the reconciliation settled to a usable state. */
	settled: boolean;
	/** Whether analysis status loaded successfully. */
	statusLoaded: boolean;
	/** Whether embedded results loaded successfully. */
	resultsLoaded: boolean;
	/** Error messages from failed sub-steps (empty if all succeeded). */
	errors: string[];
}

/**
 * Reconcile UI state after streaming analysis completes.
 *
 * Guarantees: always returns (never throws), always settles to a terminal state.
 * Individual sub-steps can fail without blocking the overall flow.
 */
export async function reconcileAfterStream(
	deps: ReconciliationDeps
): Promise<ReconciliationResult> {
	const result: ReconciliationResult = {
		settled: false,
		statusLoaded: false,
		resultsLoaded: false,
		errors: [],
	};

	// Step 1: Load analysis status (non-blocking failure)
	try {
		await deps.loadAnalysisStatus();
		result.statusLoaded = true;
	} catch (e: any) {
		result.errors.push(`Status: ${e.message || 'Failed to load analysis status'}`);
	}

	// Step 2: Load embedded results (non-blocking failure)
	try {
		await deps.loadEmbeddedResults(true);
		result.resultsLoaded = true;
	} catch (e: any) {
		const msg = e.message || 'Failed to load results';
		result.errors.push(`Results: ${msg}`);
		deps.onError('Results are ready but failed to load. Try refreshing the page.');
	}

	// Always settle
	result.settled = true;

	if (result.statusLoaded && result.resultsLoaded) {
		deps.onSuccess('Analysis complete! Loading results workspace...');
	}

	return result;
}

export type CaseLoadResult =
	| { type: 'found'; data: Record<string, any> }
	| { type: 'not_found' }
	| { type: 'error'; message: string };

/**
 * Load a case with graceful not-found handling.
 *
 * Uses maybeSingle() semantics: returns { type: 'not_found' } when the row
 * doesn't exist instead of throwing a 406. This prevents the stuck-spinner
 * bug where .single() throws on missing rows.
 */
export async function loadCaseGracefully(
	queryFn: () => Promise<{ data: any; error: any }>
): Promise<CaseLoadResult> {
	try {
		const { data, error } = await queryFn();
		if (error) {
			return { type: 'error', message: error.message || 'Failed to load case' };
		}
		if (!data) {
			return { type: 'not_found' };
		}
		return { type: 'found', data };
	} catch (e: any) {
		return { type: 'error', message: e.message || 'Failed to load case' };
	}
}
