<script lang="ts">
	import { isPdfLikeDocument, isImageLikeDocument, isTextLikeDocument } from '$lib/utils/documentClassification';
	import { formatFileSize } from '$lib/utils/formatters';
	import { getSecureSession } from '$lib/supabase';
	import { getApiUrl } from '$lib/config';
	import { toastStore } from '$lib/stores/toastStore';
	import DocumentSummaryCard from '$lib/components/DocumentSummaryCard.svelte';
	import DocumentPreviewPane from '$lib/components/DocumentPreviewPane.svelte';

	let {
		document = null,
		documents = [],
		supabaseClient,
		results = null,
		showReextract = false,
		onclose,
		onreextract,
	}: {
		document: any | null;
		documents: any[];
		supabaseClient: any;
		results?: any | null;
		showReextract?: boolean;
		onclose: () => void;
		onreextract?: (detail: { docId: string; method: 'ocr' | 'vision' }) => void;
	} = $props();

	// Internal state
	let documentViewerContent = $state('');
	let documentViewerTab = $state<'preview' | 'summary' | 'text'>('preview');
	let documentSummary = $state<any>(null);
	let loadingDocumentSummary = $state(false);
	let documentSummaries = $state<any[]>([]);
	let loadingExtractedText = $state(false);
	let extractedTextData = $state<any>(null);
	let pdfBlobUrl = $state<string | null>(null);
	let previewBlobDocumentId = $state<string | null>(null);
	let loadingPreview = $state(false);

	let isPdfDocument = $derived(isPdfLikeDocument(document));
	let isImageDocument = $derived(isImageLikeDocument(document));

	// Auto-load when document changes
	$effect(() => {
		if (document) {
			// Reset internal state first, then initialize
			documentViewerContent = '';
			documentViewerTab = 'preview';
			documentSummary = null;
			loadingPreview = false;
			extractedTextData = null;

			// Cleanup previous blob URL
			if (pdfBlobUrl) {
				URL.revokeObjectURL(pdfBlobUrl);
				pdfBlobUrl = null;
			}
			previewBlobDocumentId = null;

			// Initialize the viewer
			initializeViewer(document);
		} else {
			// document became null — cleanup blob URL
			if (pdfBlobUrl) {
				URL.revokeObjectURL(pdfBlobUrl);
				pdfBlobUrl = null;
			}
			previewBlobDocumentId = null;
		}
	});

	// Auto-load extracted text when switching to text tab
	$effect(() => {
		if (document && documentViewerTab === 'text' && !extractedTextData && !loadingExtractedText) {
			loadExtractedText(document.id);
		}
	});

	async function initializeViewer(doc: any) {
		// Try to find document summary if we have analysis results
		await loadDocumentSummary(doc.file_name);

		try {
			// Images are lightweight enough for immediate preview.
			// PDFs are loaded on demand to avoid expensive click-path work.
			if (isImageLikeDocument(doc)) {
				await loadDocumentBinaryPreview(doc);
				return;
			}
			if (isPdfLikeDocument(doc)) {
				return;
			}

			// Show loading state while fetching text content
			loadingPreview = true;

			// If document has text extracted (indicated by extracted_at), fetch it on demand
			if (doc.extracted_at) {
				const { data: textData, error: textError } = await supabaseClient
					.from('documents')
					.select('extracted_text')
					.eq('id', doc.id)
					.single();

				const typedData = textData as any;
				if (!textError && typedData?.extracted_text) {
					documentViewerContent = typedData.extracted_text;
					loadingPreview = false;
					return;
				}
			}

			if (!isTextLikeDocument(doc)) {
				documentViewerContent = `Unable to display this document. File type: ${doc.file_type}`;
				loadingPreview = false;
				return;
			}

			const { session, user } = await getSecureSession();
			if (!session || !user) {
				documentViewerContent = 'Error: Not authenticated';
				loadingPreview = false;
				return;
			}

			const { data, error } = await supabaseClient.storage
				.from('documents')
				.download(doc.storage_path);

			if (error) throw error;

			documentViewerContent = await data.text();
		} catch (error: any) {
			console.error('Failed to load document:', error);
			documentViewerContent = `Unable to display this document. File type: ${doc.file_type}`;
		} finally {
			loadingPreview = false;
		}
	}

	async function loadDocumentBinaryPreview(doc: any = document) {
		if (!doc?.storage_path) return;

		const docId = doc.id ? String(doc.id) : null;
		if (docId && previewBlobDocumentId === docId && pdfBlobUrl) {
			return;
		}

		loadingPreview = true;
		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) {
				documentViewerContent = 'Error: Not authenticated';
				return;
			}

			const { data, error } = await supabaseClient.storage
				.from('documents')
				.download(doc.storage_path);

			if (error) throw error;

			if (pdfBlobUrl) {
				URL.revokeObjectURL(pdfBlobUrl);
			}
			pdfBlobUrl = URL.createObjectURL(data);
			previewBlobDocumentId = docId;
		} catch (error: any) {
			console.error('Failed to load document preview:', error);
			toastStore.error('Failed to load document preview');
		} finally {
			loadingPreview = false;
		}
	}

	async function loadExtractedText(docId: string) {
		loadingExtractedText = true;
		extractedTextData = null;
		try {
			const { session, user } = await getSecureSession();

			if (!session || !user) throw new Error('Not authenticated');

			const response = await fetch(`${getApiUrl()}/api/documents/${docId}/extracted-text`, {
				headers: {
					Authorization: `Bearer ${session.access_token}`
				}
			});

			if (!response.ok) throw new Error('Failed to fetch extracted text');
			extractedTextData = await response.json();
		} catch (error: any) {
			console.error('Error fetching extracted text:', error);
			extractedTextData = { extracted_text: `Error: ${error.message}` };
		} finally {
			loadingExtractedText = false;
		}
	}

	async function loadDocumentSummariesFromAnalysis() {
		if (!results) return;

		try {
			// Parse document_summaries from the results prop if available
			if (results.document_summaries) {
				if (typeof results.document_summaries === 'string') {
					try {
						documentSummaries = JSON.parse(results.document_summaries);
					} catch {
						documentSummaries = [];
					}
				} else if (Array.isArray(results.document_summaries)) {
					documentSummaries = results.document_summaries;
				}
				return;
			}

			// Otherwise try to fetch from the streamed results if available
			if (results.streamed?.results) {
				const resolvedResults = await Promise.resolve(results.streamed.results);
				if (resolvedResults?.document_summaries) {
					if (typeof resolvedResults.document_summaries === 'string') {
						try {
							documentSummaries = JSON.parse(resolvedResults.document_summaries);
						} catch {
							documentSummaries = [];
						}
					} else if (Array.isArray(resolvedResults.document_summaries)) {
						documentSummaries = resolvedResults.document_summaries;
					}
					return;
				}
			}

			// Fall back to API fetch
			const { session } = await getSecureSession();
			if (!session) return;

			const caseId = results?.caseId;
			if (!caseId) return;

			const response = await fetch(`${getApiUrl()}/api/analysis/results/${caseId}`, {
				headers: {
					Authorization: `Bearer ${session.access_token}`
				}
			});

			if (!response.ok) return;

			const apiResults = await response.json();

			if (apiResults.document_summaries) {
				if (typeof apiResults.document_summaries === 'string') {
					try {
						documentSummaries = JSON.parse(apiResults.document_summaries);
					} catch {
						documentSummaries = [];
					}
				} else if (Array.isArray(apiResults.document_summaries)) {
					documentSummaries = apiResults.document_summaries;
				}
			}
		} catch (error) {
			console.error('Failed to load document summaries:', error);
		}
	}

	async function loadDocumentSummary(fileName: string) {
		// First ensure we have document summaries loaded
		if (documentSummaries.length === 0) {
			loadingDocumentSummary = true;
			await loadDocumentSummariesFromAnalysis();
			loadingDocumentSummary = false;
		}

		// Find the summary for this document by matching filename
		const summary = documentSummaries.find(
			(s: any) => s.document_name === fileName ||
						s.document_name?.toLowerCase() === fileName?.toLowerCase()
		);

		documentSummary = summary || null;
	}

	function closeDocumentViewer() {
		// Clean up blob URL to prevent memory leaks
		if (pdfBlobUrl) {
			URL.revokeObjectURL(pdfBlobUrl);
			pdfBlobUrl = null;
		}
		previewBlobDocumentId = null;
		documentViewerContent = '';
		documentViewerTab = 'preview';
		loadingPreview = false;
		extractedTextData = null;
		loadingExtractedText = false;
		documentSummary = null;
		onclose();
	}
</script>

{#if document}
	<div
		role="button"
		tabindex="0"
		class="modal-overlay"
		onclick={closeDocumentViewer}
		onkeydown={(e) => e.key === 'Escape' && closeDocumentViewer()}
	>
		<div
			role="dialog"
			aria-modal="true"
			tabindex="-1"
			class="relative bg-white rounded-lg shadow-2xl max-w-5xl w-full max-h-[90vh] flex flex-col"
			onclick={(e) => e.stopPropagation()}
			onkeydown={(e) => e.stopPropagation()}
		>
			<!-- Header -->
			<div class="flex items-start justify-between p-6 border-b border-gray-100">
				<div class="flex-1 min-w-0">
					<div class="flex items-center space-x-2 mb-2">
						{#if document.metadata?.is_intake_form}
							<svg class="h-5 w-5 text-accent shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
							</svg>
							<span class="px-2 py-0.5 text-[10px] font-bold tracking-wider rounded-full bg-accent text-white uppercase">
								Primary Intake
							</span>
						{/if}
						{#if document.metadata?.clio_source}
							<span class="px-2 py-0.5 text-[10px] font-bold tracking-wider rounded-full bg-contrast/10 text-contrast uppercase">
								{document.metadata.clio_type || 'CLIO'}
							</span>
						{/if}
					</div>
					<h3 class="text-xl font-heading font-bold text-contrast truncate">
						{document.file_name}
					</h3>
					<p class="text-xs font-medium text-gray-500 mt-1">
						{formatFileSize(document.file_size)} • {document.file_type}
					</p>
				</div>
				<button
					onclick={closeDocumentViewer}
					class="ml-4 p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors"
				>
					<span class="sr-only">Close</span>
					<svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>

			<!-- Tabs -->
			<div class="px-6 border-b border-gray-200">
				<nav class="-mb-px flex space-x-6" aria-label="Tabs">
					<button
						onclick={() => (documentViewerTab = 'preview')}
						class="whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm {documentViewerTab === 'preview' ? 'border-accent text-accent' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}"
					>
						Preview
					</button>
					<button
						onclick={() => (documentViewerTab = 'summary')}
						class="whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center gap-2 {documentViewerTab === 'summary' ? 'border-accent text-accent' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}"
					>
						Summary
						{#if documentSummary}
							<span class="w-2 h-2 rounded-full bg-green-500"></span>
						{/if}
					</button>
					<button
						onclick={() => (documentViewerTab = 'text')}
						class="whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm {documentViewerTab === 'text' ? 'border-accent text-accent' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}"
					>
						Raw Text
					</button>
				</nav>
			</div>

			<!-- Content -->
			<div class="flex-1 overflow-y-auto p-6">
				{#if documentViewerTab === 'preview'}
					<DocumentPreviewPane
						fileName={document.file_name}
						fileType={document.file_type}
						documentId={document.id}
						hasStoragePath={Boolean(document.storage_path)}
						previewUrl={pdfBlobUrl}
						loading={loadingPreview}
						isPdf={isPdfDocument}
						isImage={isImageDocument}
						isTextDocument={!isPdfDocument && !isImageDocument}
						textPreview={documentViewerContent}
						onLoadPreview={() => loadDocumentBinaryPreview(document)}
						loadingLabel="Loading document preview..."
						pdfHintMessage="PDF preview is loaded on demand to reduce click latency and suppress browser PDF viewer warnings."
						unavailableStorageMessage="PDF preview unavailable because the original file could not be loaded from storage."
						loadPdfLabel="Load PDF Preview"
						loadImageLabel="Load Image Preview"
						openLinkLabel="Open PDF in New Tab"
						openInNewTab={true}
						linkDownload={false}
						noPreviewTitle="No file preview available"
						textTheme="light"
						previewHeightClass="h-[600px]"
					/>
				{:else if documentViewerTab === 'summary'}
					{#if loadingDocumentSummary}
						<div class="flex items-center justify-center h-64">
							<div class="text-center">
								<svg class="mx-auto h-12 w-12 text-gray-400 animate-spin" fill="none" viewBox="0 0 24 24">
									<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
									<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
								</svg>
								<p class="mt-2 text-sm text-gray-500">Loading document analysis...</p>
							</div>
						</div>
					{:else if documentSummary}
						<DocumentSummaryCard
							summary={documentSummary}
							rawText={documentViewerContent || extractedTextData?.extracted_text || ''}
							signatureDetection={document?.metadata?.signature_detection || null}
							collapsible={false}
							showHeader={false}
						/>
					{:else}
						<div class="flex flex-col items-center justify-center h-64 text-gray-400">
							<svg class="h-12 w-12 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
							</svg>
							<p class="font-medium text-gray-600">No analysis available</p>
							<p class="text-sm mt-2 text-center max-w-sm">
								Run case analysis to generate a structured summary of this document with key facts, legal significance, and evidence quotes.
							</p>
						</div>
					{/if}
				{:else if documentViewerTab === 'text'}
					{#if loadingExtractedText}
						<div class="flex items-center justify-center h-64">
							<div class="text-center">
								<svg class="mx-auto h-12 w-12 text-gray-400 animate-spin" fill="none" viewBox="0 0 24 24">
									<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
									<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
								</svg>
								<p class="mt-2 text-sm text-gray-500">Fetching extracted text...</p>
							</div>
						</div>
					{:else if extractedTextData}
						<div class="space-y-4">
							{#if extractedTextData.extraction_method}
								<div class="flex items-center justify-between text-xs text-gray-500 bg-gray-50 p-2 rounded border border-gray-100">
									<div class="flex gap-4">
										<span>Method: <span class="font-semibold text-gray-700">{extractedTextData.extraction_method}</span></span>
										{#if extractedTextData.extraction_quality}
											<span>Quality:
												<span class="font-semibold {
													extractedTextData.extraction_quality === 'high' ? 'text-green-600' :
													extractedTextData.extraction_quality === 'medium' ? 'text-yellow-600' : 'text-red-600'
												}">{extractedTextData.extraction_quality.toUpperCase()}</span>
											</span>
										{/if}
										{#if extractedTextData.page_count}
											<span>Pages: <span class="font-semibold text-gray-700">{extractedTextData.page_count}</span></span>
										{/if}
									</div>
									<button
										class="text-accent hover:text-accent-hover font-medium flex items-center gap-1"
										onclick={() => {
											navigator.clipboard.writeText(extractedTextData.extracted_text);
											toastStore.success('Text copied to clipboard');
										}}
									>
										<svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
										</svg>
										Copy Text
									</button>
								</div>
							{/if}

							{#if extractedTextData.extracted_text}
								<div class="prose prose-sm max-w-none">
									<pre class="whitespace-pre-wrap font-mono text-sm text-gray-800 bg-white p-4 rounded-lg border border-gray-200 overflow-x-auto">{extractedTextData.extracted_text}</pre>
								</div>
							{:else}
								<div class="flex flex-col items-center justify-center h-64 text-gray-400">
									<svg class="h-12 w-12 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
									</svg>
									<p>No text content extracted for this document yet.</p>
									<p class="text-xs mt-1">Run analysis to extract content.</p>
								</div>
							{/if}

							{#if extractedTextData.extraction_error}
								<div class="mt-4 p-3 bg-red-50 text-red-700 text-xs rounded border border-red-100">
									<p class="font-bold">Extraction Error:</p>
									<p class="mt-1 font-mono">{extractedTextData.extraction_error}</p>
								</div>
							{/if}
						</div>
					{/if}
				{/if}
			</div>

			<!-- Footer -->
			<div class="flex justify-end space-x-3 px-6 py-4 border-t border-gray-200">
				{#if showReextract && onreextract}
					<button
						onclick={() => onreextract!({ docId: document.id, method: 'ocr' })}
						class="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent"
					>
						Re-Extract (OCR)
					</button>
					<button
						onclick={() => onreextract!({ docId: document.id, method: 'vision' })}
						class="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent"
					>
						Re-Extract (Vision)
					</button>
				{/if}
				<button
					onclick={closeDocumentViewer}
					class="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent"
				>
					Close
				</button>
			</div>
		</div>
	</div>
{/if}
