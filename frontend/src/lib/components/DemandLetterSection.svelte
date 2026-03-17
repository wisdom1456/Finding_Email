<script lang="ts">
	import { getApiUrl } from '$lib/config';
	import { getSecureSession } from '$lib/supabase';
	import { toastStore } from '$lib/stores/toastStore';
	import { parseMarkdown } from '$lib/utils/markdown';
	import { letterHtmlToPlainText, letterHtmlToRichFragment, normalizeLetterHtml } from '$lib/utils/letterCopy';
	import { SSEEventParser } from '$lib/utils/sseEventParser';
	import { fetchWithRetry } from '$lib/utils/fetchWithRetry';
	import { onDestroy } from 'svelte';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';

	let {
		analysisId,
		caseId,
		opposingParties,
		initialDemandLetters = {},
		initialDemandAmount = null,
		initialSpecificDemands = '',
	}: {
		analysisId: string;
		caseId: string;
		opposingParties: Array<{ name: string; role: string }>;
		initialDemandLetters?: Record<string, string>;
		initialDemandAmount?: number | null;
		initialSpecificDemands?: string;
	} = $props();

	let demandLetters = $state<Record<string, string>>(initialDemandLetters);
	let generatingDemand = $state(false);
	let selectedParty = $state(opposingParties.length > 0 ? opposingParties[0].name : '');
	let demandAmount = $state<number | null>(initialDemandAmount);
	let demandDeadline = $state('10 business days');
	let specificDemands = $state(initialSpecificDemands);
	let calculatingAmount = $state(false);
	let calculationReasoning = $state('');
	let calculationBreakdown = $state<Array<{ description: string; amount: number }>>([]);
	let attorneyName = $state('');
	let firmName = $state('');
	let contactPhone = $state('');
	let contactEmail = $state('');

	type DemandGenerationState =
		| 'idle'
		| 'connecting'
		| 'strategy'
		| 'context_build'
		| 'draft_generation'
		| 'lint_validation'
		| 'repair'
		| 'polishing'
		| 'finalizing'
		| 'complete'
		| 'error';

	const DEMAND_PHASE_LABELS: Record<string, string> = {
		strategy: 'Planning strategy',
		context_build: 'Building context',
		draft_generation: 'Drafting letter',
		lint_validation: 'Reviewing for accuracy',
		repair: 'Fixing issues',
		polishing: 'Final polish',
		finalizing: 'Saving',
	};

	let demandGenerationState = $state<DemandGenerationState>('idle');
	let demandPhaseMessage = $state('');
	let demandGenerationPercent = $state(0);
	let demandStreamingPreview = $state<string | null>(null);

	type ActiveDemandRequest = {
		requestId: number;
		controller: AbortController;
	};
	let activeDemandRequest: ActiveDemandRequest | null = null;
	let demandRequestCounter = 0;

	onDestroy(() => {
		activeDemandRequest?.controller.abort();
		activeDemandRequest = null;
	});

	async function calculateDemandAmount() {
		if (!selectedParty) {
			alert('Please select an opposing party first');
			return;
		}

		calculatingAmount = true;
		calculationReasoning = '';
		calculationBreakdown = [];

		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/analysis/calculate-demand-amount`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`
				},
				body: JSON.stringify({
					case_id: caseId,
					target_party_name: selectedParty
				})
			});

			if (!response.ok) {
				const detail = await response.json().catch(() => ({}));
				throw new Error(detail?.detail || 'Failed to calculate demand amount');
			}

			const data = await response.json();
			demandAmount = data.amount;
			calculationReasoning = data.reasoning;
			calculationBreakdown = data.breakdown || [];
		} catch (err: any) {
			alert(err.message || 'Failed to calculate demand amount');
			console.error('Demand calculation error:', err);
		} finally {
			calculatingAmount = false;
		}
	}

	async function generateDemandLetterStreaming() {
		const previousRequest = activeDemandRequest;
		if (previousRequest) {
			previousRequest.controller.abort();
		}

		const controller = new AbortController();
		const requestId = ++demandRequestCounter;
		activeDemandRequest = { requestId, controller };
		const isCurrentRequest = () => activeDemandRequest?.requestId === requestId;

		demandGenerationState = 'connecting';
		demandPhaseMessage = 'Connecting...';
		demandGenerationPercent = 0;
		demandStreamingPreview = null;

		const { session, user } = await getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

		const apiUrl = getApiUrl();
		const demandLines = specificDemands
			.split('\n')
			.map((line) => line.trim())
			.filter(Boolean);

		const params = new URLSearchParams({
			target_party_name: selectedParty,
			demand_deadline: demandDeadline,
			schema_version: '2',
			mode: 'strict_quality',
		});
		if (demandAmount != null) {
			params.set('demand_amount', String(demandAmount));
		}
		if (demandLines.length > 0) {
			params.set('specific_demands', demandLines.join('|'));
		}

		const response = await fetchWithRetry(
			`${apiUrl}/api/analysis/${analysisId}/demand-letter/stream?${params.toString()}`,
			{
				headers: { Authorization: `Bearer ${session.access_token}` },
				signal: controller.signal,
			}
		);

		if (response.status === 404) {
			// Feature flag is off — fall back to synchronous POST
			await generateDemandLetterSync();
			return;
		}

		if (!response.ok) {
			const detail = await response.json().catch(() => ({}));
			throw new Error(detail?.detail || 'Failed to stream demand letter');
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
		let draftStarted = false;

		const renderPreview = () => {
			if (!isCurrentRequest()) return;
			demandStreamingPreview = `<div class="legal-letter">${parseMarkdown(markdownBuffer)}</div>`;
		};

		const flushPendingTokens = () => {
			if (!isCurrentRequest()) return;
			if (pendingTokens) {
				markdownBuffer += pendingTokens;
				pendingTokens = '';
				renderPreview();
			}
			if (flushTimer) {
				clearTimeout(flushTimer);
				flushTimer = null;
			}
		};

		const queueToken = (token: string) => {
			if (!isCurrentRequest()) return;
			if (!draftStarted) {
				draftStarted = true;
				markdownBuffer = '';
				pendingTokens = '';
				demandStreamingPreview = '';
			}
			pendingTokens += token;
			if (flushTimer) return;
			flushTimer = setTimeout(() => {
				if (!isCurrentRequest()) { pendingTokens = ''; flushTimer = null; return; }
				if (!pendingTokens) { flushTimer = null; return; }
				markdownBuffer += pendingTokens;
				pendingTokens = '';
				flushTimer = null;
				renderPreview();
			}, 80);
		};

		const applyPhase = (phase: string, message?: string, percent?: number) => {
			if (!isCurrentRequest()) return;
			const allowed: DemandGenerationState[] = [
				'strategy', 'context_build', 'draft_generation',
				'lint_validation', 'repair', 'polishing', 'finalizing',
			];
			if (allowed.includes(phase as DemandGenerationState)) {
				demandGenerationState = phase as DemandGenerationState;
			}
			if (message) demandPhaseMessage = message;
			if (typeof percent === 'number' && percent > demandGenerationPercent) {
				demandGenerationPercent = percent;
			}
		};

		while (true) {
			if (!isCurrentRequest()) throw new DOMException('Demand request superseded', 'AbortError');
			const { done, value } = await reader.read();
			if (done) { flushPendingTokens(); break; }

			const chunk = decoder.decode(value, { stream: true });
			const events = parser.push(chunk);

			for (const data of events) {
				const eventType =
					(typeof data.event === 'string' && data.event) ||
					(typeof data.type === 'string' && data.type) ||
					(data.token ? 'token' : data.done ? 'done' : data.error ? 'error' : '');

				if (eventType === 'phase') {
					applyPhase(
						String(data.phase || ''),
						typeof data.message === 'string' ? data.message : undefined,
						typeof data.percent === 'number' ? data.percent : undefined,
					);
				} else if (eventType === 'token' && typeof data.token === 'string') {
					demandGenerationState = 'draft_generation';
					queueToken(data.token);
				} else if (eventType === 'final') {
					flushPendingTokens();
					const content = data.content as Record<string, unknown> | undefined;
					if (content && typeof content.html === 'string') {
						demandLetters = { ...demandLetters, [selectedParty]: content.html };
					} else if (content && typeof content.markdown === 'string') {
						demandLetters = {
							...demandLetters,
							[selectedParty]: `<div class="legal-letter">${parseMarkdown(content.markdown as string)}</div>`,
						};
					}
					demandGenerationState = 'complete';
					demandPhaseMessage = 'Complete';
					demandStreamingPreview = null;
				} else if (eventType === 'error') {
					const message = (typeof data.error === 'string' && data.error) || 'Demand letter generation failed';
					if (!Boolean(data.recoverable)) {
						demandGenerationState = 'error';
						demandPhaseMessage = message;
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

			if (streamDone) break;
		}

		flushPendingTokens();

		if (demandGenerationState !== 'complete' && demandGenerationState !== 'error') {
			if (markdownBuffer.trim()) {
				demandLetters = {
					...demandLetters,
					[selectedParty]: `<div class="legal-letter">${parseMarkdown(markdownBuffer)}</div>`,
				};
			}
			demandGenerationState = 'complete';
			demandPhaseMessage = 'Complete';
			demandStreamingPreview = null;
		}
	}

	async function generateDemandLetterSync() {
		const demandLines = specificDemands.split('\n').map((line) => line.trim()).filter(Boolean);
		demandGenerationState = 'draft_generation';
		demandPhaseMessage = 'Generating...';

		const { session, user } = await getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

		const apiUrl = getApiUrl();
		const response = await fetchWithRetry(`${apiUrl}/api/analysis/generate-letter`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				Authorization: `Bearer ${session.access_token}`
			},
			body: JSON.stringify({
				case_id: caseId,
				letter_type: 'demand',
				target_party_name: selectedParty,
				demand_amount: demandAmount ?? undefined,
				demand_deadline: demandDeadline,
				specific_demands: demandLines,
				attorney_name: attorneyName || undefined,
				firm_name: firmName || undefined,
				contact_phone: contactPhone || undefined,
				contact_email: contactEmail || undefined
			})
		});

		if (!response.ok) {
			const detail = await response.json().catch(() => ({}));
			throw new Error(detail?.detail || 'Failed to generate demand letter');
		}

		const data = await response.json();
		if (data.target_party_name) {
			demandLetters = { ...demandLetters, [data.target_party_name]: data.letter_html };
		}
		demandGenerationState = 'complete';
		demandPhaseMessage = 'Complete';
	}

	async function generateDemandLetter() {
		if (!selectedParty) {
			alert('Please select an opposing party');
			return;
		}
		generatingDemand = true;
		demandStreamingPreview = null;
		demandGenerationState = 'idle';
		try {
			await generateDemandLetterStreaming();
		} catch (err: any) {
			if (err.name === 'AbortError') return;
			if (err instanceof TypeError && /fetch|network/i.test(err.message)) {
				console.warn('Network error during streaming — checking if letter was saved...', err);
				const recovered = await tryRecoverSavedLetter();
				if (recovered) return;
			}
			if (demandGenerationState !== 'error') {
				demandGenerationState = 'error';
				demandPhaseMessage = err.message || 'Generation failed';
			}
			alert(err.message || 'Letter generation failed');
		} finally {
			generatingDemand = false;
		}
	}

	async function tryRecoverSavedLetter(): Promise<boolean> {
		await new Promise((r) => setTimeout(r, 5000));

		try {
			const { session } = await getSecureSession();
			if (!session) return false;

			const apiUrl = getApiUrl();
			const res = await fetch(`${apiUrl}/api/analysis/results/${caseId}`, {
				headers: { Authorization: `Bearer ${session.access_token}` }
			});
			if (!res.ok) return false;

			const analysisResult = await res.json();
			const letters = analysisResult?.result?.generated_letters;
			if (!letters) return false;

			if (selectedParty) {
				const key = `demand_${selectedParty.replace(/\s+/g, '_')}`;
				if (letters[key]) {
					demandLetters = { ...demandLetters, [selectedParty]: letters[key] };
					toastStore.success('Letter recovered after network interruption');
					return true;
				}
			}
		} catch (e) {
			console.warn('Recovery fetch also failed:', e);
		}
		return false;
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

	async function copyLetterRichText(letter: string, label: string) {
		try {
			const richHtml = letterHtmlToRichFragment(letter);
			const plainText = letterHtmlToPlainText(letter);
			if (!plainText) throw new Error('No text content available');

			if (typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write) {
				const payload = new ClipboardItem({
					'text/html': new Blob([richHtml], { type: 'text/html' }),
					'text/plain': new Blob([plainText], { type: 'text/plain' })
				});
				await navigator.clipboard.write([payload]);
			} else {
				await navigator.clipboard.writeText(plainText);
			}

			toastStore.success(`${label} copied`);
		} catch (err: any) {
			toastStore.error(err?.message || `Failed to copy ${label.toLowerCase()}`);
		}
	}
</script>

<section class="card-standard">
	<h3 class="text-xl font-heading font-bold text-contrast mb-6">Demand Letter</h3>
	<div class="grid gap-6 md:grid-cols-2">
		<div class="space-y-4">
			<div>
				<label for="opposing-party" class="block text-sm font-bold text-contrast mb-1.5">Opposing Party</label>
				<select
					id="opposing-party"
					data-testid="party-select"
					bind:value={selectedParty}
					class="input-standard focus:ring-accent"
				>
					<option value="">Select party</option>
					{#each opposingParties as party}
						<option value={party.name}>{party.name} ({party.role})</option>
					{/each}
				</select>
			</div>
			<div>
				<label for="demand-amount" class="block text-sm font-bold text-contrast mb-1.5">Demand Amount ($)</label>
				<div class="flex gap-2">
					<input
						id="demand-amount"
						type="number"
						class="input-standard focus:ring-accent"
						min="0"
						step="100"
						bind:value={demandAmount}
					/>
					<AsyncButton
						type="button"
						onclick={calculateDemandAmount}
						disabled={!selectedParty}
						loading={calculatingAmount}
						variant="secondary"
						loadingText="Calc..."
						class="whitespace-nowrap font-bold"
						title={!selectedParty ? "Please select an opposing party first" : "Calculate suggested demand amount based on case analysis"}
					>
						Calculate
					</AsyncButton>
				</div>
				{#if calculationReasoning}
					<div class="mt-3 p-4 info-box info-box-blue text-xs leading-relaxed animate-fade-in-up">
						<p class="text-contrast font-bold mb-1 uppercase tracking-wider">AI Calculation Reasoning:</p>
						<p class="text-contrast-light font-medium">{calculationReasoning}</p>
						{#if calculationBreakdown && calculationBreakdown.length > 0}
							<details class="mt-3 border-t border-contrast-light/10 pt-2">
								<summary class="text-accent font-bold cursor-pointer hover:underline">View line-item breakdown</summary>
								<ul class="mt-3 space-y-2">
									{#each calculationBreakdown as item}
										<li class="text-contrast-light flex justify-between font-medium">
											<span>{item.description}</span>
											<span class="font-mono font-bold">${item.amount.toLocaleString()}</span>
										</li>
									{/each}
								</ul>
							</details>
						{/if}
					</div>
				{/if}
			</div>
			<div>
				<label for="response-deadline" class="block text-sm font-bold text-contrast mb-1.5">Response Deadline</label>
				<select
					id="response-deadline"
					class="input-standard focus:ring-accent"
					bind:value={demandDeadline}
				>
					<option>10 business days</option>
					<option>14 days</option>
					<option>30 days</option>
				</select>
			</div>
		</div>

		<div class="space-y-4">
			<div>
				<label for="specific-demands" class="block text-sm font-bold text-contrast mb-1.5">Specific Demands (one per line)</label>
				<textarea
					id="specific-demands"
					class="input-standard focus:ring-accent min-h-[120px]"
					rows="6"
					bind:value={specificDemands}
					placeholder="e.g. Return of full security deposit&#10;Repairs to main dwelling roof&#10;Payment of outstanding interest"
				></textarea>
			</div>

			<div class="pt-2">
				<h4 class="text-sm font-bold text-contrast mb-3">Attorney Information</h4>
				<div class="grid grid-cols-2 gap-3">
					<input
						type="text"
						bind:value={attorneyName}
						class="input-standard text-xs focus:ring-accent"
						placeholder="Attorney name"
					/>
					<input
						type="text"
						bind:value={firmName}
						class="input-standard text-xs focus:ring-accent"
						placeholder="Firm name"
					/>
					<input
						type="tel"
						bind:value={contactPhone}
						class="input-standard text-xs focus:ring-accent"
						placeholder="Phone number"
					/>
					<input
						type="email"
						bind:value={contactEmail}
						class="input-standard text-xs focus:ring-accent"
						placeholder="Email address"
					/>
				</div>
			</div>
		</div>
	</div>

	{#if generatingDemand && demandGenerationState !== 'idle'}
		<div class="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg animate-fade-in-up">
			<div class="flex items-center gap-3">
				<div class="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
				<div class="flex-1">
					<p class="text-sm font-bold text-blue-900">
						{DEMAND_PHASE_LABELS[demandGenerationState] || demandPhaseMessage || 'Processing...'}
					</p>
					{#if demandPhaseMessage && demandPhaseMessage !== DEMAND_PHASE_LABELS[demandGenerationState]}
						<p class="text-xs text-blue-700 mt-0.5">{demandPhaseMessage}</p>
					{/if}
				</div>
				{#if demandGenerationPercent > 0}
					<span class="text-xs font-mono text-blue-600">{demandGenerationPercent}%</span>
				{/if}
			</div>
			{#if demandGenerationPercent > 0}
				<div class="mt-2 w-full bg-blue-200 rounded-full h-1.5">
					<div
						class="bg-blue-500 h-1.5 rounded-full transition-all duration-300"
						style="width: {demandGenerationPercent}%"
					></div>
				</div>
			{/if}
		</div>
	{/if}

	{#if demandStreamingPreview}
		<div class="mt-4 border border-gray-200 rounded-xl overflow-hidden bg-gray-50 shadow-sm animate-fade-in-up">
			<div class="flex items-center justify-between p-4 bg-white border-b border-gray-200">
				<h4 class="font-bold text-contrast">Preview: {selectedParty}</h4>
				<span class="text-xs text-blue-600 font-medium animate-pulse">Streaming...</span>
			</div>
			<div class="p-4">
				<div class="border border-gray-200 rounded-lg bg-white overflow-hidden shadow-inner">
					<iframe srcdoc={demandStreamingPreview} title="Demand Letter Preview" class="w-full h-[400px] border-0" sandbox=""></iframe>
				</div>
			</div>
		</div>
	{/if}

	<div class="mt-8 flex justify-end border-t border-gray-100 pt-6">
		<AsyncButton
			variant="primary"
			onclick={generateDemandLetter}
			disabled={!selectedParty}
			loading={generatingDemand}
			loadingText="Generating Letter..."
			class="px-8 shadow-sm"
			data-testid="generate-btn"
		>
			Generate Letter to {selectedParty || 'Party'}
		</AsyncButton>
	</div>

	{#if Object.keys(demandLetters).length > 0}
		<div class="mt-8 space-y-6">
				{#each Object.entries(demandLetters) as [partyName, letterHtml]}
					<div class="border border-gray-200 rounded-xl overflow-hidden bg-gray-50 shadow-sm animate-fade-in-up">
						<div class="flex items-center justify-between p-4 bg-white border-b border-gray-200">
							<h4 class="font-bold text-contrast">Demand Letter: {partyName}</h4>
							<div class="flex items-center gap-2">
								<button
									class="inline-flex items-center px-3 py-1.5 border border-gray-300 text-xs font-bold rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent transition-all"
									onclick={() => copyLetterRichText(letterHtml, `Demand letter for ${partyName}`)}
								>
									Copy Rich Text
								</button>
								<button
									class="inline-flex items-center px-3 py-1.5 border border-gray-300 text-xs font-bold rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent transition-all"
									onclick={() => downloadLetter(letterHtml, `demand-letter-${partyName}.html`)}
								>
									Download HTML
								</button>
							</div>
						</div>
						<div class="p-4">
							<div class="border border-gray-200 rounded-lg bg-white overflow-hidden shadow-inner">
								<iframe srcdoc={letterHtml.replace(/\\n/g, '\n')} title={`Demand Letter ${partyName}`} class="w-full h-[400px] border-0" sandbox=""></iframe>
							</div>
						</div>
					</div>
				{/each}
		</div>
	{/if}
</section>
