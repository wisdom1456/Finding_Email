<script lang="ts">
	interface Step {
		label: string;
		status: 'pending' | 'processing' | 'completed' | 'error';
		progress?: number; // 0-100
		detail?: string;
		subStep?: string; // Additional granular sub-step information
		docsProcessed?: string[]; // List of processed documents
		currentDoc?: { name: string; index: number; total: number }; // Current document being processed
	}

	let {
		steps = [],
		currentStep = 0,
		showPercentage = true,
		showDetails = false
	}: {
		steps: Step[];
		currentStep?: number;
		showPercentage?: boolean;
		showDetails?: boolean;
	} = $props();
	
	let expandedSteps = $state<Set<number>>(new Set());

	function getStepIcon(status: Step['status']) {
		switch (status) {
			case 'completed':
				return '✅';
			case 'processing':
				return '⏳';
			case 'error':
				return '❌';
			default:
				return '⭕';
		}
	}

	function getStepColor(status: Step['status']) {
		switch (status) {
			case 'completed':
				return 'text-green-600';
			case 'processing':
				return 'text-blue-600';
			case 'error':
				return 'text-red-600';
			default:
				return 'text-gray-400';
		}
	}
</script>

<div class="space-y-4">
	{#each steps as step, index}
		<div class="flex items-start space-x-3">
			<div class="flex-shrink-0 mt-1">
				<span class="text-2xl {getStepColor(step.status)}">{getStepIcon(step.status)}</span>
			</div>
			<div class="flex-1 min-w-0">
				<p class="text-sm font-medium {getStepColor(step.status)}">
					{step.label}
				</p>
				{#if step.detail}
					<p class="text-xs text-gray-500 mt-1">{step.detail}</p>
				{/if}
				
				{#if step.subStep}
					<p class="text-xs text-gray-500 mt-1 italic">{step.subStep}</p>
				{/if}
				
				{#if step.currentDoc}
					<p class="text-xs text-blue-600 mt-1">
						Processing {step.currentDoc.index}/{step.currentDoc.total}: {step.currentDoc.name}
					</p>
				{/if}
				
				{#if step.status === 'processing' && step.progress !== undefined}
					<div class="mt-2">
						<div class="w-full bg-gray-200 rounded-full h-2">
							<div
								class="bg-blue-600 h-2 rounded-full transition-all duration-300"
								style="width: {step.progress}%"
							></div>
						</div>
						{#if showPercentage}
							<p class="text-xs text-gray-500 mt-1">{step.progress}%</p>
						{/if}
					</div>
				{/if}
				
				{#if showDetails && step.docsProcessed && step.docsProcessed.length > 0}
					<div class="mt-2">
						<button
							onclick={() => {
								if (expandedSteps.has(index)) {
									expandedSteps.delete(index);
								} else {
									expandedSteps.add(index);
								}
								expandedSteps = new Set(expandedSteps);
							}}
							class="text-xs text-blue-600 hover:text-blue-800 underline"
						>
							{expandedSteps.has(index) ? 'Hide' : 'Show'} processed documents ({step.docsProcessed.length})
						</button>
						
						{#if expandedSteps.has(index)}
							<ul class="mt-2 text-xs text-gray-600 space-y-1 ml-4 list-disc">
								{#each step.docsProcessed as doc}
									<li>{doc}</li>
								{/each}
							</ul>
						{/if}
					</div>
				{/if}
			</div>
		</div>
	{/each}
</div>

<style>
	/* Optional: Add pulse animation for processing state */
	@keyframes pulse {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0.5;
		}
	}
</style>

