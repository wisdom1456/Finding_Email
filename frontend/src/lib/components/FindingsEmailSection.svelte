<script lang="ts">
	import { getApiUrl } from '$lib/config';
	import { getSecureSession } from '$lib/supabase';
	import { toastStore } from '$lib/stores/toastStore';
	import { parseMarkdown, sanitizeHtml } from '$lib/utils/markdown';
	import { letterHtmlToPlainText, normalizeLetterHtml } from '$lib/utils/letterCopy';
	import { SSEEventParser } from '$lib/utils/sseEventParser';
	import { fetchWithRetry } from '$lib/utils/fetchWithRetry';
	import { onDestroy } from 'svelte';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
	import { AlertTriangle } from 'lucide-svelte';
	import {
		FINDINGS_PHASE_ORDER,
		FINDINGS_PHASE_LABELS,
		type FindingsGenerationState
	} from './FindingsEmailSection.utils';

	let {
		analysisId,
		caseId,
		hasMultiStageSupport,
		multiStageError,
		gapAnalysis,
		recommendationLetters,
		initialFindingsLetter = null,
		initialFindingsQualityReport = null,
		initialFindingsMetrics = null,
	}: {
		analysisId: string;
		caseId: string;
		hasMultiStageSupport: boolean;
		multiStageError: string | null | undefined;
		gapAnalysis: any;
		recommendationLetters: Record<string, string>;
		initialFindingsLetter?: string | null;
		initialFindingsQualityReport?: Record<string, any> | null;
		initialFindingsMetrics?: Record<string, any> | null;
	} = $props();

	let findingsLetter = $state<string | null>(initialFindingsLetter);
	let findingsGenerationState = $state<FindingsGenerationState>(initialFindingsLetter ? 'complete' : 'idle');
	let findingsPhaseMessage = $state(initialFindingsLetter ? 'Complete' : '');
	let findingsGenerationPercent = $state(0);
	let findingsQualityReport = $state<Record<string, any> | null>(initialFindingsQualityReport);
	let findingsGenerationMetrics = $state<Record<string, any> | null>(initialFindingsMetrics);
	let findingsRecoverableError = $state<string | null>(null);
	let findingsDraftStarted = $state(false);
	let generatingFindings = $state(false);
	let forceGeneration = $state(false);
	let insufficientDocError = $state<{ completeness_score: number; critical_gaps: number } | null>(null);

	type ActiveFindingsRequest = {
		requestId: number;
		controller: AbortController;
	};
	let activeFindingsRequest: ActiveFindingsRequest | null = null;
	let findingsRequestCounter = 0;

	onDestroy(() => {
		activeFindingsRequest?.controller.abort();
		activeFindingsRequest = null;
	});



	async function generateFindingsLetter() {
		const previousRequest = activeFindingsRequest;
		if (previousRequest) {
			previousRequest.controller.abort();
		}

		const controller = new AbortController();
		const requestId = ++findingsRequestCounter;
		activeFindingsRequest = { requestId, controller };
		const isCurrentRequest = () => activeFindingsRequest?.requestId === requestId;

		generatingFindings = true;
		findingsGenerationState = 'connecting';
		findingsPhaseMessage = 'Connecting...';
		findingsGenerationPercent = 0;
		findingsRecoverableError = null;
		findingsDraftStarted = false;
		insufficientDocError = null;
		findingsQualityReport = null;
		findingsGenerationMetrics = null;

		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const params = new URLSearchParams({
				schema_version: '2',
				mode: 'strict_quality'
			});
			if (forceGeneration) {
				params.set('force_generation', 'true');
			}

			const response = await fetchWithRetry(`${apiUrl}/api/analysis/${analysisId}/letter/stream?${params.toString()}`, {
				headers: { Authorization: `Bearer ${session.access_token}` },
				signal: controller.signal
			});

			if (!response.ok) {
				const detail = await response.json().catch(() => ({}));
				if (detail?.detail?.error === 'documentation_insufficient') {
					if (isCurrentRequest()) {
						insufficientDocError = {
							completeness_score: detail.detail.completeness_score,
							critical_gaps: detail.detail.critical_gaps
						};
						toastStore.warning('Case documentation is insufficient. Review gaps or enable force override.');
						findingsGenerationState = 'idle';
						findingsPhaseMessage = '';
					}
					return;
				}
				throw new Error(detail?.detail?.message || detail?.detail || 'Failed to stream findings email');
			}

			const reader = response.body?.getReader();
			if (!reader) throw new Error('No reader available');

			const decoder = new TextDecoder();
			const parser = new SSEEventParser();
			let markdownBuffer = '';
			let pendingTokens = '';
			let flushTimer: ReturnType<typeof setTimeout> | null = null;
			let processedEventCount = 0;
			let streamDone = false;
			let hadUnrecoverableError = false;

			const renderFindingsPreview = () => {
				if (!isCurrentRequest()) return;
				findingsLetter = `<div class="legal-letter">${parseMarkdown(markdownBuffer)}</div>`;
			};

			const flushPendingTokens = () => {
				if (!isCurrentRequest()) return;
				if (pendingTokens) {
					markdownBuffer += pendingTokens;
					pendingTokens = '';
					renderFindingsPreview();
				}
				if (flushTimer) {
					clearTimeout(flushTimer);
					flushTimer = null;
				}
			};

			const queueToken = (token: string) => {
				if (!isCurrentRequest()) return;
				if (!findingsDraftStarted) {
					findingsDraftStarted = true;
					markdownBuffer = '';
					pendingTokens = '';
					findingsLetter = '';
				}
				pendingTokens += token;
				if (flushTimer) return;
				flushTimer = setTimeout(() => {
					if (!isCurrentRequest()) {
						pendingTokens = '';
						flushTimer = null;
						return;
					}
					if (!pendingTokens) {
						flushTimer = null;
						return;
					}
					markdownBuffer += pendingTokens;
					pendingTokens = '';
					flushTimer = null;
					renderFindingsPreview();
				}, 80);
			};

			const applyPhase = (phase: string, message?: string, percent?: number) => {
				if (!isCurrentRequest()) return;
				const allowed: FindingsGenerationState[] = [
					'strategy',
					'context_build',
					'draft_generation',
					'lint_validation',
					'repair',
					'polishing',
					'finalizing'
				];
				if (allowed.includes(phase as FindingsGenerationState)) {
					findingsGenerationState = phase as FindingsGenerationState;
				}
				if (message) {
					findingsPhaseMessage = message;
				}
				if (typeof percent === 'number' && percent > findingsGenerationPercent) {
					findingsGenerationPercent = percent;
				}
			};

			while (true) {
				if (!isCurrentRequest()) {
					throw new DOMException('Findings request superseded', 'AbortError');
				}
				const { done, value } = await reader.read();
				if (done) {
					flushPendingTokens();
					break;
				}

				const chunk = decoder.decode(value, { stream: true });
				const events = parser.push(chunk);

				for (const data of events) {
					const eventType =
						(typeof data.event === 'string' && data.event) ||
						(typeof data.type === 'string' && data.type) ||
						(data.token ? 'token' : data.done ? 'done' : data.error ? 'error' : '');

					if (eventType === 'phase') {
						applyPhase(String(data.phase || ''), typeof data.message === 'string' ? data.message : undefined, typeof data.percent === 'number' ? data.percent : undefined);
					} else if (eventType === 'token' && typeof data.token === 'string') {
						findingsGenerationState = 'draft_generation';
						queueToken(data.token);
					} else if (eventType === 'quality') {
						if (data.quality_report && typeof data.quality_report === 'object') {
							findingsQualityReport = data.quality_report as Record<string, any>;
						}
						if (data.generation_metrics && typeof data.generation_metrics === 'object') {
							findingsGenerationMetrics = data.generation_metrics as Record<string, any>;
						}
					} else if (eventType === 'final') {
						flushPendingTokens();
						const content = data.content as Record<string, unknown> | undefined;
						if (content && typeof content.html === 'string') {
							findingsLetter = content.html;
						} else if (content && typeof content.markdown === 'string') {
							findingsLetter = `<div class="legal-letter">${parseMarkdown(content.markdown)}</div>`;
						}
						if (data.quality_report && typeof data.quality_report === 'object') {
							findingsQualityReport = data.quality_report as Record<string, any>;
						}
						if (data.generation_metrics && typeof data.generation_metrics === 'object') {
							findingsGenerationMetrics = data.generation_metrics as Record<string, any>;
						}
						findingsGenerationState = 'complete';
						findingsPhaseMessage = 'Complete';
					} else if (eventType === 'error') {
						const message =
							(typeof data.error === 'string' && data.error) || 'Findings email generation failed';
						const recoverable = Boolean(data.recoverable);
						if (recoverable) {
							findingsRecoverableError = message;
						} else {
							findingsGenerationState = 'error';
							findingsPhaseMessage = message;
							hadUnrecoverableError = true;
							throw new Error(message);
						}
					} else if (eventType === 'done') {
						flushPendingTokens();
						streamDone = true;
						break;
					}

					processedEventCount += 1;
					if (processedEventCount % 120 === 0) {
						await new Promise((resolve) => setTimeout(resolve, 0));
					}
				}

				if (streamDone) {
					break;
				}
			}

			flushPendingTokens();
			if (isCurrentRequest() && !hadUnrecoverableError) {
				findingsGenerationState = 'complete';
				findingsPhaseMessage = 'Complete';
			}
		} catch (err: any) {
			if (err?.name === 'AbortError') {
				if (isCurrentRequest()) {
					findingsGenerationState = 'cancelled';
					findingsPhaseMessage = 'Cancelled';
				}
			} else {
				const isNetworkError = err instanceof TypeError && /fetch|network/i.test(err.message);
				if (isNetworkError) {
					// Network dropped — auto-retry up to 3 times with increasing delays
					console.warn('Findings letter network error, will auto-retry on next call');
				}
				toastStore.error(err.message || 'Findings email generation failed. Click Generate again to retry.');
				if (isCurrentRequest()) {
					findingsGenerationState = 'error';
					findingsPhaseMessage = isNetworkError
						? 'Network interrupted. Click Generate to retry.'
						: (err.message || 'Findings email generation failed');
				}
			}
		} finally {
			if (activeFindingsRequest?.requestId === requestId) {
				activeFindingsRequest = null;
				generatingFindings = false;
				if (findingsGenerationState === 'connecting') {
					findingsGenerationState = 'idle';
					findingsPhaseMessage = '';
				}
			}
		}
	}

	function downloadLetter(letter: string, filename: string) {
		const cleanedLetter = normalizeLetterHtml(letter);
		const blob = new Blob([cleanedLetter], { type: 'text/html' });
		const url = URL.createObjectURL(blob);
		const link = document.createElement('a');
		link.href = url;
		link.download = filename;
		link.click();
		URL.revokeObjectURL(url);
	}

	async function copyLetterPlainText(letter: string, label: string) {
		try {
			const text = letterHtmlToPlainText(letter);
			if (!text) throw new Error('No text content available');
			await navigator.clipboard.writeText(text);
			toastStore.success(`${label} copied as plain text`);
		} catch (err: any) {
			toastStore.error(err?.message || `Failed to copy ${label.toLowerCase()}`);
		}
	}
</script>

{#if !hasMultiStageSupport}
	<div class="info-box border-amber-200 bg-amber-50">
		<p class="text-amber-900 font-medium">
			{#if multiStageError}
				<strong class="font-bold">⚠️ Advanced analysis failed:</strong> {multiStageError}.
				Findings email generation is unavailable for this specific analysis run.
			{:else}
				On-demand findings emails are unavailable because this case was processed with an older workflow.
			{/if}
			Please re-run analysis to enable this feature.
		</p>
	</div>
{:else}
	<section class="card-standard">
		<div class="flex items-center justify-between mb-6">
			<div>
				<h3 class="text-xl font-heading font-bold text-contrast">Findings Email</h3>
				<p class="text-sm text-gray-500 mt-1">Generate a client-ready findings email on demand.</p>
				{#if findingsGenerationMetrics?.repair_applied}
					<div class="mt-2 inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
						Quality pass applied
					</div>
				{/if}
				{#if findingsGenerationMetrics?.critic_applied}
					<div class="mt-2 ml-2 inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold bg-sky-50 text-sky-700 border border-sky-200">
						Critic-guided repair
					</div>
				{/if}
				{#if findingsQualityReport?.quality_report_v2}
					<div class="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-600">
						<span class="px-2 py-1 rounded border border-gray-200 bg-gray-50">
							Micro-explainers: {findingsQualityReport.quality_report_v2.term_explainer_passed ? 'Pass' : 'Needs review'}
						</span>
						<span class="px-2 py-1 rounded border border-gray-200 bg-gray-50">
							Evidence linkage: {Math.round((findingsQualityReport.quality_report_v2.evidence_linkage_score ?? 0) * 100)}%
						</span>
					</div>
				{/if}
			</div>
			<AsyncButton
				variant="primary"
				onclick={generateFindingsLetter}
				loading={generatingFindings}
				loadingText="Generating..."
			>
				Generate Email
			</AsyncButton>
		</div>

		{#if generatingFindings || (findingsGenerationState !== 'idle' && findingsGenerationState !== 'complete' && findingsGenerationState !== 'error' && findingsGenerationState !== 'cancelled')}
			<div class="mb-4">
				<div class="flex items-center gap-2 text-sm text-gray-600 mb-2">
					<div class="h-2.5 w-2.5 rounded-full bg-accent animate-pulse"></div>
					<span>{findingsPhaseMessage || FINDINGS_PHASE_LABELS[findingsGenerationState] || findingsGenerationState.replace(/_/g, ' ')}</span>
				</div>
				<!-- Phase progress steps -->
				<div class="flex items-center gap-1 ml-5">
					{#each FINDINGS_PHASE_ORDER as phase, i}
						{@const phaseIdx = FINDINGS_PHASE_ORDER.indexOf(findingsGenerationState as any)}
						{@const isPast = i < phaseIdx}
						{@const isCurrent = findingsGenerationState === phase}
						<div class="h-1 flex-1 rounded-full transition-all duration-300 {isPast ? 'bg-accent' : isCurrent ? 'bg-accent/50 animate-pulse' : 'bg-gray-200'}"></div>
					{/each}
				</div>
			</div>
		{/if}

		{#if findingsRecoverableError}
			<div class="mb-4 p-3 rounded-lg border border-blue-200 bg-blue-50 text-sm text-blue-800">
				{findingsRecoverableError} You can review the current draft while we finalize output.
			</div>
		{/if}

		<!-- Insufficient Documentation Warning -->
		{#if insufficientDocError}
			<div class="mb-6 p-4 bg-amber-50 border border-amber-300 rounded-lg">
				<div class="flex items-start gap-3">
					<AlertTriangle class="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
					<div class="flex-1">
						<h4 class="font-semibold text-amber-900 mb-1">Insufficient Documentation</h4>
						<p class="text-sm text-amber-800 mb-3">
							Case completeness is {insufficientDocError.completeness_score.toFixed(0)}% with {insufficientDocError.critical_gaps} critical gap(s).
							Review the Gap Analysis tab to identify missing documents, or enable force generation to proceed anyway.
						</p>
						<label class="flex items-center gap-2 cursor-pointer">
							<input
								type="checkbox"
								bind:checked={forceGeneration}
								class="w-4 h-4 rounded border-amber-400 text-amber-600 focus:ring-amber-500"
							/>
							<span class="text-sm font-medium text-amber-900">
								Force generation despite insufficient documentation
							</span>
						</label>
						{#if forceGeneration}
							<p class="text-xs text-amber-700 mt-2 italic">
								Warning: Generated letter may contain gaps or require significant manual review.
							</p>
						{/if}
					</div>
				</div>
			</div>
		{:else if gapAnalysis && gapAnalysis.overall_completeness_score < 60}
			<div class="mb-6 p-4 bg-yellow-50 border border-yellow-300 rounded-lg">
				<div class="flex items-start gap-3">
					<AlertTriangle class="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
					<div>
						<h4 class="font-semibold text-yellow-900 mb-1">Low Completeness Warning</h4>
						<p class="text-sm text-yellow-800">
							Case completeness is {gapAnalysis.overall_completeness_score.toFixed(0)}%.
							Consider reviewing the Gap Analysis tab before generating letters.
						</p>
					</div>
				</div>
			</div>
		{/if}

		{#if generatingFindings && !findingsDraftStarted && !findingsLetter}
			<div class="space-y-4 animate-fade-in-up">
				<!-- Progress bar -->
				<div class="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
					<div
						class="h-full bg-accent rounded-full transition-all duration-700 ease-out"
						style="width: {findingsGenerationPercent}%"
					></div>
				</div>
				<!-- Phase step list -->
				<div class="flex flex-col gap-2 py-2">
					{#each FINDINGS_PHASE_ORDER as phase}
						{@const phaseIdx = FINDINGS_PHASE_ORDER.indexOf(phase)}
						{@const activeIdx = FINDINGS_PHASE_ORDER.indexOf(findingsGenerationState as any)}
						{@const isDone = activeIdx > phaseIdx}
						{@const isActive = activeIdx === phaseIdx}
						{@const label = isActive && findingsPhaseMessage && phase === 'draft_generation'
							? findingsPhaseMessage
							: FINDINGS_PHASE_LABELS[phase]}
						<div class="flex items-center gap-2.5 text-sm {isActive ? 'text-accent font-medium' : isDone ? 'text-green-600' : 'text-gray-400'}">
							{#if isDone}
								<svg class="h-4 w-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
									<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
								</svg>
							{:else if isActive}
								<div class="h-4 w-4 flex-shrink-0 animate-spin rounded-full border-2 border-accent border-t-transparent"></div>
							{:else}
								<div class="h-4 w-4 flex-shrink-0 rounded-full border-2 border-gray-200"></div>
							{/if}
							<span>{label}</span>
						</div>
					{/each}
				</div>
				<div class="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-inner p-6 h-[600px] flex items-center justify-center text-gray-500">
					Waiting for first token...
				</div>
			</div>
		{:else if generatingFindings && findingsDraftStarted && findingsLetter && findingsGenerationState !== 'complete'}
			<!-- Streaming preview - shows text to avoid iframe blinking -->
			<div class="space-y-4 animate-fade-in-up">
				<!-- Progress bar -->
				<div class="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
					<div
						class="h-full bg-accent rounded-full transition-all duration-700 ease-out"
						style="width: {findingsGenerationPercent}%"
					></div>
				</div>
				<div class="flex items-center gap-2 text-sm text-accent font-medium">
					<div class="animate-spin rounded-full h-4 w-4 border-2 border-accent border-t-transparent"></div>
					{findingsPhaseMessage || 'Generating email...'}
				</div>
				<div class="relative border border-gray-200 rounded-lg overflow-hidden bg-white shadow-inner">
					{#if findingsGenerationState === 'polishing'}
						<div class="absolute inset-0 z-10 flex flex-col items-center justify-center bg-white/80 backdrop-blur-sm rounded-lg">
							<div class="animate-spin rounded-full h-8 w-8 border-2 border-accent border-t-transparent mb-3"></div>
							<span class="text-sm font-medium text-accent">Polishing letter...</span>
						</div>
					{/if}
					<div class="p-6 h-[600px] overflow-y-auto prose prose-sm max-w-none">
						{@html sanitizeHtml(findingsLetter)}
					</div>
				</div>
			</div>
			{:else if findingsLetter}
				<!-- Completed findings email - show in iframe -->
				<div class="space-y-4 animate-fade-in-up">
					<div class="flex justify-end gap-2">
						<button
							class="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-bold rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent transition-all shadow-sm"
							onclick={() => copyLetterPlainText(findingsLetter!, 'Findings email')}
						>
							Copy Plain Text
						</button>
						<button
							class="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-bold rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent transition-all shadow-sm"
							onclick={() => downloadLetter(findingsLetter!, `findings-email-${caseId}.html`)}
						>
							Download HTML
					</button>
				</div>
				<div class="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-inner">
					<iframe srcdoc={findingsLetter.replace(/\\n/g, '\n')} title="Findings Email" class="w-full h-[600px] border-0" sandbox=""></iframe>
				</div>
			</div>
		{:else}
			<div class="bg-gray-50 rounded-lg p-12 text-center border-2 border-dashed border-gray-200">
				<p class="text-gray-400 text-sm font-medium">No findings email generated yet. Click "Generate Email" to start.</p>
			</div>
		{/if}
	</section>

	<!-- Recommendation Letters Section -->
	{#if Object.keys(recommendationLetters).length > 0}
		<section class="card-standard">
			<h3 class="text-xl font-heading font-bold text-contrast mb-6">Advisory Letters</h3>
			<div class="space-y-6">
					{#each Object.entries(recommendationLetters) as [letterType, letterHtml]}
						<div class="border border-gray-200 rounded-xl overflow-hidden bg-gray-50 shadow-sm animate-fade-in-up">
							<div class="flex items-center justify-between p-4 bg-white border-b border-gray-200">
								<h4 class="font-bold text-contrast capitalize">{letterType.replace(/_/g, ' ')} Letter</h4>
								<div class="flex items-center gap-2">
									{#if letterType === 'request_documents'}
										<button
											class="inline-flex items-center px-3 py-1.5 border border-gray-300 text-xs font-bold rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent transition-all"
											onclick={() => copyLetterPlainText(letterHtml, 'Request documents letter')}
										>
											Copy Plain Text
										</button>
									{/if}
									<button
										class="inline-flex items-center px-3 py-1.5 border border-gray-300 text-xs font-bold rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent transition-all"
										onclick={() => downloadLetter(letterHtml, `${letterType}-letter-${caseId}.html`)}
									>
										Download HTML
									</button>
								</div>
							</div>
						<div class="p-4">
							<div class="border border-gray-200 rounded-lg bg-white overflow-hidden shadow-inner">
								<iframe srcdoc={letterHtml.replace(/\\n/g, '\n')} title={`${letterType} Letter`} class="w-full h-[400px] border-0" sandbox=""></iframe>
							</div>
						</div>
					</div>
				{/each}
			</div>
		</section>
	{/if}
{/if}
