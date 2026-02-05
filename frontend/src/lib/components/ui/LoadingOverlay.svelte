<!--
	LoadingOverlay - Full-screen loading indicator
	
	Use for operations that:
	- Take more than 2-3 seconds
	- Block user interaction
	- Are critical (delete, import, etc.)
-->
<script lang="ts">
	import { Loader2 } from 'lucide-svelte';
	import { fade } from 'svelte/transition';
	
	let {
		show = false,
		message = 'Loading...',
		description = '',
		allowCancel = false,
		onCancel
	}: {
		show: boolean;
		message?: string;
		description?: string;
		allowCancel?: boolean;
		onCancel?: () => void;
	} = $props();
</script>

{#if show}
	<div
		class="modal-overlay"
		transition:fade={{ duration: 200 }}
		role="dialog"
		aria-modal="true"
		aria-label="Loading"
	>
		<div class="card-standard shadow-2xl p-8 max-w-md w-full mx-4">
			<div class="flex flex-col items-center text-center">
				<Loader2 class="h-12 w-12 text-accent animate-spin mb-6" />
				
				<h3 class="text-xl font-heading font-bold text-contrast mb-2">
					{message}
				</h3>
				
				{#if description}
					<p class="text-sm text-gray-600 mb-4">
						{description}
					</p>
				{/if}
				
				{#if allowCancel && onCancel}
					<button
						onclick={onCancel}
						class="mt-4 px-4 py-2 text-sm font-medium text-gray-700 hover:text-gray-900 transition-colors"
					>
						Cancel
					</button>
				{/if}
			</div>
		</div>
	</div>
{/if}

<style>
	/* Force cursor to wait on the overlay */
	div[role="dialog"] {
		cursor: wait;
	}
	
	div[role="dialog"] * {
		cursor: wait;
	}
	
	/* Except for the cancel button */
	div[role="dialog"] button {
		cursor: pointer;
	}
</style>

