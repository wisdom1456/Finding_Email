<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import ClioMatterSearch from '$lib/components/ClioMatterSearch.svelte';
	import ProgressIndicator from '$lib/components/ProgressIndicator.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
	import LoadingOverlay from '$lib/components/ui/LoadingOverlay.svelte';
	import { clioStore } from '$lib/stores/clioStore';
	import { toastStore } from '$lib/stores/toastStore';
	import { getApiUrl } from '$lib/config';
	import { AlertTriangle, Info, ArrowLeft } from 'lucide-svelte';

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

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/cases`, {
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
	<title>Create New Case | Bernhardt Riley</title>
</svelte:head>

<div class="space-y-6">
	<!-- Header -->
	<PageHeader
		title="Create New Case"
		subtitle={$clioStore.connected && !showManualForm
			? 'Search for a Clio matter to automatically populate case details and documents'
			: 'Enter case details manually'}
		breadcrumbs={[
			{ label: 'Dashboard', href: '/app' },
			{ label: 'Cases', href: '/app/cases' },
			{ label: 'New Case' }
		]}
	/>

	{#if error && !partialCaseId}
		<div class="bg-red-50 border border-red-200 rounded-lg p-4">
			<div class="flex">
				<AlertTriangle class="h-5 w-5 text-red-400 flex-shrink-0" />
				<div class="ml-3">
					<h3 class="text-sm font-medium text-red-800">Error Creating Case</h3>
					<p class="mt-1 text-sm text-red-700">{error}</p>
				</div>
			</div>
		</div>
	{/if}

	{#if partialCaseId}
		<!-- Partial Success / Error Recovery UI -->
		<div class="bg-amber-50 border border-amber-200 rounded-lg p-6">
			<div class="flex items-start">
				<AlertTriangle class="h-6 w-6 text-amber-500 mt-0.5 flex-shrink-0" />
				<div class="ml-4 flex-1">
					<h3 class="text-sm font-semibold text-amber-800">Import Error</h3>
					<div class="mt-2 text-sm text-amber-700">
						<p>Case was created successfully, but document import encountered errors:</p>
						<p class="mt-1 font-mono text-xs bg-amber-100 p-2 rounded">{error}</p>
					</div>
					<div class="mt-4 flex space-x-3">
						<button
							onclick={viewPartialCase}
							class="px-4 py-2 rounded-md text-sm font-medium text-amber-700 bg-white border border-amber-300 hover:bg-amber-50 transition-colors"
						>
							View Case Anyway
						</button>
						<button
							onclick={() => goto('/app/cases/new')}
							class="px-4 py-2 rounded-md text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 transition-colors"
						>
							Start Over
						</button>
					</div>
				</div>
			</div>
		</div>
	{:else if isCreating}
		<!-- Progress Indicator -->
		<div class="bg-white shadow-card rounded-lg p-6">
			<h2 class="text-lg font-heading font-semibold text-contrast mb-4">Creating Case from Clio Matter</h2>
			
			{#if progressSteps.length > 0}
				<ProgressIndicator steps={progressSteps} showPercentage={false} />
			{:else}
				<div class="flex items-center space-x-3">
					<div class="animate-spin rounded-full h-5 w-5 border-2 border-accent border-t-transparent"></div>
					<p class="text-sm text-gray-600">Initializing...</p>
				</div>
			{/if}

			<div class="mt-6 p-4 bg-contrast-light/5 border border-contrast-light/20 rounded-lg">
				<p class="text-sm text-contrast-light">
					<strong>Please wait.</strong> Do not close this window. Case creation and document import may take a few moments.
				</p>
			</div>
		</div>
	{:else if !showManualForm && $clioStore.connected}
		<!-- Clio Search (Default State) -->
		<div class="bg-white shadow-card rounded-lg p-6">
			<h2 class="text-lg font-heading font-semibold text-contrast mb-2">Find Your Clio Matter</h2>
			<p class="text-sm text-gray-500 mb-6">
				Search for the matter associated with this case. We'll automatically populate the case details and import all documents.
			</p>

			<ClioMatterSearch
				createMode={true}
				onCaseCreated={handleCaseCreatedFromClio}
			/>

			<div class="mt-8 pt-6 border-t border-gray-100">
				<button
					onclick={() => (showManualForm = true)}
					class="text-sm text-accent hover:text-accent-hover transition-colors"
				>
					Create case manually without Clio
				</button>
			</div>
		</div>
	{:else}
		<!-- Manual Case Creation Form -->
		<div class="bg-white shadow-card rounded-lg p-6">
			<h2 class="text-lg font-heading font-semibold text-contrast mb-6">Manual Case Creation</h2>

			<form onsubmit={(e) => { e.preventDefault(); createManualCase(); }} class="space-y-5">
				<div>
					<label for="client_name" class="block text-sm font-medium text-contrast mb-1">
						Client Name <span class="text-red-500">*</span>
					</label>
					<input
						type="text"
						id="client_name"
						bind:value={clientName}
						required
						class="block w-full px-3 py-2.5 border border-gray-300 rounded-md text-contrast placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
						placeholder="John Doe"
					/>
				</div>

				<div>
					<label for="reference_number" class="block text-sm font-medium text-contrast mb-1">
						Reference Number
					</label>
					<input
						type="text"
						id="reference_number"
						bind:value={referenceNumber}
						class="block w-full px-3 py-2.5 border border-gray-300 rounded-md text-contrast placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors"
						placeholder="2024-001"
					/>
				</div>

				<div>
					<label for="description" class="block text-sm font-medium text-contrast mb-1">
						Description
					</label>
					<textarea
						id="description"
						bind:value={description}
						rows="3"
						class="block w-full px-3 py-2.5 border border-gray-300 rounded-md text-contrast placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-colors resize-none"
						placeholder="Brief description of the case..."
					></textarea>
				</div>

				<div class="flex items-center justify-between pt-4">
					{#if $clioStore.connected}
						<button
							type="button"
							onclick={() => (showManualForm = false)}
							class="inline-flex items-center text-sm text-gray-600 hover:text-gray-800 transition-colors"
						>
							<ArrowLeft class="h-4 w-4 mr-1" />
							Back to Clio Search
						</button>
				{:else}
					<div></div>
				{/if}
				<AsyncButton
					type="submit"
					disabled={!clientName.trim()}
					loading={isCreating}
					variant="primary"
					loadingText="Creating..."
				>
					Create Case
				</AsyncButton>
			</div>
			</form>
		</div>
	{/if}

	{#if !$clioStore.connected && !showManualForm}
		<!-- Not Connected to Clio -->
		<div class="bg-contrast-light/5 border border-contrast-light/20 rounded-lg p-6">
			<div class="flex">
				<Info class="h-5 w-5 text-contrast-light flex-shrink-0" />
				<div class="ml-4 flex-1">
					<h3 class="text-sm font-semibold text-contrast-light">Clio Not Connected</h3>
					<p class="mt-1 text-sm text-gray-600">
						Connect to Clio to search for matters and automatically import case details. You can still create cases manually.
					</p>
					<div class="mt-4">
						<button
							onclick={() => (showManualForm = true)}
							class="px-4 py-2 rounded-md text-sm font-medium text-white bg-accent hover:bg-accent-hover transition-colors"
						>
							Create Manual Case
						</button>
					</div>
				</div>
			</div>
		</div>
	{/if}
</div>

<!-- Clio Import Loading Overlay -->
<LoadingOverlay
	show={isCreating}
	message="Creating Case from Clio"
	description={progressSteps.length > 0 
		? progressSteps.find(s => s.status === 'processing')?.label || 'Setting up your case...'
		: 'Importing matter details and documents from Clio. This may take a few minutes...'}
/>
