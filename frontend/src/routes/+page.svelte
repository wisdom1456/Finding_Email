<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import type { PageData } from './$types';

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

<div class="min-h-screen flex items-center justify-center">
	<div class="text-center">
		<h1 class="text-2xl font-bold mb-4">Legal Document Analysis Portal</h1>
		<p class="text-gray-600">Redirecting...</p>
	</div>
</div>
