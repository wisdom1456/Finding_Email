import { getApiUrl } from '$lib/config';
import { getSecureSession } from '$lib/supabase';

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
	const { session, user } = await getSecureSession();

	if (!session || !user) {
		throw new Error('Not authenticated - please log in');
	}

	const apiUrl = getApiUrl();
	const response = await fetch(`${apiUrl}/api/cases/${caseId}/dedup`, {
		method: 'POST',
		headers: {
			Authorization: `Bearer ${session.access_token}`
		}
	});

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: 'Failed to deduplicate documents' }));
		throw new Error(error.detail || 'Failed to deduplicate documents');
	}

	return response.json();
}

export async function syncClioMatter(caseId: string): Promise<ClioSyncResponse> {
	const { session, user } = await getSecureSession();

	if (!session || !user) {
		throw new Error('Not authenticated - please log in');
	}

	const apiUrl = getApiUrl();
	const response = await fetch(`${apiUrl}/api/clio/sync/${caseId}`, {
		method: 'POST',
		headers: {
			Authorization: `Bearer ${session.access_token}`
		}
	});

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: 'Failed to sync Clio matter' }));
		throw new Error(error.detail || 'Failed to sync Clio matter');
	}

	return response.json();
}
