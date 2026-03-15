<script lang="ts">
	import { isCaseSummary } from '$lib/utils/documentClassification';
	import { formatFileSize } from '$lib/utils/formatters';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';

	let {
		intakeCandidates,
		selectedIntakeDocId = $bindable<string | null>(null),
		onconfirm,
		oncancel,
	}: {
		intakeCandidates: any[];
		selectedIntakeDocId?: string | null;
		onconfirm: () => void;
		oncancel: () => void;
	} = $props();
</script>

<div class="fixed inset-0 bg-gray-500 bg-opacity-75 flex items-center justify-center p-4 z-50">
	<div class="bg-white rounded-lg max-w-2xl w-full p-6 max-h-[80vh] overflow-y-auto">
		<div class="mb-6">
			<h3 class="text-lg font-medium text-gray-900 mb-2">Select Primary Intake Document</h3>
			<p class="text-sm text-gray-600 mb-3">
				The primary intake document provides essential case context for analysis.
				<strong>Case summaries</strong> are preferred as they typically contain more comprehensive information than intake forms.
			</p>
			<div class="bg-blue-50 border border-blue-200 rounded-lg p-3">
				<p class="text-xs text-blue-800">
					<strong>💡 Recommendation:</strong> If you have a case summary document, select it for the most accurate analysis context.
				</p>
			</div>
		</div>

		<div class="space-y-2 mb-6">
			{#each [...intakeCandidates].sort((a, b) => {
				const aIsSummary = isCaseSummary(a);
				const bIsSummary = isCaseSummary(b);
				if (aIsSummary && !bIsSummary) return -1;
				if (!aIsSummary && bIsSummary) return 1;
				return 0;
			}) as doc}
				<label class="flex items-start p-4 border rounded-lg cursor-pointer hover:bg-gray-50 transition-colors {selectedIntakeDocId === doc.id ? (isCaseSummary(doc) ? 'border-indigo-500 bg-indigo-50' : 'border-accent bg-accent/10') : (isCaseSummary(doc) ? 'border-indigo-200 bg-indigo-50/50' : 'border-gray-200')}">
					<input
						type="radio"
						name="intake-document"
						value={doc.id}
						checked={selectedIntakeDocId === doc.id}
						onchange={() => (selectedIntakeDocId = doc.id)}
						class="mt-1 h-4 w-4 {isCaseSummary(doc) ? 'text-indigo-600 focus:ring-indigo-500' : 'text-accent focus:ring-accent'} border-gray-300"
					/>
					<div class="ml-3 flex-1 min-w-0">
						<div class="flex items-center space-x-2 mb-1 flex-wrap">
							{#if isCaseSummary(doc)}
								<svg class="h-4 w-4 text-indigo-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
								</svg>
							{:else if doc.metadata?.clio_source}
								<svg class="h-4 w-4 text-accent shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
								</svg>
							{/if}
							<p class="text-sm font-medium {isCaseSummary(doc) ? 'text-indigo-900' : 'text-gray-900'} truncate">{doc.file_name}</p>
							{#if isCaseSummary(doc)}
								<span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-indigo-500 text-white">
									⭐ CASE SUMMARY (RECOMMENDED)
								</span>
							{:else if doc.metadata?.clio_source}
								<span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-purple-100 text-purple-800">
									{doc.metadata.clio_type?.toUpperCase() || 'CLIO'}
								</span>
							{/if}
							{#if doc.metadata?.is_intake_form}
								<span class="px-2 py-0.5 text-xs font-semibold rounded-full {isCaseSummary(doc) ? 'bg-indigo-600' : 'bg-accent'} text-white">
									CURRENT PRIMARY
								</span>
							{/if}
						</div>
						<p class="text-xs {isCaseSummary(doc) ? 'text-indigo-600' : 'text-gray-500'}">{formatFileSize(doc.file_size)} • {doc.file_type}</p>
						{#if isCaseSummary(doc)}
							<p class="text-xs text-indigo-700 mt-1 font-medium">
								✓ Comprehensive case overview - best for analysis context
							</p>
						{/if}
						{#if doc.extracted_at}
							<p class="text-xs text-gray-600 mt-1 italic">
								<span class="inline-block w-2 h-2 rounded-full bg-green-500 mr-1"></span>
								Text extracted and ready
							</p>
						{:else}
							<p class="text-xs text-amber-600 mt-1 italic">
								No text extracted yet
							</p>
						{/if}
					</div>
				</label>
			{/each}
		</div>

		<div class="flex justify-end space-x-3">
			<button
				onclick={oncancel}
				class="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
			>
				Cancel
			</button>
			<AsyncButton
				onclick={onconfirm}
				disabled={!selectedIntakeDocId}
				variant="primary"
				loadingText="Saving..."
			>
				{#if intakeCandidates.find(d => d.id === selectedIntakeDocId)?.metadata?.is_intake_form}
					Close
				{:else}
					Confirm Selection
				{/if}
			</AsyncButton>
		</div>
	</div>
</div>
