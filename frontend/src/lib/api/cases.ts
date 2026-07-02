import { apiFetch } from '$lib/utils/apiFetch';

export interface ClioSyncItemDetail {
	name: string;
	type: 'document' | 'communication' | 'note';
	date?: string;
	previous_version_date?: string;
}

export interface ClioSyncSummary {
	new_items: number;
	updated_items: number;
	total_processed: number;
}

export interface ClioSyncResponse {
	success: boolean;
	case_id: string;
	synced_at: string;
	summary: ClioSyncSummary;
	details: {
		new: ClioSyncItemDetail[];
		updated: ClioSyncItemDetail[];
	};
	needs_reanalysis: boolean;
}

export interface DedupResponse {
	success: boolean;
	duplicates_found: number;
	documents_checked: number;
	message: string;
}

export async function dedupCaseDocuments(caseId: string): Promise<DedupResponse> {
	return apiFetch<DedupResponse>(`/api/cases/${caseId}/dedup`, { method: 'POST' });
}

export async function syncClioMatter(caseId: string): Promise<ClioSyncResponse> {
	return apiFetch<ClioSyncResponse>(`/api/clio/sync/${caseId}`, { method: 'POST' });
}
