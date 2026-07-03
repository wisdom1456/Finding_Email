export interface AutoExtractDoc {
	status?: string | null;
	extracted_at?: string | null;
	extracted_text?: string | null;
	is_flagged_as_junk?: boolean | null;
}

export interface AutoExtractOpts {
	flagEnabled: boolean;
	analysisInProgress: boolean;
	importInProgress: boolean;
	alreadyRanThisLoad: boolean;
}

// Keep in sync with NON_RETRYABLE in src/legal_portal/api/routes/documents.py.
// extraction_failed is terminal for auto-fire: a doc the bulk pass could not
// extract must not re-trigger the whole bulk run on every future page load.
const EXCLUDED_STATUSES = new Set([
	'skipped_small_image',
	'skipped',
	'duplicate',
	'corrupted',
	'download_failed',
	'extraction_failed',
]);

export function docNeedsExtraction(doc: AutoExtractDoc): boolean {
	if (doc.is_flagged_as_junk) return false;
	if (EXCLUDED_STATUSES.has(doc.status ?? '')) return false;
	const hasText = Boolean((doc.extracted_text ?? '').trim());
	return !doc.extracted_at && !hasText;
}

export function shouldAutoExtract(docs: AutoExtractDoc[], opts: AutoExtractOpts): boolean {
	if (!opts.flagEnabled) return false;
	if (opts.analysisInProgress || opts.importInProgress) return false;
	if (opts.alreadyRanThisLoad) return false;
	return docs.some(docNeedsExtraction);
}
