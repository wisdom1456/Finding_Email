<script lang="ts">
	import { ChevronDown } from 'lucide-svelte';

	let {
		title,
		children,
		defaultOpen = false
	}: {
		title: string;
		children: any;
		defaultOpen?: boolean;
	} = $props();

	let isOpen = $state(defaultOpen);

	function toggle() {
		isOpen = !isOpen;
	}
</script>

<div class="border-b border-gray-200 last:border-b-0">
	<button
		type="button"
		onclick={toggle}
		class="w-full flex justify-between items-center py-4 text-left hover:bg-gray-50 transition-colors px-1 -mx-1 rounded"
		aria-expanded={isOpen}
	>
		<span class="font-medium text-contrast pr-4">{title}</span>
		<ChevronDown
			class="h-5 w-5 text-gray-400 shrink-0 transition-transform duration-200 {isOpen ? 'rotate-180' : ''}"
		/>
	</button>
	{#if isOpen}
		<div class="pb-4 text-gray-600 animate-fade-in">
			{@render children()}
		</div>
	{/if}
</div>
