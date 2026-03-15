<script lang="ts">
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';

	let {
		documentName,
		onconfirm,
		oncancel,
	}: {
		documentName: string;
		onconfirm: () => void;
		oncancel: () => void;
	} = $props();
</script>

<div class="modal-overlay">
	<div class="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
		<h3 class="text-lg font-heading font-semibold text-contrast mb-4">Delete Document</h3>
		<p class="text-sm text-gray-600 mb-4">
			Are you sure you want to delete this document? This action cannot be undone.
		</p>
		<p class="text-sm font-semibold text-contrast mb-4">
			{documentName}
		</p>

		<div class="flex justify-end space-x-3">
			<button
				onclick={oncancel}
				class="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
			>
				Cancel
			</button>
			<AsyncButton
				onclick={onconfirm}
				variant="danger"
				loadingText="Deleting..."
				class="min-w-[100px]"
			>
				Delete
			</AsyncButton>
		</div>
	</div>
</div>
