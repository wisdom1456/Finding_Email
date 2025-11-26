<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase } from '$lib/supabase';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { Plus, Link2, FileText, Filter } from 'lucide-svelte';

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
				return 'bg-accent/10 text-accent';
			case 'processing':
				return 'bg-contrast-light/10 text-contrast-light';
			case 'error':
				return 'bg-red-100 text-red-700';
			default:
				return 'bg-gray-100 text-gray-700';
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

<svelte:head>
	<title>Cases | Bernhardt Riley</title>
</svelte:head>

<div class="space-y-6">
	<!-- Header -->
	<PageHeader
		title="All Cases"
		subtitle="{cases.length} total case{cases.length !== 1 ? 's' : ''}{clioCount > 0 ? ` · ${clioCount} linked to Clio` : ''}"
		breadcrumbs={[
			{ label: 'Dashboard', href: '/app' },
			{ label: 'Cases' }
		]}
	>
		{#snippet children()}
			<a
				href="/app/cases/new"
				class="inline-flex items-center px-4 py-2 rounded-md text-sm font-medium text-white bg-accent hover:bg-accent-hover transition-colors"
			>
				<Plus class="h-4 w-4 mr-2" />
				New Case
			</a>
		{/snippet}
	</PageHeader>

	<!-- Filter Toggle -->
	{#if clioCount > 0}
		<div class="flex items-center space-x-3 bg-white px-4 py-3 rounded-lg shadow-card">
			<Filter class="h-4 w-4 text-gray-400" />
			<label class="flex items-center cursor-pointer">
				<input
					type="checkbox"
					bind:checked={showOnlyClioCases}
					class="h-4 w-4 text-accent focus:ring-accent border-gray-300 rounded transition-colors"
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
	<div class="bg-white shadow-card rounded-lg">
		{#if loading}
			<div class="p-8 text-center">
				<div class="inline-block animate-spin rounded-full h-8 w-8 border-2 border-accent border-t-transparent"></div>
				<p class="mt-3 text-sm text-gray-500">Loading cases...</p>
			</div>
		{:else if errorMessage}
			<div class="p-8 text-center">
				<p class="text-sm text-red-600">{errorMessage}</p>
			</div>
		{:else if filteredCases.length === 0}
			<div class="p-8 text-center">
				{#if showOnlyClioCases && cases.length > 0}
					<Link2 class="mx-auto h-12 w-12 text-gray-300" />
					<p class="mt-3 text-sm text-gray-500">No Clio cases found.</p>
					<button
						onclick={() => (showOnlyClioCases = false)}
						class="mt-4 text-sm font-medium text-accent hover:text-accent-hover transition-colors"
					>
						Show all cases
					</button>
				{:else}
					<FileText class="mx-auto h-12 w-12 text-gray-300" />
					<p class="mt-3 text-sm text-gray-500">No cases yet. Create your first case to get started.</p>
					<a
						href="/app/cases/new"
						class="mt-4 inline-flex items-center px-4 py-2 text-sm font-medium rounded-md text-accent bg-accent/10 hover:bg-accent/20 transition-colors"
					>
						<Plus class="h-4 w-4 mr-2" />
						Create Case
					</a>
				{/if}
			</div>
		{:else}
			<ul class="divide-y divide-gray-100">
				{#each filteredCases as caseItem}
					<li class="{hasClioMatter(caseItem) ? 'border-l-4 border-accent' : ''}">
						<a
							href="/app/cases/{caseItem.id}"
							class="block hover:bg-gray-50 transition-colors"
						>
							<div class="px-5 py-4">
								<div class="flex items-start justify-between">
									<div class="flex-1 min-w-0">
										<div class="flex items-center gap-2 mb-1">
											{#if hasClioMatter(caseItem)}
												<Link2 class="h-4 w-4 text-accent flex-shrink-0" />
											{/if}
											<p class="text-base font-semibold text-contrast truncate">
												{caseItem.client_name}
											</p>
										</div>
										{#if getClioMatterNumber(caseItem)}
											<p class="text-sm text-gray-600 font-medium">
												#{getClioMatterNumber(caseItem)}
												{#if caseItem.clio_matter_data?.practice_area}
													· {caseItem.clio_matter_data.practice_area}
												{/if}
											</p>
										{/if}
										{#if caseItem.description}
											<p class="mt-1 text-sm text-gray-500 line-clamp-2">
												{caseItem.description}
											</p>
										{/if}

										<!-- Stats Row -->
										<div class="mt-3 flex items-center flex-wrap gap-2 text-xs">
											{#if caseItem.clio_matter_data}
												{@const totalDocs = (caseItem.clio_matter_data.communications_count || 0) + 
													(caseItem.clio_matter_data.notes_count || 0) + 
													(caseItem.clio_matter_data.documents_count || 0)}
												{#if totalDocs > 0}
													<span class="flex items-center text-gray-500">
														<FileText class="h-3.5 w-3.5 mr-1" />
														{totalDocs} document{totalDocs !== 1 ? 's' : ''}
													</span>
												{/if}
											{/if}
											
											{#if hasClioMatter(caseItem)}
												<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-accent/10 text-accent">
													Linked to Clio
												</span>
											{:else}
												<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
													Manual Case
												</span>
											{/if}
										</div>
									</div>
									<div class="ml-4 flex-shrink-0 flex flex-col items-end space-y-2">
										<span
											class="px-2.5 py-0.5 inline-flex text-xs font-medium rounded-full {getStatusColor(caseItem.status)}"
										>
											{caseItem.status}
										</span>
									</div>
								</div>
								<div class="mt-3 text-xs text-gray-400">
									Created {formatDate(caseItem.created_at)}
								</div>
							</div>
						</a>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</div>
