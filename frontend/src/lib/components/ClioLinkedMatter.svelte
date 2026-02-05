<script lang="ts">
	import { getApiUrl } from '$lib/config';
	import { getSecureSession } from '$lib/supabase';
	import type { ClioMatterData, CaseData } from '$lib/types';
	import ClioMatterSearch from './ClioMatterSearch.svelte';
	import ConfirmDialog from './ui/ConfirmDialog.svelte';
	import Badge from './ui/Badge.svelte';

	let { 
		caseId, 
		matterData, 
		caseData,
		onUnlinked,
		onMatterChanged
	} = $props<{
		caseId: string;
		matterData: ClioMatterData;
		caseData?: CaseData;
		onUnlinked?: () => void;
		onMatterChanged?: () => void;
	}>();

	let unlinking = $state(false);
	let changingMatter = $state(false);
	let showChangeMatterModal = $state(false);
	let showAdvanced = $state(false);
	let errorMessage = $state('');
	let showUnlinkConfirm = $state(false);
	let showChangeMatterConfirm = $state(false);
	let selectedMatterId = $state<number | null>(null);

	// Determine if this case was created via Clio
	const createdViaClio = $derived(caseData?.created_via_clio || false);

	async function handleUnlink() {
		unlinking = true;
		errorMessage = '';

		try {
			const { session, user } = await getSecureSession();

			if (!session || !user) {
				throw new Error('Not authenticated');
			}

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/clio/unlink/${caseId}`, {
				method: 'DELETE',
				headers: {
					Authorization: `Bearer ${session.access_token}`
				}
			});

			if (!response.ok) {
				const error = await response.json().catch(() => ({}));
				throw new Error(error.detail || 'Failed to unlink Clio matter');
			}

			// Call the callback to refresh parent component
			if (onUnlinked) {
				onUnlinked();
			}
		} catch (error: any) {
			errorMessage = error.message || 'Failed to unlink Clio matter';
		} finally {
			unlinking = false;
		}
	}

	async function handleChangeMatter(result: { matterId: number; success: boolean; error?: string }) {
		if (!result.success) {
			errorMessage = result.error || 'Failed to change matter';
			return;
		}

		// Close modal and refresh
		showChangeMatterModal = false;
		if (onMatterChanged) {
			onMatterChanged();
		}
	}

	async function changeMatter(matterId: number) {
		changingMatter = true;
		errorMessage = '';

		try {
			const { session, user } = await getSecureSession();

			if (!session || !user) {
				throw new Error('Not authenticated');
			}

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/cases/${caseId}/change-matter`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`
				},
				body: JSON.stringify({
					matter_id: matterId,
					auto_import: true
				})
			});

			if (!response.ok) {
				const error = await response.json();
				throw new Error(error.detail || 'Failed to change matter');
			}

			const result = await response.json();
			
			// Close modal and refresh
			showChangeMatterModal = false;
			if (onMatterChanged) {
				onMatterChanged();
			}
		} catch (error: any) {
			errorMessage = error.message || 'Failed to change matter';
		} finally {
			changingMatter = false;
		}
	}

	function handleMatterSelection(matterId: number) {
		selectedMatterId = matterId;
		showChangeMatterConfirm = true;
	}

	async function confirmChangeMatter() {
		if (selectedMatterId !== null) {
			await changeMatter(selectedMatterId);
			selectedMatterId = null;
		}
	}

	// Format the import date
	function formatDate(isoDate: string): string {
		const date = new Date(isoDate);
		return date.toLocaleDateString('en-US', {
			year: 'numeric',
			month: 'long',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}
</script>

<div class="space-y-6">
	<!-- Matter Information Card -->
	<div class="bg-accent/10 border border-accent/30 rounded-lg p-6">
		<div class="flex items-start justify-between">
			<div class="flex-1">
				<div class="flex items-center gap-2 mb-2">
					<svg
						class="h-5 w-5 text-accent"
						fill="none"
						viewBox="0 0 24 24"
						stroke="currentColor"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
						/>
					</svg>
					<h4 class="text-lg font-medium text-contrast">Linked to Clio Matter</h4>
				</div>

				<div class="space-y-2 text-sm">
					<div class="flex items-center gap-2">
						<span class="font-medium text-contrast">Matter #:</span>
						<span class="text-accent">{matterData.display_number}</span>
					</div>

					<div class="flex items-center gap-2">
						<span class="font-medium text-contrast">Client:</span>
						<span class="text-accent">{matterData.client_name}</span>
					</div>

					{#if matterData.description}
						<div class="flex items-start gap-2">
							<span class="font-medium text-contrast">Description:</span>
							<span class="text-gray-700">{matterData.description}</span>
						</div>
					{/if}

					{#if matterData.practice_area}
						<div class="flex items-center gap-2">
							<span class="font-medium text-contrast">Practice Area:</span>
							<span class="text-gray-700">{matterData.practice_area}</span>
						</div>
					{/if}

					<div class="flex items-center gap-2">
						<span class="font-medium text-contrast">Status:</span>
						<Badge variant="info" size="sm">
							{matterData.status}
						</Badge>
					</div>
				</div>
			</div>
		</div>

		<!-- Import Summary -->
		<div class="mt-4 pt-4 border-t border-accent/30">
			<p class="text-xs text-gray-600 mb-3">
				Imported on {formatDate(matterData.imported_at)}
			</p>

			<div class="grid grid-cols-3 gap-4">
				<!-- Communications -->
				<div class="bg-white rounded-md p-3 text-center">
					<div class="flex items-center justify-center gap-2 mb-1">
						<svg class="h-4 w-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
							/>
						</svg>
						<span class="text-2xl font-bold text-contrast"
							>{matterData.communications_count || 0}</span
						>
					</div>
					<p class="text-xs text-gray-600">Communications</p>
				</div>

				<!-- Notes -->
				<div class="bg-white rounded-md p-3 text-center">
					<div class="flex items-center justify-center gap-2 mb-1">
						<svg class="h-4 w-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
							/>
						</svg>
						<span class="text-2xl font-bold text-contrast">{matterData.notes_count || 0}</span>
					</div>
					<p class="text-xs text-gray-600">Notes</p>
				</div>

				<!-- Documents -->
				<div class="bg-white rounded-md p-3 text-center">
					<div class="flex items-center justify-center gap-2 mb-1">
						<svg class="h-4 w-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
							/>
						</svg>
						<span class="text-2xl font-bold text-contrast">{matterData.documents_count || 0}</span>
					</div>
					<p class="text-xs text-gray-600">Documents</p>
				</div>
			</div>
		</div>
	</div>

	<!-- Action Buttons -->
	<div class="flex justify-between items-center">
		<div>
			{#if createdViaClio}
				<!-- Cases created via Clio show Change Matter button prominently -->
				<button
					onclick={() => (showChangeMatterModal = true)}
					disabled={changingMatter}
					class="inline-flex items-center px-4 py-2 border border-accent/50 rounded-md shadow-sm text-sm font-medium text-accent bg-white hover:bg-accent/10 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent disabled:opacity-50 disabled:cursor-not-allowed"
				>
					<svg class="-ml-1 mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"
						/>
					</svg>
					Change Matter
				</button>
			{:else}
				<!-- Manual cases show Link to Clio as primary, with Advanced menu for Unlink -->
				<details bind:open={showAdvanced} class="relative">
					<summary
						class="cursor-pointer text-sm text-gray-600 hover:text-gray-800 list-none flex items-center gap-1"
					>
						<svg
							class="h-4 w-4 transition-transform {showAdvanced ? 'rotate-90' : ''}"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
						>
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
						</svg>
						Advanced Options
					</summary>
					<div class="mt-2 pl-5">
						<button
							onclick={() => showUnlinkConfirm = true}
							disabled={unlinking}
							class="btn btn-secondary text-red-600 hover:text-red-700 border-red-200 hover:border-red-300 text-xs px-3 py-1.5"
						>
							{#if unlinking}
								<svg
									class="animate-spin -ml-1 mr-2 h-3 w-3 text-red-700"
									fill="none"
									viewBox="0 0 24 24"
								>
									<circle
										class="opacity-25"
										cx="12"
										cy="12"
										r="10"
										stroke="currentColor"
										stroke-width="4"
									></circle>
									<path
										class="opacity-75"
										fill="currentColor"
										d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
									></path>
								</svg>
								Unlinking...
							{:else}
								<svg class="-ml-1 mr-1.5 h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"
									/>
								</svg>
								Remove Clio Link Completely
							{/if}
						</button>
					</div>
				</details>
			{/if}
		</div>
	</div>

	<!-- Error Message -->
	{#if errorMessage}
		<div class="rounded-md bg-red-50 p-4">
			<div class="flex">
				<div class="shrink-0">
					<svg class="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
						<path
							fill-rule="evenodd"
							d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
							clip-rule="evenodd"
						/>
					</svg>
				</div>
				<div class="ml-3">
					<p class="text-sm font-medium text-red-800">{errorMessage}</p>
				</div>
			</div>
		</div>
	{/if}
</div>

<!-- Change Matter Modal -->
{#if showChangeMatterModal}
	<div
		class="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50 flex items-center justify-center p-4"
		role="dialog"
		aria-modal="true"
		tabindex="-1"
		onclick={() => !changingMatter && (showChangeMatterModal = false)}
		onkeydown={(e) => { if (e.key === 'Escape' && !changingMatter) showChangeMatterModal = false; }}
	>
		<div
			class="relative card-standard shadow-xl max-w-4xl w-full max-h-[90vh] flex flex-col p-0"
			role="presentation"
			onclick={(e) => e.stopPropagation()}
			onkeydown={(e) => e.stopPropagation()}
		>
			<div class="flex items-start justify-between p-6 border-b border-gray-200">
				<h3 class="text-lg font-medium text-gray-900">Change Clio Matter</h3>
				<button
					onclick={() => !changingMatter && (showChangeMatterModal = false)}
					disabled={changingMatter}
					class="text-gray-400 hover:text-gray-500 disabled:opacity-50"
				>
					<span class="sr-only">Close</span>
					<svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
			<div class="p-6 overflow-y-auto flex-1">
				<div class="mb-4 bg-yellow-50 border border-yellow-200 rounded-md p-4">
					<div class="flex">
						<svg class="h-5 w-5 text-yellow-400 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
							/>
						</svg>
						<div class="ml-3">
							<p class="text-sm text-yellow-800">
								<strong>Warning:</strong> Changing the matter will delete all currently imported Clio documents and import documents from the new matter.
							</p>
						</div>
					</div>
				</div>

				<ClioMatterSearch
					{caseId}
					createMode={false}
					onMatterSelected={handleMatterSelection}
				/>
			</div>
		</div>
	</div>
{/if}

<!-- Confirmation Dialogs -->
<ConfirmDialog
	bind:open={showUnlinkConfirm}
	title="Remove Clio Link"
	message="Are you sure you want to completely remove the Clio link? This will delete all imported communications, notes, and documents from this case."
	confirmText="Remove Link"
	variant="danger"
	loading={unlinking}
	onConfirm={handleUnlink}
/>

<ConfirmDialog
	bind:open={showChangeMatterConfirm}
	title="Change Clio Matter"
	message={`Replace current matter "${matterData.display_number} - ${matterData.client_name}" with new matter? This will delete all old Clio documents and import documents from the new matter.`}
	confirmText="Change Matter"
	variant="warning"
	loading={changingMatter}
	onConfirm={confirmChangeMatter}
/>
