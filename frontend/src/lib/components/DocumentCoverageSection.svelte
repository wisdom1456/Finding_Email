<script lang="ts">
	import { FileCheck2, Layers, FileQuestion, Files } from 'lucide-svelte';

	interface Props {
		totalDocuments: number;
		fullyAnalyzed: number;
		groupedDocuments?: number;
		groupCount?: number;
		metadataOnly?: number;
		skipped?: number;
	}

	let {
		totalDocuments,
		fullyAnalyzed,
		groupedDocuments = 0,
		groupCount = 0,
		metadataOnly = 0,
		skipped = 0,
	}: Props = $props();

	const coveragePercent = $derived(
		totalDocuments > 0 ? Math.round(((fullyAnalyzed + groupedDocuments) / totalDocuments) * 100) : 0
	);

	const analyzedWidth = $derived(
		totalDocuments > 0 ? (fullyAnalyzed / totalDocuments) * 100 : 0
	);
	const groupedWidth = $derived(
		totalDocuments > 0 ? (groupedDocuments / totalDocuments) * 100 : 0
	);
	const metadataWidth = $derived(
		totalDocuments > 0 ? (metadataOnly / totalDocuments) * 100 : 0
	);

	const coverageColor = $derived(
		coveragePercent >= 90 ? 'text-green-600' :
		coveragePercent >= 70 ? 'text-blue-600' :
		coveragePercent >= 50 ? 'text-amber-600' :
		'text-red-600'
	);
</script>

<div class="rounded-xl border border-gray-200 bg-white p-4 space-y-3">
	<div class="flex items-center justify-between">
		<h3 class="text-sm font-semibold text-gray-700 flex items-center gap-1.5">
			<Files class="w-4 h-4 text-gray-400" />
			Document Coverage
		</h3>
		<span class="text-sm font-bold {coverageColor}">{coveragePercent}%</span>
	</div>

	<!-- Stacked progress bar -->
	<div class="h-2 bg-gray-100 rounded-full overflow-hidden flex">
		{#if analyzedWidth > 0}
			<div
				class="h-full bg-green-500 transition-all duration-500"
				style="width: {analyzedWidth}%"
				title="{fullyAnalyzed} fully analyzed"
			></div>
		{/if}
		{#if groupedWidth > 0}
			<div
				class="h-full bg-blue-500 transition-all duration-500"
				style="width: {groupedWidth}%"
				title="{groupedDocuments} analyzed as groups"
			></div>
		{/if}
		{#if metadataWidth > 0}
			<div
				class="h-full bg-amber-300 transition-all duration-500"
				style="width: {metadataWidth}%"
				title="{metadataOnly} metadata only"
			></div>
		{/if}
	</div>

	<!-- Legend -->
	<div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600">
		<span class="inline-flex items-center gap-1.5">
			<span class="w-2 h-2 rounded-full bg-green-500 flex-shrink-0"></span>
			<FileCheck2 class="w-3 h-3 text-gray-400" />
			{fullyAnalyzed} fully analyzed
		</span>
		{#if groupedDocuments > 0}
			<span class="inline-flex items-center gap-1.5">
				<span class="w-2 h-2 rounded-full bg-blue-500 flex-shrink-0"></span>
				<Layers class="w-3 h-3 text-gray-400" />
				{groupedDocuments} in {groupCount} group{groupCount !== 1 ? 's' : ''}
			</span>
		{/if}
		{#if metadataOnly > 0}
			<span class="inline-flex items-center gap-1.5">
				<span class="w-2 h-2 rounded-full bg-amber-300 flex-shrink-0"></span>
				<FileQuestion class="w-3 h-3 text-gray-400" />
				{metadataOnly} metadata only
			</span>
		{/if}
		{#if skipped > 0}
			<span class="inline-flex items-center gap-1.5">
				<span class="w-2 h-2 rounded-full bg-gray-300 flex-shrink-0"></span>
				{skipped} skipped
			</span>
		{/if}
	</div>

	{#if groupedDocuments > 0 || metadataOnly > 0}
		<p class="text-[11px] text-gray-400 leading-relaxed">
			{#if groupedDocuments > 0}
				Grouped documents were summarized together to reduce redundancy.
			{/if}
			{#if metadataOnly > 0}
				Metadata-only documents were catalogued but not fully evaluated.
			{/if}
			All documents remain in the case file.
		</p>
	{/if}
</div>
