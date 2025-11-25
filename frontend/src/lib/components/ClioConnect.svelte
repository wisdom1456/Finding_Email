<script lang="ts">
	import { onMount } from 'svelte';
	import { getApiUrl } from '$lib/config';
	import { supabase } from '$lib/supabase';
	import { clioStore } from '$lib/stores/clioStore';

	let loading = $state(true);
	let errorMessage = $state('');
	
	// Subscribe to store
	let connected = $derived($clioStore.connected);
	let clioUserId = $derived($clioStore.clioUserId);
	let expiresAt = $derived($clioStore.expiresAt);

	onMount(async () => {
		await checkConnection();
	});

	async function checkConnection() {
		loading = true;
		errorMessage = '';

		try {
			const {
				data: { session }
			} = await supabase.auth.getSession();

			if (!session) {
				errorMessage = 'Not authenticated - please log in';
				loading = false;
				return;
			}

			const apiUrl = getApiUrl();
			const endpoint = `${apiUrl}/api/clio/status`;

			const response = await fetch(endpoint, {
				headers: {
					Authorization: `Bearer ${session.access_token}`
				}
			});

			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				throw new Error(errorData.detail || 'Failed to check Clio status');
			}

			const status = await response.json();
			clioStore.setConnected(status.connected, status.clio_user_id, status.expires_at);
		} catch (error: any) {
			console.error('Clio connection check failed:', error);
			errorMessage = error.message || 'Failed to check connection status';
		} finally {
			loading = false;
		}
	}

	async function connectClio() {
		try {
			const {
				data: { session }
			} = await supabase.auth.getSession();

			if (!session) {
				errorMessage = 'Not authenticated';
				return;
			}

			const apiUrl = getApiUrl();
			// Redirect to OAuth authorization with token as query param
			// (Required because direct navigation can't set Authorization header)
			window.location.href = `${apiUrl}/api/clio/authorize?token=${session.access_token}`;
		} catch (error: any) {
			console.error('Failed to initiate Clio connection:', error);
			errorMessage = error.message || 'Failed to initiate connection';
		}
	}

	async function disconnectClio() {
		if (!confirm('Are you sure you want to disconnect Clio? This will remove your saved credentials.')) {
			return;
		}

		try {
			const {
				data: { session }
			} = await supabase.auth.getSession();

			if (!session) {
				errorMessage = 'Not authenticated';
				return;
			}

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/clio/disconnect`, {
				method: 'DELETE',
				headers: {
					Authorization: `Bearer ${session.access_token}`
				}
			});

			if (!response.ok) {
				throw new Error('Failed to disconnect');
			}

			clioStore.disconnect();
		} catch (error: any) {
			errorMessage = error.message || 'Failed to disconnect';
		}
	}
</script>

<div class="bg-white shadow rounded-lg p-6">
	<h3 class="text-lg font-medium text-gray-900 mb-4">Clio Integration</h3>

	{#if loading}
		<div class="flex items-center justify-center p-4">
			<div class="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
			<span class="ml-2 text-sm text-gray-600">Checking connection...</span>
		</div>
	{:else if connected}
		<div class="space-y-4">
			<div class="flex items-center">
				<div class="flex-shrink-0">
					<svg class="h-6 w-6 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
						/>
					</svg>
				</div>
				<div class="ml-3">
					<p class="text-sm font-medium text-gray-900">Connected to Clio</p>
					{#if clioUserId}
						<p class="text-xs text-gray-500">User ID: {clioUserId}</p>
					{/if}
				</div>
			</div>

			<p class="text-sm text-gray-600">
				Your Clio account is connected. You can now import matters, communications, and documents.
			</p>

			<button
				onclick={disconnectClio}
				class="inline-flex items-center px-4 py-2 border border-red-300 shadow-sm text-sm font-medium rounded-md text-red-700 bg-white hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
			>
				Disconnect
			</button>
		</div>
	{:else}
		<div class="space-y-4">
			<p class="text-sm text-gray-600">
				Connect your Clio account to import matters, communications, and documents directly into your
				cases.
			</p>

			<ul class="text-sm text-gray-600 space-y-2">
				<li class="flex items-start">
					<svg class="h-5 w-5 text-blue-500 mr-2 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
					</svg>
					<span>Import client communications and emails</span>
				</li>
				<li class="flex items-start">
					<svg class="h-5 w-5 text-blue-500 mr-2 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
					</svg>
					<span>Access case notes and documents</span>
				</li>
				<li class="flex items-start">
					<svg class="h-5 w-5 text-blue-500 mr-2 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
					</svg>
					<span>Sync matter information automatically</span>
				</li>
			</ul>

			<button
				onclick={connectClio}
				class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
			>
				<svg class="h-5 w-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M13 10V3L4 14h7v7l9-11h-7z"
					/>
				</svg>
				Connect to Clio
			</button>
		</div>
	{/if}

	{#if errorMessage}
		<div class="mt-4 rounded-md bg-red-50 p-4">
			<p class="text-sm text-red-800">{errorMessage}</p>
		</div>
	{/if}
</div>

