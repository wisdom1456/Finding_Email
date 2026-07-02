<script lang="ts">
	import { onDestroy } from 'svelte';
	import { get } from 'svelte/store';
	import { getApiUrl } from '$lib/config';
	import { getSecureSession } from '$lib/supabase';
	import { progressStore } from '$lib/stores/progressStore';
	import ClioImportProgressModal from './ClioImportProgressModal.svelte';
	import ConfirmDialog from './ui/ConfirmDialog.svelte';
	
	let { 
		caseId, 
		createMode = false,
		onMatterSelected,
		onCaseCreated
	} = $props<{
		caseId?: string;
		createMode?: boolean;
		onMatterSelected?: (matterId: number) => void;
		onCaseCreated?: (result: { caseId: string; success: boolean; error?: string }) => void;
	}>();
	
	let createdCaseId = $state<string | null>(null);
	let importResult = $state<any>(null);
	
	onDestroy(() => {
		// Clean up SSE connection if active
		progressStore.disconnect();
	});

	let searchQuery = $state('');
	let searching = $state(false);
	let importingMatterId = $state<number | null>(null);
	let matters = $state<any[]>([]);
	let errorMessage = $state('');
	let selectedMatterId = $state<number | null>(null);
	let importSuccess = $state(false);
	
	// Modal state for progress feedback
	let showImportModal = $state(false);
	let importPhase = $state<'creating' | 'importing' | 'analyzing' | 'complete' | 'error'>('creating');
	let importError = $state<string | null>(null);
	let currentMatterName = $state<string>('');

	async function searchMatters() {
		if (searchQuery.length < 3) {
			errorMessage = 'Please enter at least 3 characters';
			return;
		}

		searching = true;
		errorMessage = '';
		matters = [];

		try {
			const { session, user } = await getSecureSession();

			if (!session || !user) {
				throw new Error('Not authenticated');
			}

			const apiUrl = getApiUrl();
			const response = await fetch(
				`${apiUrl}/api/clio/search-matters?query=${encodeURIComponent(searchQuery)}&limit=20`,
				{
					headers: {
						Authorization: `Bearer ${session.access_token}`
					}
				}
			);

			if (!response.ok) {
				const error = await response.json();
				throw new Error(error.detail || 'Failed to search matters');
			}

			matters = await response.json();

			if (matters.length === 0) {
				errorMessage = 'No matters found matching your search';
			}
		} catch (error: any) {
			errorMessage = error.message || 'Failed to search matters';
		} finally {
			searching = false;
		}
	}

	async function handleMatterAction(matterId: number) {
		if (createMode) {
			await createCaseFromMatter(matterId);
		} else {
			await importMatter(matterId);
		}
	}

	let showCreateConfirm = $state(false);
	let pendingCreateMatterId = $state<number | null>(null);
	let showImportConfirm = $state(false);
	let pendingImportMatterId = $state<number | null>(null);

	function createCaseFromMatter(matterId: number) {
		// Find the matter to get its name
		const matter = matters.find(m => m.id === matterId);
		currentMatterName = matter ? `${matter.display_number} - ${matter.client_name}` : 'Clio Matter';
		pendingCreateMatterId = matterId;
		showCreateConfirm = true;
	}

	async function confirmCreateCaseFromMatter() {
		const matterId = pendingCreateMatterId;
		if (matterId === null) return;
		pendingCreateMatterId = null;

		importingMatterId = matterId;
		showImportModal = true;
		importPhase = 'creating';
		importError = null;
		errorMessage = '';
		importSuccess = false;

		try {
			const { session, user } = await getSecureSession();

			if (!session || !user) {
				throw new Error('Not authenticated');
			}

			// Use simple POST endpoint
			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/cases/create-from-clio`, {
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

			const result = await response.json();

			if (!response.ok) {
				throw new Error(result.detail || 'Failed to create case');
			}

			// Store result data
			selectedMatterId = matterId;
			createdCaseId = result.case_id;
			// importResult is usually null here because we run in background now
			// We will update it when SSE completes
			
			// Start SSE for import progress if import_id is returned
			if (result.import_id) {
				// Token is sent via Authorization header — never in the URL
				const sseUrl = `${apiUrl}/api/progress/clio-import/${result.import_id}`;
				const statusUrl = `${apiUrl}/api/progress/clio-import/${result.import_id}/status`;

				// Keep phase as 'creating' or 'importing' until SSE starts
				importPhase = 'importing';

				// Fire-and-forget: start the import via StreamingResponse endpoint.
				// On Vercel, BackgroundTasks get killed — this endpoint runs the import
				// inline with heartbeats to keep the function alive.
				// On local dev, BackgroundTask handles it, so this is a no-op safety net.
				fetch(`${apiUrl}/api/cases/${result.case_id}/run-import`, {
					method: 'POST',
					headers: {
						'Content-Type': 'application/json',
						Authorization: `Bearer ${session.access_token}`,
					},
					body: JSON.stringify({ import_id: result.import_id }),
				}).catch((err) => console.warn('run-import fire-and-forget error:', err));

				progressStore.connect(
					sseUrl,
					(data: any) => {
						if (data && data.import_status) {
							importResult = data.import_status;
						}

						const finalProgress = get(progressStore);
						const importFailed =
							finalProgress.status === 'error' || data?.import_status?.success === false;

						if (importFailed) {
							importPhase = 'error';
							importSuccess = false;
							importError =
								data?.import_status?.error ||
								finalProgress.error ||
								'Clio import failed before any documents could be saved.';
							errorMessage = importError ?? 'Clio import failed before any documents could be saved.';
							return;
						}

						// On successful completion, update UI with stats
						importPhase = 'complete';
						importSuccess = true;
					},
					statusUrl,  // Polling fallback URL
					session.access_token  // Auth token
				);
			} else {
				// No SSE available (legacy path?), mark as complete immediately
				importPhase = 'complete';
				importSuccess = true;
				importResult = result.import_status;
			}
			
			// Clear search results
			searchQuery = '';
			matters = [];
			
			// DON'T call parent callback immediately - let modal handle it
		} catch (error: any) {
			importPhase = 'error';
			importError = error.message || 'Failed to create case';
			errorMessage = error.message || 'Failed to create case';
		} finally {
			importingMatterId = null;
		}
	}
	
	function closeModalAndRedirect() {
		showImportModal = false;
		
		// Now notify parent to redirect
		if (createdCaseId && onCaseCreated) {
			onCaseCreated({
				caseId: createdCaseId,
				success: true
			});
		}
	}
	
	function closeModalWithError() {
		showImportModal = false;
		importingMatterId = null;
		
		// Notify parent of error
		if (onCaseCreated) {
			onCaseCreated({
				caseId: '',
				success: false,
				error: importError || 'Unknown error'
			});
		}
	}
	

	function importMatter(matterId: number) {
		if (!caseId) {
			errorMessage = 'Case ID is required for import';
			return;
		}
		pendingImportMatterId = matterId;
		showImportConfirm = true;
	}

	async function confirmImportMatter() {
		const matterId = pendingImportMatterId;
		if (matterId === null) return;
		pendingImportMatterId = null;

		importingMatterId = matterId;
		errorMessage = '';
		importSuccess = false;

		try {
			const { session, user } = await getSecureSession();

			if (!session || !user) {
				throw new Error('Not authenticated');
			}

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/clio/import`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`
				},
				body: JSON.stringify({
					matter_id: matterId,
					case_id: caseId
				})
			});

			if (!response.ok) {
				const error = await response.json();
				throw new Error(error.detail || 'Failed to import matter');
			}

			const result = await response.json();
			
			// If import_id is returned, connect to SSE stream
			if (result.import_id) {
				// Token sent via Authorization header (not in URL) for security
				const sseUrl = `${apiUrl}/api/progress/clio-import/${result.import_id}`;
				const statusUrl = `${apiUrl}/api/progress/clio-import/${result.import_id}/status`;

				progressStore.connect(
					sseUrl,
					(data: any) => {
						const finalProgress = get(progressStore);
						const importFailed =
							finalProgress.status === 'error' || data?.import_status?.success === false;

						if (importFailed) {
							importSuccess = false;
							errorMessage =
								data?.import_status?.error ||
								finalProgress.error ||
								'Clio import failed before any documents could be saved.';
							importingMatterId = null;
							return;
						}

						// On successful completion
						importSuccess = true;
						selectedMatterId = matterId;
						importingMatterId = null;
					},
					statusUrl,  // Polling fallback URL
					session.access_token  // Auth token
				);
			} else {
				// No import_id, mark as success immediately
				importSuccess = true;
				selectedMatterId = matterId;
			}

			// Clear search results after successful import
			searchQuery = '';
			matters = [];

			// Call callback immediately to refresh parent component
			if (onMatterSelected) {
				onMatterSelected(matterId);
			}
		} catch (error: any) {
			errorMessage = error.message || 'Failed to import matter';
		} finally {
			importingMatterId = null;
		}
	}

	function formatDate(dateString: string | null) {
		if (!dateString) return 'N/A';
		return new Date(dateString).toLocaleDateString('en-US', {
			year: 'numeric',
			month: 'short',
			day: 'numeric'
		});
	}
</script>

<!-- Import Progress Modal -->
<ClioImportProgressModal
	bind:show={showImportModal}
	caseId={createdCaseId || undefined}
	importResult={importResult}
	onClose={closeModalAndRedirect}
/>

<!-- Create-case Confirmation -->
<ConfirmDialog
	bind:open={showCreateConfirm}
	title="Create Case from Clio"
	message={`Create a new case from ${currentMatterName}? All documents will be imported automatically.`}
	confirmText="Create Case"
	variant="info"
	onConfirm={confirmCreateCaseFromMatter}
	onCancel={() => (pendingCreateMatterId = null)}
/>

<!-- Import Confirmation -->
<ConfirmDialog
	bind:open={showImportConfirm}
	title="Import from Clio"
	message="Import communications, notes, and documents from this Clio matter?"
	confirmText="Import"
	variant="info"
	onConfirm={confirmImportMatter}
	onCancel={() => (pendingImportMatterId = null)}
/>

<div class="space-y-4">
	<form
		onsubmit={(e) => {
			e.preventDefault();
			searchMatters();
		}}
		class="space-y-4"
	>
		<div>
			<label for="search-query" class="block text-sm font-semibold text-contrast mb-1">
				Client Name or Matter Number
			</label>
			<div class="mt-1 flex rounded-md shadow-sm">
				<input
					id="search-query"
					type="text"
					bind:value={searchQuery}
					placeholder="Enter at least 3 characters..."
					class="flex-1 min-w-0 block w-full px-3 py-2.5 rounded-l-md border border-gray-300 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent sm:text-sm text-contrast"
				/>
				<button
					type="submit"
					disabled={searching || searchQuery.length < 3}
					class="inline-flex items-center px-4 py-2 border border-l-0 border-gray-300 text-sm font-semibold rounded-r-md text-gray-700 bg-gray-50 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
				>
					{#if searching}
						<svg
							class="animate-spin h-5 w-5"
							fill="none"
							stroke="currentColor"
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
					{:else}
						<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
							/>
						</svg>
					{/if}
					<span class="ml-2">{searching ? 'Searching...' : 'Search'}</span>
				</button>
			</div>
		</div>
	</form>

	{#if importSuccess}
		<div class="rounded-md bg-green-50 p-4">
			<div class="flex">
				<div class="flex-shrink-0">
					<svg class="h-5 w-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
						<path
							fill-rule="evenodd"
							d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
							clip-rule="evenodd"
						/>
					</svg>
				</div>
				<div class="ml-3">
					<p class="text-sm font-medium text-green-800">
						{createMode ? 'Case created successfully!' : 'Matter imported successfully!'}
					</p>
				</div>
			</div>
		</div>
	{/if}

	{#if errorMessage}
		<div class="rounded-md bg-red-50 p-4">
			<p class="text-sm text-red-800">{errorMessage}</p>
		</div>
	{/if}

	{#if matters.length > 0}
		<div>
			<h4 class="text-sm font-bold text-contrast mb-3">Search Results ({matters.length})</h4>
			<ul class="divide-y divide-gray-100 border border-gray-200 rounded-lg overflow-hidden bg-white shadow-sm">
				{#each matters as matter}
					<li class="p-4 hover:bg-gray-50 transition-colors">
						<div class="flex items-start justify-between">
							<div class="flex-1 min-w-0">
								<div class="flex items-center space-x-2">
									<p class="text-sm font-bold text-accent">{matter.display_number}</p>
									{#if selectedMatterId === matter.id}
										<span
											class="px-2 py-0.5 text-[10px] font-bold tracking-wider rounded-full bg-green-100 text-green-800 uppercase"
										>
											{createMode ? 'Created' : 'Imported'}
										</span>
									{/if}
								</div>
								<p class="text-sm font-bold text-contrast mt-1">{matter.client_name}</p>
								{#if matter.description}
									<p class="text-xs text-gray-500 mt-1 line-clamp-2 italic">{matter.description}</p>
								{/if}
								<div class="mt-2 flex items-center space-x-4 text-[10px] font-medium text-gray-400 uppercase tracking-wide">
									{#if matter.practice_area}
										<span class="flex items-center">
											<svg
												class="h-3 w-3 mr-1"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
												/>
											</svg>
											{matter.practice_area}
										</span>
									{/if}
									<span>{matter.status}</span>
									<span>Opened: {formatDate(matter.open_date)}</span>
								</div>
							</div>
						<div class="ml-4 flex flex-col items-end">
						<button
							onclick={() => handleMatterAction(matter.id)}
							disabled={importingMatterId === matter.id || selectedMatterId === matter.id}
								class="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-bold rounded-md text-white bg-accent hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent disabled:opacity-50 disabled:cursor-not-allowed shadow-sm transition-all"
						>
							{#if importingMatterId === matter.id}
								<svg class="animate-spin -ml-1 mr-2 h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24">
									<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
									<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
								</svg>
								{createMode ? 'Creating...' : 'Importing...'}
							{:else if selectedMatterId === matter.id}
								<svg class="-ml-1 mr-2 h-3.5 w-3.5 text-white" fill="currentColor" viewBox="0 0 20 20">
									<path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"></path>
								</svg>
								{createMode ? 'Created' : 'Imported'}
							{:else}
								{createMode ? 'Create Case' : 'Import'}
							{/if}
						</button>
							
							{#if importingMatterId === matter.id && $progressStore.status === 'active'}
								<div class="mt-2 text-xs text-gray-600 max-w-xs">
									<p>{$progressStore.message}</p>
									{#if $progressStore.percent > 0}
										<div class="mt-1 w-full bg-gray-200 rounded-full h-1.5">
											<div 
												class="bg-accent h-1.5 rounded-full transition-all duration-300"
												style="width: {$progressStore.percent}%"
											></div>
										</div>
									{/if}
									{#if $progressStore.current_doc}
										<p class="mt-1 text-xs text-gray-500 truncate">
											{$progressStore.current_doc.name}
										</p>
									{/if}
								</div>
							{/if}
						</div>
						</div>
					</li>
				{/each}
			</ul>
		</div>
	{/if}
</div>
