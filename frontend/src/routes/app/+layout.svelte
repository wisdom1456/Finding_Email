<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase } from '$lib/supabase';
	import { goto } from '$app/navigation';
	import { PUBLIC_API_URL } from '$env/static/public';
	import ClioConnect from '$lib/components/ClioConnect.svelte';
	import { clioStore } from '$lib/stores/clioStore';
	import type { LayoutData } from './$types';

	let { data, children }: { data: LayoutData; children: any } = $props();
	
	let showClioModal = $state(false);
	let clioConnected = $derived($clioStore.connected);

	// Check Clio connection status on mount
	onMount(async () => {
		await checkClioStatus();
	});

	async function checkClioStatus() {
		try {
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) return;

			const response = await fetch(`${PUBLIC_API_URL}/api/clio/status`, {
				headers: { Authorization: `Bearer ${session.access_token}` }
			});

			if (response.ok) {
				const status = await response.json();
				clioStore.setConnected(status.connected, status.clio_user_id, status.expires_at);
			}
		} catch (error) {
			// Silently fail - user can still manually check via modal
			console.log('Could not check Clio status on load:', error);
		}
	}

	async function handleLogout() {
		await supabase.auth.signOut();
		goto('/login');
	}
</script>

<div class="min-h-screen bg-gray-50">
	<!-- Navigation -->
	<nav class="bg-white shadow-sm">
		<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
			<div class="flex justify-between h-16">
				<div class="flex">
					<div class="flex-shrink-0 flex items-center">
						<a href="/app" class="text-xl font-bold text-gray-900">
							Legal Document Analysis
						</a>
					</div>
					<div class="hidden sm:ml-6 sm:flex sm:space-x-8">
						<a
							href="/app"
							class="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium"
						>
							Dashboard
						</a>
						<a
							href="/app/cases"
							class="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium"
						>
							Cases
						</a>
					</div>
				</div>
				<div class="flex items-center space-x-4">
					<!-- Clio Integration Button -->
					<button
						onclick={() => showClioModal = !showClioModal}
						class="inline-flex items-center px-3 py-2 border text-sm leading-4 font-medium rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 {clioConnected ? 'border-green-500 text-green-700 bg-green-50 hover:bg-green-100' : 'border-gray-300 text-gray-700 bg-white hover:bg-gray-50'}"
						title={clioConnected ? 'Clio Connected' : 'Clio Integration'}
					>
						<svg class="h-4 w-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
						</svg>
						Clio
						{#if clioConnected}
							<span class="ml-2 inline-block h-2 w-2 rounded-full bg-green-500"></span>
						{/if}
					</button>
					
					<span class="text-sm text-gray-700">{data.user?.email}</span>
					<button
						onclick={handleLogout}
						class="inline-flex items-center px-3 py-2 border border-transparent text-sm leading-4 font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
					>
						Logout
					</button>
				</div>
			</div>
		</div>
	</nav>

	<!-- Main Content -->
	<main class="py-10">
		<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
			{@render children()}
		</div>
	</main>
</div>

<!-- Clio Integration Modal -->
{#if showClioModal}
	<div class="fixed inset-0 bg-gray-500 bg-opacity-75 flex items-center justify-center p-4 z-50" onclick={() => showClioModal = false}>
		<div class="bg-white rounded-lg shadow-xl max-w-md w-full p-6" onclick={(e) => e.stopPropagation()}>
			<div class="flex justify-between items-center mb-4">
				<h3 class="text-lg font-medium text-gray-900">Clio Integration</h3>
				<button
					onclick={() => showClioModal = false}
					class="text-gray-400 hover:text-gray-500"
					aria-label="Close"
				>
					<svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
			
			<ClioConnect />
			
			<div class="mt-4 text-sm text-gray-500">
				<p>Connect your Clio account to import matter details, documents, communications, and notes across all your cases.</p>
			</div>
			
			<!-- OK Button -->
			<div class="mt-6 flex justify-end">
				<button
					onclick={() => showClioModal = false}
					class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
				>
					OK
				</button>
			</div>
		</div>
	</div>
{/if}

