<script lang="ts">
	import { onMount } from 'svelte';
	import { getApiUrl } from '$lib/config';
	import { getSecureSession } from '$lib/supabase';
	import { clioStore } from '$lib/stores/clioStore';
	import ConfirmDialog from './ui/ConfirmDialog.svelte';
	import Badge from './ui/Badge.svelte';
	import { Zap, CheckCircle2, XCircle } from 'lucide-svelte';

	let loading = $state(true);
	let errorMessage = $state('');
	let showDisconnectConfirm = $state(false);
	
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
			const { session, user } = await getSecureSession();

			if (!session || !user) {
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
			const { session, user } = await getSecureSession();

			if (!session || !user) {
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
		try {
			const { session, user } = await getSecureSession();

			if (!session || !user) {
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

<div class="card-standard">
	<h3 class="text-lg font-heading font-semibold text-contrast mb-4">Clio Integration</h3>

	{#if loading}
		<div class="flex items-center justify-center p-4">
			<div class="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-accent"></div>
			<span class="ml-2 text-sm text-gray-600">Checking connection...</span>
		</div>
	{:else if connected}
		<div class="space-y-4">
			<div class="flex items-center">
				<div class="flex-shrink-0">
					<CheckCircle2 class="h-6 w-6 text-green-500" />
				</div>
				<div class="ml-3">
					<p class="text-sm font-medium text-gray-900">Connected to Clio</p>
					{#if clioUserId}
						<p class="text-xs text-gray-500 font-mono">User ID: {clioUserId}</p>
					{/if}
				</div>
			</div>

			<p class="text-sm text-gray-600">
				Your Clio account is connected. You can now import matters, communications, and documents.
			</p>

			<button
				onclick={() => showDisconnectConfirm = true}
				class="btn btn-secondary text-red-600 hover:text-red-700 border-red-200 hover:border-red-300"
			>
				Disconnect Clio
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
					<CheckCircle2 class="h-5 w-5 text-accent mr-2 mt-0.5" />
					<span>Import client communications and emails</span>
				</li>
				<li class="flex items-start">
					<CheckCircle2 class="h-5 w-5 text-accent mr-2 mt-0.5" />
					<span>Access case notes and documents</span>
				</li>
				<li class="flex items-start">
					<CheckCircle2 class="h-5 w-5 text-accent mr-2 mt-0.5" />
					<span>Sync matter information automatically</span>
				</li>
			</ul>

			<button
				onclick={connectClio}
				class="btn btn-primary w-full sm:w-auto"
			>
				<Zap class="h-5 w-5 mr-2" />
				Connect to Clio
			</button>
		</div>
	{/if}

	{#if errorMessage}
		<div class="mt-4 rounded-lg bg-red-50 p-4 border border-red-100 flex items-start gap-3">
			<XCircle class="h-5 w-5 text-red-600 shrink-0" />
			<p class="text-sm text-red-800">{errorMessage}</p>
		</div>
	{/if}
</div>

<ConfirmDialog
	bind:open={showDisconnectConfirm}
	title="Disconnect Clio"
	message="Are you sure you want to disconnect Clio? This will remove your saved credentials and stop active imports."
	confirmText="Disconnect"
	variant="danger"
	onConfirm={disconnectClio}
/>

