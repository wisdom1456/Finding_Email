<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Loader2, CheckCircle, Circle, XCircle, X } from 'lucide-svelte';
	import { progressStore } from '$lib/stores/progressStore';
	import type { EnhancedProgressState } from '$lib/stores/progressStore';

	let { 
		analysisId,
		onComplete,
		onError,
		onCancel
	}: { 
		analysisId: string;
		onComplete?: () => void;
		onError?: (error: string) => void;
		onCancel?: () => void;
	} = $props();

	// Use the enhanced progress store
	let state = $derived($progressStore as EnhancedProgressState);
	
	// Track previous status to detect transition to completed/error
	let prevStatus = '';
	let completionTimeout: ReturnType<typeof setTimeout> | null = null;

	// Safety valve: if the component is alive for more than 10 minutes without
	// reaching a terminal state, stop listening and report an error.
	// This prevents the UI from staying stuck indefinitely.
	let safetyTimer: ReturnType<typeof setTimeout> | null = null;
	const MAX_PROGRESS_AGE_MS = 10 * 60 * 1000; // 10 minutes

	$effect(() => {
		if (state.status === 'completed' && prevStatus !== 'completed') {
			if (completionTimeout) clearTimeout(completionTimeout);
			completionTimeout = setTimeout(() => {
				onComplete?.();
			}, 1500);
		}
		if (state.status === 'error' && prevStatus !== 'error') {
			onError?.(state.message || 'An unknown error occurred during analysis');
		}
		prevStatus = state.status;
	});

	onMount(async () => {
		// Start listening to the analysis stream
		await progressStore.startListening(analysisId);

		// Safety valve — prevent indefinite stuck state
		safetyTimer = setTimeout(() => {
			const current = state.status;
			if (current !== 'completed' && current !== 'error' && current !== 'idle') {
				console.warn('[InlineAnalysisProgress] Safety timeout — forcing error state after 10 min');
				progressStore.stopListening();
				onError?.('Analysis progress timed out. The analysis may have completed — try refreshing the page.');
			}
		}, MAX_PROGRESS_AGE_MS);
	});

	onDestroy(() => {
		if (completionTimeout) {
			clearTimeout(completionTimeout);
			completionTimeout = null;
		}
		if (safetyTimer) {
			clearTimeout(safetyTimer);
			safetyTimer = null;
		}
		progressStore.stopListening();
	});

	// Calculate overall progress: use state.percent directly, or calculate from stages
	let overallProgress = $derived.by(() => {
		// If we have a direct percent from SSE events, use it
		if (state.percent > 0) {
			return state.percent;
		}
		// Fallback: calculate from stages
		if (state.stages.length === 0) return 0;
		const completedStages = state.stages.filter(s => s.status === 'completed').length;
		const activeStage = state.stages.find(s => s.status === 'active');
		const activeProgress = activeStage ? activeStage.progress / 100 : 0;
		return Math.round(((completedStages + activeProgress) / state.stages.length) * 100);
	});
</script>

<div class="card-standard border-2 border-accent/30 bg-accent/5">
	<!-- Header -->
	<div class="flex items-center justify-between mb-4">
		<div class="flex items-center gap-3">
			<div class="p-2 rounded-lg bg-accent/20">
				<Loader2 class="w-5 h-5 text-accent animate-spin" />
			</div>
			<div>
				<h3 class="font-heading font-semibold text-contrast">Analysis in Progress</h3>
				<p class="text-sm text-gray-500">{state.message || 'Initializing...'}</p>
			</div>
		</div>
		{#if onCancel}
			<button 
				onclick={onCancel}
				class="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
				title="Cancel analysis"
			>
				<X class="w-5 h-5" />
			</button>
		{/if}
	</div>

	<!-- Progress Bar -->
	<div class="mb-4">
		<div class="flex justify-between text-xs text-gray-500 mb-1">
			<span>Progress</span>
			<span>{overallProgress}%</span>
		</div>
		<div class="h-2 bg-gray-200 rounded-full overflow-hidden">
			<div 
				class="h-full bg-accent transition-all duration-500 ease-out"
				style="width: {overallProgress}%"
			></div>
		</div>
	</div>

	<!-- Stage Checklist -->
	<div class="space-y-2">
		{#each state.stages as stage}
			<div class="flex items-center gap-3 py-1.5 px-2 rounded-lg {stage.status === 'active' ? 'bg-accent/10' : ''}">
				{#if stage.status === 'completed'}
					<CheckCircle class="w-4 h-4 text-accent flex-shrink-0" />
				{:else if stage.status === 'active'}
					<Loader2 class="w-4 h-4 text-accent animate-spin flex-shrink-0" />
				{:else if stage.status === 'error'}
					<XCircle class="w-4 h-4 text-red-500 flex-shrink-0" />
				{:else}
					<Circle class="w-4 h-4 text-gray-300 flex-shrink-0" />
				{/if}
				<span class={`text-sm ${
					stage.status === 'completed' ? 'text-gray-700 font-medium' : 
					stage.status === 'active' ? 'text-contrast font-semibold' : 
					stage.status === 'error' ? 'text-red-600' :
					'text-gray-400'
				}`}>
					{stage.name}
				</span>
				{#if stage.extracted}
					<span class="ml-auto text-xs text-accent font-medium">
						{stage.extracted.count} {stage.extracted.type}
					</span>
				{/if}
			</div>
		{/each}
	</div>

	<!-- Error State -->
	{#if state.status === 'error'}
		<div class="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
			<p class="text-sm text-red-700 font-medium">{state.message || 'Analysis failed'}</p>
		</div>
	{/if}

	<!-- Completion State -->
	{#if state.status === 'completed'}
		<div class="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg flex items-center gap-2">
			<CheckCircle class="w-5 h-5 text-green-600" />
			<p class="text-sm text-green-700 font-medium">Analysis complete! Redirecting to results...</p>
		</div>
	{/if}

	<!-- Stats (compact) -->
	<div class="mt-4 pt-3 border-t border-gray-200 flex items-center gap-4 text-xs text-gray-500">
		<span>Time: {Math.floor(state.stats.elapsedSeconds / 60)}:{String(Math.floor(state.stats.elapsedSeconds % 60)).padStart(2, '0')}</span>
		<span>•</span>
		<span>Tokens: {state.stats.tokens_used.toLocaleString()}</span>
		<span>•</span>
		<span>Model: {state.stats.model}</span>
	</div>
</div>
