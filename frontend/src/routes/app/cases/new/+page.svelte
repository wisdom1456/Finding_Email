<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import ClioMatterSearch from '$lib/components/ClioMatterSearch.svelte';
	import ProgressIndicator from '$lib/components/ProgressIndicator.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { clioStore } from '$lib/stores/clioStore';

	interface ProgressStep {
		label: string;
		status: 'pending' | 'processing' | 'completed' | 'error';
		progress?: number;
		detail?: string;
	}

	let isCreating = $state(false);
	let showManualForm = $state(false);
	let error = $state<string | null>(null);
	let progressSteps = $state<ProgressStep[]>([]);
	let partialCaseId = $state<string | null>(null);

	// Manual form fields
	let clientName = $state('');
	let referenceNumber = $state('');
	let description = $state('');

	async function handleCaseCreatedFromClio(result: { caseId: string; success: boolean; error?: string }) {
		console.log('Case created from Clio:', result);
		
		if (result.success) {
			// Redirect to the new case detail page
			await goto(`/app/cases/${result.caseId}`);
		} else {
			// Handle partial success or error
			if (result.caseId) {
				// Case was created but import failed
				partialCaseId = result.caseId;
				error = result.error || 'Document import failed';
			} else {
				error = result.error || 'Failed to create case';
			}
		}
	}

	async function createManualCase() {
		if (!clientName.trim()) {
			error = 'Client name is required';
			return;
		}

		isCreating = true;
		error = null;

		try {
			const token = localStorage.getItem('supabase_access_token');
			if (!token) {
				throw new Error('Not authenticated');
			}

			const PUBLIC_API_URL = import.meta.env.PUBLIC_API_URL || 'http://127.0.0.1:8000';
			const response = await fetch(`${PUBLIC_API_URL}/api/cases`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${token}`
				},
				body: JSON.stringify({
					client_name: clientName,
					reference_number: referenceNumber || null,
					description: description || null
				})
			});

			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || 'Failed to create case');
			}

			const newCase = await response.json();
			await goto(`/app/cases/${newCase.id}`);
		} catch (err: any) {
			console.error('Error creating manual case:', err);
			error = err.message || 'Failed to create case';
		} finally {
			isCreating = false;
		}
	}

	function viewPartialCase() {
		if (partialCaseId) {
			goto(`/app/cases/${partialCaseId}`);
		}
	}

	// Prevent navigation during creation
	onMount(() => {
		const handleBeforeUnload = (e: BeforeUnloadEvent) => {
			if (isCreating) {
				e.preventDefault();
				e.returnValue = '';
				return '';
			}
		};

		window.addEventListener('beforeunload', handleBeforeUnload);

		return () => {
			window.removeEventListener('beforeunload', handleBeforeUnload);
		};
	});
</script>

<svelte:head>
	<title>Create New Case | Legal Portal</title>
</svelte:head>

<div class="space-y-6">
	<!-- Header -->
	<PageHeader
		title="Create New Case"
		subtitle="{$clioStore.connected && !showManualForm
			? 'Search for a Clio matter to automatically populate case details and documents'
			: 'Enter case details manually'}"
		breadcrumbs={[
			{ label: 'Dashboard', href: '/app' },
			{ label: 'Cases', href: '/app/cases' },
			{ label: 'New Case' }
		]}
	/>

		{#if error && !partialCaseId}
			<div class="mb-6 bg-red-50 border border-red-200 rounded-md p-4">
				<div class="flex">
					<svg class="h-5 w-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
						/>
					</svg>
					<div class="ml-3">
						<h3 class="text-sm font-medium text-red-800">Error Creating Case</h3>
						<p class="mt-1 text-sm text-red-700">{error}</p>
					</div>
				</div>
			</div>
		{/if}

		{#if partialCaseId}
			<!-- Partial Success / Error Recovery UI -->
			<div class="bg-yellow-50 border border-yellow-200 rounded-lg p-6 mb-6">
				<div class="flex items-start">
					<svg class="h-6 w-6 text-yellow-400 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
						/>
					</svg>
					<div class="ml-3 flex-1">
						<h3 class="text-sm font-medium text-yellow-800">Import Error</h3>
						<div class="mt-2 text-sm text-yellow-700">
							<p>Case was created successfully, but document import encountered errors:</p>
							<p class="mt-1 font-mono text-xs">{error}</p>
						</div>
						<div class="mt-4 flex space-x-3">
							<button
								onclick={viewPartialCase}
								class="px-4 py-2 border border-yellow-600 rounded-md text-sm font-medium text-yellow-700 bg-white hover:bg-yellow-50"
							>
								View Case Anyway
							</button>
							<button
								onclick={() => goto('/app/cases/new')}
								class="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
							>
								Start Over
							</button>
						</div>
					</div>
				</div>
			</div>
		{:else if isCreating}
			<!-- Progress Indicator -->
			<div class="bg-white shadow rounded-lg p-6">
				<h2 class="text-lg font-medium text-gray-900 mb-4">Creating Case from Clio Matter</h2>
				
				{#if progressSteps.length > 0}
					<ProgressIndicator steps={progressSteps} showPercentage={false} />
				{:else}
					<div class="flex items-center space-x-3">
						<svg class="animate-spin h-5 w-5 text-blue-600" fill="none" viewBox="0 0 24 24">
							<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
							<path
								class="opacity-75"
								fill="currentColor"
								d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
							></path>
						</svg>
						<p class="text-sm text-gray-600">Initializing...</p>
					</div>
				{/if}

				<div class="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-md">
					<p class="text-sm text-blue-800">
						<strong>Please wait.</strong> Do not close this window. Case creation and document import may take a few moments.
					</p>
				</div>
			</div>
		{:else if !showManualForm && $clioStore.connected}
			<!-- Clio Search (Default State) -->
			<div class="bg-white shadow rounded-lg p-6">
				<h2 class="text-lg font-medium text-gray-900 mb-2">Find Your Clio Matter</h2>
				<p class="text-sm text-gray-600 mb-4">
					Search for the matter associated with this case. We'll automatically populate the case details and import all documents.
				</p>

				<ClioMatterSearch
					createMode={true}
					onCaseCreated={handleCaseCreatedFromClio}
				/>

				<div class="mt-6 pt-6 border-t border-gray-200">
					<button
						onclick={() => (showManualForm = true)}
						class="text-sm text-blue-600 hover:text-blue-800 hover:underline"
					>
						Create case manually without Clio
					</button>
				</div>
			</div>
		{:else}
			<!-- Manual Case Creation Form -->
			<div class="bg-white shadow rounded-lg p-6">
				<h2 class="text-lg font-medium text-gray-900 mb-4">Manual Case Creation</h2>

				<form onsubmit={(e) => { e.preventDefault(); createManualCase(); }} class="space-y-4">
					<div>
						<label for="client_name" class="block text-sm font-medium text-gray-700">
							Client Name <span class="text-red-500">*</span>
						</label>
						<input
							type="text"
							id="client_name"
							bind:value={clientName}
							required
							class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm px-3 py-2 border"
							placeholder="John Doe"
						/>
					</div>

					<div>
						<label for="reference_number" class="block text-sm font-medium text-gray-700">
							Reference Number
						</label>
						<input
							type="text"
							id="reference_number"
							bind:value={referenceNumber}
							class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm px-3 py-2 border"
							placeholder="2024-001"
						/>
					</div>

					<div>
						<label for="description" class="block text-sm font-medium text-gray-700">
							Description
						</label>
						<textarea
							id="description"
							bind:value={description}
							rows="3"
							class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm px-3 py-2 border"
							placeholder="Brief description of the case..."
						></textarea>
					</div>

					<div class="flex items-center justify-between pt-4">
						{#if $clioStore.connected}
							<button
								type="button"
								onclick={() => (showManualForm = false)}
								class="text-sm text-gray-600 hover:text-gray-800 hover:underline"
							>
								← Back to Clio Search
							</button>
						{:else}
							<div></div>
						{/if}
						<button
							type="submit"
							disabled={isCreating || !clientName.trim()}
							class="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
						>
							{isCreating ? 'Creating...' : 'Create Case'}
						</button>
					</div>
				</form>
			</div>
		{/if}

	{#if !$clioStore.connected && !showManualForm}
		<!-- Not Connected to Clio -->
		<div class="bg-blue-50 border border-blue-200 rounded-lg p-6">
			<div class="flex">
				<svg class="h-5 w-5 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
					/>
				</svg>
				<div class="ml-3 flex-1">
					<h3 class="text-sm font-medium text-blue-800">Clio Not Connected</h3>
					<p class="mt-1 text-sm text-blue-700">
						Connect to Clio to search for matters and automatically import case details. You can still create cases manually.
					</p>
					<div class="mt-4">
						<button
							onclick={() => (showManualForm = true)}
							class="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700"
						>
							Create Manual Case
						</button>
					</div>
				</div>
			</div>
		</div>
	{/if}
</div>
