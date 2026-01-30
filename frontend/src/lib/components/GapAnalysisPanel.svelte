<script lang="ts">
	import { slide } from 'svelte/transition';
	import {
		AlertCircle,
		AlertTriangle,
		Info,
		FileQuestion,
		FileX,
		Calendar,
		ShieldAlert,
		ClipboardList,
		Copy,
		Check,
		ChevronDown
	} from 'lucide-svelte';
	import type { GapAnalysisResult, GapCategory, GapItem, GapSeverity } from '$lib/types';
	import Badge from '$lib/components/ui/Badge.svelte';

	// Props
	export let gapAnalysis: GapAnalysisResult;
	export let caseId: string;

	// State
	let selectedSeverity: GapSeverity | 'all' = 'all';
	let selectedCategory: GapCategory | 'all' = 'all';
	let expandedGaps = new Set<string>();
	let copiedGaps = new Set<string>();

	// Get all gaps as a flat array
	$: allGaps = Object.values(gapAnalysis.gaps_by_category).flat();

	// Filter gaps based on selected severity and category
	$: filteredGaps = allGaps.filter((gap) => {
		const severityMatch = selectedSeverity === 'all' || gap.severity === selectedSeverity;
		const categoryMatch = selectedCategory === 'all' || gap.category === selectedCategory;
		return severityMatch && categoryMatch;
	});

	// Toggle gap expansion
	function toggleGap(gapId: string) {
		if (expandedGaps.has(gapId)) {
			expandedGaps.delete(gapId);
		} else {
			expandedGaps.add(gapId);
		}
		expandedGaps = expandedGaps;
	}

	// Copy gap to clipboard
	async function copyGap(gap: GapItem, event: MouseEvent) {
		event.stopPropagation();
		const text = `${gap.title}\n\n${gap.description}\n\nImpact: ${gap.impact_on_case}\n\nRecommendations:\n${gap.recommendations.map((r) => `- ${r}`).join('\n')}`;

		try {
			await navigator.clipboard.writeText(text);
			copiedGaps.add(gap.gap_id);
			copiedGaps = copiedGaps;

			// Reset after 2 seconds
			setTimeout(() => {
				copiedGaps.delete(gap.gap_id);
				copiedGaps = copiedGaps;
			}, 2000);
		} catch (err) {
			console.error('Failed to copy:', err);
		}
	}

	// Get severity color class
	function getSeverityColorClass(severity: GapSeverity): string {
		switch (severity) {
			case 'critical':
				return 'bg-red-100 text-red-800 border-red-300';
			case 'high':
				return 'bg-orange-100 text-orange-800 border-orange-300';
			case 'medium':
				return 'bg-yellow-100 text-yellow-800 border-yellow-300';
			case 'low':
				return 'bg-blue-100 text-blue-800 border-blue-300';
			default:
				return 'bg-gray-100 text-gray-800 border-gray-300';
		}
	}

	// Get severity icon component
	function getSeverityIcon(severity: GapSeverity) {
		switch (severity) {
			case 'critical':
				return AlertCircle;
			case 'high':
				return AlertTriangle;
			case 'medium':
			case 'low':
				return Info;
			default:
				return Info;
		}
	}

	// Get category icon component
	function getCategoryIcon(category: GapCategory) {
		switch (category) {
			case 'missing_document':
				return FileX;
			case 'factual_contradiction':
				return ShieldAlert;
			case 'timeline_gap':
				return Calendar;
			case 'unverifiable_claim':
				return FileQuestion;
			case 'incomplete_info':
				return ClipboardList;
			default:
				return Info;
		}
	}

	// Get category label
	function getCategoryLabel(category: GapCategory): string {
		switch (category) {
			case 'missing_document':
				return 'Missing Document';
			case 'factual_contradiction':
				return 'Contradiction';
			case 'timeline_gap':
				return 'Timeline Gap';
			case 'unverifiable_claim':
				return 'Unverifiable Claim';
			case 'incomplete_info':
				return 'Incomplete Info';
			default:
				return category;
		}
	}

	// Get completeness score color
	$: scoreColor =
		gapAnalysis.overall_completeness_score >= 90
			? 'text-green-600'
			: gapAnalysis.overall_completeness_score >= 75
				? 'text-blue-600'
				: gapAnalysis.overall_completeness_score >= 60
					? 'text-yellow-600'
					: gapAnalysis.overall_completeness_score >= 40
						? 'text-orange-600'
						: 'text-red-600';
</script>

<div class="space-y-6">
	<!-- Header Card -->
	<div class="card-standard">
		<h2 class="text-2xl font-heading font-bold text-contrast mb-6 flex items-center gap-2">
			<svelte:component this={ShieldAlert} class="h-6 w-6 text-accent" />
			Case Completeness Assessment
		</h2>

		<div class="space-y-6">
			<!-- Completeness Score -->
			<div class="flex items-center justify-between p-6 bg-gradient-to-br from-gray-50 to-white rounded-xl border border-gray-100">
				<div class="space-y-2">
					<p class="text-sm font-medium text-gray-600">Completeness Score</p>
					<p class="text-4xl font-bold {scoreColor}">
						{gapAnalysis.overall_completeness_score.toFixed(0)}/100
					</p>
				</div>
				<div class="flex flex-wrap gap-2">
					{#if gapAnalysis.critical_count > 0}
						<Badge variant="error">{gapAnalysis.critical_count} Critical</Badge>
					{/if}
					{#if gapAnalysis.high_count > 0}
						<span class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-orange-100 text-orange-800 border border-orange-300">
							{gapAnalysis.high_count} High
						</span>
					{/if}
					{#if gapAnalysis.medium_count > 0}
						<span class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-yellow-100 text-yellow-800 border border-yellow-300">
							{gapAnalysis.medium_count} Medium
						</span>
					{/if}
					{#if gapAnalysis.low_count > 0}
						<Badge variant="info">{gapAnalysis.low_count} Low</Badge>
					{/if}
				</div>
			</div>

			<!-- Attorney Summary -->
			<div class="rounded-lg bg-blue-50 border border-blue-200 p-4">
				<p class="text-sm font-semibold text-blue-900 mb-2">Attorney Summary</p>
				<p class="text-sm text-blue-800">{gapAnalysis.attorney_summary}</p>
			</div>

			<!-- Filters -->
			<div class="space-y-4">
				<div class="flex flex-wrap gap-2">
					<span class="text-sm font-medium text-gray-700 self-center">Severity:</span>
					<button
						class="px-3 py-1 text-sm rounded-md transition-colors {selectedSeverity === 'all' ? 'bg-accent text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}"
						onclick={() => (selectedSeverity = 'all')}
					>
						All ({allGaps.length})
					</button>
					<button
						class="px-3 py-1 text-sm rounded-md transition-colors {selectedSeverity === 'critical' ? 'bg-red-500 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}"
						onclick={() => (selectedSeverity = 'critical')}
					>
						Critical ({gapAnalysis.critical_count})
					</button>
					<button
						class="px-3 py-1 text-sm rounded-md transition-colors {selectedSeverity === 'high' ? 'bg-orange-500 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}"
						onclick={() => (selectedSeverity = 'high')}
					>
						High ({gapAnalysis.high_count})
					</button>
					<button
						class="px-3 py-1 text-sm rounded-md transition-colors {selectedSeverity === 'medium' ? 'bg-yellow-500 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}"
						onclick={() => (selectedSeverity = 'medium')}
					>
						Medium ({gapAnalysis.medium_count})
					</button>
					<button
						class="px-3 py-1 text-sm rounded-md transition-colors {selectedSeverity === 'low' ? 'bg-blue-500 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}"
						onclick={() => (selectedSeverity = 'low')}
					>
						Low ({gapAnalysis.low_count})
					</button>
				</div>

				<div class="flex flex-wrap gap-2">
					<span class="text-sm font-medium text-gray-700 self-center">Category:</span>
					<button
						class="px-3 py-1 text-sm rounded-md transition-colors {selectedCategory === 'all' ? 'bg-accent text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}"
						onclick={() => (selectedCategory = 'all')}
					>
						All
					</button>
					<button
						class="px-3 py-1 text-sm rounded-md transition-colors flex items-center gap-1 {selectedCategory === 'missing_document' ? 'bg-accent text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}"
						onclick={() => (selectedCategory = 'missing_document')}
					>
						<svelte:component this={FileX} class="h-3 w-3" />
						Missing Docs
					</button>
					<button
						class="px-3 py-1 text-sm rounded-md transition-colors flex items-center gap-1 {selectedCategory === 'factual_contradiction' ? 'bg-accent text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}"
						onclick={() => (selectedCategory = 'factual_contradiction')}
					>
						<svelte:component this={ShieldAlert} class="h-3 w-3" />
						Contradictions
					</button>
					<button
						class="px-3 py-1 text-sm rounded-md transition-colors flex items-center gap-1 {selectedCategory === 'timeline_gap' ? 'bg-accent text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}"
						onclick={() => (selectedCategory = 'timeline_gap')}
					>
						<svelte:component this={Calendar} class="h-3 w-3" />
						Timeline
					</button>
					<button
						class="px-3 py-1 text-sm rounded-md transition-colors flex items-center gap-1 {selectedCategory === 'unverifiable_claim' ? 'bg-accent text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}"
						onclick={() => (selectedCategory = 'unverifiable_claim')}
					>
						<svelte:component this={FileQuestion} class="h-3 w-3" />
						Unverifiable
					</button>
					<button
						class="px-3 py-1 text-sm rounded-md transition-colors flex items-center gap-1 {selectedCategory === 'incomplete_info' ? 'bg-accent text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}"
						onclick={() => (selectedCategory = 'incomplete_info')}
					>
						<svelte:component this={ClipboardList} class="h-3 w-3" />
						Incomplete
					</button>
				</div>
			</div>
		</div>
	</div>

	<!-- Gap Items -->
	<div class="space-y-4">
		{#if filteredGaps.length === 0}
			<div class="card-standard text-center py-12">
				<svelte:component this={Info} class="h-16 w-16 mx-auto mb-4 text-gray-300" />
				<p class="text-gray-500">No gaps found matching the selected filters.</p>
			</div>
		{:else}
			{#each filteredGaps as gap (gap.gap_id)}
				{@const SeverityIcon = getSeverityIcon(gap.severity)}
				{@const CategoryIcon = getCategoryIcon(gap.category)}
				{@const isExpanded = expandedGaps.has(gap.gap_id)}
				{@const isCopied = copiedGaps.has(gap.gap_id)}

				<div
					class="card-standard cursor-pointer hover:shadow-md transition-shadow {
						gap.severity === 'critical' ? 'border-l-4 border-l-red-500' :
						gap.severity === 'high' ? 'border-l-4 border-l-orange-500' : ''
					}"
					onclick={() => toggleGap(gap.gap_id)}
				>
					<div class="flex items-start justify-between gap-4">
						<div class="flex-1">
							<div class="flex items-center gap-2 mb-3">
								<span class="inline-flex items-center px-2 py-1 rounded text-xs font-medium border {getSeverityColorClass(gap.severity)}">
									<svelte:component this={SeverityIcon} class="h-3 w-3 mr-1" />
									{gap.severity.toUpperCase()}
								</span>
								<span class="inline-flex items-center px-2 py-1 rounded text-xs font-medium border bg-gray-100 text-gray-700 border-gray-300">
									<svelte:component this={CategoryIcon} class="h-3 w-3 mr-1" />
									{getCategoryLabel(gap.category)}
								</span>
								{#if gap.affected_issue}
									<span class="inline-flex items-center px-2 py-1 rounded text-xs font-medium border bg-blue-50 text-blue-700 border-blue-200">
										Affects: {gap.affected_issue}
									</span>
								{/if}
							</div>
							<h3 class="text-lg font-semibold text-contrast mb-2 flex items-center gap-2">
								{gap.title}
								<svelte:component this={ChevronDown} class="h-4 w-4 text-gray-400 transition-transform {isExpanded ? 'rotate-180' : ''}" />
							</h3>
						</div>
						<button
							class="p-2 text-gray-400 hover:text-gray-600 transition-colors rounded"
							onclick={(e) => copyGap(gap, e)}
							title="Copy gap details"
						>
							{#if isCopied}
								<svelte:component this={Check} class="h-5 w-5 text-green-500" />
							{:else}
								<svelte:component this={Copy} class="h-5 w-5" />
							{/if}
						</button>
					</div>

					{#if isExpanded}
						<div transition:slide class="mt-4 space-y-4 pt-4 border-t border-gray-200">
							<div>
								<p class="text-sm font-semibold text-gray-700 mb-1">Description</p>
								<p class="text-sm text-gray-600">{gap.description}</p>
							</div>

							<div>
								<p class="text-sm font-semibold text-gray-700 mb-1">Impact on Case</p>
								<p class="text-sm text-gray-600">{gap.impact_on_case}</p>
							</div>

							{#if gap.recommendations.length > 0}
								<div>
									<p class="text-sm font-semibold text-gray-700 mb-2">Recommendations</p>
									<ul class="list-disc list-inside space-y-1">
										{#each gap.recommendations as recommendation}
											<li class="text-sm text-gray-600">{recommendation}</li>
										{/each}
									</ul>
								</div>
							{/if}

							{#if gap.related_documents.length > 0}
								<div>
									<p class="text-sm font-semibold text-gray-700 mb-2">Related Documents</p>
									<div class="flex flex-wrap gap-2">
										{#each gap.related_documents as doc}
											<span class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-gray-100 text-gray-700 border border-gray-300">
												{doc}
											</span>
										{/each}
									</div>
								</div>
							{/if}
						</div>
					{/if}
				</div>
			{/each}
		{/if}
	</div>
</div>
