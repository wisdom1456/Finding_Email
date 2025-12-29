<script lang="ts">
	import { getApiUrl } from '$lib/config';
	import { supabase } from '$lib/supabase';
	import { toastStore } from '$lib/stores/toastStore';
	import { slide, fade } from 'svelte/transition';
	import { 
		Search, 
		Filter, 
		Trash2, 
		CheckCircle2, 
		AlertTriangle, 
		XCircle, 
		RefreshCw,
		MoreHorizontal,
		CheckSquare,
		Square,
		Inbox,
		Zap
	} from 'lucide-svelte';
	
	import AsyncButton from './ui/AsyncButton.svelte';
	import CorrectionModal from './CorrectionModal.svelte';
	import RecoveryModal from './RecoveryModal.svelte';
	import DocumentCard from './DocumentCard.svelte';
	import DocumentStatusBanner from './DocumentStatusBanner.svelte';

	// Props
	let {
		documents = [],
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
	let filterQuery = $state('');
	let editingDocument = $state<any>(null);
	let recoveryDocument = $state<any>(null);
	let viewMode = $state<'triage' | 'all'>('triage');

	// Triage Groups
	let triageGroups = $derived.by(() => {
		const groups = {
			critical: [] as any[], // download_failed, corrupted
			needs_attention: [] as any[], // extraction_failed, needs_review (low quality)
			ready: [] as any[] // ready (high/medium quality)
		};

		for (const doc of documents) {
			const status = doc.status;
			if (status === 'download_failed' || status === 'corrupted') {
				groups.critical.push(doc);
			} else if (status === 'extraction_failed' || status === 'needs_review' || (status === 'ready' && !doc.is_verified)) {
				groups.needs_attention.push(doc);
			} else {
				groups.ready.push(doc);
			}
		}

		return groups;
	});

	// Filtered list for "All" view
	let filteredDocs = $derived.by(() => {
		if (!filterQuery) return documents;
		const query = filterQuery.toLowerCase();
		return documents.filter(doc => 
			doc.file_name.toLowerCase().includes(query) || 
			doc.status.toLowerCase().includes(query)
		);
	});

	// Stats for Banner
	let stats = $derived.by(() => {
		const counts = { ready: 0, review: 0, failed: 0, missing: 0 };
		for (const doc of documents) {
			if (doc.status === 'ready') counts.ready++;
			else if (doc.status === 'needs_review') counts.review++;
			else if (doc.status === 'extraction_failed') counts.failed++;
			else if (doc.status === 'download_failed' || doc.status === 'corrupted') counts.missing++;
		}
		return counts;
	});

	// Selection Handlers
	function toggleSelection(docId: string) {
		const newSet = new Set(selectedDocIds);
		if (newSet.has(docId)) newSet.delete(docId);
		else newSet.add(docId);
		selectedDocIds = newSet;
	}

	function toggleAll() {
		if (selectedDocIds.size === documents.length) {
			selectedDocIds = new Set();
		} else {
			selectedDocIds = new Set(documents.map(d => d.id));
		}
	}

	// Document Actions
	async function handleVerify(docId: string) {
		try {
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) throw new Error('Not authenticated');

			const response = await fetch(`${getApiUrl()}/api/documents/${docId}/verify`, {
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`,
				},
				body: JSON.stringify({ is_verified: true }),
			});

			if (!response.ok) throw new Error('Failed to verify document');
			toastStore.success('Document verified');
			await onDocumentsUpdated();
		} catch (error: any) {
			toastStore.error(error.message);
		}
	}

	async function handleDelete(docId: string) {
		if (!confirm('Are you sure you want to delete this document?')) return;

		try {
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) throw new Error('Not authenticated');

			const response = await fetch(`${getApiUrl()}/api/documents/bulk-delete`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`,
				},
				body: JSON.stringify({ document_ids: [docId] }),
			});

			if (!response.ok) throw new Error('Failed to delete document');
			toastStore.success('Document deleted');
			await onDocumentsUpdated();
		} catch (error: any) {
			toastStore.error(error.message);
		}
	}

	async function handleReExtract(docId: string) {
		toastStore.info('Re-extracting with Vision OCR...');
		try {
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) throw new Error('Not authenticated');

			const response = await fetch(`${getApiUrl()}/api/documents/${docId}/extract`, {
				method: 'POST',
				headers: {
					Authorization: `Bearer ${session.access_token}`,
				}
			});

			if (!response.ok) throw new Error('Extraction failed');
			toastStore.success('Extraction complete');
			await onDocumentsUpdated();
		} catch (error: any) {
			toastStore.error(error.message);
		}
	}

	async function handleSkip(docId: string) {
		try {
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) throw new Error('Not authenticated');

			const response = await fetch(`${getApiUrl()}/api/documents/${docId}/verify`, {
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`,
				},
				body: JSON.stringify({ is_verified: false, is_flagged_as_junk: true }),
			});

			if (!response.ok) throw new Error('Failed to skip document');
			toastStore.success('Document skipped');
			await onDocumentsUpdated();
		} catch (error: any) {
			toastStore.error(error.message);
		}
	}

	// Bulk Actions
	async function bulkVerify() {
		if (selectedDocIds.size === 0) return;
		bulkActionLoading = true;
		try {
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) throw new Error('Not authenticated');

			for (const id of selectedDocIds) {
				await fetch(`${getApiUrl()}/api/documents/${id}/verify`, {
					method: 'PATCH',
					headers: {
						'Content-Type': 'application/json',
						Authorization: `Bearer ${session.access_token}`,
					},
					body: JSON.stringify({ is_verified: true }),
				});
			}
			toastStore.success(`Verified ${selectedDocIds.size} documents`);
			selectedDocIds = new Set();
			await onDocumentsUpdated();
		} finally {
			bulkActionLoading = false;
		}
	}

	async function bulkDelete() {
		if (selectedDocIds.size === 0 || !confirm(`Delete ${selectedDocIds.size} documents?`)) return;
		bulkActionLoading = true;
		try {
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) throw new Error('Not authenticated');

			await fetch(`${getApiUrl()}/api/documents/bulk-delete`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`,
				},
				body: JSON.stringify({ document_ids: Array.from(selectedDocIds) }),
			});
			toastStore.success(`Deleted ${selectedDocIds.size} documents`);
			selectedDocIds = new Set();
			await onDocumentsUpdated();
		} finally {
			bulkActionLoading = false;
		}
	}
</script>

<div class="space-y-8" id="verification">
	<!-- Summary Header -->
	<div class="flex flex-col sm:flex-row sm:items-end justify-between gap-6">
		<div class="flex-1">
			<h2 class="text-3xl font-black text-gray-900 tracking-tight flex items-center gap-3">
				<div class="p-2 rounded-xl bg-accent/10 text-accent">
					<Inbox class="w-8 h-8" />
				</div>
				Verification Hub
			</h2>
			<p class="mt-2 text-gray-500 font-medium text-lg max-w-2xl">
				Review and confirm extracted data from {documents.length} documents before running the final legal analysis.
			</p>
		</div>

		<div class="flex items-center gap-3 p-1.5 bg-gray-100 rounded-xl">
			<button 
				onclick={() => viewMode = 'triage'}
				class={`px-4 py-2 text-sm font-bold rounded-lg transition-all ${viewMode === 'triage' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
			>
				Triage View
			</button>
			<button 
				onclick={() => viewMode = 'all'}
				class={`px-4 py-2 text-sm font-bold rounded-lg transition-all ${viewMode === 'all' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
			>
				All Documents
			</button>
		</div>
	</div>

	<!-- Status Banner -->
	<DocumentStatusBanner {stats} />

	<!-- Search & Bulk Actions -->
	<div class="sticky top-4 z-30 flex flex-col md:flex-row items-center gap-4 bg-white/80 backdrop-blur-md p-4 rounded-2xl border border-gray-200 shadow-xl shadow-black/5">
		<div class="relative flex-1 w-full">
			<Search class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
			<input 
				type="text" 
				bind:value={filterQuery}
				placeholder="Search documents by name or status..."
				class="w-full pl-12 pr-4 py-3 bg-gray-50 border-none rounded-xl focus:ring-2 focus:ring-accent font-medium text-sm"
			/>
		</div>

		{#if selectedDocIds.size > 0}
			<div transition:fade class="flex items-center gap-3 w-full md:w-auto">
				<span class="text-sm font-black text-accent whitespace-nowrap bg-accent/10 px-3 py-1.5 rounded-lg">
					{selectedDocIds.size} Selected
				</span>
				<div class="flex gap-2 w-full md:w-auto">
					<button 
						onclick={bulkVerify}
						disabled={bulkActionLoading}
						class="flex-1 md:flex-none inline-flex items-center justify-center px-4 py-2.5 text-sm font-black rounded-xl bg-accent text-white hover:bg-accent-hover transition-all shadow-lg shadow-accent/20"
					>
						Verify All
					</button>
					<button 
						onclick={bulkDelete}
						disabled={bulkActionLoading}
						class="flex-1 md:flex-none inline-flex items-center justify-center px-4 py-2.5 text-sm font-black rounded-xl bg-red-50 text-red-600 border border-red-100 hover:bg-red-100 transition-all"
					>
						Delete
					</button>
				</div>
			</div>
		{:else}
			<button 
				onclick={toggleAll}
				class="hidden md:flex items-center gap-2 px-4 py-2.5 text-sm font-bold text-gray-600 hover:bg-gray-50 rounded-xl transition-colors"
			>
				<CheckSquare class="w-5 h-5" />
				Select All
			</button>
		{/if}
	</div>

	<!-- Main Content Area -->
	{#if viewMode === 'triage'}
		<div class="space-y-12">
			<!-- Critical Issues (Missing files, etc) -->
			{#if triageGroups.critical.length > 0}
				<section>
					<div class="flex items-center gap-3 mb-6">
						<div class="p-1.5 rounded-lg bg-red-100 text-red-600">
							<AlertTriangle class="w-5 h-5" />
						</div>
						<h3 class="text-xl font-black text-gray-900 uppercase tracking-tight">Needs Immediate Attention</h3>
						<span class="ml-auto text-xs font-bold text-red-600 bg-red-50 px-2 py-1 rounded-full border border-red-100">
							{triageGroups.critical.length} Critical
						</span>
					</div>
					<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
						{#each triageGroups.critical as doc (doc.id)}
							<DocumentCard 
								{doc}
								onReplace={() => recoveryDocument = doc}
								onSkip={() => handleSkip(doc.id)}
								onDelete={() => handleDelete(doc.id)}
							/>
						{/each}
					</div>
				</section>
			{/if}

			<!-- Needs Attention (Extraction failed, low quality) -->
			{#if triageGroups.needs_attention.length > 0}
				<section>
					<div class="flex items-center gap-3 mb-6">
						<div class="p-1.5 rounded-lg bg-amber-100 text-amber-600">
							<Zap class="w-5 h-5" />
						</div>
						<h3 class="text-xl font-black text-gray-900 uppercase tracking-tight">Pending Review</h3>
						<span class="ml-auto text-xs font-bold text-amber-600 bg-amber-50 px-2 py-1 rounded-full border border-amber-100">
							{triageGroups.needs_attention.length} Pending
						</span>
					</div>
					<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
						{#each triageGroups.needs_attention as doc (doc.id)}
							<DocumentCard 
								{doc}
								onEdit={() => editingDocument = doc}
								onReExtract={() => handleReExtract(doc.id)}
								onVerify={() => handleVerify(doc.id)}
								onSkip={() => handleSkip(doc.id)}
								onDelete={() => handleDelete(doc.id)}
							/>
						{/each}
					</div>
				</section>
			{/if}

			<!-- Ready for Analysis -->
			{#if triageGroups.ready.length > 0}
				<section>
					<div class="flex items-center gap-3 mb-6">
						<div class="p-1.5 rounded-lg bg-green-100 text-green-600">
							<CheckCircle2 class="w-5 h-5" />
						</div>
						<h3 class="text-xl font-black text-gray-900 uppercase tracking-tight text-gray-400">Ready for Analysis</h3>
						<span class="ml-auto text-xs font-bold text-gray-400 bg-gray-50 px-2 py-1 rounded-full border border-gray-100">
							{triageGroups.ready.length} Ready
						</span>
					</div>
					<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 opacity-60 grayscale-[0.5] hover:opacity-100 hover:grayscale-0 transition-all">
						{#each triageGroups.ready as doc (doc.id)}
							<DocumentCard 
								{doc}
								onEdit={() => editingDocument = doc}
								onDelete={() => handleDelete(doc.id)}
							/>
						{/each}
					</div>
				</section>
			{/if}

			{#if documents.length === 0}
				<div class="flex flex-col items-center justify-center py-20 bg-gray-50 rounded-3xl border border-dashed border-gray-200">
					<div class="p-4 rounded-full bg-white shadow-sm text-gray-300 mb-4">
						<Inbox class="w-12 h-12" />
					</div>
					<h3 class="text-lg font-bold text-gray-900">No documents found</h3>
					<p class="text-gray-500 text-sm mt-1">Upload files to get started with the analysis.</p>
				</div>
			{/if}
		</div>
	{:else}
		<!-- All Documents List View -->
		<div class="space-y-3">
			{#each filteredDocs as doc (doc.id)}
				<div class="flex items-center gap-4 group">
					<button 
						onclick={() => toggleSelection(doc.id)}
						class={`p-1.5 rounded-lg transition-colors ${selectedDocIds.has(doc.id) ? 'bg-accent/10 text-accent' : 'text-gray-300 hover:text-gray-400'}`}
					>
						{#if selectedDocIds.has(doc.id)}
							<CheckSquare class="w-6 h-6" />
						{:else}
							<Square class="w-6 h-6" />
						{/if}
					</button>
					<div class="flex-1">
						<DocumentCard 
							{doc}
							onEdit={() => editingDocument = doc}
							onReplace={() => recoveryDocument = doc}
							onReExtract={() => handleReExtract(doc.id)}
							onVerify={() => handleVerify(doc.id)}
							onSkip={() => handleSkip(doc.id)}
							onDelete={() => handleDelete(doc.id)}
						/>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<!-- Modals -->
{#if editingDocument}
	<CorrectionModal
		document={editingDocument}
		onClose={() => editingDocument = null}
		onSaved={onDocumentsUpdated}
	/>
{/if}

{#if recoveryDocument}
	<RecoveryModal
		doc={recoveryDocument}
		bind:isOpen={recoveryDocument}
		onSuccess={onDocumentsUpdated}
	/>
{/if}
