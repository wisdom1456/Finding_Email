<script lang="ts">
	import { Loader2 } from 'lucide-svelte';

	type Size = 'sm' | 'default' | 'lg';

	let {
		size = 'default',
		label = '',
		class: className = ''
	}: {
		size?: Size;
		label?: string;
		class?: string;
	} = $props();

	const sizeClasses: Record<Size, string> = {
		sm: 'h-4 w-4',
		default: 'h-6 w-6',
		lg: 'h-8 w-8'
	};

	const iconSize = $derived(sizeClasses[size]);
</script>

<div class="inline-flex items-center gap-2 {className}" role="status" aria-label={label || 'Loading'}>
	<Loader2 class="{iconSize} animate-spin text-current" />
	{#if label}
		<span class="text-sm text-gray-600">{label}</span>
	{/if}
</div>
