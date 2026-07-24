<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { writable } from 'svelte/store';
	import { Loader2, CheckCircle, Circle, XCircle, X } from 'lucide-svelte';
	import { env } from '$env/dynamic/public';
	import { progressStore } from '$lib/stores/progressStore';
	import type { EnhancedProgressState } from '$lib/stores/progressStore';
	import { formatEta, livenessLine, substanceLine } from '$lib/utils/waitDisplay';

	// Trustworthy-Wait line (Task 7): gated behind a flag so the default
	// experience is byte-for-byte unchanged. Matches the PUBLIC_ env
	// accessor pattern used elsewhere in the app (see +page.svelte for
	// [id] cases, VerificationHub.svelte).
	const trustworthyWait = env.PUBLIC_ENABLE_TRUSTWORTHY_WAIT === 'true';

	let {
		analysisId,
		jobId = null,
		pollingOnly = false,
		onComplete,
		onError,
		onCancel
	}: {
		analysisId: string;
		jobId?: string | null;
		pollingOnly?: boolean;
		onComplete?: () => void;
		onError?: (error: string) => void;
		onCancel?: () => void;
	} = $props();

	// Use the enhanced progress store
	let state = $derived($progressStore as EnhancedProgressState);
	
	// Track previous status to detect transition to completed/error
	let prevStatus = '';
	let completionTimeout: ReturnType<typeof setTimeout> | null = null;

	// Safety valve: if the component is alive too long without reaching a
	// terminal state, stop listening and report an error.
	// Durable mode (Railway worker): 60 min — large cases take 30-60 min.
	// Legacy mode: 10 min — Vercel SSE/polling has shorter lifecycle.
	let safetyTimer: ReturnType<typeof setTimeout> | null = null;
	const MAX_PROGRESS_AGE_MS = jobId ? 60 * 60 * 1000 : 10 * 60 * 1000;

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
		// Start listening to the analysis stream.
		// In durable mode, pass jobId to poll the job endpoint instead.
		await progressStore.startListening(analysisId, {
			pollingOnly,
			jobId: jobId ?? undefined,
		});

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

	// Elapsed timer per active stage — uses a Svelte store for reactivity
	const elapsedStore = writable<Record<string, number>>({});
	let timerInterval: ReturnType<typeof setInterval> | null = null;

	function startElapsedTimer() {
		if (timerInterval) return;
		timerInterval = setInterval(() => {
			const now = Date.now();
			elapsedStore.update(prev => {
				const updated = { ...prev };
				for (const stage of state.stages) {
					if (stage.status === 'active' && stage.startedAt) {
						updated[stage.id] = Math.floor((now - new Date(stage.startedAt).getTime()) / 1000);
					} else if (stage.status === 'active' && !stage.startedAt) {
						updated[stage.id] = (prev[stage.id] ?? 0) + 1;
					}
				}
				return updated;
			});
		}, 1000);
	}

	$effect(() => {
		const hasActive = state.stages.some(s => s.status === 'active');
		if (hasActive) {
			startElapsedTimer();
		} else if (timerInterval && !hasActive) {
			clearInterval(timerInterval);
			timerInterval = null;
		}
	});

	onDestroy(() => {
		if (timerInterval) {
			clearInterval(timerInterval);
			timerInterval = null;
		}
	});

	function formatElapsed(seconds: number): string {
		const m = Math.floor(seconds / 60);
		const s = seconds % 60;
		return `${m}:${String(s).padStart(2, '0')}`;
	}

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

	<!-- Trustworthy-Wait line: step / substance / eta / liveness.
	     Flag-gated and only rendered for an explicitly active run so
	     older ticks (uiState undefined) or terminal states never show it. -->
	{#if trustworthyWait && (state.uiState === 'running' || state.uiState === 'queued')}
		<div class="mb-4 space-y-0.5">
			<p class="tw-step text-sm font-medium text-contrast">
				Step {state.stepIndex} of {state.stepTotal} · {state.stepLabel}
			</p>
			<p class="tw-substance text-xs text-gray-500">
				{substanceLine(state.itemsDone, state.itemsTotal, state.stepIndex)}
				{#if formatEta(state.etaSeconds)} · {formatEta(state.etaSeconds)}{/if}
			</p>
			<p class="tw-liveness text-xs text-gray-400">
				{livenessLine(state.healthy, null)}
			</p>
		</div>
	{/if}

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
			<div class="py-1.5 px-2 rounded-lg {stage.status === 'active' ? 'bg-accent/10 stage-pulse' : ''}">
				<div class="flex items-center gap-3">
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
					{#if stage.status === 'active' && $elapsedStore[stage.id] !== undefined}
						<span class="ml-auto text-xs text-gray-400 tabular-nums">
							{formatElapsed($elapsedStore[stage.id])}
						</span>
					{/if}
				</div>
				{#if stage.id === 'analyzing' && stage.status === 'active' && state.current_doc}
					<div class="text-xs text-gray-400 ml-7 mt-0.5">
						{state.current_doc.name} ({state.current_doc.index}/{state.current_doc.total})
					</div>
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

<style>
	@keyframes stage-pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.7; }
	}

	:global(.stage-pulse) {
		animation: stage-pulse 3s ease-in-out infinite;
	}

	@media (prefers-reduced-motion: reduce) {
		:global(.stage-pulse) {
			animation: none;
		}
	}
</style>
