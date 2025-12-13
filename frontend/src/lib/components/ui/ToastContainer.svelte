<script lang="ts">
	/**
	 * ToastContainer - Renders all active toast notifications
	 * Add this component to your root layout to enable app-wide notifications
	 *
	 * Usage in +layout.svelte:
	 *   <ToastContainer />
	 *
	 * Then in any component:
	 *   import { toastStore } from '$lib/stores/toastStore';
	 *   toastStore.success('Operation completed!');
	 *   toastStore.error('Something went wrong');
	 */

	import { toastStore } from '$lib/stores/toastStore';
	import Toast from './Toast.svelte';
</script>

<div class="fixed bottom-4 right-4 z-50 space-y-2">
	{#each $toastStore as toast (toast.id)}
		<Toast
			type={toast.type}
			message={toast.message}
			duration={toast.duration}
			onClose={() => toastStore.remove(toast.id)}
		/>
	{/each}
</div>


