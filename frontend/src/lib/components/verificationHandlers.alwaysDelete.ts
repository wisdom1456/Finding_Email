/**
 * Extracted handleAlwaysDelete logic for testability.
 *
 * Operation order (safe):
 *   1. Auth check
 *   2. Fetch profile and validate prerequisites (non-destructive)
 *   3. Add blacklist rule (non-destructive, idempotent)
 *   4. Delete documents (destructive — only after blacklist is saved)
 *   5. Refresh UI
 *
 * This ordering ensures that if any step fails:
 *   - Step 2 fails → nothing happens (safe)
 *   - Step 3 fails → nothing happens (safe)
 *   - Step 4 fails → blacklist rule exists, docs survive, user can retry delete
 *   - Step 4 partial → blacklist rule still prevents re-import
 */

import { deriveBlacklistRule, isNameBlacklisted, toCanonicalBlacklistTerm } from '$lib/utils/blacklist';

export interface AlwaysDeleteDeps {
	getSecureSession: () => Promise<{ session: any; user: any }>;
	getApiUrl: () => string;
	toastStore: {
		success: (msg: string) => void;
		error: (msg: string) => void;
		warning: (msg: string) => void;
	};
	onDocumentsUpdated: () => Promise<void>;
	localDocuments: any[];
	fetchFn?: typeof fetch;
}

export interface AlwaysDeleteResult {
	success: boolean;
	blacklistRuleAdded: boolean;
	documentsDeleted: number;
	error?: string;
}

export async function handleAlwaysDelete(
	docName: string,
	docId: string | undefined,
	deps: AlwaysDeleteDeps,
): Promise<AlwaysDeleteResult> {
	const f = deps.fetchFn ?? fetch;

	try {
		// 1. Auth check
		const { session, user } = await deps.getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

		const apiUrl = deps.getApiUrl();
		const blacklistRule = deriveBlacklistRule(docName) || docName;

		// 2. Fetch profile — validate prerequisite before any destructive action
		const getResponse = await f(`${apiUrl}/api/profile`, {
			headers: {
				Authorization: `Bearer ${session.access_token}`,
				'Content-Type': 'application/json',
			},
		});

		if (!getResponse.ok) throw new Error('Failed to fetch profile');
		const profile = await getResponse.json();

		// 3. Add blacklist rule — idempotent, before deleting
		const currentBlacklist: string[] = profile.ai_preferences?.blacklisted_documents || [];
		const hasEquivalentRule = currentBlacklist.some((rule: string) => {
			const existingCanonical = toCanonicalBlacklistTerm(rule);
			const incomingCanonical = toCanonicalBlacklistTerm(blacklistRule);
			return (
				rule.trim().toLowerCase() === blacklistRule.trim().toLowerCase() ||
				(existingCanonical && existingCanonical === incomingCanonical)
			);
		});

		let blacklistRuleAdded = false;
		if (!hasEquivalentRule) {
			const updatedBlacklist = [...currentBlacklist, blacklistRule];
			const profileData = {
				ai_preferences: {
					...profile.ai_preferences,
					blacklisted_documents: updatedBlacklist,
				},
			};

			const updateResponse = await f(`${apiUrl}/api/profile`, {
				method: 'PUT',
				headers: {
					Authorization: `Bearer ${session.access_token}`,
					'Content-Type': 'application/json',
				},
				body: JSON.stringify(profileData),
			});

			if (!updateResponse.ok) throw new Error('Failed to update blacklist');
			blacklistRuleAdded = true;
		}

		// 4. Delete documents — only after blacklist is secured
		let documentsDeleted = 0;
		let deleteWarning = '';

		if (docId) {
			const docsToDelete = deps.localDocuments.filter(
				(d) => d.file_name === docName || isNameBlacklisted(d.file_name, [blacklistRule]),
			);
			const docIds = [...new Set(docsToDelete.map((d: any) => d.id))];

			if (docIds.length > 0) {
				const deleteResponse = await f(`${apiUrl}/api/documents/bulk-delete`, {
					method: 'POST',
					headers: {
						'Content-Type': 'application/json',
						Authorization: `Bearer ${session.access_token}`,
					},
					body: JSON.stringify({ document_ids: docIds }),
				});

				if (!deleteResponse.ok) throw new Error('Failed to delete selected documents');

				const deleteResult = await deleteResponse.json();
				documentsDeleted = deleteResult?.deleted_count ?? docIds.length;
				const failedCount = deleteResult?.failed_ids?.length ?? 0;
				if (failedCount > 0) {
					deleteWarning = `Deleted ${documentsDeleted} documents, but ${failedCount} could not be deleted.`;
				}
			}
		}

		// 5. Success notifications
		deps.toastStore.success(`"${blacklistRule}" will always be excluded from future imports`);
		if (deleteWarning) {
			deps.toastStore.warning(deleteWarning);
		}
		await deps.onDocumentsUpdated();

		return { success: true, blacklistRuleAdded, documentsDeleted };
	} catch (error: any) {
		deps.toastStore.error(`Blacklist error: ${error.message}`);
		return { success: false, blacklistRuleAdded: false, documentsDeleted: 0, error: error.message };
	}
}
