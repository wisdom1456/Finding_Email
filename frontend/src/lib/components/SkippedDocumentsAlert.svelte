<script lang="ts">
	import { AlertCircle, ChevronDown, ChevronUp, FileQuestion, RefreshCw, Ban } from 'lucide-svelte';
	import { slide } from 'svelte/transition';

	let { skippedDocs = [] }: { skippedDocs: any[] } = $props();
	let isExpanded = $state(false);

	// Split triage skips from real errors — different messaging
	let triageSkips = $derived(skippedDocs.filter(d => d.error_type === 'TRIAGE_SKIP'));
	let errorSkips = $derived(skippedDocs.filter(d => d.error_type !== 'TRIAGE_SKIP'));
</script>

{#if skippedDocs.length > 0}
	<div class="mb-8 overflow-hidden bg-amber-50 border border-amber-200 rounded-2xl shadow-sm">
		<div class="p-4 sm:p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
			<div class="flex items-start gap-4">
				<div class="mt-1 p-2 rounded-xl bg-amber-100 text-amber-600">
					<AlertCircle class="w-6 h-6" />
				</div>
				<div>
					<h3 class="text-lg font-bold text-amber-900">
						{skippedDocs.length} {skippedDocs.length === 1 ? 'Document' : 'Documents'} excluded
					</h3>
					<p class="text-sm font-medium text-amber-700 mt-1">
						{#if errorSkips.length > 0 && triageSkips.length > 0}
							{errorSkips.length} had errors; {triageSkips.length} {triageSkips.length === 1 ? 'is' : 'are'} boilerplate or zero-content.
						{:else if errorSkips.length > 0}
							Some documents had errors and were excluded to ensure accuracy.
						{:else}
							These are boilerplate templates or zero-content files with no legal value.
						{/if}
					</p>
				</div>
			</div>

			<div class="flex items-center gap-3 w-full sm:w-auto">
				<button
					onclick={() => isExpanded = !isExpanded}
					class="flex-1 sm:flex-none inline-flex items-center justify-center px-4 py-2 text-sm font-bold rounded-xl bg-white border border-amber-200 text-amber-700 hover:bg-amber-100/50 transition-colors"
				>
					{isExpanded ? 'Hide Details' : 'View Details'}
					{#if isExpanded}
						<ChevronUp class="w-4 h-4 ml-2" />
					{:else}
						<ChevronDown class="w-4 h-4 ml-2" />
					{/if}
				</button>

				{#if errorSkips.length > 0}
					<button
						onclick={() => window.location.hash = 'verification'}
						class="flex-1 sm:flex-none inline-flex items-center justify-center px-4 py-2 text-sm font-bold rounded-xl bg-amber-600 text-white hover:bg-amber-700 transition-colors shadow-sm shadow-amber-200"
					>
						<RefreshCw class="w-4 h-4 mr-2" />
						Fix Documents
					</button>
				{/if}
			</div>
		</div>

		{#if isExpanded}
			<div transition:slide={{ duration: 300 }} class="border-t border-amber-200 bg-white/50">
				<div class="p-6">
					{#if errorSkips.length > 0}
						<h4 class="text-xs font-bold uppercase tracking-wider text-red-600 mb-3">Errors ({errorSkips.length})</h4>
						<div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
							{#each errorSkips as doc}
								<div class="p-4 rounded-xl border border-red-100 bg-white flex items-start gap-4 shadow-sm">
									<div class="mt-1 p-2 rounded-lg bg-red-50 text-red-400">
										<FileQuestion class="w-5 h-5" />
									</div>
									<div class="min-w-0">
										<h4 class="text-sm font-bold text-gray-900 truncate">{doc.file_name}</h4>
										<div class="mt-1 flex items-center gap-2">
											<span class="px-1.5 py-0.5 rounded text-[10px] font-black uppercase tracking-wider bg-red-100 text-red-700">
												{doc.error_type || 'ERROR'}
											</span>
											<span class="text-xs font-medium text-gray-500">&bull;</span>
											<span class="text-xs font-medium text-gray-600">{doc.reason}</span>
										</div>
										<p class="mt-2 text-xs font-bold text-amber-700 italic">
											{doc.recommendation}
										</p>
									</div>
								</div>
							{/each}
						</div>
					{/if}

					{#if triageSkips.length > 0}
						<h4 class="text-xs font-bold uppercase tracking-wider text-gray-500 mb-3">Excluded by triage ({triageSkips.length})</h4>
						<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
							{#each triageSkips as doc}
								<div class="p-3 rounded-lg border border-gray-100 bg-white flex items-center gap-3">
									<div class="p-1.5 rounded-md bg-gray-50 text-gray-400">
										<Ban class="w-4 h-4" />
									</div>
									<div class="min-w-0">
										<h4 class="text-sm font-medium text-gray-700 truncate">{doc.file_name}</h4>
										<span class="text-xs text-gray-500">{doc.reason}</span>
									</div>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			</div>
		{/if}
	</div>
{/if}
