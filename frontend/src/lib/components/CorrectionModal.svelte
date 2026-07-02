<script lang="ts">
	import { getApiUrl } from '$lib/config';
	import { supabase, getSecureSession } from '$lib/supabase';
	import { toastStore } from '$lib/stores/toastStore';
	import AsyncButton from './ui/AsyncButton.svelte';
	import Modal from './ui/Modal.svelte';
	import ConfirmDialog from './ui/ConfirmDialog.svelte';
	import Badge from './ui/Badge.svelte';
	import DocumentPreviewPane from './DocumentPreviewPane.svelte';

	// Props
	let {
		document,
		onClose,
		onSaved,
	}: {
		document: any;
		onClose: () => void;
		onSaved: () => Promise<void>;
	} = $props();

	// State
	let isOpen = $state(true);
	let editedText = $state(document?.manual_text || document?.extracted_text || '');
	let saving = $state(false);
	let triggeringExtraction = $state(false);
	let pdfBlobUrl = $state<string | null>(null);
	let loadingPreview = $state(true);
	let loadingText = $state(true);
	let originalText = $state(document?.manual_text || document?.extracted_text || '');

	// When modal closes, call parent's onClose
	$effect(() => {
		if (!isOpen) {
			onClose();
		}
	});

	// Derived: Quality score based on content
	let qualityScore = $derived.by(() => {
		const text = editedText.trim();
		if (!text || text.length === 0) return { score: 0, level: 'low', issues: ['No content'] };

		let score = 10;
		const issues: string[] = [];

		// Check content length
		if (text.length < 50) {
			score -= 5;
			issues.push('Very short content');
		} else if (text.length < 200) {
			score -= 2;
			issues.push('Short content');
		}

		// Check word count
		const wordCount = text.split(/\s+/).filter((w: string) => w.length > 0).length;
		if (wordCount < 10) {
			score -= 3;
			issues.push(`Only ${wordCount} words`);
		}

		// Check for gibberish (high ratio of non-word characters)
		const wordChars = text.replace(/[^a-zA-Z0-9]/g, '').length;
		const gibberishRatio = 1 - (wordChars / text.length);
		if (gibberishRatio > 0.5) {
			score -= 2;
			issues.push('High proportion of symbols/noise');
		}

		// Determine level
		let level: 'high' | 'medium' | 'low';
		if (score >= 8) level = 'high';
		else if (score >= 5) level = 'medium';
		else level = 'low';

		return {
			score: Math.max(0, Math.min(10, score)),
			level,
			issues: issues.length > 0 ? issues : ['Good quality'],
		};
	});

	// Derived: Has changes
	let hasChanges = $derived(editedText !== originalText);

	// Load PDF preview and document text on mount
	$effect(() => {
		loadPreview();
		fetchDocumentText();
		return () => {
			if (pdfBlobUrl) {
				URL.revokeObjectURL(pdfBlobUrl);
			}
		};
	});

	async function fetchDocumentText() {
		if (!document?.id) {
			loadingText = false;
			return;
		}
		try {
			const { data, error } = await supabase
				.from('documents')
				.select('extracted_text, manual_text')
				.eq('id', document.id)
				.single<{ extracted_text: string | null; manual_text: string | null }>();

			if (error) throw error;
			if (data) {
				const text = data.manual_text || data.extracted_text || '';
				editedText = text;
				originalText = text;
			}
		} catch (err) {
			console.error('Failed to fetch document text:', err);
		} finally {
			loadingText = false;
		}
	}

	async function loadPreview() {
		if (!document) return;

		const isPdf = document.file_type === 'application/pdf';
		const isImage = document.file_type?.startsWith('image/');

		if (!isPdf && !isImage) {
			loadingPreview = false;
			return;
		}

		try {
			const { data, error } = await supabase.storage
				.from('documents')
				.download(document.storage_path);

			if (error) throw error;

			pdfBlobUrl = URL.createObjectURL(data);
		} catch (error) {
			console.error('Failed to load preview:', error);
		} finally {
			loadingPreview = false;
		}
	}

	async function saveChanges() {
		saving = true;

		try {
const { session, user } = await getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

			const response = await fetch(`${getApiUrl()}/api/documents/${document.id}/verify`, {
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`,
				},
				body: JSON.stringify({
					manual_text: editedText,
					is_verified: true,
					is_flagged_as_junk: false,
				}),
			});

		if (!response.ok) {
			const error = await response.json();
			throw new Error(error.detail || 'Failed to save');
		}

		toastStore.success('Document text saved and verified');
		await onSaved();
		isOpen = false;
	} catch (error: any) {
		toastStore.error(error.message || 'Failed to save');
	} finally {
		saving = false;
	}
}

	async function triggerReExtraction() {
		triggeringExtraction = true;

		try {
const { session, user } = await getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

			const response = await fetch(`${getApiUrl()}/api/documents/${document.id}/extract`, {
				method: 'POST',
				headers: {
					Authorization: `Bearer ${session.access_token}`,
				},
			});

			if (!response.ok) {
				const error = await response.json();
				throw new Error(error.detail || 'Extraction failed');
			}

			const result = await response.json();
			editedText = result.extracted_text || '';
			toastStore.success(`Re-extracted text using ${result.extraction_method}`);
			await onSaved();
		} catch (error: any) {
			toastStore.error(error.message || 'Failed to re-extract');
		} finally {
			triggeringExtraction = false;
		}
	}

	function getQualityColor(level: string): string {
		switch (level) {
			case 'high':
				return 'text-green-600 bg-green-100 border-green-300';
			case 'medium':
				return 'text-yellow-600 bg-yellow-100 border-yellow-300';
			case 'low':
				return 'text-red-600 bg-red-100 border-red-300';
			default:
				return 'text-gray-600 bg-gray-100 border-gray-300';
		}
	}

	function copyToClipboard() {
		navigator.clipboard.writeText(editedText);
		toastStore.success('Text copied to clipboard');
	}

	let showClearConfirm = $state(false);

	function clearText() {
		showClearConfirm = true;
	}
</script>

<ConfirmDialog
	bind:open={showClearConfirm}
	title="Clear Text"
	message="Clear all text? This cannot be undone."
	confirmText="Clear"
	variant="danger"
	onConfirm={() => {
		editedText = '';
	}}
/>

<!-- Modal Wrapper -->
<Modal
	bind:open={isOpen}
	title="Edit Extracted Text"
	size="full"
>
	<!-- Subtitle in the content area since it's specific to the doc -->
	<div class="mb-4 px-1">
		<p class="text-sm text-gray-500">
			{document.file_name}
		</p>
	</div>

	<!-- Content: Side-by-Side Layout -->
	<div class="flex-1 overflow-auto flex min-h-[500px] border border-gray-200 rounded-lg">
		<!-- Left: Preview Panel -->
		<div class="w-1/2 border-r border-gray-200 flex flex-col">
			<div class="px-4 py-2 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
				<span class="text-sm font-medium text-gray-700">Original Document</span>
				<AsyncButton
					onclick={triggerReExtraction}
					loading={triggeringExtraction}
					variant="secondary"
					size="sm"
					loadingText="Extracting..."
				>
					Re-Extract Text
				</AsyncButton>
			</div>
			<div class="flex-1 overflow-auto p-4 bg-gray-100">
				<DocumentPreviewPane
					fileName={document.file_name}
					fileType={document.file_type}
					documentId={document.id}
					hasStoragePath={Boolean(document.storage_path)}
					previewUrl={pdfBlobUrl}
					loading={loadingPreview}
					isPdf={document.file_type === 'application/pdf'}
					isImage={Boolean(document.file_type?.startsWith('image/'))}
					isTextDocument={false}
					textPreview=""
					onLoadPreview={null}
					loadingLabel="Loading preview..."
					openLinkLabel="Open PDF"
					openInNewTab={true}
					linkDownload={false}
					noPreviewTitle="Preview not available for this file type"
					noPreviewDescription={document.file_type}
					previewHeightClass="h-full"
				/>
			</div>
		</div>

		<!-- Right: Editor Panel -->
		<div class="w-1/2 flex flex-col">
			<div class="px-4 py-2 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
				<div class="flex items-center gap-2">
					<span class="text-sm font-medium text-gray-700">Extracted Text</span>
					{#if hasChanges}
						<Badge variant="warning" size="xs">
							Unsaved Changes
						</Badge>
					{/if}
				</div>
				<div class="flex items-center gap-2">
					<button
						onclick={copyToClipboard}
						class="text-sm text-gray-600 hover:text-gray-800 flex items-center gap-1"
						title="Copy to clipboard"
					>
						<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
						</svg>
						Copy
					</button>
					<button
						onclick={clearText}
						class="text-sm text-red-600 hover:text-red-800"
						title="Clear all text"
					>
						Clear
					</button>
				</div>
			</div>
			<div class="flex-1 p-4">
				{#if loadingText}
					<div class="w-full h-full flex items-center justify-center text-gray-400 text-sm">
						Loading document text...
					</div>
				{:else}
					<textarea
						bind:value={editedText}
						class="w-full h-full resize-none p-4 font-mono text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-accent focus:border-transparent"
						placeholder="Paste or type the document text here..."
					></textarea>
				{/if}
			</div>

			<!-- Quality Issues -->
			{#if qualityScore.issues.length > 0}
				<div class="px-4 pb-2">
					<div class="flex flex-wrap gap-2">
						{#each qualityScore.issues as issue}
							<Badge variant={qualityScore.level === 'high' ? 'ready' : qualityScore.level === 'medium' ? 'needs_review' : 'error'} size="xs">
								{issue}
							</Badge>
						{/each}
					</div>
				</div>
			{/if}
		</div>
	</div>

	{#snippet footer()}
		<div class="flex items-center justify-between w-full">
			<div class="text-sm text-gray-500">
				{editedText.length.toLocaleString()} characters
				•
				{editedText.split(/\s+/).filter((w: string) => w.length > 0).length.toLocaleString()} words
			</div>
			<div class="flex items-center gap-3">
				<!-- Quality Score in footer -->
				<Badge variant={qualityScore.level === 'high' ? 'ready' : qualityScore.level === 'medium' ? 'needs_review' : 'error'} class="py-1.5 px-3">
					<span class="mr-1 opacity-70">Quality:</span>
					<span class="font-bold">{qualityScore.score.toFixed(1)}/10</span>
				</Badge>
				
				<button
					onclick={onClose}
					class="btn btn-secondary"
				>
					Cancel
				</button>
				<AsyncButton
					onclick={saveChanges}
					loading={saving}
					disabled={!hasChanges && document.is_verified}
					variant="primary"
					loadingText="Saving..."
				>
					{hasChanges ? 'Save & Verify' : 'Mark as Verified'}
				</AsyncButton>
			</div>
		</div>
	{/snippet}
</Modal>
