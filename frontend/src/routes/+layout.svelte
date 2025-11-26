<script lang="ts">
	import '../app.css';
	import ToastContainer from '$lib/components/ui/ToastContainer.svelte';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
</svelte:head>

{@render children()}

<!-- App-wide toast notifications -->
<ToastContainer />
