<script lang="ts">
	import { ChevronRight } from 'lucide-svelte';

	interface BreadcrumbItem {
		label: string;
		href?: string;
	}

	let { items = [] }: { items: BreadcrumbItem[] } = $props();
</script>

<nav class="flex" aria-label="Breadcrumb">
	<ol class="flex items-center space-x-2">
		{#each items as item, index}
			<li class="flex items-center">
				{#if index > 0}
					<ChevronRight class="h-4 w-4 text-gray-400 mx-2" />
				{/if}
				{#if item.href && index < items.length - 1}
					<a
						href={item.href}
						class="text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors"
					>
						{item.label}
					</a>
				{:else}
					<span class="text-sm font-medium text-gray-900" aria-current="page">
						{item.label}
					</span>
				{/if}
			</li>
		{/each}
	</ol>
</nav>


