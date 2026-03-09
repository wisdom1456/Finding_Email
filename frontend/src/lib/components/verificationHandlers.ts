/**
 * Extracted handler logic from VerificationHub.svelte for testability.
 *
 * These functions encapsulate the auth → fetch → update patterns used by
 * the VerificationHub component. They accept dependencies as parameters
 * so they can be tested without rendering the component.
 */

export interface HandlerDeps {
	getSecureSession: () => Promise<{ session: any; user: any }>;
	getApiUrl: () => string;
	toastStore: {
		success: (msg: string) => void;
		error: (msg: string) => void;
		info: (msg: string) => void;
		warning: (msg: string) => void;
	};
	onDocumentsUpdated: () => Promise<void>;
	fetchFn?: typeof fetch;
}

export interface OptimisticResult<T> {
	rollback: () => void;
	applied: boolean;
	value?: T;
}

/**
 * Apply an optimistic update to a local document array, returning a rollback function.
 * If the updater returns false, the update is skipped (document not found).
 */
export function applyOptimistic(
	localDocuments: any[],
	docId: string,
	updater: (doc: any) => any,
): { newDocs: any[]; rollback: any[] | null; idx: number } {
	const idx = localDocuments.findIndex((d: any) => d.id === docId);
	if (idx < 0) {
		return { newDocs: localDocuments, rollback: null, idx: -1 };
	}
	const snapshot = [...localDocuments];
	const doc = localDocuments[idx];
	const updatedDocs = [...localDocuments];
	updatedDocs[idx] = updater(doc);
	return { newDocs: updatedDocs, rollback: snapshot, idx };
}

/**
 * Handle document type override with optimistic update + rollback on failure.
 */
export async function handleTypeOverride(
	docId: string,
	type: string,
	localDocuments: any[],
	deps: HandlerDeps,
): Promise<{ documents: any[]; success: boolean }> {
	const f = deps.fetchFn ?? fetch;

	// Apply optimistic update
	const { newDocs, rollback } = applyOptimistic(localDocuments, docId, (doc) => ({
		...doc,
		metadata: {
			...doc.metadata,
			attorney_enrichment: {
				...(doc.metadata?.attorney_enrichment || {}),
				document_type_override: type,
			},
		},
	}));

	try {
		const { session, user } = await deps.getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

		const response = await f(`${deps.getApiUrl()}/api/documents/${docId}/verify`, {
			method: 'PATCH',
			headers: {
				'Content-Type': 'application/json',
				Authorization: `Bearer ${session.access_token}`,
			},
			body: JSON.stringify({ document_type_override: type }),
		});

		if (!response.ok) throw new Error('Failed to save changes');
		return { documents: newDocs, success: true };
	} catch (e: any) {
		deps.toastStore.error('Failed to save document type');
		// Rollback on failure
		return { documents: rollback ?? localDocuments, success: false };
	}
}

/**
 * Handle relevance level change with optimistic update + rollback on failure.
 */
export async function handleRelevanceChange(
	docId: string,
	level: string,
	localDocuments: any[],
	deps: HandlerDeps,
): Promise<{ documents: any[]; success: boolean }> {
	const f = deps.fetchFn ?? fetch;

	const { newDocs, rollback } = applyOptimistic(localDocuments, docId, (doc) => ({
		...doc,
		metadata: {
			...doc.metadata,
			attorney_enrichment: {
				...(doc.metadata?.attorney_enrichment || {}),
				relevance_level: level,
			},
		},
	}));

	try {
		const { session, user } = await deps.getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

		const response = await f(`${deps.getApiUrl()}/api/documents/${docId}/verify`, {
			method: 'PATCH',
			headers: {
				'Content-Type': 'application/json',
				Authorization: `Bearer ${session.access_token}`,
			},
			body: JSON.stringify({ relevance_level: level }),
		});

		if (!response.ok) throw new Error('Failed to save changes');
		return { documents: newDocs, success: true };
	} catch (e: any) {
		deps.toastStore.error('Failed to save relevance');
		return { documents: rollback ?? localDocuments, success: false };
	}
}

/**
 * Handle notes update with optimistic update + rollback on failure.
 */
export async function handleNotesUpdate(
	docId: string,
	notes: string,
	localDocuments: any[],
	deps: HandlerDeps,
): Promise<{ documents: any[]; success: boolean }> {
	const f = deps.fetchFn ?? fetch;

	const { newDocs, rollback } = applyOptimistic(localDocuments, docId, (doc) => ({
		...doc,
		metadata: {
			...doc.metadata,
			attorney_enrichment: {
				...(doc.metadata?.attorney_enrichment || {}),
				attorney_notes: notes,
			},
		},
	}));

	try {
		const { session, user } = await deps.getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

		const response = await f(`${deps.getApiUrl()}/api/documents/${docId}/verify`, {
			method: 'PATCH',
			headers: {
				'Content-Type': 'application/json',
				Authorization: `Bearer ${session.access_token}`,
			},
			body: JSON.stringify({ attorney_notes: notes }),
		});

		if (!response.ok) throw new Error('Failed to save changes');
		return { documents: newDocs, success: true };
	} catch (e: any) {
		deps.toastStore.error('Failed to save notes');
		return { documents: rollback ?? localDocuments, success: false };
	}
}

/**
 * Handle re-extract with double-submit prevention.
 * Returns whether extraction was attempted (false if already processing).
 */
export async function handleReExtract(
	docId: string,
	processingDocIds: Set<string>,
	deps: HandlerDeps,
): Promise<{ attempted: boolean; success: boolean; newProcessingIds: Set<string> }> {
	const f = deps.fetchFn ?? fetch;

	// Double-submit guard
	if (processingDocIds.has(docId)) {
		return { attempted: false, success: false, newProcessingIds: processingDocIds };
	}

	const withDoc = new Set(processingDocIds);
	withDoc.add(docId);

	deps.toastStore.info('Re-extracting with Vision OCR...');

	try {
		const { session, user } = await deps.getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

		const response = await f(`${deps.getApiUrl()}/api/documents/${docId}/extract`, {
			method: 'POST',
			headers: { Authorization: `Bearer ${session.access_token}` },
		});

		if (!response.ok) {
			const errBody = await response.json().catch(() => ({}));
			throw new Error(errBody.detail || `Extraction failed (${response.status})`);
		}

		deps.toastStore.success('Extraction complete');
		await deps.onDocumentsUpdated();

		const withoutDoc = new Set(withDoc);
		withoutDoc.delete(docId);
		return { attempted: true, success: true, newProcessingIds: withoutDoc };
	} catch (error: any) {
		deps.toastStore.error(error.message);
		const withoutDoc = new Set(withDoc);
		withoutDoc.delete(docId);
		return { attempted: true, success: false, newProcessingIds: withoutDoc };
	}
}

/**
 * Handle bulk extract with double-submit prevention and batch processing.
 * Returns updated processing state.
 */
export async function handleBulkExtract(
	docsToProcess: any[],
	processingDocIds: Set<string>,
	isAlreadyBulkLoading: boolean,
	deps: HandlerDeps,
): Promise<{
	success: boolean;
	extractedCount: number;
	failedCount: number;
	newProcessingIds: Set<string>;
}> {
	const f = deps.fetchFn ?? fetch;

	if (docsToProcess.length === 0 || isAlreadyBulkLoading) {
		return {
			success: false,
			extractedCount: 0,
			failedCount: 0,
			newProcessingIds: processingDocIds,
		};
	}

	const BATCH_SIZE = 3;
	let extractedCount = 0;
	let failedCount = 0;
	let currentProcessing = new Set(processingDocIds);

	try {
		const { session, user } = await deps.getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

		for (let i = 0; i < docsToProcess.length; i += BATCH_SIZE) {
			const batch = docsToProcess.slice(i, i + BATCH_SIZE);

			// Mark batch as processing
			for (const doc of batch) {
				currentProcessing.add(doc.id);
			}

			const results = await Promise.allSettled(
				batch.map((doc: any) =>
					f(`${deps.getApiUrl()}/api/documents/${doc.id}/extract`, {
						method: 'POST',
						headers: { Authorization: `Bearer ${session.access_token}` },
					})
				)
			);

			for (let j = 0; j < results.length; j++) {
				const r = results[j];
				if (r.status === 'fulfilled' && r.value.ok) {
					extractedCount++;
				} else {
					failedCount++;
				}
				currentProcessing = new Set(currentProcessing);
				currentProcessing.delete(batch[j].id);
			}

			await deps.onDocumentsUpdated();
		}

		if (failedCount > 0) {
			deps.toastStore.warning(`Extracted ${extractedCount} docs, but ${failedCount} failed.`);
		} else {
			deps.toastStore.success(`Successfully extracted all ${extractedCount} documents`);
		}

		return { success: true, extractedCount, failedCount, newProcessingIds: new Set() };
	} catch (error: any) {
		deps.toastStore.error(error.message);
		return { success: false, extractedCount, failedCount, newProcessingIds: new Set() };
	}
}
