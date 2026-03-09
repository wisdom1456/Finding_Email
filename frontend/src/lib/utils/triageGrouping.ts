/**
 * Pure triage grouping logic extracted from VerificationHub.
 *
 * Groups documents into 5 categories:
 *   - critical: download_failed, corrupted
 *   - needs_attention: extraction_failed, needs_review, pending, ready without extraction
 *   - ready: ready with extraction
 *   - duplicates: duplicate documents
 *   - excluded: manually excluded from analysis
 *
 * Each group is sorted by attention score (highest first).
 */
import { sortByAttention } from './documentSorting';

export interface TriageGroups {
	critical: any[];
	needs_attention: any[];
	ready: any[];
	duplicates: any[];
	excluded: any[];
}

export function groupDocuments(documents: any[]): TriageGroups {
	const groups: TriageGroups = {
		critical: [],
		needs_attention: [],
		ready: [],
		duplicates: [],
		excluded: [],
	};

	for (const doc of documents) {
		const status = doc.status;
		const isDuplicate = doc.metadata?.is_duplicate === true || status === 'duplicate';
		const isExcluded = doc.metadata?.excluded === true;

		if (isExcluded) {
			groups.excluded.push(doc);
		} else if (isDuplicate) {
			groups.duplicates.push(doc);
		} else if (status === 'download_failed' || status === 'corrupted') {
			groups.critical.push(doc);
		} else if (
			status === 'extraction_failed' ||
			status === 'needs_review' ||
			status === 'pending' ||
			(status === 'ready' && !doc.extracted_at)
		) {
			groups.needs_attention.push(doc);
		} else {
			groups.ready.push(doc);
		}
	}

	groups.critical = sortByAttention(groups.critical);
	groups.needs_attention = sortByAttention(groups.needs_attention);
	groups.ready = sortByAttention(groups.ready);
	groups.duplicates = sortByAttention(groups.duplicates);
	groups.excluded = sortByAttention(groups.excluded);

	return groups;
}

/**
 * Filter documents by triage chip filters.
 *
 * When no filters are active, returns all documents.
 * When filters are active, returns only documents matching at least one filter.
 */
export function filterDocuments(
	documents: any[],
	activeFilters: Set<string>
): any[] {
	if (activeFilters.size === 0) return documents;

	return documents.filter((d) => {
		const enrichment = d.metadata?.attorney_enrichment || {};
		const quality = d.metadata?.quality_score ?? 10;

		if (activeFilters.has('missing-signatures')) {
			const sigExpected =
				d.signature_expected === true ||
				d.metadata?.registry?.signature_expected === true;
			const sigSatisfied =
				d.signed_status === 'signed' ||
				enrichment.signature_verification === 'signed';
			if (sigExpected && !sigSatisfied) return true;
		}
		if (activeFilters.has('low-ocr')) {
			if (quality < 5) return true;
		}
		if (activeFilters.has('needs-type')) {
			if (!d.document_type_label && !enrichment.document_type_override)
				return true;
		}
		if (activeFilters.has('ready')) {
			if (d.status === 'ready') return true;
		}
		return false;
	});
}
