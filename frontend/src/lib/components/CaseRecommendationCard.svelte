<script lang="ts">
	import { CheckCircle, FileQuestion, Scale, XCircle, ChevronRight, Loader2 } from 'lucide-svelte';
	import type { CaseRecommendation, CaseRecommendationCategory, ConfidenceLevel } from '$lib/types';
	import Badge from '$lib/components/ui/Badge.svelte';

	// Props
	export let recommendation: CaseRecommendation;
	export let onGenerateLetter: () => void;
	export let generatingLetter: boolean = false;

	// Get icon based on category
	function getCategoryIcon(category: CaseRecommendationCategory) {
		switch (category) {
			case 'strong_case':
				return CheckCircle;
			case 'needs_documentation':
				return FileQuestion;
			case 'settlement_recommended':
				return Scale;
			case 'not_viable':
				return XCircle;
			default:
				return FileQuestion;
		}
	}

	// Get color classes based on recommendation color
	function getColorClasses(color: string): {
		bg: string;
		border: string;
		icon: string;
		button: string;
	} {
		switch (color) {
			case 'green':
				return {
					bg: 'bg-green-50',
					border: 'border-green-300',
					icon: 'text-green-600',
					button: 'bg-green-600 hover:bg-green-700 text-white'
				};
			case 'yellow':
				return {
					bg: 'bg-yellow-50',
					border: 'border-yellow-300',
					icon: 'text-yellow-600',
					button: 'bg-yellow-600 hover:bg-yellow-700 text-white'
				};
			case 'orange':
				return {
					bg: 'bg-orange-50',
					border: 'border-orange-300',
					icon: 'text-orange-600',
					button: 'bg-orange-600 hover:bg-orange-700 text-white'
				};
			case 'red':
				return {
					bg: 'bg-red-50',
					border: 'border-red-300',
					icon: 'text-red-600',
					button: 'bg-red-600 hover:bg-red-700 text-white'
				};
			default:
				return {
					bg: 'bg-gray-50',
					border: 'border-gray-300',
					icon: 'text-gray-600',
					button: 'bg-gray-600 hover:bg-gray-700 text-white'
				};
		}
	}

	// Get confidence badge variant - maps to valid Badge variants
	function getConfidenceBadgeVariant(confidence: ConfidenceLevel): 'success' | 'warning' | 'neutral' {
		switch (confidence) {
			case 'high':
				return 'success';
			case 'medium':
				return 'warning';
			case 'low':
				return 'neutral';
			default:
				return 'neutral';
		}
	}

	// Get button text based on letter type
	function getButtonText(letterType: string): string {
		switch (letterType) {
			case 'proceed':
				return 'Generate Engagement Letter';
			case 'request_documents':
				return 'Generate Document Request';
			case 'settlement_advisory':
				return 'Generate Settlement Advisory';
			case 'declination':
				return 'Generate Declination Letter';
			default:
				return 'Generate Letter';
		}
	}

	$: Icon = getCategoryIcon(recommendation.category);
	$: colors = getColorClasses(recommendation.category_color);
</script>

<div
	class="rounded-lg border-2 p-6 mb-6 {colors.bg} {colors.border}"
	role="region"
	aria-label="Case Recommendation"
>
	<!-- Header with Icon and Title -->
	<div class="flex items-start gap-4">
		<!-- Large Icon -->
		<div class="flex-shrink-0">
			<div class="w-14 h-14 rounded-full flex items-center justify-center {colors.bg} border {colors.border}">
				<svelte:component this={Icon} class="w-8 h-8 {colors.icon}" />
			</div>
		</div>

		<!-- Content -->
		<div class="flex-1 min-w-0">
			<!-- Title Row with Category and Confidence -->
			<div class="flex items-center gap-3 mb-2 flex-wrap">
				<h3 class="text-xl font-semibold text-gray-900">
					{recommendation.category_display_name}
				</h3>
				<Badge variant={getConfidenceBadgeVariant(recommendation.confidence)}>
					{recommendation.confidence.charAt(0).toUpperCase() + recommendation.confidence.slice(1)} Confidence
				</Badge>
			</div>

			<!-- Reasoning -->
			<p class="text-gray-700 mb-4 leading-relaxed">
				{recommendation.reasoning}
			</p>

			<!-- Next Steps -->
			<div class="mb-4">
				<h4 class="text-sm font-medium text-gray-600 mb-2 uppercase tracking-wide">
					Recommended Next Steps
				</h4>
				<ul class="space-y-2">
					{#each recommendation.next_steps as step}
						<li class="flex items-start gap-2 text-gray-700">
							<ChevronRight class="w-4 h-4 mt-1 flex-shrink-0 {colors.icon}" />
							<span>{step}</span>
						</li>
					{/each}
				</ul>
			</div>

			<!-- Generate Letter Button -->
			<div class="flex justify-end pt-2">
				<button
					on:click={onGenerateLetter}
					disabled={generatingLetter}
					class="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium transition-colors {colors.button} disabled:opacity-50 disabled:cursor-not-allowed"
				>
					{#if generatingLetter}
						<Loader2 class="w-4 h-4 animate-spin" />
						Generating...
					{:else}
						{getButtonText(recommendation.suggested_letter_type)}
					{/if}
				</button>
			</div>
		</div>
	</div>
</div>
