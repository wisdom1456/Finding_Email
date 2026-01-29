<script lang="ts">
	import type { PageData } from './$types';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { parseMarkdown } from '$lib/utils/markdown';
	import { ArrowLeft } from 'lucide-svelte';

	let { data }: { data: PageData } = $props();

	const title = data.jurisdiction === 'florida' ? 'Florida Legal Corpus' : 'New Mexico Legal Corpus';
	const subtitle =
		data.jurisdiction === 'florida'
			? 'Verified Florida statutes and rules'
			: 'Verified New Mexico statutes and rules';

	const breadcrumbs = [
		{ label: 'Dashboard', href: '/app' },
		{ label: 'Help', href: '/app/help' },
		{ label: title }
	];

	const html = $derived(parseMarkdown(data.markdown || ''));
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

	<div class="card-standard">
		<div
			class="prose prose-gray max-w-none prose-headings:font-heading prose-headings:text-contrast prose-p:text-gray-600 prose-a:text-accent prose-a:no-underline hover:prose-a:underline prose-strong:text-contrast prose-code:bg-gray-100 prose-code:px-1 prose-code:rounded prose-code:before:content-none prose-code:after:content-none"
		>
			{@html html}
		</div>
	</div>
</div>
