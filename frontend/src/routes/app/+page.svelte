<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase } from '$lib/supabase';
	import { goto } from '$app/navigation';
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
				return 'bg-green-100 text-green-800';
			case 'processing':
				return 'bg-blue-100 text-blue-800';
			case 'error':
				return 'bg-red-100 text-red-800';
			default:
				return 'bg-gray-100 text-gray-800';
		}
	}
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="md:flex md:items-center md:justify-between">
		<div class="flex-1 min-w-0">
			<h2 class="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
				Dashboard
			</h2>
			<p class="mt-1 text-sm text-gray-500">Welcome back, {data.user?.email}</p>
		</div>
		<div class="mt-4 flex md:mt-0 md:ml-4">
			<a
				href="/app/cases/new"
				class="ml-3 inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
			>
				New Case
			</a>
		</div>
	</div>

	<!-- Statistics Cards -->
	<div class="grid grid-cols-1 gap-5 sm:grid-cols-3">
		<div class="bg-white overflow-hidden shadow rounded-lg">
			<div class="p-5">
				<div class="flex items-center">
					<div class="flex-shrink-0">
						<svg
							class="h-6 w-6 text-gray-400"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
							/>
						</svg>
					</div>
					<div class="ml-5 w-0 flex-1">
						<dl>
							<dt class="text-sm font-medium text-gray-500 truncate">Total Cases</dt>
							<dd class="text-lg font-medium text-gray-900">{cases.length}</dd>
						</dl>
					</div>
				</div>
			</div>
		</div>

		<div class="bg-white overflow-hidden shadow rounded-lg">
			<div class="p-5">
				<div class="flex items-center">
					<div class="flex-shrink-0">
						<svg
							class="h-6 w-6 text-gray-400"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
							/>
						</svg>
					</div>
					<div class="ml-5 w-0 flex-1">
						<dl>
							<dt class="text-sm font-medium text-gray-500 truncate">Processing</dt>
							<dd class="text-lg font-medium text-gray-900">
								{cases.filter((c) => c.status === 'processing').length}
							</dd>
						</dl>
					</div>
				</div>
			</div>
		</div>

		<div class="bg-white overflow-hidden shadow rounded-lg">
			<div class="p-5">
				<div class="flex items-center">
					<div class="flex-shrink-0">
						<svg
							class="h-6 w-6 text-gray-400"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
							/>
						</svg>
					</div>
					<div class="ml-5 w-0 flex-1">
						<dl>
							<dt class="text-sm font-medium text-gray-500 truncate">Completed</dt>
							<dd class="text-lg font-medium text-gray-900">
								{cases.filter((c) => c.status === 'completed').length}
							</dd>
						</dl>
					</div>
				</div>
			</div>
		</div>
	</div>

	<!-- Recent Cases -->
	<div class="bg-white shadow rounded-lg">
		<div class="px-4 py-5 sm:px-6 border-b border-gray-200">
			<h3 class="text-lg leading-6 font-medium text-gray-900">Recent Cases</h3>
		</div>

		{#if loading}
			<div class="p-8 text-center">
				<div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
				<p class="mt-2 text-sm text-gray-500">Loading cases...</p>
			</div>
		{:else if errorMessage}
			<div class="p-8 text-center">
				<p class="text-sm text-red-600">{errorMessage}</p>
			</div>
		{:else if cases.length === 0}
			<div class="p-8 text-center">
				<p class="text-sm text-gray-500">No cases yet. Create your first case to get started.</p>
				<a
					href="/app/cases/new"
					class="mt-4 inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-blue-700 bg-blue-100 hover:bg-blue-200"
				>
					Create Case
				</a>
			</div>
		{:else}
			<ul class="divide-y divide-gray-200">
				{#each cases as caseItem}
					<li>
						<a
							href="/app/cases/{caseItem.id}"
							class="block hover:bg-gray-50 transition duration-150"
						>
							<div class="px-4 py-4 sm:px-6">
								<div class="flex items-center justify-between">
									<div class="flex-1 min-w-0">
										<p class="text-sm font-medium text-blue-600 truncate">
											{caseItem.client_name}
										</p>
										{#if caseItem.reference_number}
											<p class="text-sm text-gray-500">{caseItem.reference_number}</p>
										{/if}
									</div>
									<div class="ml-2 flex-shrink-0 flex">
										<span
											class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full {getStatusColor(
												caseItem.status
											)}"
										>
											{caseItem.status}
										</span>
									</div>
								</div>
								<div class="mt-2">
									<p class="text-sm text-gray-500">
										Created {formatDate(caseItem.created_at)}
									</p>
								</div>
							</div>
						</a>
					</li>
				{/each}
			</ul>

			<div class="px-4 py-4 sm:px-6 border-t border-gray-200">
				<a href="/app/cases" class="text-sm font-medium text-blue-600 hover:text-blue-500">
					View all cases →
				</a>
			</div>
		{/if}
	</div>
</div>

