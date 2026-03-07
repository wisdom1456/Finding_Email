<script lang="ts">
	/**
	 * DocumentSummaryCard - Renders structured document analysis for attorney review
	 * 
	 * This component displays the AI-analyzed summary of a document in an attorney-friendly format,
	 * showing executive summaries, key content, legal significance, evidence quotes, and more.
	 * The raw extracted text can optionally be shown via a toggle.
	 */
	import { slide } from 'svelte/transition';
	import { ChevronRight, FileText, Scale, AlertCircle, Quote, Calendar, DollarSign, Users } from 'lucide-svelte';

	interface KeyDate {
		date: string;
		event: string;
	}

	interface KeyAmount {
		amount: string;
		description: string;
	}

	interface DocumentSummary {
		document_name: string;
		document_type?: string;
		extraction_quality?: 'high' | 'medium' | 'low';
		relevance_to_case?: string | boolean;
		executive_summary?: string;
		key_content?: string;
		key_quotes?: string[];
		statute_citations?: string[];
		important_details?: string[];
		legal_significance?: string;
		key_dates?: KeyDate[];
		key_amounts?: KeyAmount[];
		parties?: string[];
		extraction_notes?: string;
	}

	interface Props {
		summary: DocumentSummary;
		rawText?: string;
		signatureDetection?: Record<string, any> | null;
		collapsible?: boolean;
		defaultCollapsed?: boolean;
		showHeader?: boolean;
		compact?: boolean;
	}

	let { 
		summary, 
		rawText = '', 
		signatureDetection = null,
		collapsible = true, 
		defaultCollapsed = false,
		showHeader = true,
		compact = false
	}: Props = $props();

	let isCollapsed = $state(defaultCollapsed);
	let showRawText = $state(false);

	function toggleCollapse() {
		if (collapsible) {
			isCollapsed = !isCollapsed;
		}
	}

	function toggleRawText() {
		showRawText = !showRawText;
	}

	// Check if there's any structured content to display
	const hasStructuredContent = $derived(
		summary.executive_summary ||
		summary.key_content ||
		(summary.key_quotes && summary.key_quotes.length > 0) ||
		(summary.statute_citations && summary.statute_citations.length > 0) ||
		(summary.important_details && summary.important_details.length > 0) ||
		summary.legal_significance ||
		(summary.key_dates && summary.key_dates.length > 0) ||
		(summary.key_amounts && summary.key_amounts.length > 0) ||
		(summary.parties && summary.parties.length > 0)
	);

	// Check if there's any structured data (dates, amounts, parties)
	const hasStructuredData = $derived(
		(summary.key_dates && summary.key_dates.length > 0) ||
		(summary.key_amounts && summary.key_amounts.length > 0) ||
		(summary.parties && summary.parties.length > 0)
	);

	const qualityColors = {
		high: 'bg-green-50 text-green-700 border-green-200',
		medium: 'bg-amber-50 text-amber-700 border-amber-200',
		low: 'bg-red-50 text-red-700 border-red-200'
	};

	const signatureRequiredKeywords = [
		'agreement',
		'contract',
		'lease',
		'addendum',
		'amendment',
		'settlement',
		'release',
		'authorization',
		'consent',
		'affidavit',
		'declaration',
		'stipulation',
		'promissory note',
		'guaranty',
		'power of attorney',
		'poa',
		'signature page',
		'executed'
	];

	const _NO_SIG_EXTENSIONS = new Set([
		'.eml', '.txt', '.csv', '.doc', '.jpg', '.jpeg', '.png', '.heic', '.gif', '.bmp', '.tiff', '.tif',
	]);
	const _NO_SIG_TYPES = new Set([
		'correspondence', 'email', 'photo/media', 'note', 'communication',
	]);

	function requiresSignatureReview(documentName: string | undefined, documentType: string | undefined): boolean {
		const normalizedName = String(documentName || '').toLowerCase();
		const ext = normalizedName.includes('.') ? '.' + normalizedName.split('.').pop() : '';
		if (_NO_SIG_EXTENSIONS.has(ext)) return false;
		if (normalizedName.startsWith('clio note') || normalizedName.startsWith('clio communication')) return false;
		const normalizedType = String(documentType || '').toLowerCase();
		if (_NO_SIG_TYPES.has(normalizedType)) return false;

		if (normalizedType.includes('contract') || normalizedType.includes('agreement')) {
			return true;
		}

		return signatureRequiredKeywords.some((keyword) => normalizedName.includes(keyword));
	}

	function getSignatureStatus(): 'signed' | 'not_detected' | 'other' | 'none' {
		if (!signatureDetection || typeof signatureDetection !== 'object') return 'none';
		const status = String(signatureDetection.status || '').toLowerCase();
		if (status === 'signed') return 'signed';
		if (status === 'not_detected') return 'not_detected';
		return 'other';
	}

	function getSignatureLabel(): string {
		if (!signatureDetection) return '';
		const confidence = signatureDetection?.confidence
			? ` (${String(signatureDetection.confidence).toUpperCase()})`
			: '';
		const status = getSignatureStatus();
		if (status === 'signed') return `Signed${confidence}`;
		if (status === 'not_detected') return `No signature detected${confidence}`;
		return `Signature: ${String(signatureDetection.status || 'unknown')}${confidence}`;
	}

	function getSignatureClasses(): string {
		const status = getSignatureStatus();
		if (status === 'signed') return 'bg-emerald-50 text-emerald-700 border-emerald-200';
		if (status === 'not_detected') return 'bg-amber-50 text-amber-700 border-amber-200';
		return 'bg-gray-50 text-gray-700 border-gray-200';
	}

	function shouldShowSignatureBadge(): boolean {
		const status = getSignatureStatus();
		if (status === 'none') return false;
		if (status === 'signed') return true;
		return requiresSignatureReview(summary.document_name, summary.document_type);
	}
</script>

<div class="border border-gray-200 rounded-lg overflow-hidden shadow-sm hover:shadow-md transition-shadow bg-white">
	{#if showHeader}
		<!-- Clickable Header -->
		<button
			onclick={toggleCollapse}
			class="w-full bg-gray-50/80 {compact ? 'p-4' : 'p-5'} border-b border-gray-200 hover:bg-gray-100 transition-colors text-left"
			disabled={!collapsible}
		>
			<div class="flex items-center justify-between">
				<div class="flex-1 min-w-0">
					<div class="flex items-center gap-3 mb-2">
						{#if collapsible}
							<ChevronRight 
								class="w-5 h-5 text-gray-400 transition-transform shrink-0 {isCollapsed ? '' : 'rotate-90'}"
							/>
						{:else}
							<FileText class="w-5 h-5 text-gray-400 shrink-0" />
						{/if}
						<h3 class="{compact ? 'text-base' : 'text-lg'} font-bold text-contrast truncate">{summary.document_name}</h3>
					</div>
					<div class="flex flex-wrap gap-2 {collapsible ? 'ml-8' : 'ml-8'}">
						{#if summary.document_type}
							<span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wider bg-contrast/5 text-contrast uppercase border border-contrast/10">
								{summary.document_type}
							</span>
						{/if}
						{#if summary.extraction_quality}
							<span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase border {qualityColors[summary.extraction_quality]}">
								Quality: {summary.extraction_quality}
							</span>
						{/if}
						{#if summary.relevance_to_case}
							<span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-accent/10 text-accent border border-accent/20">
								Relevant
							</span>
						{/if}
						{#if shouldShowSignatureBadge()}
							<span
								class={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase border ${getSignatureClasses()}`}
								title={getSignatureLabel()}
							>
								{getSignatureLabel()}
							</span>
						{/if}
					</div>
				</div>
			</div>
		</button>
	{/if}

	<!-- Content -->
	{#if !isCollapsed}
		<div transition:slide class="{compact ? 'p-4' : 'p-6'} space-y-5">
			{#if hasStructuredContent}
				<!-- Executive Summary -->
				{#if summary.executive_summary}
					<div>
						<p class="text-sm text-gray-700 leading-relaxed font-medium italic border-l-2 border-accent/30 pl-4">
							{summary.executive_summary}
						</p>
					</div>
				{/if}

				<!-- Key Content -->
				{#if summary.key_content}
					<div class="bg-gray-50 rounded-lg {compact ? 'p-4' : 'p-5'} border border-gray-200 shadow-inner">
						<p class="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-1.5">
							<FileText class="w-3.5 h-3.5" />
							Key Content
						</p>
						<p class="text-sm text-contrast leading-relaxed whitespace-pre-wrap">{summary.key_content}</p>
					</div>
				{/if}

				<!-- Key Quotes (Evidence) -->
				{#if summary.key_quotes && summary.key_quotes.length > 0}
					<div>
						<p class="text-[10px] font-bold text-accent uppercase tracking-widest mb-3 flex items-center gap-1.5">
							<Quote class="w-3.5 h-3.5" />
							Evidence Quotes
						</p>
						<div class="space-y-3">
							{#each summary.key_quotes as quote}
								<blockquote class="border-l-4 border-accent pl-5 py-3 bg-accent/5 rounded-r italic text-sm text-contrast leading-relaxed">
									"{quote}"
								</blockquote>
							{/each}
						</div>
					</div>
				{/if}

				<!-- Statute Citations -->
				{#if summary.statute_citations && summary.statute_citations.length > 0}
					<div>
						<p class="text-[10px] font-bold text-contrast-light uppercase tracking-widest mb-3 flex items-center gap-1.5">
							<Scale class="w-3.5 h-3.5" />
							Relevant Statutes
						</p>
						<div class="flex flex-wrap gap-2">
							{#each summary.statute_citations as statute}
								<span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-contrast/5 text-contrast border border-contrast/10">
									{statute}
								</span>
							{/each}
						</div>
					</div>
				{/if}

				<!-- Important Details -->
				{#if summary.important_details && summary.important_details.length > 0}
					<div>
						<p class="text-[10px] font-bold text-orange-800 uppercase tracking-widest mb-3 flex items-center gap-1.5">
							<AlertCircle class="w-3.5 h-3.5" />
							Important Details
						</p>
						<ul class="space-y-2">
							{#each summary.important_details as detail}
								<li class="text-sm text-gray-700 flex items-start">
									<span class="text-orange-400 mr-2 font-bold">•</span>
									<span>{detail}</span>
								</li>
							{/each}
						</ul>
					</div>
				{/if}

				<!-- Legal Significance -->
				{#if summary.legal_significance}
					<div class="bg-amber-50/50 border border-amber-200 rounded-lg {compact ? 'p-4' : 'p-5'}">
						<p class="text-[10px] font-bold text-amber-800 uppercase tracking-widest mb-2 flex items-center gap-1.5">
							<Scale class="w-3.5 h-3.5" />
							Legal Significance
						</p>
						<p class="text-sm text-contrast font-medium leading-relaxed">{summary.legal_significance}</p>
					</div>
				{/if}

				<!-- Structured Data (Dates, Amounts, Parties) -->
				{#if hasStructuredData}
					<div class="grid grid-cols-1 md:grid-cols-3 gap-6 pt-5 border-t border-gray-100">
						{#if summary.key_dates && summary.key_dates.length > 0}
							<div>
								<p class="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-1.5">
									<Calendar class="w-3.5 h-3.5" />
									Key Dates
								</p>
								<ul class="space-y-3">
									{#each summary.key_dates as date}
										<li class="text-xs text-contrast">
											<span class="font-bold block mb-0.5">{date.date}</span>
											<span class="text-gray-500 font-medium">{date.event}</span>
										</li>
									{/each}
								</ul>
							</div>
						{/if}

						{#if summary.key_amounts && summary.key_amounts.length > 0}
							<div>
								<p class="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-1.5">
									<DollarSign class="w-3.5 h-3.5" />
									Key Amounts
								</p>
								<ul class="space-y-3">
									{#each summary.key_amounts as amount}
										<li class="text-xs text-contrast">
											<span class="font-bold block mb-0.5 text-accent">{amount.amount}</span>
											<span class="text-gray-500 font-medium">{amount.description}</span>
										</li>
									{/each}
								</ul>
							</div>
						{/if}

						{#if summary.parties && summary.parties.length > 0}
							<div>
								<p class="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-1.5">
									<Users class="w-3.5 h-3.5" />
									Parties
								</p>
								<div class="flex flex-wrap gap-2">
									{#each summary.parties as party}
										<span class="inline-flex items-center px-2 py-1 rounded text-[10px] font-bold bg-gray-100 text-gray-600 border border-gray-200 uppercase tracking-wider">
											{party}
										</span>
									{/each}
								</div>
							</div>
						{/if}
					</div>
				{/if}

				<!-- Extraction Notes -->
				{#if summary.extraction_notes}
					<div class="text-xs text-gray-500 italic pt-3 border-t border-gray-100">
						<span class="font-semibold">Note:</span> {summary.extraction_notes}
					</div>
				{/if}
			{:else}
				<!-- Fallback when no structured content available -->
				<div class="text-center py-8 text-gray-500">
					<FileText class="w-10 h-10 mx-auto mb-3 text-gray-300" />
					<p class="font-medium">No structured analysis available</p>
					<p class="text-sm mt-1">Run analysis to generate document insights</p>
				</div>
			{/if}

			<!-- Raw Text Toggle Section -->
			{#if rawText}
				<div class="pt-4 border-t border-gray-100">
					<button
						onclick={toggleRawText}
						class="text-xs font-bold text-gray-500 hover:text-gray-700 uppercase tracking-wider flex items-center gap-2 transition-colors"
					>
						<ChevronRight class="w-4 h-4 transition-transform {showRawText ? 'rotate-90' : ''}" />
						{showRawText ? 'Hide' : 'View'} Raw Extracted Text
					</button>
					
					{#if showRawText}
						<div transition:slide class="mt-4">
							<div class="bg-gray-900 rounded-lg p-4 max-h-96 overflow-auto">
								<pre class="whitespace-pre-wrap font-mono text-xs text-gray-300 leading-relaxed">{rawText}</pre>
							</div>
						</div>
					{/if}
				</div>
			{/if}
		</div>
	{/if}
</div>
