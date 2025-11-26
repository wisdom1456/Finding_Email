<script lang="ts">
	import { CheckCircle, Loader2, XCircle, Circle, ChevronDown, ChevronUp } from 'lucide-svelte';
	
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

	function getStepColor(status: Step['status']) {
		switch (status) {
			case 'completed':
				return 'text-accent';
			case 'processing':
				return 'text-contrast-light';
			case 'error':
				return 'text-red-600';
			default:
				return 'text-gray-400';
		}
	}
	
	function getProgressBarColor(status: Step['status']) {
		switch (status) {
			case 'completed':
				return 'bg-accent';
			case 'processing':
				return 'bg-contrast-light';
			case 'error':
				return 'bg-red-600';
			default:
				return 'bg-gray-300';
		}
	}
</script>

<div class="space-y-4">
	{#each steps as step, index}
		<div class="flex items-start space-x-3">
			<div class="flex-shrink-0 mt-0.5">
				{#if step.status === 'completed'}
					<CheckCircle class="h-5 w-5 {getStepColor(step.status)}" />
				{:else if step.status === 'processing'}
					<Loader2 class="h-5 w-5 {getStepColor(step.status)} animate-spin" />
				{:else if step.status === 'error'}
					<XCircle class="h-5 w-5 {getStepColor(step.status)}" />
				{:else}
					<Circle class="h-5 w-5 {getStepColor(step.status)}" />
				{/if}
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
					<p class="text-xs text-contrast-light mt-1">
						Processing {step.currentDoc.index}/{step.currentDoc.total}: {step.currentDoc.name}
					</p>
				{/if}
				
				{#if step.status === 'processing' && step.progress !== undefined}
					<div class="mt-2">
						<div class="w-full bg-gray-200 rounded-full h-1.5">
							<div
								class="{getProgressBarColor(step.status)} h-1.5 rounded-full transition-all duration-300"
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
							class="inline-flex items-center text-xs text-accent hover:text-accent-hover transition-colors"
						>
							{#if expandedSteps.has(index)}
								<ChevronUp class="h-3 w-3 mr-1" />
								Hide processed documents ({step.docsProcessed.length})
							{:else}
								<ChevronDown class="h-3 w-3 mr-1" />
								Show processed documents ({step.docsProcessed.length})
							{/if}
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
