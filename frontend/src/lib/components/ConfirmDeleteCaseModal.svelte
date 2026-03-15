<script lang="ts">
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';

	let {
		clientName,
		referenceNumber = null,
		documentCount,
		onconfirm,
		oncancel,
	}: {
		clientName: string;
		referenceNumber?: string | null;
		documentCount: number;
		onconfirm: () => void;
		oncancel: () => void;
	} = $props();

	let confirmText = $state('');
</script>

<div class="modal-overlay">
	<div class="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
		<h3 class="text-lg font-heading font-semibold text-contrast mb-4">Delete Case</h3>
		<div class="text-sm text-gray-600 space-y-3 mb-4">
			<p><strong class="text-contrast">Case:</strong> {clientName}</p>
			{#if referenceNumber}
				<p><strong class="text-contrast">Reference:</strong> {referenceNumber}</p>
			{/if}
			<p class="text-red-600 font-semibold bg-red-50 p-3 rounded-md border border-red-100">
				⚠️ This will permanently delete the case and all {documentCount} associated document(s).
			</p>
			<p>This action cannot be undone.</p>
		</div>

		<div class="mb-4">
			<label for="delete-confirm" class="block text-sm font-semibold text-contrast mb-2">
				Type <span class="font-mono font-bold text-red-600">DELETE</span> to confirm:
			</label>
			<input
				id="delete-confirm"
				type="text"
				bind:value={confirmText}
				placeholder="DELETE"
				class="input-standard focus:ring-red-500 border-gray-300"
			/>
		</div>

		<div class="flex justify-end space-x-3">
			<button
				onclick={() => {
					confirmText = '';
					oncancel();
				}}
				class="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
			>
				Cancel
			</button>
			<AsyncButton
				onclick={onconfirm}
				disabled={confirmText !== 'DELETE'}
				variant="danger"
				loadingText="Deleting..."
				class="min-w-[120px]"
			>
				Delete Case
			</AsyncButton>
		</div>
	</div>
</div>
