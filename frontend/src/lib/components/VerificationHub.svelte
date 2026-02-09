<script lang="ts">
	import { getApiUrl } from '$lib/config';
	import { supabase, getSecureSession } from '$lib/supabase';
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
		Zap,
		Info
	} from 'lucide-svelte';
	
	import AsyncButton from './ui/AsyncButton.svelte';
	import Badge from './ui/Badge.svelte';
	import Modal from './ui/Modal.svelte';
	import ConfirmDialog from './ui/ConfirmDialog.svelte';
	import CorrectionModal from './CorrectionModal.svelte';
	import RecoveryModal from './RecoveryModal.svelte';
	import DocumentCard from './DocumentCard.svelte';
	import DocumentStatusBanner from './DocumentStatusBanner.svelte';
	import DocumentSummaryCard from './DocumentSummaryCard.svelte';

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
	let showRecoveryModal = $state(false);
	let viewingDocument = $state<any>(null);
	let pdfBlobUrl = $state<string | null>(null);
	let loadingPreview = $state(false);
	let documentViewerTab = $state<'preview' | 'summary' | 'text'>('preview');
	let documentSummary = $state<any>(null);
	let documentSummaries = $state<any[]>([]);
	let loadingDocumentSummary = $state(false);
	let viewMode = $state<'triage' | 'all'>('triage');
	let showInstructions = $state(false);
	let processingDocIds = $state<Set<string>>(new Set());
	let remainingOcrCount = $state(0);

	// Confirmation dialog state
	let confirmDialog = $state<{
		open: boolean;
		type: 'delete' | 'bulk-delete' | 'skip';
		docId?: string;
		count?: number;
	}>({ open: false, type: 'delete' });

	// Triage Groups
	let triageGroups = $derived.by(() => {
		const groups = {
			critical: [] as any[], // download_failed, corrupted
			needs_attention: [] as any[], // extraction_failed, needs_review (low quality)
			ready: [] as any[], // ready (high/medium quality)
			duplicates: [] as any[], // duplicate documents
			excluded: [] as any[] // documents manually excluded from analysis
		};

		for (const doc of documents) {
			const status = doc.status;
			const isDuplicate = doc.metadata?.is_duplicate === true || status === 'duplicate';
			const isExcluded = doc.metadata?.excluded === true;
			
			if (isExcluded) {
				groups.excluded.push(doc);
			} else if (isDuplicate) {
				// Duplicates go to their own section
				groups.duplicates.push(doc);
			} else if (status === 'download_failed' || status === 'corrupted') {
				groups.critical.push(doc);
			} else if (
				status === 'extraction_failed' ||
				status === 'needs_review' ||
				status === 'pending' ||
				(status === 'ready' && !doc.is_verified)
			) {
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
		const counts = { ready: 0, review: 0, failed: 0, missing: 0, duplicates: 0 };
		for (const doc of documents) {
			const isDuplicate = doc.metadata?.is_duplicate === true || doc.status === 'duplicate';
			if (isDuplicate) counts.duplicates++;
			else if (doc.status === 'ready') counts.ready++;
			else if (doc.status === 'needs_review' || doc.status === 'pending') counts.review++;
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
const { session, user } = await getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

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
		confirmDialog = { open: true, type: 'delete', docId };
	}

	async function performDelete(docId: string) {
		try {
const { session, user } = await getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

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

	async function handleAlwaysDelete(docName: string, docId?: string) {
		try {
const { session, user } = await getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();

			// 1. Delete the current document (and any others with same name) - no confirmation needed
			if (docId) {
				// Find all documents with this name and delete them
				const docsToDelete = documents.filter(d => d.file_name === docName);
				const docIds = docsToDelete.map(d => d.id);
				
				if (docIds.length > 0) {
					const deleteResponse = await fetch(`${apiUrl}/api/documents/bulk-delete`, {
						method: 'POST',
						headers: {
							'Content-Type': 'application/json',
							Authorization: `Bearer ${session.access_token}`,
						},
						body: JSON.stringify({ document_ids: docIds }),
					});

					if (!deleteResponse.ok) {
						console.warn('Failed to delete documents, continuing with blacklist update');
					}
				}
			}

			// 2. Fetch current profile
			const getResponse = await fetch(`${apiUrl}/api/profile`, {
				headers: {
					'Authorization': `Bearer ${session.access_token}`,
					'Content-Type': 'application/json'
				}
			});

			if (!getResponse.ok) throw new Error('Failed to fetch profile');
			const profile = await getResponse.json();

			// 3. Update blacklist
			const currentBlacklist = profile.ai_preferences?.blacklisted_documents || [];
			if (!currentBlacklist.includes(docName)) {
				const updatedBlacklist = [...currentBlacklist, docName];
				
				const profileData = {
					ai_preferences: {
						...profile.ai_preferences,
						blacklisted_documents: updatedBlacklist
					}
				};

				// 4. Save profile
				const updateResponse = await fetch(`${apiUrl}/api/profile`, {
					method: 'PUT',
					headers: {
						'Authorization': `Bearer ${session.access_token}`,
						'Content-Type': 'application/json'
					},
					body: JSON.stringify(profileData)
				});

				if (!updateResponse.ok) throw new Error('Failed to update blacklist');
			}

			toastStore.success(`"${docName}" will always be excluded from future imports`);
			await onDocumentsUpdated(); // Refresh the document list
		} catch (error: any) {
			toastStore.error(`Blacklist error: ${error.message}`);
		}
	}

	async function handleReExtract(docId: string) {
		toastStore.info('Re-extracting with Vision OCR...');
		try {
const { session, user } = await getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

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
const { session, user } = await getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

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

	async function handleToggleExclusion(docId: string, excluded: boolean) {
		try {
const { session, user } = await getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

			const response = await fetch(`${getApiUrl()}/api/documents/${docId}/exclusion`, {
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`,
				},
				body: JSON.stringify({ excluded }),
			});

			if (!response.ok) throw new Error('Failed to toggle exclusion');
			toastStore.success(excluded ? 'Document excluded from analysis' : 'Document included in analysis');
			await onDocumentsUpdated();
		} catch (error: any) {
			toastStore.error(error.message);
		}
	}

	async function handleBulkExtract() {
		const docsToProcess = triageGroups.needs_attention.filter(d => !d.extracted_text || d.status === 'pending');
		if (docsToProcess.length === 0) return;

		toastStore.info(`Running sequential extraction on ${docsToProcess.length} documents...`);
		bulkActionLoading = true;
		remainingOcrCount = docsToProcess.length;
		
		try {
const { session, user } = await getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

			let extractedCount = 0;
			let failedCount = 0;

			for (const doc of docsToProcess) {
				processingDocIds.add(doc.id);
				
				try {
					const response = await fetch(`${getApiUrl()}/api/documents/${doc.id}/extract`, {
						method: 'POST',
						headers: {
							Authorization: `Bearer ${session.access_token}`,
						}
					});

					if (!response.ok) throw new Error('Extraction failed');
					extractedCount++;
				} catch (err) {
					console.error(`Failed to extract ${doc.file_name}:`, err);
					failedCount++;
				} finally {
					processingDocIds.delete(doc.id);
					remainingOcrCount--;
					// Update UI as each document completes
					await onDocumentsUpdated();
				}
			}
			
			if (failedCount > 0) {
				toastStore.warning(`Extracted ${extractedCount} docs, but ${failedCount} failed.`);
			} else {
				toastStore.success(`Successfully extracted all ${extractedCount} documents`);
			}
		} catch (error: any) {
			toastStore.error(error.message);
		} finally {
			bulkActionLoading = false;
			remainingOcrCount = 0;
			processingDocIds.clear();
		}
	}

	async function handleView(doc: any) {
		viewingDocument = doc;
		loadingPreview = true;
		documentSummary = null;
		documentViewerTab = 'preview';

		// Clean up previous blob URL if it exists
		if (pdfBlobUrl) {
			URL.revokeObjectURL(pdfBlobUrl);
			pdfBlobUrl = null;
		}
		
		// Load document summary in the background
		loadDocumentSummary(doc.file_name);

		try {
			const isPdf = doc.file_type === 'application/pdf' || doc.file_name.toLowerCase().endsWith('.pdf');
			const isImage = doc.file_type?.startsWith('image/');

			if ((isPdf || isImage) && doc.storage_path) {
const { session, user } = await getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

				const { data, error } = await supabase.storage
					.from('documents')
					.download(doc.storage_path);

				if (error) throw error;
				pdfBlobUrl = URL.createObjectURL(data);
			}
		} catch (error: any) {
			console.error('Failed to load document preview:', error);
			toastStore.error('Failed to load preview');
		} finally {
			loadingPreview = false;
		}
	}

	function closeDocumentViewer() {
		viewingDocument = null;
		documentSummary = null;
		documentViewerTab = 'preview';
		if (pdfBlobUrl) {
			URL.revokeObjectURL(pdfBlobUrl);
			pdfBlobUrl = null;
		}
	}

	async function loadDocumentSummariesFromAnalysis() {
		// Load document summaries from the latest analysis results if available
		if (!caseId) return;
		
		try {
			const { session } = await getSecureSession();
			if (!session) return;
			
			const response = await fetch(`${getApiUrl()}/api/analysis/results/${caseId}`, {
				headers: {
					Authorization: `Bearer ${session.access_token}`
				}
			});
			
			if (!response.ok) return;
			
			const results = await response.json();
			
			// Parse document_summaries if it's a JSON string
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

	// Bulk Actions
	async function bulkVerify() {
		if (selectedDocIds.size === 0) return;
		bulkActionLoading = true;
		try {
const { session, user } = await getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

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
		if (selectedDocIds.size === 0) return;
		confirmDialog = { open: true, type: 'bulk-delete', count: selectedDocIds.size };
	}

	async function performBulkDelete() {
		bulkActionLoading = true;
		try {
const { session, user } = await getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

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
		} catch (error: any) {
			toastStore.error(error.message);
		} finally {
			bulkActionLoading = false;
		}
	}

	async function handleConfirmAction() {
		const { type, docId } = confirmDialog;
		if (type === 'delete' && docId) {
			await performDelete(docId);
		} else if (type === 'bulk-delete') {
			await performBulkDelete();
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
			<button 
				onclick={() => showInstructions = !showInstructions}
				class="mt-4 inline-flex items-center gap-2 text-sm font-bold text-accent hover:text-accent-hover transition-colors"
			>
				<Info class="w-4 h-4" />
				{showInstructions ? 'Hide Instructions' : 'How to use the Verification Hub'}
			</button>
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

	{#if showInstructions}
		<div transition:slide class="bg-blue-50 border border-blue-100 rounded-2xl p-6 overflow-hidden">
			<h3 class="text-blue-900 font-black flex items-center gap-2 mb-4">
				<Info class="w-5 h-5" />
				Verification Hub Guide
			</h3>
			<div class="grid grid-cols-1 md:grid-cols-3 gap-8">
				<div class="space-y-3">
					<h4 class="text-blue-800 font-bold text-sm uppercase tracking-wider">1. Review Status</h4>
					<ul class="space-y-2">
						<li class="flex items-start gap-2 text-sm text-blue-700">
							<div class="w-2 h-2 rounded-full bg-red-500 mt-1.5 flex-shrink-0"></div>
							<span><strong>Critical:</strong> Missing files or corrupted data. Must be re-uploaded.</span>
						</li>
						<li class="flex items-start gap-2 text-sm text-blue-700">
							<div class="w-2 h-2 rounded-full bg-amber-500 mt-1.5 flex-shrink-0"></div>
							<span><strong>Pending:</strong> Extraction failed or low quality. Manual review required.</span>
						</li>
						<li class="flex items-start gap-2 text-sm text-blue-700">
							<div class="w-2 h-2 rounded-full bg-green-500 mt-1.5 flex-shrink-0"></div>
							<span><strong>Ready:</strong> High quality extraction. Verify and proceed.</span>
						</li>
					</ul>
				</div>
				<div class="space-y-3">
					<h4 class="text-blue-800 font-bold text-sm uppercase tracking-wider">2. Take Action</h4>
					<ul class="space-y-2">
						<li class="text-sm text-blue-700 flex gap-2">
							<CheckCircle2 class="w-4 h-4 text-green-600 flex-shrink-0" />
							<span><strong>Verify:</strong> Confirm the data is correct.</span>
						</li>
						<li class="text-sm text-blue-700 flex gap-2">
							<Trash2 class="w-4 h-4 text-red-600 flex-shrink-0" />
							<span><strong>Delete:</strong> Remove irrelevant documents.</span>
						</li>
						<li class="text-sm text-blue-700 flex gap-2">
							<RefreshCw class="w-4 h-4 text-blue-600 flex-shrink-0" />
							<span><strong>Re-extract:</strong> Try Vision OCR for better results.</span>
						</li>
					</ul>
				</div>
				<div class="space-y-3">
					<h4 class="text-blue-800 font-bold text-sm uppercase tracking-wider">3. Final Step</h4>
					<p class="text-sm text-blue-700 leading-relaxed">
						Once all documents are <strong>Verified</strong> or <strong>Skipped</strong>, click the <strong>Run Analysis</strong> button at the top of the case details page to generate the final legal findings.
					</p>
				</div>
			</div>
		</div>
	{/if}

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
						class="btn btn-primary flex-1 md:flex-none py-2.5 font-black shadow-lg shadow-accent/20"
					>
						Verify All
					</button>
					<button 
						onclick={bulkDelete}
						disabled={bulkActionLoading}
						class="btn btn-secondary flex-1 md:flex-none py-2.5 font-black text-red-600 border-red-200 hover:bg-red-50"
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
								onView={() => handleView(doc)}
								onReplace={() => { recoveryDocument = doc; showRecoveryModal = true; }}
								onSkip={() => handleSkip(doc.id)}
								onDelete={() => handleDelete(doc.id)}
								onAlwaysDelete={(name, id) => handleAlwaysDelete(name, id)}
								onToggleExclusion={(id, excluded) => handleToggleExclusion(id, excluded)}
								isProcessing={processingDocIds.has(doc.id)}
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
						
						<!-- Bulk Extraction Action -->
						{#if triageGroups.needs_attention.filter(d => !d.extracted_text || d.status === 'pending').length > 0}
							<button 
								onclick={handleBulkExtract}
								disabled={bulkActionLoading}
								class="ml-4 btn btn-secondary py-1.5 text-xs font-bold text-accent border-accent/20 hover:bg-accent/5"
							>
								<RefreshCw class={`w-3.5 h-3.5 ${bulkActionLoading ? 'animate-spin' : ''}`} />
								{#if bulkActionLoading}
									Processing {remainingOcrCount} Doc{remainingOcrCount === 1 ? '' : 's'}...
								{:else}
									Run OCR on {triageGroups.needs_attention.filter(d => !d.extracted_text || d.status === 'pending').length} Doc{triageGroups.needs_attention.filter(d => !d.extracted_text || d.status === 'pending').length === 1 ? '' : 's'}
								{/if}
							</button>
						{/if}

						<span class="ml-auto text-xs font-bold text-amber-600 bg-amber-50 px-2 py-1 rounded-full border border-amber-100">
							{triageGroups.needs_attention.length} Pending
						</span>
					</div>
					<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
						{#each triageGroups.needs_attention as doc (doc.id)}
							<DocumentCard 
								{doc}
								onView={() => handleView(doc)}
								onEdit={() => editingDocument = doc}
								onReExtract={() => handleReExtract(doc.id)}
								onVerify={() => handleVerify(doc.id)}
								onSkip={() => handleSkip(doc.id)}
								onDelete={() => handleDelete(doc.id)}
								onAlwaysDelete={(name, id) => handleAlwaysDelete(name, id)}
								onToggleExclusion={(id, excluded) => handleToggleExclusion(id, excluded)}
								isProcessing={processingDocIds.has(doc.id)}
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
								onView={() => handleView(doc)}
								onEdit={() => editingDocument = doc}
								onDelete={() => handleDelete(doc.id)}
								onAlwaysDelete={(name, id) => handleAlwaysDelete(name, id)}
								onToggleExclusion={(id, excluded) => handleToggleExclusion(id, excluded)}
								isProcessing={processingDocIds.has(doc.id)}
							/>
						{/each}
					</div>
				</section>
			{/if}

			<!-- Excluded Documents Section (above duplicates) -->
			{#if triageGroups.excluded.length > 0}
				<section class="mt-8 pt-8 border-t border-gray-200">
					<div class="flex items-center gap-3 mb-6">
						<div class="p-1.5 rounded-lg bg-gray-100 text-gray-600">
							<XCircle class="w-5 h-5" />
						</div>
						<div>
							<h3 class="text-xl font-black text-gray-900 uppercase tracking-tight">Excluded from Analysis</h3>
							<p class="text-xs text-gray-500">These files will be skipped during the next analysis run.</p>
						</div>
						<span class="ml-auto text-xs font-bold text-gray-600 bg-gray-50 px-2 py-1 rounded-full border border-gray-100">
							{triageGroups.excluded.length} Excluded
						</span>
					</div>
					<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 opacity-60 grayscale hover:opacity-100 hover:grayscale-0 transition-all">
						{#each triageGroups.excluded as doc (doc.id)}
							<DocumentCard 
								{doc}
								onView={() => handleView(doc)}
								onEdit={() => editingDocument = doc}
								onDelete={() => handleDelete(doc.id)}
								onAlwaysDelete={(name, id) => handleAlwaysDelete(name, id)}
								onToggleExclusion={(id, excluded) => handleToggleExclusion(id, excluded)}
								isProcessing={processingDocIds.has(doc.id)}
							/>
						{/each}
					</div>
				</section>
			{/if}

			<!-- Duplicates Section (at bottom) -->
			{#if triageGroups.duplicates.length > 0}
				<section class="mt-8 pt-8 border-t border-purple-200">
					<div class="flex items-center gap-3 mb-6">
						<div class="p-1.5 rounded-lg bg-purple-100 text-purple-600">
							<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
							</svg>
						</div>
						<div>
							<h3 class="text-xl font-black text-gray-900 uppercase tracking-tight">Duplicate Documents</h3>
							<p class="text-xs text-gray-500">These files appear to be duplicates. Review and include if needed.</p>
						</div>
						<span class="ml-auto text-xs font-bold text-purple-600 bg-purple-50 px-2 py-1 rounded-full border border-purple-100">
							{triageGroups.duplicates.length} {triageGroups.duplicates.length === 1 ? 'Duplicate' : 'Duplicates'}
						</span>
					</div>
					<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 opacity-70 hover:opacity-100 transition-opacity">
						{#each triageGroups.duplicates as doc (doc.id)}
							<DocumentCard 
								{doc}
								onView={() => handleView(doc)}
								onEdit={() => editingDocument = doc}
								onDelete={() => handleDelete(doc.id)}
								onAlwaysDelete={(name, id) => handleAlwaysDelete(name, id)}
								onToggleExclusion={(id, excluded) => handleToggleExclusion(id, excluded)}
								isProcessing={processingDocIds.has(doc.id)}
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
							onView={() => handleView(doc)}
							onEdit={() => editingDocument = doc}
							onReplace={() => { recoveryDocument = doc; showRecoveryModal = true; }}
							onReExtract={() => handleReExtract(doc.id)}
							onVerify={() => handleVerify(doc.id)}
							onSkip={() => handleSkip(doc.id)}
							onDelete={() => handleDelete(doc.id)}
							onAlwaysDelete={(name, id) => handleAlwaysDelete(name, id)}
							onToggleExclusion={(id, excluded) => handleToggleExclusion(id, excluded)}
							isProcessing={processingDocIds.has(doc.id)}
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

{#if showRecoveryModal && recoveryDocument}
	<RecoveryModal
		doc={recoveryDocument}
		bind:isOpen={showRecoveryModal}
		onSuccess={onDocumentsUpdated}
	/>
{/if}

<!-- Document Viewer Modal -->
{#if viewingDocument}
	<Modal
		open={true}
		title={viewingDocument.file_name}
		size="full"
	>
		<!-- Tabs -->
		<div class="border-b border-gray-200 mb-4">
			<nav class="-mb-px flex space-x-6" aria-label="Tabs">
				<button
					onclick={() => (documentViewerTab = 'preview')}
					class="whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm {documentViewerTab === 'preview' ? 'border-accent text-accent' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}"
				>
					Preview
				</button>
				<button
					onclick={() => (documentViewerTab = 'summary')}
					class="whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm flex items-center gap-2 {documentViewerTab === 'summary' ? 'border-accent text-accent' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}"
				>
					Summary
					{#if documentSummary}
						<span class="w-2 h-2 rounded-full bg-green-500"></span>
					{/if}
				</button>
				<button
					onclick={() => (documentViewerTab = 'text')}
					class="whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm {documentViewerTab === 'text' ? 'border-accent text-accent' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}"
				>
					Raw Text
				</button>
			</nav>
		</div>

		<div class="bg-gray-50 min-h-[400px] rounded-lg overflow-hidden">
			{#if documentViewerTab === 'preview'}
				{#if loadingPreview}
					<div class="flex flex-col items-center justify-center h-full py-12">
						<RefreshCw class="w-8 h-8 text-accent animate-spin mb-4" />
						<p class="text-gray-500 font-medium">Loading preview...</p>
					</div>
				{:else if pdfBlobUrl}
					<iframe
						src={pdfBlobUrl}
						class="w-full h-full min-h-[600px] border-0 bg-white"
						title="Document Preview"
					></iframe>
				{:else if viewingDocument.extracted_text}
					<div class="flex flex-col items-center justify-center h-full py-20 text-center">
						<div class="p-4 rounded-full bg-blue-50 text-blue-500 mb-4">
							<Info class="w-12 h-12" />
						</div>
						<h3 class="text-lg font-bold text-gray-900">No File Preview</h3>
						<p class="text-gray-500 text-sm mt-1 max-w-xs mx-auto">
							Use the Summary or Raw Text tabs to view the extracted content.
						</p>
					</div>
				{:else}
					<div class="flex flex-col items-center justify-center h-full py-20 text-center">
						<div class="p-4 rounded-full bg-amber-50 text-amber-500 mb-4">
							<AlertTriangle class="w-12 h-12" />
						</div>
						<h3 class="text-lg font-bold text-gray-900">Preview Unavailable</h3>
						<p class="text-gray-500 text-sm mt-1 max-w-xs mx-auto">
							This document doesn't have a preview available. You can view the extracted text in the correction modal.
						</p>
					</div>
				{/if}
			{:else if documentViewerTab === 'summary'}
				{#if loadingDocumentSummary}
					<div class="flex flex-col items-center justify-center h-full py-12">
						<RefreshCw class="w-8 h-8 text-accent animate-spin mb-4" />
						<p class="text-gray-500 font-medium">Loading document analysis...</p>
					</div>
				{:else if documentSummary}
					<div class="p-4">
						<DocumentSummaryCard 
							summary={documentSummary}
							rawText={viewingDocument?.extracted_text || ''}
							signatureDetection={viewingDocument?.metadata?.signature_detection || null}
							collapsible={false}
							showHeader={false}
						/>
					</div>
				{:else}
					<div class="flex flex-col items-center justify-center h-full py-20 text-center">
						<div class="p-4 rounded-full bg-gray-100 text-gray-400 mb-4">
							<Info class="w-12 h-12" />
						</div>
						<h3 class="text-lg font-bold text-gray-900">No Analysis Available</h3>
						<p class="text-gray-500 text-sm mt-2 max-w-sm mx-auto">
							Run case analysis to generate a structured summary of this document with key facts, legal significance, and evidence quotes.
						</p>
					</div>
				{/if}
			{:else if documentViewerTab === 'text'}
				{#if viewingDocument.extracted_text}
					<div class="bg-white p-8 border border-gray-200 max-w-none prose prose-sm prose-slate h-full overflow-auto max-h-[600px]">
						<pre class="whitespace-pre-wrap font-mono text-xs text-gray-800 leading-relaxed">{viewingDocument.extracted_text}</pre>
					</div>
				{:else}
					<div class="flex flex-col items-center justify-center h-full py-20 text-center">
						<div class="p-4 rounded-full bg-amber-50 text-amber-500 mb-4">
							<AlertTriangle class="w-12 h-12" />
						</div>
						<h3 class="text-lg font-bold text-gray-900">No Extracted Text</h3>
						<p class="text-gray-500 text-sm mt-1 max-w-xs mx-auto">
							Run OCR or text extraction to view the document content.
						</p>
					</div>
				{/if}
			{/if}
		</div>

		{#snippet footer()}
			<button
				onclick={closeDocumentViewer}
				class="btn btn-secondary px-6"
			>
				Close
			</button>
		{/snippet}
	</Modal>
{/if}

<!-- Confirmation Dialog -->
<ConfirmDialog
	bind:open={confirmDialog.open}
	title={confirmDialog.type === 'delete' ? 'Delete Document' : 'Delete Documents'}
	message={confirmDialog.type === 'delete' 
		? 'Are you sure you want to delete this document? This cannot be undone.'
		: `Are you sure you want to delete ${confirmDialog.count} documents? This cannot be undone.`
	}
	confirmText="Delete"
	variant="danger"
	loading={bulkActionLoading}
	onConfirm={handleConfirmAction}
/>
