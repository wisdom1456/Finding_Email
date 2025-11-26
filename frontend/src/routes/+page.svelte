<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import type { PageData } from './$types';
	import logoImg from '$lib/assets/logo-br.png';

	let { data }: { data: PageData } = $props();

	onMount(() => {
		// Redirect to dashboard if logged in, otherwise to login
		if (data.session) {
			goto('/app');
		} else {
			goto('/login');
		}
	});
</script>

<svelte:head>
	<title>Bernhardt Riley | Legal Document Analysis Portal</title>
</svelte:head>

<div class="min-h-screen flex flex-col items-center justify-center bg-contrast">
	<div class="text-center">
		<img src={logoImg} alt="Bernhardt Riley" class="h-20 w-auto mx-auto mb-8" />
		<div class="flex items-center justify-center space-x-2">
			<div class="animate-spin rounded-full h-5 w-5 border-2 border-accent border-t-transparent"></div>
			<p class="text-gray-400 text-sm">Redirecting...</p>
		</div>
	</div>
</div>
