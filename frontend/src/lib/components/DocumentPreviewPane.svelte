<script lang="ts">
	type LoadPreviewHandler = (() => void | Promise<void>) | null | undefined;
	type TextTheme = 'dark' | 'light';

	let {
		fileName = '',
		fileType = '',
		documentId = '',
		hasStoragePath = false,
		previewUrl = null,
		loading = false,
		isPdf = false,
		isImage = false,
		isTextDocument = false,
		textPreview = '',
		onLoadPreview = null,
		loadingLabel = 'Loading preview...',
		pdfHintMessage = 'PDF preview is loaded on demand.',
		unavailableStorageMessage = 'Preview unavailable because the original file could not be loaded from storage.',
		loadPdfLabel = 'Load PDF Preview',
		loadImageLabel = 'Load Image Preview',
		openLinkLabel = 'Open PDF',
		openInNewTab = true,
		linkDownload = false,
		noPreviewTitle = 'No file preview available',
		noPreviewDescription = '',
		textEmptyTitle = 'No text preview available',
		textEmptyDescription = '',
		textTheme = 'light',
		previewHeightClass = 'h-[600px]',
		textContainerClass = '',
		wrapperClass = ''
	}: {
		fileName?: string;
		fileType?: string;
		documentId?: string;
		hasStoragePath?: boolean;
		previewUrl?: string | null;
		loading?: boolean;
		isPdf?: boolean;
		isImage?: boolean;
		isTextDocument?: boolean;
		textPreview?: string;
		onLoadPreview?: LoadPreviewHandler;
		loadingLabel?: string;
		pdfHintMessage?: string;
		unavailableStorageMessage?: string;
		loadPdfLabel?: string;
		loadImageLabel?: string;
		openLinkLabel?: string;
		openInNewTab?: boolean;
		linkDownload?: boolean;
		noPreviewTitle?: string;
		noPreviewDescription?: string;
		textEmptyTitle?: string;
		textEmptyDescription?: string;
		textTheme?: TextTheme;
		previewHeightClass?: string;
		textContainerClass?: string;
		wrapperClass?: string;
	} = $props();

	const downloadHref = $derived(documentId ? `/api/documents/${documentId}/download` : '');
	const previewText = $derived(String(textPreview || '').trim());
	const hasLoadHandler = $derived(Boolean(onLoadPreview));

	const resolvedTextContainerClass = $derived(
		textContainerClass ||
			(textTheme === 'dark'
				? 'bg-gray-900 rounded-lg p-4 max-h-[600px] overflow-auto'
				: 'bg-white border border-gray-200 rounded-lg p-4 max-h-[600px] overflow-auto')
	);
	const resolvedTextClass = $derived(
		textTheme === 'dark'
			? 'whitespace-pre-wrap font-mono text-xs text-gray-300 leading-relaxed'
			: 'whitespace-pre-wrap font-mono text-sm text-gray-800 leading-relaxed'
	);

	function triggerLoadPreview() {
		void onLoadPreview?.();
	}
</script>

<div class={wrapperClass}>
	{#if loading}
		<div class="flex items-center justify-center h-64">
			<div class="text-center">
				<svg class="mx-auto h-12 w-12 text-gray-400 animate-spin" fill="none" viewBox="0 0 24 24">
					<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
					<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
				</svg>
				<p class="mt-2 text-sm text-gray-500">{loadingLabel}</p>
			</div>
		</div>
	{:else if isPdf}
		{#if previewUrl}
			<object
				data={previewUrl}
				type="application/pdf"
				title="PDF Preview"
				class={`w-full ${previewHeightClass} border border-gray-300 rounded-lg`}
			>
				<p class="text-sm text-gray-600 p-4">
					PDF preview unavailable in this browser.
					{#if downloadHref}
						<a
							href={downloadHref}
							class="text-accent hover:text-accent-hover underline ml-1"
							download={linkDownload ? '' : undefined}
						>
							{openLinkLabel}
						</a>
					{/if}
				</p>
			</object>
		{:else if hasStoragePath}
			<div class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
				<p class="text-blue-800 text-sm">{pdfHintMessage}</p>
			</div>
			<div class="flex items-center gap-3">
				{#if hasLoadHandler}
					<button
						type="button"
						class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-accent hover:bg-accent-hover"
						onclick={triggerLoadPreview}
					>
						{loadPdfLabel}
					</button>
				{/if}
				{#if downloadHref}
					{#if openInNewTab}
						<a
							href={downloadHref}
							class="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
							target="_blank"
							rel="noopener noreferrer"
							download={linkDownload ? '' : undefined}
						>
							{openLinkLabel}
						</a>
					{:else}
						<a
							href={downloadHref}
							class="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
							download={linkDownload ? '' : undefined}
						>
							{openLinkLabel}
						</a>
					{/if}
				{/if}
			</div>
		{:else}
			<div class="bg-amber-50 border border-amber-200 rounded-lg p-4">
				<p class="text-amber-800 text-sm">{unavailableStorageMessage}</p>
			</div>
		{/if}
	{:else if isImage}
		{#if previewUrl}
			<div class="flex items-center justify-center">
				<img src={previewUrl} alt={fileName} class="max-w-full h-auto rounded-lg shadow-lg" />
			</div>
		{:else if hasStoragePath && hasLoadHandler}
			<div class="text-center">
				<p class="text-sm text-gray-600 mb-3">Image preview not loaded yet.</p>
				<button
					type="button"
					class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-accent hover:bg-accent-hover"
					onclick={triggerLoadPreview}
				>
					{loadImageLabel}
				</button>
			</div>
		{:else}
			<div class="flex flex-col items-center justify-center h-64 text-gray-400">
				<svg class="h-12 w-12 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
				</svg>
				<p class="font-medium text-gray-600">Image preview unavailable</p>
			</div>
		{/if}
	{:else if isTextDocument}
		{#if previewText}
			<div class={resolvedTextContainerClass}>
				<pre class={resolvedTextClass}>{previewText}</pre>
			</div>
		{:else}
			<div class="flex flex-col items-center justify-center h-64 text-gray-400 text-center">
				<svg class="h-12 w-12 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
				</svg>
				<p class="font-medium text-gray-600">{textEmptyTitle}</p>
				{#if textEmptyDescription}
					<p class="text-sm mt-2">{textEmptyDescription}</p>
				{/if}
			</div>
		{/if}
	{:else}
		<div class="flex flex-col items-center justify-center h-64 text-gray-400 text-center">
			<svg class="h-12 w-12 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
			</svg>
			<p class="font-medium text-gray-600">{noPreviewTitle}</p>
			{#if noPreviewDescription}
				<p class="text-sm mt-2">{noPreviewDescription}</p>
			{:else if fileType}
				<p class="text-sm mt-2">{fileType}</p>
			{/if}
		</div>
	{/if}
</div>
