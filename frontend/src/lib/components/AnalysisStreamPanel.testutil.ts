/**
 * Test utility that mirrors the emitComplete + saveAnalysis behavioral contract
 * from AnalysisStreamPanel.svelte. This allows testing the save timing logic
 * without mounting the full Svelte component.
 *
 * IMPORTANT: This must be kept in sync with the actual component logic.
 */

export async function testEmitComplete(
	caseId: string,
	analysisContent: string,
	onComplete: ((content: string) => void) | undefined,
	fetchFn: typeof fetch
): Promise<void> {
	// Mirror the saveAnalysis logic
	try {
		const response = await fetchFn(`/api/analysis/stream/${caseId}/save`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ content: analysisContent })
		});
		if (!response.ok) {
			console.error('Failed to save analysis');
		}
	} catch (e) {
		console.error('Error saving analysis:', e);
	}

	// onComplete fires AFTER save completes (success or failure)
	onComplete?.(analysisContent);
}
