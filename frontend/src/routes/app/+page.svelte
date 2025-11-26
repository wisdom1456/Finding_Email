<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase } from '$lib/supabase';
	import { goto } from '$app/navigation';
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
			const { data: casesData, error } = await supabase
				.from('cases')
				.select('*')
				.order('created_at', { ascending: false })
				.limit(5);

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
	
	const totalCases = $derived(cases.length);
	const processingCases = $derived(cases.filter((c) => c.status === 'processing').length);
	const completedCases = $derived(cases.filter((c) => c.status === 'completed').length);
</script>

<svelte:head>
	<title>Dashboard | Bernhardt Riley</title>
</svelte:head>

<div class="space-y-8">
	<!-- Header -->
	<div class="md:flex md:items-center md:justify-between">
		<div class="flex-1 min-w-0">
			<h1 class="text-2xl font-heading font-bold text-contrast sm:text-3xl">
				Dashboard
			</h1>
			<p class="mt-1 text-sm text-gray-500">Welcome back, {data.user?.email}</p>
		</div>
		<div class="mt-4 md:mt-0">
			<a
				href="/app/cases/new"
				class="inline-flex items-center px-4 py-2 rounded-md text-sm font-medium text-white bg-accent hover:bg-accent-hover transition-colors"
			>
				<Plus class="h-4 w-4 mr-2" />
				New Case
			</a>
		</div>
	</div>

	<!-- Statistics Cards -->
	<div class="grid grid-cols-1 gap-5 sm:grid-cols-3">
		<div class="bg-white overflow-hidden shadow-card rounded-lg">
			<div class="p-5">
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
		</div>

		<div class="bg-white overflow-hidden shadow-card rounded-lg">
			<div class="p-5">
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
		</div>

		<div class="bg-white overflow-hidden shadow-card rounded-lg">
			<div class="p-5">
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
	</div>

	<!-- Recent Cases -->
	<div class="bg-white shadow-card rounded-lg">
		<div class="px-5 py-4 border-b border-gray-100">
			<h2 class="text-lg font-heading font-semibold text-contrast">Recent Cases</h2>
		</div>

		{#if loading}
			<div class="p-8 text-center">
				<div class="inline-block animate-spin rounded-full h-8 w-8 border-2 border-accent border-t-transparent"></div>
				<p class="mt-3 text-sm text-gray-500">Loading cases...</p>
			</div>
		{:else if errorMessage}
			<div class="p-8 text-center">
				<p class="text-sm text-red-600">{errorMessage}</p>
			</div>
		{:else if cases.length === 0}
			<div class="p-8 text-center">
				<FileText class="mx-auto h-12 w-12 text-gray-300" />
				<p class="mt-3 text-sm text-gray-500">No cases yet. Create your first case to get started.</p>
				<a
					href="/app/cases/new"
					class="mt-4 inline-flex items-center px-4 py-2 text-sm font-medium rounded-md text-accent bg-accent/10 hover:bg-accent/20 transition-colors"
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
										<span
											class="px-2.5 py-0.5 inline-flex text-xs font-medium rounded-full {getStatusColor(caseItem.status)}"
										>
											{caseItem.status}
										</span>
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
