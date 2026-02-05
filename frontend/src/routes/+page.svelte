<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import type { PageData } from './$types';
	import logoImg from '$lib/assets/logo-br.png';
	import Spinner from '$lib/components/ui/Spinner.svelte';

	let { data }: { data: PageData } = $props();
	
	// Cast data to include session from layout
	const layoutData = data as unknown as { session: any };

	onMount(() => {
		// Redirect to dashboard if logged in, otherwise to login
		if (layoutData.session) {
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
		<Spinner label="Redirecting..." class="text-accent" />
	</div>
</div>
