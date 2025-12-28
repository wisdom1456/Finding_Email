<script lang="ts">
	import { getApiUrl } from '$lib/config';
	import { supabase } from '$lib/supabase';
	import { toastStore } from '$lib/stores/toastStore';
	import AsyncButton from './ui/AsyncButton.svelte';

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
	let editedText = $state(document?.manual_text || document?.extracted_text || '');
	let saving = $state(false);
	let triggeringExtraction = $state(false);
	let pdfBlobUrl = $state<string | null>(null);
	let loadingPreview = $state(true);

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
		const wordCount = text.split(/\s+/).filter(w => w.length > 0).length;
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
	let hasChanges = $derived(
		editedText !== (document?.manual_text || document?.extracted_text || '')
	);

	// Load PDF preview on mount
	$effect(() => {
		loadPreview();
		return () => {
			if (pdfBlobUrl) {
				URL.revokeObjectURL(pdfBlobUrl);
			}
		};
	});

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
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) throw new Error('Not authenticated');

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
			onClose();
		} catch (error: any) {
			toastStore.error(error.message || 'Failed to save');
		} finally {
			saving = false;
		}
	}

	async function triggerReExtraction() {
		triggeringExtraction = true;

		try {
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) throw new Error('Not authenticated');

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

	function clearText() {
		if (confirm('Clear all text? This cannot be undone.')) {
			editedText = '';
		}
	}
</script>

<!-- Modal Backdrop -->
<div
	class="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50 flex items-center justify-center p-4"
	role="dialog"
	aria-modal="true"
	aria-labelledby="correction-modal-title"
>
	<div class="relative bg-white rounded-lg shadow-xl max-w-7xl w-full max-h-[90vh] flex flex-col">
		<!-- Header -->
		<div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
			<div>
				<h2 id="correction-modal-title" class="text-lg font-medium text-gray-900">
					Edit Extracted Text
				</h2>
				<p class="text-sm text-gray-500 mt-1">
					{document.file_name}
				</p>
			</div>
			<div class="flex items-center gap-4">
				<!-- Real-time Quality Score -->
				<div class="flex items-center gap-2 px-3 py-1.5 rounded-lg border {getQualityColor(qualityScore.level)}">
					<span class="text-sm font-medium">Quality:</span>
					<span class="text-lg font-bold">{qualityScore.score.toFixed(1)}/10</span>
					<span class="text-xs uppercase font-medium">({qualityScore.level})</span>
				</div>
				<button
					onclick={onClose}
					class="text-gray-400 hover:text-gray-500 transition-colors"
					aria-label="Close"
				>
					<svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
		</div>

		<!-- Content: Side-by-Side Layout -->
		<div class="flex-1 overflow-hidden flex">
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
					{#if loadingPreview}
						<div class="flex items-center justify-center h-full">
							<svg class="animate-spin h-8 w-8 text-gray-400" fill="none" viewBox="0 0 24 24">
								<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
								<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
							</svg>
						</div>
					{:else if pdfBlobUrl}
						{#if document.file_type === 'application/pdf'}
							<iframe
								src={pdfBlobUrl}
								class="w-full h-full border border-gray-300 rounded-lg bg-white"
								title="PDF Preview"
							></iframe>
						{:else if document.file_type?.startsWith('image/')}
							<img
								src={pdfBlobUrl}
								alt={document.file_name}
								class="max-w-full h-auto rounded-lg shadow-lg mx-auto"
							/>
						{/if}
					{:else}
						<div class="flex flex-col items-center justify-center h-full text-gray-400">
							<svg class="h-12 w-12 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
							</svg>
							<p class="text-sm">Preview not available for this file type</p>
							<p class="text-xs mt-1">{document.file_type}</p>
						</div>
					{/if}
				</div>
			</div>

			<!-- Right: Editor Panel -->
			<div class="w-1/2 flex flex-col">
				<div class="px-4 py-2 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
					<div class="flex items-center gap-2">
						<span class="text-sm font-medium text-gray-700">Extracted Text</span>
						{#if hasChanges}
							<span class="text-xs px-2 py-0.5 bg-amber-100 text-amber-700 rounded-full font-medium">
								Unsaved Changes
							</span>
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
					<textarea
						bind:value={editedText}
						class="w-full h-full resize-none p-4 font-mono text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-accent focus:border-transparent"
						placeholder="Paste or type the document text here..."
					></textarea>
				</div>

				<!-- Quality Issues -->
				{#if qualityScore.issues.length > 0}
					<div class="px-4 pb-2">
						<div class="flex flex-wrap gap-2">
							{#each qualityScore.issues as issue}
								<span class="text-xs px-2 py-1 rounded-full {getQualityColor(qualityScore.level)}">
									{issue}
								</span>
							{/each}
						</div>
					</div>
				{/if}
			</div>
		</div>

		<!-- Footer -->
		<div class="flex items-center justify-between px-6 py-4 border-t border-gray-200 bg-gray-50">
			<div class="text-sm text-gray-500">
				{editedText.length.toLocaleString()} characters
				•
				{editedText.split(/\s+/).filter(w => w.length > 0).length.toLocaleString()} words
			</div>
			<div class="flex items-center gap-3">
				<button
					onclick={onClose}
					class="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
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
	</div>
</div>

