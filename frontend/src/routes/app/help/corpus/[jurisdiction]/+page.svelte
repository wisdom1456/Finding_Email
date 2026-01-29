<script lang="ts">
	import type { PageData } from './$types';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { parseMarkdown } from '$lib/utils/markdown';
	import { ArrowLeft, ChevronDown, ChevronRight, ExternalLink, Scale } from 'lucide-svelte';

	let { data }: { data: PageData } = $props();

	interface CorpusEntry {
		id: string;
		type: 'statute' | 'rule';
		citation: string;
		title: string;
		text: string;
		summary?: string;
		source_urls?: string[];
		effective_date?: string;
		source_doc_version?: string;
	}

	const title = data.jurisdiction === 'florida' ? 'Florida Legal Corpus' : 'New Mexico Legal Corpus';
	const subtitle =
		data.jurisdiction === 'florida'
			? 'Verified Florida statutes and rules — view full text and official sources'
			: 'Verified New Mexico statutes and rules — view full text and official sources';

	const breadcrumbs = [
		{ label: 'Dashboard', href: '/app' },
		{ label: 'Help', href: '/app/help' },
		{ label: title }
	];

	const statutes = (data.statutes ?? []) as CorpusEntry[];
	const rules = (data.rules ?? []) as CorpusEntry[];

	let searchQuery = $state('');
	let expandedId = $state<string | null>(null);
	let showAbout = $state(false);

	const queryLower = $derived(searchQuery.trim().toLowerCase());

	const filteredStatutes = $derived(
		queryLower
			? statutes.filter(
					(s) =>
						s.citation?.toLowerCase().includes(queryLower) ||
						s.title?.toLowerCase().includes(queryLower)
				)
			: statutes
	);

	const filteredRules = $derived(
		queryLower
			? rules.filter(
					(r) =>
						r.citation?.toLowerCase().includes(queryLower) ||
						r.title?.toLowerCase().includes(queryLower)
				)
			: rules
	);

	function toggleExpanded(entry: CorpusEntry) {
		expandedId = expandedId === entry.id ? null : entry.id;
	}

	const aboutHtml = $derived(parseMarkdown(data.markdown || ''));
</script>

<svelte:head>
	<title>{title} | Help | Bernhardt Riley</title>
</svelte:head>

<div class="page-spacing">
	<PageHeader {title} {subtitle} {breadcrumbs}>
		<a
			href="/app/help"
			class="inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-contrast hover:bg-gray-100 transition-colors"
		>
			<ArrowLeft class="h-4 w-4" />
			Back to Help
		</a>
	</PageHeader>

	<!-- Search -->
	<div class="mb-6">
		<label for="corpus-search" class="sr-only">Search by citation or title</label>
		<input
			id="corpus-search"
			type="search"
			placeholder="Search by citation or title (e.g. 83.51, landlord)"
			class="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-contrast shadow-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
			bind:value={searchQuery}
		/>
	</div>

	<!-- Statutes & Rules (primary content) -->
	<div class="space-y-8">
		<!-- Statutes -->
		<section>
			<h2 class="text-lg font-heading font-semibold text-contrast mb-3 flex items-center gap-2">
				<Scale class="h-5 w-5 text-contrast-light" />
				Statutes ({filteredStatutes.length})
			</h2>
			<div class="border border-gray-200 rounded-lg overflow-hidden bg-white">
				{#if filteredStatutes.length === 0}
					<p class="p-4 text-gray-500 text-sm">No statutes match your search.</p>
				{:else}
					<ul class="divide-y divide-gray-200">
						{#each filteredStatutes as entry (entry.id)}
							<li>
								<button
									type="button"
									class="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors focus:outline-none focus:ring-2 focus:ring-inset focus:ring-accent"
									onclick={() => toggleExpanded(entry)}
								>
									<span class="shrink-0 text-gray-400">
										{#if expandedId === entry.id}
											<ChevronDown class="h-5 w-5" />
										{:else}
											<ChevronRight class="h-5 w-5" />
										{/if}
									</span>
									<span class="font-mono text-sm font-medium text-contrast shrink-0 min-w-40">
										{entry.citation}
									</span>
									<span class="text-gray-600 text-sm truncate">{entry.title}</span>
								</button>
								{#if expandedId === entry.id}
									<div class="border-t border-gray-200 bg-gray-50/80 px-4 py-4 space-y-4">
										<div>
											<p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
												Citation
											</p>
											<p class="font-mono text-contrast">{entry.citation}</p>
										</div>
										<div>
											<p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
												Title
											</p>
											<p class="text-contrast">{entry.title}</p>
										</div>
										<div>
											<p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
												Full text
											</p>
											<div
												class="text-sm text-gray-700 whitespace-pre-wrap font-serif max-h-96 overflow-y-auto rounded border border-gray-200 bg-white p-4"
											>
												{entry.text || '—'}
											</div>
										</div>
										{#if entry.effective_date}
											<div>
												<p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
													Effective date
												</p>
												<p class="text-sm text-gray-600">{entry.effective_date}</p>
											</div>
										{/if}
										{#if entry.source_doc_version}
											<div>
												<p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
													Source version
												</p>
												<p class="text-sm text-gray-600">{entry.source_doc_version}</p>
											</div>
										{/if}
										{#if entry.source_urls && entry.source_urls.length > 0}
											<div>
												<p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
													Official source
												</p>
												<ul class="space-y-1">
													{#each entry.source_urls as url}
														<li>
															<a
																href={url}
																target="_blank"
																rel="noopener noreferrer"
																class="inline-flex items-center gap-1 text-sm text-accent hover:text-accent-hover"
															>
																{url}
																<ExternalLink class="h-3.5 w-3.5 shrink-0" />
															</a>
														</li>
													{/each}
												</ul>
											</div>
										{/if}
										<div class="pt-2 border-t border-gray-200">
											<a
												href="mailto:?subject=Corpus correction: {encodeURIComponent(entry.citation)}&body=Citation: {encodeURIComponent(entry.citation)}%0A%0APlease describe the correction or addition:"
												class="text-sm text-accent hover:text-accent-hover font-medium"
											>
												Suggest a correction
											</a>
										</div>
									</div>
								{/if}
							</li>
						{/each}
					</ul>
				{/if}
			</div>
		</section>

		<!-- Rules -->
		<section>
			<h2 class="text-lg font-heading font-semibold text-contrast mb-3 flex items-center gap-2">
				<Scale class="h-5 w-5 text-contrast-light" />
				Rules ({filteredRules.length})
			</h2>
			<div class="border border-gray-200 rounded-lg overflow-hidden bg-white">
				{#if filteredRules.length === 0}
					<p class="p-4 text-gray-500 text-sm">No rules match your search.</p>
				{:else}
					<ul class="divide-y divide-gray-200">
						{#each filteredRules as entry (entry.id)}
							<li>
								<button
									type="button"
									class="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors focus:outline-none focus:ring-2 focus:ring-inset focus:ring-accent"
									onclick={() => toggleExpanded(entry)}
								>
									<span class="shrink-0 text-gray-400">
										{#if expandedId === entry.id}
											<ChevronDown class="h-5 w-5" />
										{:else}
											<ChevronRight class="h-5 w-5" />
										{/if}
									</span>
									<span class="font-mono text-sm font-medium text-contrast shrink-0 min-w-40">
										{entry.citation}
									</span>
									<span class="text-gray-600 text-sm truncate">{entry.title}</span>
								</button>
								{#if expandedId === entry.id}
									<div class="border-t border-gray-200 bg-gray-50/80 px-4 py-4 space-y-4">
										<div>
											<p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
												Citation
											</p>
											<p class="font-mono text-contrast">{entry.citation}</p>
										</div>
										<div>
											<p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
												Title
											</p>
											<p class="text-contrast">{entry.title}</p>
										</div>
										<div>
											<p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
												Full text
											</p>
											<div
												class="text-sm text-gray-700 whitespace-pre-wrap font-serif max-h-96 overflow-y-auto rounded border border-gray-200 bg-white p-4"
											>
												{entry.text || '—'}
											</div>
										</div>
										{#if entry.effective_date}
											<div>
												<p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
													Effective date
												</p>
												<p class="text-sm text-gray-600">{entry.effective_date}</p>
											</div>
										{/if}
										{#if entry.source_doc_version}
											<div>
												<p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
													Source version
												</p>
												<p class="text-sm text-gray-600">{entry.source_doc_version}</p>
											</div>
										{/if}
										{#if entry.source_urls && entry.source_urls.length > 0}
											<div>
												<p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
													Official source
												</p>
												<ul class="space-y-1">
													{#each entry.source_urls as url}
														<li>
															<a
																href={url}
																target="_blank"
																rel="noopener noreferrer"
																class="inline-flex items-center gap-1 text-sm text-accent hover:text-accent-hover"
															>
																{url}
																<ExternalLink class="h-3.5 w-3.5 shrink-0" />
															</a>
														</li>
													{/each}
												</ul>
											</div>
										{/if}
										<div class="pt-2 border-t border-gray-200">
											<a
												href="mailto:?subject=Corpus correction: {encodeURIComponent(entry.citation)}&body=Citation: {encodeURIComponent(entry.citation)}%0A%0APlease describe the correction or addition:"
												class="text-sm text-accent hover:text-accent-hover font-medium"
											>
												Suggest a correction
											</a>
										</div>
									</div>
								{/if}
							</li>
						{/each}
					</ul>
				{/if}
			</div>
		</section>
	</div>

	<!-- Optional: About this corpus (collapsible README) -->
	{#if data.markdown}
		<div class="mt-8 border border-gray-200 rounded-lg overflow-hidden bg-white">
			<button
				type="button"
				class="w-full flex items-center justify-between px-4 py-3 text-left font-semibold text-contrast hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-accent"
				onclick={() => (showAbout = !showAbout)}
			>
				About this corpus
				<span class="shrink-0 text-gray-400">
					{#if showAbout}
						<ChevronDown class="h-5 w-5" />
					{:else}
						<ChevronRight class="h-5 w-5" />
					{/if}
				</span>
			</button>
			{#if showAbout}
				<div
					class="border-t border-gray-200 px-4 py-4 prose prose-gray max-w-none prose-headings:font-heading prose-headings:text-contrast prose-p:text-gray-600 prose-a:text-accent prose-a:no-underline hover:prose-a:underline prose-strong:text-contrast prose-code:bg-gray-100 prose-code:px-1 prose-code:rounded prose-code:before:content-none prose-code:after:content-none text-sm"
				>
					{@html aboutHtml}
				</div>
			{/if}
		</div>
	{/if}
</div>
