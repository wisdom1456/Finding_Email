<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase } from '$lib/supabase';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { Plus } from 'lucide-svelte';

	let cases = $state<any[]>([]);
	let filteredCases = $state<any[]>([]);
	let loading = $state(true);
	let errorMessage = $state('');
	let showOnlyClioCases = $state(false);

	$effect(() => {
		if (showOnlyClioCases) {
			filteredCases = cases.filter(c => c.clio_matter_id);
		} else {
			filteredCases = cases;
		}
	});

	onMount(async () => {
		await loadCases();
	});

	async function loadCases() {
		loading = true;
		errorMessage = '';

		try {
			const { data: casesData, error } = await supabase
				.from('cases')
				.select('*')
				.order('created_at', { ascending: false });

			if (error) throw error;

			cases = casesData || [];
			filteredCases = casesData || [];
		} catch (error: any) {
			errorMessage = error.message || 'Failed to load cases';
		} finally {
			loading = false;
		}
	}

	function formatDate(dateString: string) {
		return new Date(dateString).toLocaleDateString('en-US', {
			year: 'numeric',
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function getStatusColor(status: string) {
		switch (status) {
			case 'completed':
				return 'bg-green-100 text-green-800';
			case 'processing':
				return 'bg-blue-100 text-blue-800';
			case 'error':
				return 'bg-red-100 text-red-800';
			default:
				return 'bg-gray-100 text-gray-800';
		}
	}

	function getClioMatterNumber(caseItem: any): string | null {
		return caseItem.clio_matter_data?.display_number || caseItem.reference_number || null;
	}

	function hasClioMatter(caseItem: any): boolean {
		return Boolean(caseItem.clio_matter_id);
	}

	const clioCount = $derived(cases.filter(c => c.clio_matter_id).length);
</script>

<div class="space-y-6">
	<!-- Header -->
	<PageHeader
		title="All Cases"
		subtitle="{cases.length} total case{cases.length !== 1 ? 's' : ''}{clioCount > 0 ? ` • ${clioCount} linked to Clio` : ''}"
		breadcrumbs={[
			{ label: 'Dashboard', href: '/app' },
			{ label: 'Cases' }
		]}
	>
		{#snippet children()}
			<a
				href="/app/cases/new"
				class="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
			>
				<Plus class="h-5 w-5 mr-2" />
				New Case
			</a>
		{/snippet}
	</PageHeader>

	<!-- Filter Toggle -->
	{#if clioCount > 0}
		<div class="flex items-center space-x-2 bg-white px-4 py-3 rounded-lg shadow-sm border border-gray-200">
			<label class="flex items-center cursor-pointer">
				<input
					type="checkbox"
					bind:checked={showOnlyClioCases}
					class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
				/>
				<span class="ml-2 text-sm text-gray-700">Show only Clio cases</span>
			</label>
			{#if showOnlyClioCases}
				<span class="text-sm text-gray-500">
					({filteredCases.length} of {cases.length})
				</span>
			{/if}
		</div>
	{/if}

	<!-- Cases List -->
	<div class="bg-white shadow rounded-lg">
		{#if loading}
			<div class="p-8 text-center">
				<div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
				<p class="mt-2 text-sm text-gray-500">Loading cases...</p>
			</div>
		{:else if errorMessage}
			<div class="p-8 text-center">
				<p class="text-sm text-red-600">{errorMessage}</p>
			</div>
		{:else if filteredCases.length === 0}
			<div class="p-8 text-center">
				{#if showOnlyClioCases && cases.length > 0}
					<p class="text-sm text-gray-500">No Clio cases found.</p>
					<button
						onclick={() => (showOnlyClioCases = false)}
						class="mt-4 text-sm text-blue-600 hover:text-blue-800 hover:underline"
					>
						Show all cases
					</button>
				{:else}
					<p class="text-sm text-gray-500">No cases yet. Create your first case to get started.</p>
					<a
						href="/app/cases/new"
						class="mt-4 inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-blue-700 bg-blue-100 hover:bg-blue-200"
					>
						Create Case
					</a>
				{/if}
			</div>
		{:else}
			<ul class="divide-y divide-gray-200">
				{#each filteredCases as caseItem}
					<li class="{hasClioMatter(caseItem) ? 'border-l-4 border-blue-500' : ''}">
						<a
							href="/app/cases/{caseItem.id}"
							class="block hover:bg-gray-50 transition duration-150"
						>
							<div class="px-4 py-4 sm:px-6">
								<div class="flex items-start justify-between">
									<div class="flex-1 min-w-0">
										<div class="flex items-center gap-2 mb-1">
											{#if hasClioMatter(caseItem)}
												<svg
													class="h-5 w-5 text-blue-600 flex-shrink-0"
													fill="none"
													viewBox="0 0 24 24"
													stroke="currentColor"
													title="Linked to Clio Matter"
												>
													<path
														stroke-linecap="round"
														stroke-linejoin="round"
														stroke-width="2"
														d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
													/>
												</svg>
											{/if}
											<p class="text-lg font-semibold text-gray-900 truncate">
												{caseItem.client_name}
											</p>
										</div>
										{#if getClioMatterNumber(caseItem)}
											<p class="text-sm text-gray-600 font-medium">
												#{getClioMatterNumber(caseItem)}
												{#if caseItem.clio_matter_data?.practice_area}
													• {caseItem.clio_matter_data.practice_area}
												{/if}
											</p>
										{/if}
										{#if caseItem.description}
											<p class="mt-1 text-sm text-gray-600 line-clamp-2">
												{caseItem.description}
											</p>
										{/if}

										<!-- Stats Row -->
										<div class="mt-2 flex items-center space-x-4 text-xs text-gray-500">
											{#if caseItem.clio_matter_data}
												{@const totalDocs = (caseItem.clio_matter_data.communications_count || 0) + 
													(caseItem.clio_matter_data.notes_count || 0) + 
													(caseItem.clio_matter_data.documents_count || 0)}
												{#if totalDocs > 0}
													<span class="flex items-center">
														<svg class="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
															<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
														</svg>
														{totalDocs} document{totalDocs !== 1 ? 's' : ''}
													</span>
												{/if}
											{/if}
											
											{#if hasClioMatter(caseItem)}
												<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
													Linked to Clio
												</span>
											{:else}
												<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
													Manual Case
												</span>
											{/if}
										</div>
									</div>
									<div class="ml-2 flex-shrink-0 flex flex-col items-end space-y-2">
										<span
											class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full {getStatusColor(
												caseItem.status
											)}"
										>
											{caseItem.status}
										</span>
									</div>
								</div>
								<div class="mt-2 flex items-center text-xs text-gray-500">
									<span>Created {formatDate(caseItem.created_at)}</span>
								</div>
							</div>
						</a>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</div>
