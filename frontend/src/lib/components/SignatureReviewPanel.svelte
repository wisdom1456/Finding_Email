<script lang="ts">
	import { supabase } from '$lib/supabase';
	import { getApiUrl } from '$lib/config';
	import SlideOutPanel from './ui/SlideOutPanel.svelte';
	import DocumentPreviewPane from './DocumentPreviewPane.svelte';

	let {
		open = false,
		documents = [],
		currentIndex = 0,
		caseId,
		onClose,
		onVerdictSaved,
		onNavigate
	}: {
		open?: boolean;
		documents: any[];
		currentIndex: number;
		caseId: string;
		onClose: () => void;
		onVerdictSaved: (docId: string, verdict: string) => void;
		onNavigate: (index: number) => void;
	} = $props();

	// State
	let concernMode = $state(false);
	let concernNotes = $state('');
	let saving = $state(false);
	let jumpLinkShown = $state(true);
	let pdfBlobUrl = $state<string | null>(null);
	let loadingPreview = $state(false);

	// Computed
	let currentDoc = $derived(documents[currentIndex] ?? null);
	let remaining = $derived(documents.length - currentIndex);

	// Derived PDF properties
	let isPdf = $derived(
		currentDoc
			? currentDoc.file_name?.toLowerCase().endsWith('.pdf') ||
					currentDoc.file_type === 'application/pdf'
			: false
	);
	let hasStoragePath = $derived(
		currentDoc ? Boolean(currentDoc.storage_path || currentDoc.file_path) : false
	);

	// Reset preview state when document changes
	$effect(() => {
		// Track currentDoc changes to reset preview
		const _ = currentDoc?.id;
		pdfBlobUrl = null;
		loadingPreview = false;
		jumpLinkShown = true;
	});

	async function loadPdfPreview() {
		if (!currentDoc || loadingPreview) return;
		loadingPreview = true;
		try {
			const {
				data: { session }
			} = await supabase.auth.getSession();
			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/documents/${currentDoc.id}/download`, {
				headers: {
					Authorization: `Bearer ${session?.access_token}`
				}
			});
			if (!response.ok) throw new Error('Failed to load preview');
			const blob = await response.blob();
			pdfBlobUrl = URL.createObjectURL(blob);
		} catch {
			// Preview load failed — leave pdfBlobUrl as null
		} finally {
			loadingPreview = false;
		}
	}

	async function saveVerdict(verdict: string, notes?: string) {
		if (!currentDoc || saving) return;
		saving = true;
		try {
			const {
				data: { session }
			} = await supabase.auth.getSession();
			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/documents/${currentDoc.id}/verify`, {
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session?.access_token}`
				},
				body: JSON.stringify({
					signature_verification: verdict,
					signature_verification_notes: notes || null
				})
			});
			if (!response.ok) throw new Error('Failed to save verdict');
			onVerdictSaved(currentDoc.id, verdict);
			concernMode = false;
			concernNotes = '';
			jumpLinkShown = true;
			// Auto-advance if more docs remain
			if (currentIndex < documents.length - 1) {
				onNavigate(currentIndex + 1);
			} else {
				onClose();
			}
		} finally {
			saving = false;
		}
	}

	function handleKeydown(event: KeyboardEvent) {
		if (!open || concernMode) return;
		// Ignore if focus is on an input/textarea
		const target = event.target as HTMLElement;
		if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return;

		switch (event.key) {
			case 's':
				event.preventDefault();
				saveVerdict('signed');
				break;
			case 'n':
				event.preventDefault();
				saveVerdict('not_signed');
				break;
			case 'c':
				event.preventDefault();
				concernMode = true;
				break;
			case 'ArrowRight':
			case 'ArrowDown':
				event.preventDefault();
				if (currentIndex < documents.length - 1) onNavigate(currentIndex + 1);
				break;
			case 'ArrowLeft':
			case 'ArrowUp':
				event.preventDefault();
				if (currentIndex > 0) onNavigate(currentIndex - 1);
				break;
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<SlideOutPanel {open} title="Signature Review" width="65%" {onClose}>
	<!-- Sub-header with document name and progress -->
	{#snippet children()}
		<div
			class="px-6 py-2 bg-gray-50 border-b border-gray-100 flex items-center justify-between flex-shrink-0"
		>
			<span class="text-sm font-medium text-gray-700 truncate"
				>{currentDoc?.file_name ?? ''}</span
			>
			<span class="text-xs text-gray-500 whitespace-nowrap ml-2">
				{currentIndex + 1} of {documents.length}
			</span>
		</div>

		<div class="flex flex-col h-full">
			<!-- Jump to signature hint -->
			{#if jumpLinkShown}
				<div
					class="flex items-center justify-between px-4 py-2 bg-blue-50 border-b border-blue-100 flex-shrink-0"
				>
					<span class="text-xs text-blue-600"
						>Scroll to the end to find the signature pages</span
					>
					<button
						class="text-xs text-blue-700 font-semibold hover:underline"
						onclick={() => (jumpLinkShown = false)}
					>
						Dismiss
					</button>
				</div>
			{/if}

			<!-- PDF Preview -->
			<div class="flex-1 overflow-hidden bg-gray-50 min-h-0">
				{#if currentDoc}
					<DocumentPreviewPane
						fileName={currentDoc.file_name ?? ''}
						fileType={currentDoc.file_type ?? ''}
						documentId={currentDoc.id ?? ''}
						{hasStoragePath}
						previewUrl={pdfBlobUrl}
						loading={loadingPreview}
						{isPdf}
						isImage={false}
						isTextDocument={false}
						onLoadPreview={loadPdfPreview}
						loadPdfLabel="Load PDF Preview"
						pdfHintMessage="Click to load the PDF preview for signature review."
						previewHeightClass="h-[calc(100vh-280px)]"
						wrapperClass="h-full p-4"
					/>
				{:else}
					<div class="flex items-center justify-center h-full text-gray-400">
						<span class="text-sm">No document selected</span>
					</div>
				{/if}
			</div>
		</div>
	{/snippet}

	{#snippet footer()}
		<!-- Concern notes input (shown when concern mode is active) -->
		{#if concernMode}
			<div class="p-4 border-b border-gray-100">
				<textarea
					class="w-full text-sm border border-gray-300 rounded-lg p-3 resize-none focus:ring-2 focus:ring-accent focus:border-transparent"
					rows="3"
					placeholder="Describe the concern (e.g., signature appears to be missing on page 4)..."
					bind:value={concernNotes}
				></textarea>
				<div class="flex gap-2 mt-2">
					<button
						class="btn btn-sm btn-secondary flex-1"
						onclick={() => {
							concernMode = false;
							concernNotes = '';
						}}>Cancel</button
					>
					<button
						class="btn btn-sm btn-primary flex-1"
						onclick={() => saveVerdict('unknown', concernNotes)}>Save Concern</button
					>
				</div>
			</div>
		{/if}

		<!-- Verdict buttons -->
		<div class="p-4 flex gap-3">
			<button
				class="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl font-bold text-sm transition-all
                       bg-green-600 hover:bg-green-700 text-white disabled:opacity-50"
				disabled={saving}
				onclick={() => saveVerdict('signed')}
			>
				✓ Signed
			</button>
			<button
				class="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl font-bold text-sm transition-all
                       bg-amber-500 hover:bg-amber-600 text-white disabled:opacity-50"
				disabled={saving}
				onclick={() => {
					concernMode = !concernMode;
				}}
			>
				⚠ Concern
			</button>
			<button
				class="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl font-bold text-sm transition-all
                       bg-red-600 hover:bg-red-700 text-white disabled:opacity-50"
				disabled={saving}
				onclick={() => saveVerdict('not_signed')}
			>
				✗ No Signature
			</button>
		</div>

		<!-- Keyboard shortcut hints -->
		<div class="px-4 pb-3 flex justify-center gap-6 text-xs text-gray-400" aria-hidden="true">
			<span><kbd class="font-mono bg-gray-100 px-1 rounded">S</kbd></span>
			<span><kbd class="font-mono bg-gray-100 px-1 rounded">C</kbd></span>
			<span><kbd class="font-mono bg-gray-100 px-1 rounded">N</kbd></span>
			<span><kbd class="font-mono bg-gray-100 px-1 rounded">← →</kbd></span>
		</div>
	{/snippet}
</SlideOutPanel>
