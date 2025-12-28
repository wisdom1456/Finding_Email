<script lang="ts">
	import { getApiUrl } from '$lib/config';
	import { supabase } from '$lib/supabase';
	import { toastStore } from '$lib/stores/toastStore';
	import AsyncButton from './ui/AsyncButton.svelte';
	import CorrectionModal from './CorrectionModal.svelte';

	// Props
	let {
		documents,
		caseId,
		onDocumentsUpdated,
	}: {
		documents: any[];
		caseId: string;
		onDocumentsUpdated: () => Promise<void>;
	} = $props();

	// State
	let selectedDocIds = $state<Set<string>>(new Set());
	let bulkActionLoading = $state(false);
	let viewMode = $state<'all' | 'needs-attention' | 'ready'>('all');
	let editingDocument = $state<any>(null);

	// Junk detection patterns
	const JUNK_PATTERNS = [
		/instructions?/i,
		/needed.*to.*proceed/i,
		/blank.*form/i,
		/empty/i,
		/template/i,
		/attaching.*document/i,
		/documents.*needed/i,
	];

	// Derived: Categorize documents
	let categorizedDocs = $derived.by(() => {
		const needsAttention: any[] = [];
		const ready: any[] = [];
		const junkCandidates: any[] = [];

		for (const doc of documents) {
			const quality = getQualityLevel(doc);
			const isJunk = isLikelyJunk(doc);

			if (doc.is_flagged_as_junk) {
				junkCandidates.push({ ...doc, quality, isJunk: true });
			} else if (quality === 'low' || isJunk) {
				needsAttention.push({ ...doc, quality, isJunk });
			} else {
				ready.push({ ...doc, quality, isJunk: false });
			}
		}

		return { needsAttention, ready, junkCandidates };
	});

	// Derived: Visible documents based on filter
	let visibleDocs = $derived.by(() => {
		switch (viewMode) {
			case 'needs-attention':
				return categorizedDocs.needsAttention;
			case 'ready':
				return categorizedDocs.ready;
			default:
				return documents.map(doc => ({
					...doc,
					quality: getQualityLevel(doc),
					isJunk: isLikelyJunk(doc)
				}));
		}
	});

	// Derived: Stats
	let stats = $derived({
		total: documents.length,
		needsAttention: categorizedDocs.needsAttention.length,
		ready: categorizedDocs.ready.length,
		junk: categorizedDocs.junkCandidates.length,
		selected: selectedDocIds.size,
	});

	function getQualityLevel(doc: any): 'high' | 'medium' | 'low' | 'unknown' {
		if (!doc.extracted_text || doc.extracted_text.trim().length === 0) {
			return 'low';
		}

		const textLength = doc.extracted_text.trim().length;
		const quality = doc.extraction_quality?.toLowerCase();

		if (quality === 'high' || textLength > 500) {
			return 'high';
		} else if (quality === 'medium' || textLength > 100) {
			return 'medium';
		} else if (quality === 'low' || textLength < 100) {
			return 'low';
		}

		return 'unknown';
	}

	function isLikelyJunk(doc: any): boolean {
		const fileName = doc.file_name || '';
		
		// Check filename patterns
		if (JUNK_PATTERNS.some(pattern => pattern.test(fileName))) {
			return true;
		}

		// Check for empty or near-empty content with large file size
		if (doc.extracted_text) {
			const textLength = doc.extracted_text.trim().length;
			const fileSize = doc.file_size || 0;
			
			// Large file with minimal text = likely blank form/image
			if (fileSize > 100000 && textLength < 50) {
				return true;
			}
		}

		return false;
	}

	function getQualityColor(quality: string): string {
		switch (quality) {
			case 'high':
				return 'bg-green-100 text-green-800 border-green-300';
			case 'medium':
				return 'bg-yellow-100 text-yellow-800 border-yellow-300';
			case 'low':
				return 'bg-red-100 text-red-800 border-red-300';
			default:
				return 'bg-gray-100 text-gray-600 border-gray-300';
		}
	}

	function toggleSelection(docId: string) {
		const newSet = new Set(selectedDocIds);
		if (newSet.has(docId)) {
			newSet.delete(docId);
		} else {
			newSet.add(docId);
		}
		selectedDocIds = newSet;
	}

	function selectAll() {
		selectedDocIds = new Set(visibleDocs.map(d => d.id));
	}

	function clearSelection() {
		selectedDocIds = new Set();
	}

	function selectJunkCandidates() {
		const junkIds = documents
			.filter(doc => isLikelyJunk(doc) && !doc.is_flagged_as_junk)
			.map(doc => doc.id);
		selectedDocIds = new Set(junkIds);
	}

	async function bulkDelete() {
		if (selectedDocIds.size === 0) return;

		const confirmed = confirm(
			`Are you sure you want to delete ${selectedDocIds.size} document(s)? This action cannot be undone.`
		);
		if (!confirmed) return;

		bulkActionLoading = true;

		try {
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) throw new Error('Not authenticated');

			const response = await fetch(`${getApiUrl()}/api/documents/bulk-delete`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`,
				},
				body: JSON.stringify({
					document_ids: Array.from(selectedDocIds),
				}),
			});

			if (!response.ok) {
				const error = await response.json();
				throw new Error(error.detail || 'Failed to delete documents');
			}

			const result = await response.json();
			
			if (result.deleted_count > 0) {
				toastStore.success(`Deleted ${result.deleted_count} document(s)`);
			}
			if (result.failed_ids.length > 0) {
				toastStore.error(`Failed to delete ${result.failed_ids.length} document(s)`);
			}

			selectedDocIds = new Set();
			await onDocumentsUpdated();
		} catch (error: any) {
			toastStore.error(error.message || 'Failed to delete documents');
		} finally {
			bulkActionLoading = false;
		}
	}

	async function bulkMarkAsJunk() {
		if (selectedDocIds.size === 0) return;

		bulkActionLoading = true;

		try {
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) throw new Error('Not authenticated');

			let successCount = 0;
			for (const docId of selectedDocIds) {
				const response = await fetch(`${getApiUrl()}/api/documents/${docId}/verify`, {
					method: 'PATCH',
					headers: {
						'Content-Type': 'application/json',
						Authorization: `Bearer ${session.access_token}`,
					},
					body: JSON.stringify({
						is_flagged_as_junk: true,
						is_verified: false,
					}),
				});

				if (response.ok) {
					successCount++;
				}
			}

			if (successCount > 0) {
				toastStore.success(`Marked ${successCount} document(s) as junk`);
			}

			selectedDocIds = new Set();
			await onDocumentsUpdated();
		} catch (error: any) {
			toastStore.error(error.message || 'Failed to mark documents as junk');
		} finally {
			bulkActionLoading = false;
		}
	}

	async function bulkVerify() {
		if (selectedDocIds.size === 0) return;

		bulkActionLoading = true;

		try {
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) throw new Error('Not authenticated');

			let successCount = 0;
			for (const docId of selectedDocIds) {
				const response = await fetch(`${getApiUrl()}/api/documents/${docId}/verify`, {
					method: 'PATCH',
					headers: {
						'Content-Type': 'application/json',
						Authorization: `Bearer ${session.access_token}`,
					},
					body: JSON.stringify({
						is_verified: true,
						is_flagged_as_junk: false,
					}),
				});

				if (response.ok) {
					successCount++;
				}
			}

			if (successCount > 0) {
				toastStore.success(`Verified ${successCount} document(s)`);
			}

			selectedDocIds = new Set();
			await onDocumentsUpdated();
		} catch (error: any) {
			toastStore.error(error.message || 'Failed to verify documents');
		} finally {
			bulkActionLoading = false;
		}
	}

	function formatFileSize(bytes: number): string {
		if (bytes < 1024) return bytes + ' B';
		if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
		return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
	}
</script>

<div class="space-y-4">
	<!-- Stats Bar -->
	<div class="flex items-center justify-between bg-white rounded-lg p-4 border border-gray-200">
		<div class="flex items-center gap-6">
			<div class="text-center">
				<div class="text-2xl font-bold text-gray-900">{stats.total}</div>
				<div class="text-xs text-gray-500">Total</div>
			</div>
			<div class="h-8 w-px bg-gray-200"></div>
			<button 
				onclick={() => viewMode = 'needs-attention'}
				class="text-center px-3 py-1 rounded-md transition-colors {viewMode === 'needs-attention' ? 'bg-red-100' : 'hover:bg-gray-100'}"
			>
				<div class="text-xl font-bold {stats.needsAttention > 0 ? 'text-red-600' : 'text-gray-400'}">{stats.needsAttention}</div>
				<div class="text-xs {viewMode === 'needs-attention' ? 'text-red-600 font-medium' : 'text-gray-500'}">Needs Attention</div>
			</button>
			<button 
				onclick={() => viewMode = 'ready'}
				class="text-center px-3 py-1 rounded-md transition-colors {viewMode === 'ready' ? 'bg-green-100' : 'hover:bg-gray-100'}"
			>
				<div class="text-xl font-bold text-green-600">{stats.ready}</div>
				<div class="text-xs {viewMode === 'ready' ? 'text-green-600 font-medium' : 'text-gray-500'}">Ready</div>
			</button>
			{#if stats.junk > 0}
				<div class="text-center px-3 py-1 bg-gray-100 rounded-md">
					<div class="text-xl font-bold text-gray-400">{stats.junk}</div>
					<div class="text-xs text-gray-500">Flagged Junk</div>
				</div>
			{/if}
		</div>
		<button
			onclick={() => viewMode = 'all'}
			class="text-sm text-accent hover:text-accent-hover font-medium {viewMode === 'all' ? 'underline' : ''}"
		>
			View All
		</button>
	</div>

	<!-- Bulk Action Toolbar -->
	{#if selectedDocIds.size > 0}
		<div class="sticky top-0 z-10 bg-accent/10 border border-accent/30 rounded-lg p-3 flex items-center justify-between shadow-sm">
			<div class="flex items-center gap-4">
				<span class="text-sm font-medium text-contrast">
					{selectedDocIds.size} selected
				</span>
				<button
					onclick={clearSelection}
					class="text-sm text-gray-600 hover:text-gray-800"
				>
					Clear
				</button>
			</div>
			<div class="flex items-center gap-2">
				<AsyncButton
					onclick={bulkVerify}
					loading={bulkActionLoading}
					variant="primary"
					size="sm"
					loadingText="Verifying..."
				>
					Verify Selected
				</AsyncButton>
				<AsyncButton
					onclick={bulkMarkAsJunk}
					loading={bulkActionLoading}
					variant="secondary"
					size="sm"
					loadingText="Marking..."
				>
					Mark as Junk
				</AsyncButton>
				<AsyncButton
					onclick={bulkDelete}
					loading={bulkActionLoading}
					variant="danger"
					size="sm"
					loadingText="Deleting..."
				>
					Delete Selected
				</AsyncButton>
			</div>
		</div>
	{/if}

	<!-- Quick Actions -->
	<div class="flex items-center gap-2 text-sm">
		<button
			onclick={selectAll}
			class="text-accent hover:text-accent-hover font-medium"
		>
			Select All
		</button>
		<span class="text-gray-300">|</span>
		<button
			onclick={selectJunkCandidates}
			class="text-amber-600 hover:text-amber-700 font-medium"
		>
			Select Suggested Junk
		</button>
		<span class="text-gray-300">|</span>
		<button
			onclick={clearSelection}
			class="text-gray-600 hover:text-gray-800"
		>
			Clear Selection
		</button>
	</div>

	<!-- Document List -->
	<div class="space-y-2">
		{#each visibleDocs as doc}
			<div 
				class="flex items-start gap-3 p-4 rounded-lg border transition-all cursor-pointer {
					selectedDocIds.has(doc.id) 
						? 'bg-accent/10 border-accent' 
						: doc.isJunk 
							? 'bg-amber-50 border-amber-200 hover:border-amber-300' 
							: 'bg-white border-gray-200 hover:border-gray-300'
				}"
				role="button"
				tabindex="0"
				onclick={(e) => {
					// Don't open modal if clicking on checkbox
					if ((e.target as HTMLElement).tagName === 'INPUT') return;
					editingDocument = doc;
				}}
				onkeydown={(e) => {
					if (e.key === 'Enter' || e.key === ' ') {
						e.preventDefault();
						editingDocument = doc;
					}
				}}
			>
				<!-- Checkbox -->
				<input
					type="checkbox"
					checked={selectedDocIds.has(doc.id)}
					onchange={() => toggleSelection(doc.id)}
					class="mt-1 h-4 w-4 text-accent focus:ring-accent border-gray-300 rounded cursor-pointer"
				/>

				<!-- Document Info -->
				<div class="flex-1 min-w-0">
					<div class="flex items-center gap-2 mb-1">
						<span class="font-medium text-gray-900 truncate">{doc.file_name}</span>
						
						<!-- Quality Badge -->
						<span class="px-2 py-0.5 text-xs font-medium rounded border {getQualityColor(doc.quality)}">
							{doc.quality?.toUpperCase() || 'UNKNOWN'}
						</span>

						<!-- Junk Warning -->
						{#if doc.isJunk && !doc.is_flagged_as_junk}
							<span class="px-2 py-0.5 text-xs font-medium rounded bg-amber-100 text-amber-800 border border-amber-300">
								SUGGESTED JUNK
							</span>
						{/if}

						{#if doc.is_flagged_as_junk}
							<span class="px-2 py-0.5 text-xs font-medium rounded bg-gray-200 text-gray-600 border border-gray-300 line-through">
								JUNK
							</span>
						{/if}

						{#if doc.is_verified}
							<span class="px-2 py-0.5 text-xs font-medium rounded bg-green-100 text-green-800 border border-green-300">
								VERIFIED
							</span>
						{/if}

						<!-- Extraction Method -->
						{#if doc.extraction_method}
							<span class="px-2 py-0.5 text-xs font-medium rounded bg-blue-50 text-blue-700 border border-blue-200">
								{doc.extraction_method}
							</span>
						{/if}
					</div>

					<div class="flex items-center gap-4 text-sm text-gray-500">
						<span>{formatFileSize(doc.file_size)}</span>
						{#if doc.page_count}
							<span>{doc.page_count} page{doc.page_count !== 1 ? 's' : ''}</span>
						{/if}
						{#if doc.extracted_text}
							<span>{doc.extracted_text.length.toLocaleString()} chars</span>
						{:else}
							<span class="text-red-500">No text extracted</span>
						{/if}
					</div>

					<!-- Preview of extracted text -->
					{#if doc.extracted_text && doc.extracted_text.trim().length > 0}
						<p class="mt-2 text-sm text-gray-600 line-clamp-2">
							{doc.extracted_text.trim().substring(0, 200)}...
						</p>
					{:else if doc.extraction_error}
						<p class="mt-2 text-sm text-red-600">
							Error: {doc.extraction_error}
						</p>
					{/if}
				</div>
			</div>
		{/each}
	</div>

	<!-- Empty State -->
	{#if visibleDocs.length === 0}
		<div class="text-center py-12 text-gray-500">
			<svg class="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
			</svg>
			<p class="mt-2 text-sm">
				{#if viewMode === 'needs-attention'}
					All documents are in good shape!
				{:else if viewMode === 'ready'}
					No verified documents yet.
				{:else}
					No documents uploaded.
				{/if}
			</p>
		</div>
	{/if}
</div>

<!-- Correction Modal -->
{#if editingDocument}
	<CorrectionModal
		document={editingDocument}
		onClose={() => editingDocument = null}
		onSaved={onDocumentsUpdated}
	/>
{/if}

