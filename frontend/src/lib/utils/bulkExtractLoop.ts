export interface BulkBatchResult {
	extracted_count: number;
	failed_count: number;
	errors: string[];
	remaining: number;
}

export interface BulkExtractOutcome {
	totalExtracted: number;
	totalFailed: number;
	errors: string[];
	batches: number;
	hitCap: boolean;
}

/**
 * Drive bulk-extract to full coverage.
 *
 * `runBatch` performs ONE `POST /bulk-extract` with `offset: 0` and returns the
 * parsed result. The loop never advances an offset — the backend re-queries the
 * live retry-set, which shrinks as docs are extracted or marked failed, so
 * always processing the head of that set strictly converges. `maxBatches` is a
 * safety cap that backstops pathological cases (`hitCap` reports if it was hit).
 */
export async function runCoverageLoop(
	runBatch: () => Promise<BulkBatchResult>,
	onProgress: (soFar: number) => void,
	maxBatches: number
): Promise<BulkExtractOutcome> {
	let totalExtracted = 0;
	let totalFailed = 0;
	let batches = 0;
	const errors: string[] = [];
	let remaining = Infinity;
	while (remaining > 0 && batches < maxBatches) {
		const r = await runBatch();
		batches++;
		totalExtracted += r.extracted_count ?? 0;
		totalFailed += r.failed_count ?? 0;
		if (r.errors?.length) errors.push(...r.errors);
		remaining = r.remaining ?? 0;
		onProgress(totalExtracted);
	}
	return { totalExtracted, totalFailed, errors, batches, hitCap: remaining > 0 };
}
