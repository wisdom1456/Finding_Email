<script lang="ts">
	let {
		docsWithoutText,
		runningBulkOcr = false,
		oncancel,
		onskip,
		onocr,
	}: {
		docsWithoutText: any[];
		runningBulkOcr?: boolean;
		oncancel: () => void;
		onskip: () => void;
		onocr: () => void;
	} = $props();
</script>

<div
	class="modal-overlay"
	role="dialog"
	aria-modal="true"
	tabindex="-1"
	onclick={oncancel}
	onkeydown={(e) => { if (e.key === 'Escape') oncancel(); }}
>
	<div
		class="card-standard max-w-lg w-full mx-4"
		role="presentation"
		onclick={(e) => e.stopPropagation()}
		onkeydown={(e) => e.stopPropagation()}
	>
		<h3 class="text-lg font-heading font-semibold text-contrast mb-2">Documents Missing Text</h3>
		<p class="text-sm text-gray-600 mb-4">
			{docsWithoutText.length} document{docsWithoutText.length === 1 ? '' : 's'} {docsWithoutText.length === 1 ? "doesn't" : "don't"} have extracted text and will be <strong>skipped</strong> during analysis.
		</p>

		<div class="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4 max-h-40 overflow-auto">
			<ul class="text-sm text-amber-800 space-y-1">
				{#each docsWithoutText as doc}
					<li class="flex items-center gap-2">
						<span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
						<span class="truncate">{doc.file_name}</span>
					</li>
				{/each}
			</ul>
		</div>

		<p class="text-xs text-gray-500 mb-4">
			Run OCR to extract text from these documents, or proceed without them.
		</p>

		<div class="flex flex-col sm:flex-row gap-3 justify-end">
			<button
				onclick={oncancel}
				class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
			>
				Cancel
			</button>
			<button
				onclick={onskip}
				class="px-4 py-2 text-sm font-medium text-amber-700 bg-amber-100 border border-amber-300 rounded-md hover:bg-amber-200 transition-colors"
			>
				Skip These Documents
			</button>
			<button
				onclick={onocr}
				disabled={runningBulkOcr}
				class="px-4 py-2 text-sm font-medium text-white bg-accent rounded-md hover:bg-accent-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
			>
				{#if runningBulkOcr}
					<svg class="animate-spin h-4 w-4" viewBox="0 0 24 24">
						<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"></circle>
						<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
					</svg>
					Running OCR...
				{:else}
					Run OCR on All
				{/if}
			</button>
		</div>
	</div>
</div>
