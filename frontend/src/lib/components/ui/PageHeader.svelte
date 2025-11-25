<script lang="ts">
	import Breadcrumbs from './Breadcrumbs.svelte';

	interface BreadcrumbItem {
		label: string;
		href?: string;
	}

	let {
		title,
		subtitle,
		breadcrumbs = [],
		children
	}: {
		title: string;
		subtitle?: string;
		breadcrumbs?: BreadcrumbItem[];
		children?: any;
	} = $props();
</script>

<div class="mb-6">
	{#if breadcrumbs.length > 0}
		<div class="mb-3">
			<Breadcrumbs items={breadcrumbs} />
		</div>
	{/if}

	<div class="md:flex md:items-center md:justify-between">
		<div class="flex-1 min-w-0">
			<h1 class="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
				{title}
			</h1>
			{#if subtitle}
				<p class="mt-1 text-sm text-gray-500">{subtitle}</p>
			{/if}
		</div>
		{#if children}
			<div class="mt-4 flex md:mt-0 md:ml-4">
				{@render children()}
			</div>
		{/if}
	</div>
</div>


