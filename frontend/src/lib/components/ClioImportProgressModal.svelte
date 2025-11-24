<script lang="ts">
	import { untrack } from 'svelte';
	import { progressStore } from '$lib/stores/progressStore';
	
	interface ProgressStep {
		step: string;
		current?: number;
		total?: number;
		item_name?: string;
		message?: string;
	}

	interface ImportResult {
		communications_count?: number;
		notes_count?: number;
		documents_count?: number;
		total_imported?: number;
		errors?: string[];
	}

	interface Props {
		show: boolean;
		caseId?: string;
		importResult?: ImportResult;
		onClose: () => void;
	}

	let { show = $bindable(false), caseId, importResult, onClose }: Props = $props();

	let currentStep = $state<ProgressStep>({ step: 'init', message: 'Initializing...' });
	let steps = $state<ProgressStep[]>([]);
	let isComplete = $state(false);
	let hasError = $state(false);
	let errorMessage = $state('');
	
	// Map progress store phase to modal step
	$effect(() => {
		const state = $progressStore;

		untrack(() => {
			if (state.status === 'active' || state.status === 'connecting') {
				const phaseToStep: Record<string, string> = {
					'initialization': 'init',
					'fetch_matter': 'fetch',
					'fetch_communications': 'communications',
					'fetch_notes': 'notes',
					'fetch_documents': 'documents',
					'import_communications': 'communications',
					'import_notes': 'notes',
					'import_documents': 'documents',
					'create_case': 'create_case',
					'import_start': 'documents',
					'analyze_intake': 'analyze'
				};
				
				const step = phaseToStep[state.phase] || 'init';
				
				const newStep = {
					step: step,
					message: state.message,
					current: state.current_doc?.index,
					total: state.current_doc?.total,
					item_name: state.current_doc?.name || state.sub_step || undefined
				};

				currentStep = newStep;
				
				// Add to history (avoid duplicates)
				if (steps.length === 0 || steps[steps.length - 1].message !== currentStep.message) {
					steps = [...steps, currentStep];
				}
			} else if (state.status === 'completed') {
				currentStep = { step: 'complete', message: 'Import completed!' };
				isComplete = true;
			} else if (state.status === 'error') {
				currentStep = { step: 'error', message: state.error || 'An error occurred' };
				hasError = true;
				errorMessage = state.error || 'An error occurred';
			}
		});
	});

	function getStepLabel(step: string): string {
		const labels: Record<string, string> = {
			init: 'Initializing',
			fetch: 'Fetching from Clio',
			create_case: 'Creating Case',
			communications: 'Processing Communications',
			notes: 'Processing Notes',
			documents: 'Downloading Documents',
			analyze: 'Analyzing Intake Forms',
			complete: 'Complete',
			error: 'Error'
		};
		return labels[step] || step;
	}

	function getStepIcon(step: string): string {
		const icons: Record<string, string> = {
			init: '🔄',
			fetch: '📡',
			create_case: '📁',
			communications: '📨',
			notes: '📝',
			documents: '📄',
			analyze: '🔍',
			complete: '✅',
			error: '❌'
		};
		return icons[step] || '⚙️';
	}

	function getProgressPercentage(): number {
		// Use progress store percentage if available
		if ($progressStore.status === 'active' && $progressStore.percent > 0) {
			return $progressStore.percent;
		}
		
		if (isComplete) return 100;
		if (hasError) return 0;
		
		const { step, current = 0, total = 0 } = currentStep;
		
		// Step weights for overall progress
		const stepWeights: Record<string, number> = {
			init: 5,
			fetch: 10,
			create_case: 15,
			communications: 25,
			notes: 25,
			documents: 50,
			analyze: 70,
			complete: 100
		};
		
		const baseProgress = stepWeights[step] || 0;
		
		// Add sub-progress if available
		if (total > 0) {
			const nextWeight = stepWeights[step === 'communications' ? 'notes' : step === 'notes' ? 'documents' : 'analyze'] || baseProgress + 20;
			const stepRange = nextWeight - baseProgress;
			const subProgress = (current / total) * stepRange;
			return Math.min(100, baseProgress + subProgress);
		}
		
		return baseProgress;
	}

	export function updateProgress(progress: ProgressStep) {
		currentStep = progress;
		steps = [...steps, progress];
		
		if (progress.step === 'complete') {
			isComplete = true;
		} else if (progress.step === 'error') {
			hasError = true;
			errorMessage = progress.message || 'An error occurred';
		}
	}

	export function reset() {
		currentStep = { step: 'init', message: 'Initializing...' };
		steps = [];
		isComplete = false;
		hasError = false;
		errorMessage = '';
	}
</script>

{#if show}
	<div class="fixed inset-0 bg-gray-600 bg-opacity-75 flex items-center justify-center z-50 p-4">
		<div class="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col">
			<!-- Header -->
			<div class="px-6 py-4 border-b border-gray-200">
				<div class="flex items-center justify-between">
					<h3 class="text-lg font-semibold text-gray-900">
						{#if isComplete}
							Case Created Successfully
						{:else if hasError}
							Error Creating Case
						{:else}
							Creating Case from Clio
						{/if}
					</h3>
					{#if isComplete || hasError}
						<button
							onclick={onClose}
							class="text-gray-400 hover:text-gray-500"
							aria-label="Close"
						>
							<svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M6 18L18 6M6 6l12 12"
								/>
							</svg>
						</button>
					{/if}
				</div>
			</div>

			<!-- Content -->
			<div class="flex-1 overflow-y-auto px-6 py-4">
				{#if !isComplete && !hasError}
					<!-- Progress Bar -->
					<div class="mb-6">
						<div class="flex items-center justify-between mb-2">
							<span class="text-sm font-medium text-gray-700">
								{getStepIcon(currentStep.step)} {getStepLabel(currentStep.step)}
							</span>
							<span class="text-sm text-gray-500">{Math.round(getProgressPercentage())}%</span>
						</div>
						<div class="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
							<div
								class="bg-blue-600 h-3 rounded-full transition-all duration-300 ease-out"
								style="width: {getProgressPercentage()}%"
							></div>
						</div>
					</div>

					<!-- Current Item -->
					{#if currentStep.item_name}
						<div class="mb-4 p-3 bg-blue-50 rounded-lg border border-blue-200">
							<div class="flex items-start">
								<div class="flex-shrink-0">
									<svg
										class="h-5 w-5 text-blue-600 animate-spin"
										fill="none"
										viewBox="0 0 24 24"
									>
										<circle
											class="opacity-25"
											cx="12"
											cy="12"
											r="10"
											stroke="currentColor"
											stroke-width="4"
										></circle>
										<path
											class="opacity-75"
											fill="currentColor"
											d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
										></path>
									</svg>
								</div>
								<div class="ml-3 flex-1">
									<p class="text-sm font-medium text-blue-900">
										{#if currentStep.current && currentStep.total}
											{currentStep.current} of {currentStep.total}
										{/if}
									</p>
									<p class="text-sm text-blue-700 truncate">{currentStep.item_name}</p>
								</div>
							</div>
						</div>
					{/if}

					<!-- Step History -->
					<div class="space-y-2">
						<h4 class="text-xs font-semibold text-gray-500 uppercase tracking-wider">Progress</h4>
						<div class="space-y-1 max-h-60 overflow-y-auto">
							{#each steps.slice(-10).reverse() as step}
								<div class="text-xs text-gray-600 flex items-center">
									<span class="mr-2">{getStepIcon(step.step)}</span>
									<span class="truncate">
										{step.message || `${getStepLabel(step.step)} ${step.item_name || ''}`}
									</span>
								</div>
							{/each}
						</div>
					</div>
				{:else if isComplete}
					<!-- Success Summary -->
					<div class="text-center py-6">
						<div class="mx-auto flex items-center justify-center h-16 w-16 rounded-full bg-green-100 mb-4">
							<svg
								class="h-10 w-10 text-green-600"
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M5 13l4 4L19 7"
								/>
							</svg>
						</div>
						<h4 class="text-lg font-semibold text-gray-900 mb-2">Case Created Successfully!</h4>
						
						{#if importResult}
							<div class="mt-4 grid grid-cols-3 gap-4 text-sm">
								<div class="bg-purple-50 rounded-lg p-3">
									<div class="text-2xl font-bold text-purple-600">
										{importResult.communications_count || 0}
									</div>
									<div class="text-gray-600">Communications</div>
								</div>
								<div class="bg-blue-50 rounded-lg p-3">
									<div class="text-2xl font-bold text-blue-600">{importResult.notes_count || 0}</div>
									<div class="text-gray-600">Notes</div>
								</div>
								<div class="bg-green-50 rounded-lg p-3">
									<div class="text-2xl font-bold text-green-600">
										{importResult.documents_count || 0}
									</div>
									<div class="text-gray-600">Documents</div>
								</div>
							</div>
							
							{#if importResult.errors && importResult.errors.length > 0}
								<div class="mt-4 p-3 bg-yellow-50 rounded-lg border border-yellow-200 text-left">
									<p class="text-sm font-medium text-yellow-800 mb-1">
										⚠️ Some items could not be imported
									</p>
									<div class="text-xs text-yellow-700 max-h-32 overflow-y-auto space-y-1">
										{#each importResult.errors.slice(0, 5) as error}
											<p>• {error}</p>
										{/each}
										{#if importResult.errors.length > 5}
											<p class="font-medium">... and {importResult.errors.length - 5} more</p>
										{/if}
									</div>
								</div>
							{/if}
						{/if}
					</div>
				{:else if hasError}
					<!-- Error Display -->
					<div class="text-center py-6">
						<div class="mx-auto flex items-center justify-center h-16 w-16 rounded-full bg-red-100 mb-4">
							<svg
								class="h-10 w-10 text-red-600"
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M6 18L18 6M6 6l12 12"
								/>
							</svg>
						</div>
						<h4 class="text-lg font-semibold text-gray-900 mb-2">Error Creating Case</h4>
						<p class="text-sm text-red-600">{errorMessage}</p>
					</div>
				{/if}
			</div>

			<!-- Footer -->
			{#if isComplete || hasError}
				<div class="px-6 py-4 border-t border-gray-200 flex justify-end space-x-3">
					{#if isComplete && caseId}
						<a
							href="/app/cases/{caseId}"
							class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 font-medium transition-colors"
						>
							View Case
						</a>
					{/if}
					<button
						onclick={onClose}
						class="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 font-medium transition-colors"
					>
						{isComplete ? 'Close' : 'Dismiss'}
					</button>
				</div>
			{/if}
		</div>
	</div>
{/if}

