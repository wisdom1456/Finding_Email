<script lang="ts">
	interface Tab {
		id: string;
		label: string;
		/** Optional short badge text rendered after the label (e.g. a count). */
		badge?: string | number;
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

	let tabButtons: HTMLButtonElement[] = [];

	function selectTab(tabId: string) {
		activeTab = tabId;
	}

	// Roving tabindex + arrow-key navigation per the WAI-ARIA tabs pattern:
	// Tab lands on the active tab only; arrows/Home/End move and activate.
	function onKeydown(event: KeyboardEvent, index: number) {
		let next: number | null = null;
		switch (event.key) {
			case 'ArrowRight':
				next = (index + 1) % tabs.length;
				break;
			case 'ArrowLeft':
				next = (index - 1 + tabs.length) % tabs.length;
				break;
			case 'Home':
				next = 0;
				break;
			case 'End':
				next = tabs.length - 1;
				break;
			default:
				return;
		}
		event.preventDefault();
		selectTab(tabs[next].id);
		tabButtons[next]?.focus();
	}
</script>

<div class="w-full">
	<!-- Tab Navigation -->
	<div class="border-b border-gray-200 px-4 sm:px-6">
		<div class="-mb-px flex flex-wrap gap-x-8" role="tablist" aria-label="Tabs">
			{#each tabs as tab, i}
				<button
					bind:this={tabButtons[i]}
					type="button"
					role="tab"
					id="tab-{tab.id}"
					aria-selected={activeTab === tab.id}
					aria-controls="tabpanel-{tab.id}"
					tabindex={activeTab === tab.id ? 0 : -1}
					onclick={() => selectTab(tab.id)}
					onkeydown={(e) => onKeydown(e, i)}
					class="whitespace-nowrap py-4 px-1 border-b-2 text-sm transition-all {activeTab ===
					tab.id
						? 'border-accent text-accent font-bold'
						: 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 font-medium'}"
				>
					{tab.label}
					{#if tab.badge !== undefined && tab.badge !== null && tab.badge !== ''}
						<span
							class="ml-1.5 inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800"
						>
							{tab.badge}
						</span>
					{/if}
				</button>
			{/each}
		</div>
	</div>

	<!-- Tab Content -->
	<div
		class="mt-6"
		role="tabpanel"
		id="tabpanel-{activeTab}"
		aria-labelledby="tab-{activeTab}"
	>
		{#if children}
			{@render children()}
		{/if}
	</div>
</div>
