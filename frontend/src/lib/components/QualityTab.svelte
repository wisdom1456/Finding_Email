<script lang="ts">
	let {
		qualityReport,
		onviewdocument,
	}: {
		qualityReport: any[] | null | undefined;
		onviewdocument: (documentName: string, documentId?: string) => void;
	} = $props();
</script>

<div class="card-standard">
	<div class="flex flex-col md:flex-row md:items-center justify-between mb-8 border-b border-gray-100 pb-6 gap-4">
		<div>
			<h3 data-testid="quality-heading" class="text-2xl font-heading font-bold text-contrast">Quality Report</h3>
			<p class="text-sm text-gray-500 mt-1 font-medium">Review the automated extraction quality for each document.</p>
		</div>
		{#if qualityReport && qualityReport.length > 0}
			{@const lowQualityCount = qualityReport.filter((item: { score?: number }) => (item.score ?? 0) < 6).length}
			{#if lowQualityCount > 0}
				<div class="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold bg-red-50 text-red-700 border border-red-200 shadow-sm animate-pulse">
					<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
						<path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
					</svg>
					{lowQualityCount} Documents Need Review
				</div>
			{/if}
		{/if}
	</div>

	<!-- Legend -->
	<div class="flex flex-wrap gap-6 mb-8 p-4 bg-gray-50 rounded-xl border border-gray-200">
		<div class="flex items-center gap-2">
			<span class="w-3 h-3 rounded-full bg-red-500 shadow-sm shadow-red-200"></span>
			<span class="text-xs font-bold text-gray-600 uppercase tracking-wide">Low (&lt;6)</span>
		</div>
		<div class="flex items-center gap-2">
			<span class="w-3 h-3 rounded-full bg-amber-500 shadow-sm shadow-amber-200"></span>
			<span class="text-xs font-bold text-gray-600 uppercase tracking-wide">Medium (6-8)</span>
		</div>
		<div class="flex items-center gap-2">
			<span class="w-3 h-3 rounded-full bg-green-500 shadow-sm shadow-green-200"></span>
			<span class="text-xs font-bold text-gray-600 uppercase tracking-wide">High (&gt;8)</span>
		</div>
	</div>

	{#if qualityReport && qualityReport.length > 0}
		{@const sortedReport = [...qualityReport].sort((a: { score?: number }, b: { score?: number }) => (a.score ?? 0) - (b.score ?? 0))}
		<div class="space-y-4">
			{#each sortedReport as item}
				{@const score = item.score ?? 0}
				{@const isLowQuality = score < 6}
				{@const isMediumQuality = score >= 6 && score <= 8}
				{@const isHighQuality = score > 8}
				<div data-testid="quality-item" class={`border-l-4 rounded-xl p-5 transition-all shadow-sm border border-gray-200 animate-fade-in-up ${
					isLowQuality
						? 'border-l-red-500 bg-red-50/30'
						: isMediumQuality
							? 'border-l-amber-500 bg-amber-50/30'
							: 'border-l-green-500 bg-green-50/30'
				}`}>
					<div class="flex items-start justify-between gap-4">
						<div class="flex-1 min-w-0">
							<div class="flex items-center gap-3 flex-wrap">
								<button
									onclick={() => onviewdocument(item.document, item.document_id)}
									class="text-base font-bold text-contrast hover:text-accent hover:underline text-left truncate"
									title="Click to view document"
								>
									{item.document}
								</button>
								{#if isLowQuality}
									<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-black bg-red-600 text-white uppercase tracking-tighter">
										Review Required
									</span>
								{/if}
							</div>
							<div class="flex items-center gap-6 mt-4">
								<!-- Score Bar -->
								<div class="flex items-center gap-3 flex-1 max-w-sm">
									<div class="flex-1 h-3 bg-gray-200 rounded-full overflow-hidden shadow-inner">
										<div
											class={`h-full rounded-full transition-all duration-700 shadow-sm ${
												isLowQuality ? 'bg-red-500' : isMediumQuality ? 'bg-amber-500' : 'bg-green-500'
											}`}
											style="width: {(score / 10) * 100}%"
										></div>
									</div>
									<span class={`text-sm font-black min-w-[3.5rem] ${
										isLowQuality ? 'text-red-700' : isMediumQuality ? 'text-amber-700' : 'text-green-700'
									}`}>
										{item.score?.toFixed ? item.score.toFixed(1) : item.score}/10
									</span>
								</div>
								<div class="flex items-center gap-1.5 text-xs font-bold text-gray-400 uppercase tracking-widest">
									<span>Confidence:</span>
									<span class={
										item.confidence_level === 'high' ? 'text-green-600' :
										item.confidence_level === 'medium' ? 'text-amber-600' : 'text-red-600'
									}>{item.confidence_level || 'N/A'}</span>
								</div>
							</div>
						</div>
					</div>
					{#if item.issues && item.issues.length > 0}
						<div class="mt-5 p-4 bg-white/50 rounded-lg border border-gray-100">
							<p class="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Extraction Issues</p>
							<ul class={`space-y-1.5 ${isLowQuality ? 'text-red-900' : 'text-gray-700'}`}>
								{#each item.issues as issue}
									<li class="text-xs font-medium flex items-start">
										<span class={`mr-2 ${isLowQuality ? 'text-red-400' : 'text-gray-300'}`}>•</span>
										{issue}
									</li>
								{/each}
							</ul>
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{:else}
		<div data-testid="quality-empty" class="p-12 text-center bg-gray-50 rounded-xl border-2 border-dashed border-gray-200">
			<p class="text-gray-400 font-medium italic">No quality report data for this analysis.</p>
		</div>
	{/if}
</div>
