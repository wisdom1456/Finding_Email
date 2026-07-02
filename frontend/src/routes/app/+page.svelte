<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase } from '$lib/supabase';
	import { withRetry } from '$lib/utils/supabaseRetry';
	import Badge from '$lib/components/ui/Badge.svelte';
	import SkeletonList from '$lib/components/ui/SkeletonList.svelte';
	import { FileText, Clock, CheckCircle, Plus } from 'lucide-svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let cases = $state<any[]>([]);
	let loading = $state(true);
	let errorMessage = $state('');

	onMount(async () => {
		await loadCases();
	});

	async function loadCases() {
		loading = true;
		errorMessage = '';

		try {
			const { data: casesData, error } = await withRetry(() =>
				supabase
					.from('cases')
					.select('*')
					.order('created_at', { ascending: false })
					.limit(5)
			);

			if (error) throw error;

			cases = casesData || [];
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
			day: 'numeric'
		});
	}
	
	const totalCases = $derived(cases.length);
	const processingCases = $derived(cases.filter((c) => c.status === 'processing').length);
	const completedCases = $derived(cases.filter((c) => c.status === 'completed').length);
</script>

<svelte:head>
	<title>Dashboard | Bernhardt Riley</title>
</svelte:head>

<div class="page-spacing">
	<!-- Header -->
	<div class="overflow-hidden rounded-2xl bg-gradient-to-br from-accent/5 via-transparent to-contrast/5 border border-accent/10 p-6 mb-6">
		<div class="md:flex md:items-center md:justify-between">
			<div class="flex-1 min-w-0">
				<h1 class="text-2xl font-heading font-bold text-contrast sm:text-3xl">
					Dashboard
				</h1>
				<p class="mt-1 text-sm text-gray-500">Welcome back, <span class="font-semibold text-contrast">{data.user?.email}</span></p>
			</div>
			<div class="mt-4 md:mt-0">
				<a
					href="/app/cases/new"
					class="btn btn-primary shadow-sm shadow-accent/20"
				>
					<Plus class="h-4 w-4 mr-2" />
					New Case
				</a>
			</div>
		</div>
	</div>

	<!-- Statistics Cards -->
	<div class="grid grid-cols-1 gap-6 sm:grid-cols-3">
		<div class="card-standard card-hover animate-fade-in-up stagger-1">
			<div class="flex items-center">
				<div class="flex-shrink-0 p-3 bg-contrast/5 rounded-lg">
					<FileText class="h-6 w-6 text-contrast-light" />
				</div>
				<div class="ml-5 w-0 flex-1">
					<dl>
						<dt class="text-sm font-medium text-gray-500 truncate">Total Cases</dt>
						<dd class="text-2xl font-heading font-bold text-contrast">{totalCases}</dd>
					</dl>
				</div>
			</div>
		</div>

		<div class="card-standard card-hover animate-fade-in-up stagger-2">
			<div class="flex items-center">
				<div class="flex-shrink-0 p-3 bg-contrast-light/10 rounded-lg">
					<Clock class="h-6 w-6 text-contrast-light" />
				</div>
				<div class="ml-5 w-0 flex-1">
					<dl>
						<dt class="text-sm font-medium text-gray-500 truncate">Processing</dt>
						<dd class="text-2xl font-heading font-bold text-contrast">{processingCases}</dd>
					</dl>
				</div>
			</div>
		</div>

		<div class="card-standard card-hover animate-fade-in-up stagger-3">
			<div class="flex items-center">
				<div class="flex-shrink-0 p-3 bg-accent/10 rounded-lg">
					<CheckCircle class="h-6 w-6 text-accent" />
				</div>
				<div class="ml-5 w-0 flex-1">
					<dl>
						<dt class="text-sm font-medium text-gray-500 truncate">Completed</dt>
						<dd class="text-2xl font-heading font-bold text-contrast">{completedCases}</dd>
					</dl>
				</div>
			</div>
		</div>
	</div>

	<!-- Recent Cases -->
	<div class="card-standard !p-0 overflow-hidden animate-fade-in-up stagger-4">
		<div class="px-6 py-4 border-b border-gray-100 bg-gray-50/50">
			<h2 class="text-lg font-heading font-semibold text-contrast">Recent Cases</h2>
		</div>

		{#if loading}
			<div class="p-4">
				<SkeletonList count={4} />
			</div>
		{:else if errorMessage}
			<div class="p-8 text-center">
				<p class="text-sm text-red-600">{errorMessage}</p>
				<button class="mt-4 btn btn-secondary px-6" onclick={() => loadCases()}>
					Try again
				</button>
			</div>
		{:else if cases.length === 0}
			<div class="p-8 text-center">
				<FileText class="mx-auto h-12 w-12 text-gray-300" />
				<p class="mt-3 text-sm text-gray-500">No cases yet. Create your first case to get started.</p>
				<a
					href="/app/cases/new"
					class="mt-4 btn btn-primary px-6"
				>
					<Plus class="h-4 w-4 mr-2" />
					Create Case
				</a>
			</div>
		{:else}
			<ul class="divide-y divide-gray-100">
				{#each cases as caseItem}
					<li>
						<a
							href="/app/cases/{caseItem.id}"
							class="block hover:bg-gray-50 transition-colors"
						>
							<div class="px-5 py-4">
								<div class="flex items-center justify-between">
									<div class="flex-1 min-w-0">
										<p class="text-sm font-medium text-contrast truncate">
											{caseItem.client_name}
										</p>
										{#if caseItem.reference_number}
											<p class="text-sm text-gray-500">{caseItem.reference_number}</p>
										{/if}
									</div>
									<div class="ml-4 flex-shrink-0">
										<Badge variant={caseItem.status}>{caseItem.status}</Badge>
									</div>
								</div>
								<div class="mt-2">
									<p class="text-xs text-gray-400">
										Created {formatDate(caseItem.created_at)}
									</p>
								</div>
							</div>
						</a>
					</li>
				{/each}
			</ul>

			<div class="px-5 py-4 border-t border-gray-100">
				<a href="/app/cases" class="text-sm font-medium text-accent hover:text-accent-hover transition-colors">
					View all cases &rarr;
				</a>
			</div>
		{/if}
	</div>
</div>
