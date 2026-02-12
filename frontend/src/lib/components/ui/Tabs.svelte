<script lang="ts">
	interface Tab {
		id: string;
		label: string;
	}

	let {
		tabs,
		activeTab = $bindable(),
		children
	}: {
		tabs: Tab[];
		activeTab?: string;
		children?: any;
	} = $props();

	// Set initial active tab if not provided
	if (!activeTab && tabs.length > 0) {
		activeTab = tabs[0].id;
	}

	function selectTab(tabId: string) {
		activeTab = tabId;
	}
</script>

<div class="w-full">
	<!-- Tab Navigation -->
	<div class="border-b border-gray-200 px-4 sm:px-6">
		<nav class="-mb-px flex flex-wrap gap-x-8" aria-label="Tabs">
			{#each tabs as tab}
				<button
					type="button"
					onclick={() => selectTab(tab.id)}
					class="whitespace-nowrap py-4 px-1 border-b-2 text-sm transition-all {activeTab ===
					tab.id
						? 'border-accent text-accent font-bold'
						: 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 font-medium'}"
					aria-current={activeTab === tab.id ? 'page' : undefined}
				>
					{tab.label}
				</button>
			{/each}
		</nav>
	</div>

	<!-- Tab Content -->
	<div class="mt-6">
		{#if children}
			{@render children()}
		{/if}
	</div>
</div>


