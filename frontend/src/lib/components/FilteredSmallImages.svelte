<script lang="ts">
	import { ChevronDown, ChevronUp, ImageOff, Info } from 'lucide-svelte';
	import { slide } from 'svelte/transition';

	let { documents = [] }: { documents: any[] } = $props();

	let filteredDocs = $derived(
		documents.filter(
			(doc) =>
				doc.status === 'skipped_small_image' &&
				doc.metadata?.clio_source === true
		)
	);

	let isExpanded = $state(false);

	function formatSize(bytes: number) {
		if (!bytes) return 'Unknown size';
		if (bytes < 1024) {
			return `${bytes} B`;
		}
		return `${(bytes / 1024).toFixed(1)} KB`;
	}
</script>

{#if filteredDocs.length > 0}
	<div class="mb-6 overflow-hidden bg-gray-50 border border-gray-200 rounded-2xl shadow-sm">
		<div class="p-4 sm:p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
			<div class="flex items-start gap-4">
				<div class="mt-1 p-2 rounded-xl bg-gray-100 text-gray-500">
					<ImageOff class="w-6 h-6" />
				</div>
				<div>
					<h3 class="text-lg font-bold text-gray-800">
						{filteredDocs.length} small {filteredDocs.length === 1 ? 'image was' : 'images were'} filtered
					</h3>
					<p class="text-sm font-medium text-gray-600 mt-1">
						Small image files under 50KB were skipped because they are typically email signature logos or icons.
					</p>
				</div>
			</div>

			<div class="flex items-center gap-3 w-full sm:w-auto">
				<button
					onclick={() => (isExpanded = !isExpanded)}
					class="flex-1 sm:flex-none inline-flex items-center justify-center px-4 py-2 text-sm font-bold rounded-xl bg-white border border-gray-200 text-gray-700 hover:bg-gray-100/50 transition-colors shadow-sm"
				>
					{isExpanded ? 'Hide List' : 'View Filtered Files'}
					{#if isExpanded}
						<ChevronUp class="w-4 h-4 ml-2" />
					{:else}
						<ChevronDown class="w-4 h-4 ml-2" />
					{/if}
				</button>
			</div>
		</div>

		{#if isExpanded}
			<div transition:slide={{ duration: 300 }} class="border-t border-gray-200 bg-white/50">
				<div class="p-4 sm:p-6">
					<div class="grid grid-cols-1 gap-3">
						{#each filteredDocs as doc}
							<div class="p-3 rounded-xl border border-gray-100 bg-white flex items-center gap-4 shadow-sm">
								<div class="p-2 rounded-lg bg-gray-50 text-gray-400">
									<ImageOff class="w-4 h-4" />
								</div>
								<div class="min-w-0 flex-1">
									<h4 class="text-sm font-bold text-gray-900 truncate" title={doc.file_name}>
										{doc.file_name}
									</h4>
									<div class="mt-1 flex flex-wrap items-center gap-2">
										<span class="px-1.5 py-0.5 rounded text-[10px] font-black uppercase tracking-wider bg-gray-100 text-gray-600">
											Filtered
										</span>
										<span class="text-xs font-medium text-gray-400">•</span>
										<span class="text-xs font-medium text-gray-600">{formatSize(doc.file_size)}</span>
										{#if doc.file_type}
											<span class="text-xs font-medium text-gray-400">•</span>
											<span class="text-xs text-gray-500">{doc.file_type}</span>
										{/if}
									</div>
								</div>
							</div>
						{/each}
					</div>

					<div class="mt-6 flex items-start gap-3 p-4 rounded-xl bg-blue-50 border border-blue-100 text-blue-800">
						<Info class="w-5 h-5 mt-0.5 shrink-0" />
						<p class="text-xs font-medium leading-relaxed">
							These small images are typically email signature graphics, social media icons, or company logos embedded in emails. They are not relevant to legal analysis and were automatically skipped to keep your case focused.
						</p>
					</div>
				</div>
			</div>
		{/if}
	</div>
{/if}
