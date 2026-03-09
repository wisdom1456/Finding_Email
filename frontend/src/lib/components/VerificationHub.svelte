<script lang="ts">
	import { getApiUrl } from '$lib/config';
	import { supabase, getSecureSession } from '$lib/supabase';
	import { toastStore } from '$lib/stores/toastStore';
	import { deriveBlacklistRule, isNameBlacklisted, toCanonicalBlacklistTerm } from '$lib/utils/blacklist';
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
	import DocumentSummaryCard from './DocumentSummaryCard.svelte';
	import DocumentPreviewPane from './DocumentPreviewPane.svelte';
	import TriageDashboard from './TriageDashboard.svelte';
	import SignatureReviewPanel from './SignatureReviewPanel.svelte';
	import DocumentReviewPanel from './DocumentReviewPanel.svelte';
	import { sortByAttention } from '$lib/utils/documentSorting';

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

	// Local shadow of the documents prop for optimistic updates (Svelte 5 reactivity)
	let localDocuments = $state<any[]>([]);
	$effect(() => { localDocuments = [...documents]; });

	// State
	let selectedDocIds = $state<Set<string>>(new Set());
	let bulkActionLoading = $state(false);
	let filterQuery = $state('');
	let editingDocument = $state<any>(null);
	let recoveryDocument = $state<any>(null);
	let showRecoveryModal = $state(false);
	let viewingDocument = $state<any>(null);
	let verdictSaving = $state(false);
	let verdictNotes = $state('');
	let showNotesInput = $state(false);
	let pdfBlobUrl = $state<string | null>(null);
	let previewBlobDocumentId = $state<string | null>(null);
	let loadingPreview = $state(false);
	let documentViewerTab = $state<'preview' | 'summary' | 'text'>('preview');
	let documentSummary = $state<any>(null);
	let documentSummaries = $state<any[]>([]);
	let loadingDocumentSummary = $state(false);
	let viewMode = $state<'triage' | 'all'>('triage');
	let showInstructions = $state(false);
	let processingDocIds = $state<Set<string>>(new Set());
	let remainingOcrCount = $state(0);
	let activeFilters = $state<Set<string>>(new Set());
	let signatureReviewOpen = $state(false);
	let signatureReviewQueue = $state<any[]>([]);
	let signatureReviewIndex = $state(0);
	let documentReviewOpen = $state(false);
	let documentReviewDoc = $state<any>(null);
	let expandedCardIds = $state<Set<string>>(new Set());

	// Pagination: caps DOM nodes rendered per triage group (all filtering/sorting still
	// runs over the full array — only DOM rendering is capped at INITIAL_VISIBLE docs).
	const INITIAL_VISIBLE = 30;
	let visibleCounts = $state({
		critical: INITIAL_VISIBLE,
		needs_attention: INITIAL_VISIBLE,
		ready: INITIAL_VISIBLE,
		duplicates: INITIAL_VISIBLE,
		excluded: INITIAL_VISIBLE,
	});

	function showAllDocs(group: keyof typeof visibleCounts) {
		visibleCounts[group] = Infinity;
	}

	// Confirmation dialog state
	let confirmDialog = $state<{
		open: boolean;
		type: 'delete' | 'bulk-delete' | 'skip';
		docId?: string;
		count?: number;
	}>({ open: false, type: 'delete' });

	// Triage Groups — sourced from displayDocuments so chip filters take effect
	let triageGroups = $derived.by(() => {
		const groups = {
			critical: [] as any[], // download_failed, corrupted
			needs_attention: [] as any[], // extraction_failed, needs_review (low quality)
			ready: [] as any[], // ready (high/medium quality)
			duplicates: [] as any[], // duplicate documents
			excluded: [] as any[] // documents manually excluded from analysis
		};

		for (const doc of displayDocuments) {
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
				(status === 'ready' && !doc.extracted_at)
			) {
				groups.needs_attention.push(doc);
			} else {
				groups.ready.push(doc);
			}
		}

		// Apply smart sorting within each group
		groups.critical = sortByAttention(groups.critical);
		groups.needs_attention = sortByAttention(groups.needs_attention);
		groups.ready = sortByAttention(groups.ready);
		groups.duplicates = sortByAttention(groups.duplicates);
		groups.excluded = sortByAttention(groups.excluded);

		return groups;
	});

	let docsNeedingExtraction = $derived(
		triageGroups.needs_attention.filter(d =>
			!d.extracted_at || d.extraction_method === 'deferred' || (d.status === 'pending' && !d.extracted_text)
		)
	);

	// Filtered list for "All" view
	let filteredDocs = $derived.by(() => {
		if (!filterQuery) return localDocuments;
		const query = filterQuery.toLowerCase();
		return localDocuments.filter(doc =>
			doc.file_name.toLowerCase().includes(query) ||
			doc.status.toLowerCase().includes(query)
		);
	});

	// Filter logic for TriageDashboard chips
	function handleFilterToggle(filter: string) {
		const newFilters = new Set(activeFilters);
		if (newFilters.has(filter)) {
			newFilters.delete(filter);
		} else {
			newFilters.add(filter);
		}
		activeFilters = newFilters;
	}

	// Compute filtered documents using registry-backed columns
	let displayDocuments = $derived((() => {
		if (activeFilters.size === 0) return localDocuments;
		return localDocuments.filter(d => {
			const enrichment = d.metadata?.attorney_enrichment || {};
			const quality = d.metadata?.quality_score ?? 10;

			if (activeFilters.has('missing-signatures')) {
				const sigExpected = d.signature_expected === true ||
				                    d.metadata?.registry?.signature_expected === true;
				const sigSatisfied =
					d.signed_status === 'signed' ||
					enrichment.signature_verification === 'signed';
				if (sigExpected && !sigSatisfied) return true;
			}
			if (activeFilters.has('low-ocr')) {
				if (quality < 5) return true;
			}
			if (activeFilters.has('needs-type')) {
				if (!d.document_type_label && !enrichment.document_type_override) return true;
			}
			if (activeFilters.has('ready')) {
				if (d.status === 'ready') return true;
			}
			return false;
		});
	})());

	// Selection Handlers
	function toggleSelection(docId: string) {
		const newSet = new Set(selectedDocIds);
		if (newSet.has(docId)) newSet.delete(docId);
		else newSet.add(docId);
		selectedDocIds = newSet;
	}

	function toggleAll() {
		if (selectedDocIds.size === localDocuments.length) {
			selectedDocIds = new Set();
		} else {
			selectedDocIds = new Set(localDocuments.map(d => d.id));
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

	async function handleSetVerdict(verdict: 'signed' | 'not_signed' | 'unknown', notes?: string) {
		if (!viewingDocument) return;
		verdictSaving = true;
		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			const response = await fetch(`${getApiUrl()}/api/documents/${viewingDocument.id}/verify`, {
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`,
				},
				body: JSON.stringify({
					is_verified: Boolean(viewingDocument.is_verified),
					is_flagged_as_junk: Boolean(viewingDocument.is_flagged_as_junk),
					signature_verification: verdict,
					...(notes ? { signature_verification_notes: notes } : {}),
				}),
			});

			if (!response.ok) throw new Error('Failed to save signature verdict');

			// Optimistic local update so buttons reflect new state immediately
			if (!viewingDocument.metadata) viewingDocument.metadata = {};
			viewingDocument.metadata.signature_verification = {
				status: verdict,
				notes: notes || '',
			};
			showNotesInput = false;
			verdictNotes = '';

			const label = verdict === 'signed' ? 'Signed' : verdict === 'not_signed' ? 'Not Signed' : 'Unclear';
			toastStore.success(`Marked as ${label} (attorney verified)`);
			await onDocumentsUpdated();
		} catch (error: any) {
			toastStore.error(error.message);
		} finally {
			verdictSaving = false;
		}
	}

	// Kept independent (not calling handleSetVerdict) to avoid mutating viewingDocument
	async function handleMarkSigned(doc: any) {
		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			const response = await fetch(`${getApiUrl()}/api/documents/${doc.id}/verify`, {
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`,
				},
				body: JSON.stringify({
					is_verified: Boolean(doc.is_verified),
					is_flagged_as_junk: Boolean(doc.is_flagged_as_junk),
					signature_verification: 'signed',
				}),
			});

			if (!response.ok) throw new Error('Failed to mark document as signed');
			toastStore.success('Marked as signed (attorney verified)');
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
			const blacklistRule = deriveBlacklistRule(docName) || docName;
			let deleteWarning = '';

			// 1. Delete the current document and any similar variants in this case
			if (docId) {
				const docsToDelete = localDocuments.filter(
					(d) => d.file_name === docName || isNameBlacklisted(d.file_name, [blacklistRule])
				);
				const docIds = [...new Set(docsToDelete.map((d) => d.id))];

				if (docIds.length > 0) {
					const deleteResponse = await fetch(`${apiUrl}/api/documents/bulk-delete`, {
						method: 'POST',
						headers: {
							'Content-Type': 'application/json',
							Authorization: `Bearer ${session.access_token}`,
						},
						body: JSON.stringify({ document_ids: docIds }),
					});

					if (!deleteResponse.ok) throw new Error('Failed to delete selected documents');

					const deleteResult = await deleteResponse.json();
					const failedCount = deleteResult?.failed_ids?.length ?? 0;
					if (failedCount > 0) {
						deleteWarning =
							`Deleted ${deleteResult.deleted_count} documents, but ${failedCount} could not be deleted.`;
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
			const hasEquivalentRule = currentBlacklist.some((rule: string) => {
				const existingCanonical = toCanonicalBlacklistTerm(rule);
				const incomingCanonical = toCanonicalBlacklistTerm(blacklistRule);
				return (
					rule.trim().toLowerCase() === blacklistRule.trim().toLowerCase() ||
					(existingCanonical && existingCanonical === incomingCanonical)
				);
			});

			if (!hasEquivalentRule) {
				const updatedBlacklist = [...currentBlacklist, blacklistRule];

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

			toastStore.success(`"${blacklistRule}" will always be excluded from future imports`);
			if (deleteWarning) {
				toastStore.warning(deleteWarning);
			}
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

			if (!response.ok) {
				const errBody = await response.json().catch(() => ({}));
				throw new Error(errBody.detail || `Extraction failed (${response.status})`);
			}
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
		const docsToProcess = docsNeedingExtraction;
		if (docsToProcess.length === 0) return;

		// Process in batches of 3 concurrent requests with a pause between batches.
		// This keeps Supabase compute load bounded (3 × 4-9 DB calls = 12-27 concurrent
		// connections) while being ~3x faster than fully sequential processing.
		const BATCH_SIZE = 3;
		const BATCH_DELAY_MS = 1500;

		toastStore.info(`Extracting ${docsToProcess.length} documents (${BATCH_SIZE} at a time)...`);
		bulkActionLoading = true;
		remainingOcrCount = docsToProcess.length;

		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			let extractedCount = 0;
			let failedCount = 0;

			for (let i = 0; i < docsToProcess.length; i += BATCH_SIZE) {
				const batch = docsToProcess.slice(i, i + BATCH_SIZE);

				// Mark all docs in this batch as processing
				processingDocIds = new Set([...processingDocIds, ...batch.map((d: any) => d.id)]);

				const results = await Promise.allSettled(
					batch.map((doc: any) =>
						fetch(`${getApiUrl()}/api/documents/${doc.id}/extract`, {
							method: 'POST',
							headers: { Authorization: `Bearer ${session.access_token}` },
						})
					)
				);

				// Tally results and clear processing state for this batch
				for (let j = 0; j < results.length; j++) {
					const r = results[j];
					const docId = batch[j].id;
					if (r.status === 'fulfilled' && r.value.ok) {
						extractedCount++;
					} else {
						let errorDetail = r.status === 'rejected' ? r.reason : r.value.status;
						if (r.status === 'fulfilled' && !r.value.ok) {
							try {
								const errBody = await r.value.json();
								errorDetail = `${r.value.status}: ${errBody.detail || JSON.stringify(errBody)}`;
							} catch { /* response not JSON */ }
						}
						console.error(`Failed to extract ${batch[j].file_name}:`, errorDetail);
						failedCount++;
					}
					const next = new Set(processingDocIds);
					next.delete(docId);
					processingDocIds = next;
					remainingOcrCount--;
				}

				// Refresh UI after each batch completes
				await onDocumentsUpdated();

				// Pause between batches to let Supabase compute recover
				if (i + BATCH_SIZE < docsToProcess.length) {
					await new Promise(resolve => setTimeout(resolve, BATCH_DELAY_MS));
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
			processingDocIds = new Set();
		}
	}

	async function handleView(doc: any) {
		// Open the new DocumentReviewPanel
		documentReviewDoc = doc;
		documentReviewOpen = true;

		// Also keep legacy modal state in sync (for backward compatibility)
		viewingDocument = doc;
		loadingPreview = false;
		documentSummary = null;
		documentViewerTab = 'preview';

		// Clean up previous blob URL if it exists
		if (pdfBlobUrl) {
			URL.revokeObjectURL(pdfBlobUrl);
			pdfBlobUrl = null;
		}
		previewBlobDocumentId = null;

		// Load document summary in the background
		loadDocumentSummary(doc.file_name);

		// Keep click-path light: only prefetch images automatically.
		if (isImageDocument(doc)) {
			await loadDocumentBinaryPreview(doc);
		}
	}

	function isPdfDocument(doc: any): boolean {
		if (!doc) return false;
		const fileType = String(doc.file_type || '').toLowerCase();
		const fileName = String(doc.file_name || '').toLowerCase();
		return fileType === 'application/pdf' || fileName.endsWith('.pdf');
	}

	function isImageDocument(doc: any): boolean {
		if (!doc) return false;
		return String(doc.file_type || '').toLowerCase().startsWith('image/');
	}

	async function loadDocumentBinaryPreview(doc: any = viewingDocument) {
		if (!doc?.storage_path) return;

		const docId = doc.id ? String(doc.id) : null;
		if (docId && previewBlobDocumentId === docId && pdfBlobUrl) {
			return;
		}

		loadingPreview = true;
		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			const { data, error } = await supabase.storage
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
			toastStore.error('Failed to load preview');
		} finally {
			loadingPreview = false;
		}
	}

	function closeDocumentViewer() {
		viewingDocument = null;
		documentSummary = null;
		documentViewerTab = 'preview';
		loadingPreview = false;
		previewBlobDocumentId = null;
		if (pdfBlobUrl) {
			URL.revokeObjectURL(pdfBlobUrl);
			pdfBlobUrl = null;
		}
		showNotesInput = false;
		verdictNotes = '';
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

	// Signature Review Panel handlers
	function handleSignatureReviewFromCard(doc: any) {
		const needsSig = localDocuments.filter(d => {
			const sigExpected = d.signature_expected === true ||
			                    d.metadata?.registry?.signature_expected === true;
			const sigSatisfied =
				d.signed_status === 'signed' ||
				d.metadata?.attorney_enrichment?.signature_verification === 'signed';
			return sigExpected && !sigSatisfied;
		});
		const clickedIdx = needsSig.findIndex(d => d.id === doc.id);
		if (clickedIdx >= 0) {
			signatureReviewQueue = needsSig;
			signatureReviewIndex = clickedIdx;
		} else {
			signatureReviewQueue = [doc, ...needsSig];
			signatureReviewIndex = 0;
		}
		signatureReviewOpen = true;
	}

	function handleSignatureVerdictFromPanel(docId: string, verdict: string) {
		const idx = localDocuments.findIndex(d => d.id === docId);
		if (idx >= 0) {
			localDocuments[idx] = {
				...localDocuments[idx],
				metadata: {
					...localDocuments[idx].metadata,
					signature_detection: {
						...(localDocuments[idx].metadata?.signature_detection || {}),
						status: verdict === 'signed' ? 'signed' : verdict === 'not_signed' ? 'not_detected' : 'unknown',
						verified_by_attorney: true
					}
				}
			};
		}
		onDocumentsUpdated?.();
	}

	function handleToggleExpand(docId: string) {
		const newSet = new Set(expandedCardIds);
		if (newSet.has(docId)) {
			newSet.delete(docId);
		} else {
			newSet.add(docId);
		}
		expandedCardIds = newSet;
	}

	// Enrichment API handlers
	async function handleTypeOverride(docId: string, type: string) {
		try {
			const idx = localDocuments.findIndex(d => d.id === docId);
			if (idx >= 0) {
				const doc = localDocuments[idx];
				localDocuments[idx] = {
					...doc,
					metadata: {
						...doc.metadata,
						attorney_enrichment: {
							...(doc.metadata?.attorney_enrichment || {}),
							document_type_override: type
						}
					}
				};
			}
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');
			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/documents/${docId}/verify`, {
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json',
					'Authorization': `Bearer ${session.access_token}`
				},
				body: JSON.stringify({ document_type_override: type })
			});
			if (!response.ok) throw new Error('Failed to save changes');
		} catch (e) {
			toastStore.error('Failed to save document type');
		}
	}

	async function handleRelevanceChange(docId: string, level: string) {
		try {
			const idx = localDocuments.findIndex(d => d.id === docId);
			if (idx >= 0) {
				const doc = localDocuments[idx];
				localDocuments[idx] = {
					...doc,
					metadata: {
						...doc.metadata,
						attorney_enrichment: { ...(doc.metadata?.attorney_enrichment || {}), relevance_level: level }
					}
				};
			}
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');
			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/documents/${docId}/verify`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${session.access_token}` },
				body: JSON.stringify({ relevance_level: level })
			});
			if (!response.ok) throw new Error('Failed to save changes');
		} catch (e) {
			toastStore.error('Failed to save relevance');
		}
	}

	async function handleNotesUpdate(docId: string, notes: string) {
		try {
			const idx = localDocuments.findIndex(d => d.id === docId);
			if (idx >= 0) {
				const doc = localDocuments[idx];
				localDocuments[idx] = {
					...doc,
					metadata: {
						...doc.metadata,
						attorney_enrichment: { ...(doc.metadata?.attorney_enrichment || {}), attorney_notes: notes }
					}
				};
			}
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');
			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/documents/${docId}/verify`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${session.access_token}` },
				body: JSON.stringify({ attorney_notes: notes })
			});
			if (!response.ok) throw new Error('Failed to save changes');
		} catch (e) {
			toastStore.error('Failed to save notes');
		}
	}

	async function handleFactUpdate(docId: string, factKey: string, newValue: string) {
		try {
			const idx = localDocuments.findIndex(d => d.id === docId);
			if (idx >= 0) {
				const doc = localDocuments[idx];
				const existingFacts = doc.metadata?.attorney_enrichment?.key_facts || {};
				localDocuments[idx] = {
					...doc,
					metadata: {
						...doc.metadata,
						attorney_enrichment: {
							...(doc.metadata?.attorney_enrichment || {}),
							key_facts: {
								...existingFacts,
								[factKey]: { value: newValue, confirmed: false }
							}
						}
					}
				};
			}
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');
			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/documents/${docId}/verify`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${session.access_token}` },
				body: JSON.stringify({ key_facts: { [factKey]: { value: newValue, confirmed: false } } })
			});
			if (!response.ok) throw new Error('Failed to save changes');
		} catch (e) {
			toastStore.error('Failed to save fact');
		}
	}

	async function handleFactConfirm(docId: string, factKey: string) {
		try {
			const idx = localDocuments.findIndex(d => d.id === docId);
			if (idx < 0) return;
			const doc = localDocuments[idx];
			const existingFacts = doc.metadata?.attorney_enrichment?.key_facts || {};
			const existingFact = existingFacts[factKey] || {};
			const confirmedFact = { ...existingFact, confirmed: true };
			localDocuments[idx] = {
				...doc,
				metadata: {
					...doc.metadata,
					attorney_enrichment: {
						...(doc.metadata?.attorney_enrichment || {}),
						key_facts: {
							...existingFacts,
							[factKey]: confirmedFact
						}
					}
				}
			};
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');
			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/documents/${docId}/verify`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${session.access_token}` },
				body: JSON.stringify({ key_facts: { [factKey]: { ...existingFact, confirmed: true } } })
			});
			if (!response.ok) throw new Error('Failed to save changes');
		} catch (e) {
			toastStore.error('Failed to confirm fact');
		}
	}

	async function handleRelationshipAdd(docId: string, relatedDocId: string, type: string) {
		try {
			const idx = localDocuments.findIndex(d => d.id === docId);
			if (idx >= 0) {
				const doc = localDocuments[idx];
				const existing = doc.metadata?.attorney_enrichment?.document_relationships || [];
				const relatedDoc = localDocuments.find(d => d.id === relatedDocId);
				const newRelationship = { related_doc_id: relatedDocId, relationship_type: type, related_doc_name: relatedDoc?.file_name };
				const updated = [...existing, newRelationship];
				localDocuments[idx] = {
					...doc,
					metadata: {
						...doc.metadata,
						attorney_enrichment: { ...(doc.metadata?.attorney_enrichment || {}), document_relationships: updated }
					}
				};
				const { session, user } = await getSecureSession();
				if (!session || !user) throw new Error('Not authenticated');
				const apiUrl = getApiUrl();
				const response = await fetch(`${apiUrl}/api/documents/${docId}/verify`, {
					method: 'PATCH',
					headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${session.access_token}` },
					body: JSON.stringify({ document_relationships: updated })
				});
				if (!response.ok) throw new Error('Failed to save changes');
			}
		} catch (e) {
			toastStore.error('Failed to save relationship');
		}
	}

	async function handleRelationshipRemove(docId: string, relatedDocId: string) {
		try {
			const idx = localDocuments.findIndex(d => d.id === docId);
			if (idx >= 0) {
				const doc = localDocuments[idx];
				const existing = doc.metadata?.attorney_enrichment?.document_relationships || [];
				const updated = existing.filter((r: any) => r.related_doc_id !== relatedDocId);
				localDocuments[idx] = {
					...doc,
					metadata: {
						...doc.metadata,
						attorney_enrichment: { ...(doc.metadata?.attorney_enrichment || {}), document_relationships: updated }
					}
				};
				const { session, user } = await getSecureSession();
				if (!session || !user) throw new Error('Not authenticated');
				const apiUrl = getApiUrl();
				const response = await fetch(`${apiUrl}/api/documents/${docId}/verify`, {
					method: 'PATCH',
					headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${session.access_token}` },
					body: JSON.stringify({ document_relationships: updated })
				});
				if (!response.ok) throw new Error('Failed to save changes');
			}
		} catch (e) {
			toastStore.error('Failed to remove relationship');
		}
	}
</script>

<div class="space-y-8" id="verification" data-testid="verification-hub">
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
				Review and confirm extracted data from {localDocuments.length} documents before running the final legal analysis.
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

	<!-- Triage Dashboard (replaces DocumentStatusBanner) -->
	<TriageDashboard
		documents={localDocuments}
		{activeFilters}
		onFilterToggle={handleFilterToggle}
	/>

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
										{#each triageGroups.critical.slice(0, visibleCounts.critical) as doc (doc.id)}
						<DocumentCard
							{doc}
							onView={() => handleView(doc)}
							onMarkSigned={() => handleMarkSigned(doc)}
							onReplace={() => { recoveryDocument = doc; showRecoveryModal = true; }}
							onSkip={() => handleSkip(doc.id)}
							onDelete={() => handleDelete(doc.id)}
							onAlwaysDelete={(name, id) => handleAlwaysDelete(name, id)}
							onToggleExclusion={(id, excluded) => handleToggleExclusion(id, excluded)}
							isProcessing={processingDocIds.has(doc.id)}
							onTypeOverride={handleTypeOverride}

							onNotesUpdate={handleNotesUpdate}
							onFactUpdate={handleFactUpdate}
							onFactConfirm={handleFactConfirm}
							onRelationshipAdd={handleRelationshipAdd}
							onRelationshipRemove={handleRelationshipRemove}
							onSignatureReview={handleSignatureReviewFromCard}
							availableDocuments={localDocuments.map(d => ({ id: d.id, name: d.file_name }))}
							isExpanded={expandedCardIds.has(doc.id)}
							onToggleExpand={handleToggleExpand}
						/>
					{/each}
				</div>
				{#if triageGroups.critical.length > visibleCounts.critical}
					<div class="mt-4 text-center">
						<button
							class="text-sm text-gray-500 hover:text-gray-700 underline"
							onclick={() => showAllDocs('critical')}
						>
							Show all {triageGroups.critical.length} documents
						</button>
					</div>
				{/if}
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
						{#if docsNeedingExtraction.length > 0}
							<button
								data-testid="bulk-extract-btn"
								onclick={handleBulkExtract}
								disabled={bulkActionLoading}
								class="ml-4 btn btn-secondary py-1.5 text-xs font-bold text-accent border-accent/20 hover:bg-accent/5"
							>
								<RefreshCw class={`w-3.5 h-3.5 ${bulkActionLoading ? 'animate-spin' : ''}`} />
								{#if bulkActionLoading}
									Processing {remainingOcrCount} Doc{remainingOcrCount === 1 ? '' : 's'}...
								{:else}
									Run OCR on {docsNeedingExtraction.length} Doc{docsNeedingExtraction.length === 1 ? '' : 's'}
								{/if}
							</button>
						{/if}

						<span class="ml-auto text-xs font-bold text-amber-600 bg-amber-50 px-2 py-1 rounded-full border border-amber-100">
							{triageGroups.needs_attention.length} Pending
						</span>
					</div>
				<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
										{#each triageGroups.needs_attention.slice(0, visibleCounts.needs_attention) as doc (doc.id)}
						<DocumentCard
							{doc}
							onView={() => handleView(doc)}
							onEdit={() => editingDocument = doc}
							onReExtract={() => handleReExtract(doc.id)}
							onVerify={() => handleVerify(doc.id)}
							onMarkSigned={() => handleMarkSigned(doc)}
							onSkip={() => handleSkip(doc.id)}
							onDelete={() => handleDelete(doc.id)}
							onAlwaysDelete={(name, id) => handleAlwaysDelete(name, id)}
							onToggleExclusion={(id, excluded) => handleToggleExclusion(id, excluded)}
							isProcessing={processingDocIds.has(doc.id)}
							onTypeOverride={handleTypeOverride}

							onNotesUpdate={handleNotesUpdate}
							onFactUpdate={handleFactUpdate}
							onFactConfirm={handleFactConfirm}
							onRelationshipAdd={handleRelationshipAdd}
							onRelationshipRemove={handleRelationshipRemove}
							onSignatureReview={handleSignatureReviewFromCard}
							availableDocuments={localDocuments.map(d => ({ id: d.id, name: d.file_name }))}
							isExpanded={expandedCardIds.has(doc.id)}
							onToggleExpand={handleToggleExpand}
						/>
					{/each}
				</div>
				{#if triageGroups.needs_attention.length > visibleCounts.needs_attention}
					<div class="mt-4 text-center">
						<button
							class="text-sm text-gray-500 hover:text-gray-700 underline"
							onclick={() => showAllDocs('needs_attention')}
						>
							Show all {triageGroups.needs_attention.length} documents
						</button>
					</div>
				{/if}
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
										{#each triageGroups.ready.slice(0, visibleCounts.ready) as doc (doc.id)}
							<DocumentCard
								{doc}
								onView={() => handleView(doc)}
								onEdit={() => editingDocument = doc}
								onMarkSigned={() => handleMarkSigned(doc)}
								onDelete={() => handleDelete(doc.id)}
								onAlwaysDelete={(name, id) => handleAlwaysDelete(name, id)}
								onToggleExclusion={(id, excluded) => handleToggleExclusion(id, excluded)}
								isProcessing={processingDocIds.has(doc.id)}
								onTypeOverride={handleTypeOverride}
	
								onNotesUpdate={handleNotesUpdate}
								onFactUpdate={handleFactUpdate}
								onFactConfirm={handleFactConfirm}
								onRelationshipAdd={handleRelationshipAdd}
								onRelationshipRemove={handleRelationshipRemove}
								onSignatureReview={handleSignatureReviewFromCard}
							availableDocuments={localDocuments.map(d => ({ id: d.id, name: d.file_name }))}
							isExpanded={expandedCardIds.has(doc.id)}
							onToggleExpand={handleToggleExpand}
						/>
					{/each}
				</div>
				{#if triageGroups.ready.length > visibleCounts.ready}
					<div class="mt-4 text-center">
						<button
							class="text-sm text-gray-500 hover:text-gray-700 underline"
							onclick={() => showAllDocs('ready')}
						>
							Show all {triageGroups.ready.length} documents
						</button>
					</div>
				{/if}
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
										{#each triageGroups.excluded.slice(0, visibleCounts.excluded) as doc (doc.id)}
						<DocumentCard
							{doc}
							onView={() => handleView(doc)}
							onEdit={() => editingDocument = doc}
							onMarkSigned={() => handleMarkSigned(doc)}
							onDelete={() => handleDelete(doc.id)}
							onAlwaysDelete={(name, id) => handleAlwaysDelete(name, id)}
							onToggleExclusion={(id, excluded) => handleToggleExclusion(id, excluded)}
							isProcessing={processingDocIds.has(doc.id)}
							onTypeOverride={handleTypeOverride}

							onNotesUpdate={handleNotesUpdate}
							onFactUpdate={handleFactUpdate}
							onFactConfirm={handleFactConfirm}
							onRelationshipAdd={handleRelationshipAdd}
							onRelationshipRemove={handleRelationshipRemove}
							onSignatureReview={handleSignatureReviewFromCard}
							availableDocuments={localDocuments.map(d => ({ id: d.id, name: d.file_name }))}
							isExpanded={expandedCardIds.has(doc.id)}
							onToggleExpand={handleToggleExpand}
						/>
					{/each}
				</div>
				{#if triageGroups.excluded.length > visibleCounts.excluded}
					<div class="mt-4 text-center">
						<button
							class="text-sm text-gray-500 hover:text-gray-700 underline"
							onclick={() => showAllDocs('excluded')}
						>
							Show all {triageGroups.excluded.length} documents
						</button>
					</div>
				{/if}
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
										{#each triageGroups.duplicates.slice(0, visibleCounts.duplicates) as doc (doc.id)}
						<DocumentCard
							{doc}
							onView={() => handleView(doc)}
							onEdit={() => editingDocument = doc}
							onMarkSigned={() => handleMarkSigned(doc)}
							onDelete={() => handleDelete(doc.id)}
							onAlwaysDelete={(name, id) => handleAlwaysDelete(name, id)}
							onToggleExclusion={(id, excluded) => handleToggleExclusion(id, excluded)}
							isProcessing={processingDocIds.has(doc.id)}
							onTypeOverride={handleTypeOverride}

							onNotesUpdate={handleNotesUpdate}
							onFactUpdate={handleFactUpdate}
							onFactConfirm={handleFactConfirm}
							onRelationshipAdd={handleRelationshipAdd}
							onRelationshipRemove={handleRelationshipRemove}
							onSignatureReview={handleSignatureReviewFromCard}
							availableDocuments={localDocuments.map(d => ({ id: d.id, name: d.file_name }))}
							isExpanded={expandedCardIds.has(doc.id)}
							onToggleExpand={handleToggleExpand}
						/>
					{/each}
				</div>
				{#if triageGroups.duplicates.length > visibleCounts.duplicates}
					<div class="mt-4 text-center">
						<button
							class="text-sm text-gray-500 hover:text-gray-700 underline"
							onclick={() => showAllDocs('duplicates')}
						>
							Show all {triageGroups.duplicates.length} documents
						</button>
					</div>
				{/if}
			</section>
		{/if}

			{#if localDocuments.length === 0}
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
							onMarkSigned={() => handleMarkSigned(doc)}
							onSkip={() => handleSkip(doc.id)}
							onDelete={() => handleDelete(doc.id)}
							onAlwaysDelete={(name, id) => handleAlwaysDelete(name, id)}
							onToggleExclusion={(id, excluded) => handleToggleExclusion(id, excluded)}
							isProcessing={processingDocIds.has(doc.id)}
							onTypeOverride={handleTypeOverride}

							onNotesUpdate={handleNotesUpdate}
							onFactUpdate={handleFactUpdate}
							onFactConfirm={handleFactConfirm}
							onRelationshipAdd={handleRelationshipAdd}
							onRelationshipRemove={handleRelationshipRemove}
							onSignatureReview={handleSignatureReviewFromCard}
							availableDocuments={localDocuments.map(d => ({ id: d.id, name: d.file_name }))}
							isExpanded={expandedCardIds.has(doc.id)}
							onToggleExpand={handleToggleExpand}
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
				<DocumentPreviewPane
					fileName={viewingDocument.file_name}
					fileType={viewingDocument.file_type}
					documentId={viewingDocument.id}
					hasStoragePath={Boolean(viewingDocument.storage_path)}
					previewUrl={pdfBlobUrl}
					loading={loadingPreview}
					isPdf={isPdfDocument(viewingDocument)}
					isImage={isImageDocument(viewingDocument)}
					isTextDocument={false}
					textPreview=""
					onLoadPreview={() => loadDocumentBinaryPreview(viewingDocument)}
					loadingLabel="Loading preview..."
					pdfHintMessage="Load inline preview only when needed to keep the viewer responsive."
					unavailableStorageMessage="The original file could not be loaded from storage."
					loadPdfLabel="Load PDF Preview"
					loadImageLabel="Load Image Preview"
					openLinkLabel="Open in New Tab"
					openInNewTab={true}
					linkDownload={false}
					noPreviewTitle={viewingDocument.extracted_text ? 'No File Preview' : 'Preview Unavailable'}
					noPreviewDescription={viewingDocument.extracted_text
						? 'Use the Summary or Raw Text tabs to view the extracted content.'
						: "This document doesn't have a preview available. You can view the extracted text in the correction modal."}
					previewHeightClass="min-h-[600px]"
				/>
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
			<!-- Verdict buttons -->
			{@const currentStatus = viewingDocument?.metadata?.signature_verification?.status}
			<div class="flex flex-wrap items-center gap-2 flex-1">
				<button
					onclick={() => handleSetVerdict('signed')}
					disabled={verdictSaving}
					class="btn btn-sm px-3 py-1.5 text-xs font-bold border transition-colors {currentStatus === 'signed'
						? 'bg-green-600 border-green-600 text-white'
						: 'bg-white border-green-300 text-green-700 hover:bg-green-50'}"
				>
					✓ Signed
				</button>
				<button
					onclick={() => handleSetVerdict('not_signed')}
					disabled={verdictSaving}
					class="btn btn-sm px-3 py-1.5 text-xs font-bold border transition-colors {currentStatus === 'not_signed'
						? 'bg-red-600 border-red-600 text-white'
						: 'bg-white border-red-300 text-red-700 hover:bg-red-50'}"
				>
					✗ Not Signed
				</button>
				<button
					onclick={() => { showNotesInput = !showNotesInput; verdictNotes = viewingDocument?.metadata?.signature_verification?.notes || ''; }}
					disabled={verdictSaving}
					class="btn btn-sm px-3 py-1.5 text-xs font-bold border transition-colors {currentStatus === 'unknown'
						? 'bg-amber-500 border-amber-500 text-white'
						: 'bg-white border-amber-300 text-amber-700 hover:bg-amber-50'}"
				>
					? Unclear…
				</button>

				{#if showNotesInput}
					<div class="w-full flex items-center gap-2 mt-1">
						<input
							type="text"
							bind:value={verdictNotes}
							placeholder="Add notes (optional)…"
							class="flex-1 text-xs border border-gray-300 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-amber-400"
						/>
						<button
							onclick={() => handleSetVerdict('unknown', verdictNotes)}
							disabled={verdictSaving}
							class="btn btn-sm px-3 py-1.5 text-xs font-bold bg-amber-500 text-white border-amber-500 hover:bg-amber-600"
						>
							{verdictSaving ? '…' : 'Save'}
						</button>
						<button
							onclick={() => { showNotesInput = false; verdictNotes = ''; }}
							class="btn btn-sm px-3 py-1.5 text-xs font-bold bg-white text-gray-600 border-gray-300 hover:bg-gray-50"
						>
							Cancel
						</button>
					</div>
				{/if}
			</div>

			<button
				onclick={closeDocumentViewer}
				class="btn btn-secondary px-6"
			>
				Close
			</button>
		{/snippet}
	</Modal>
{/if}

<!-- Document Review Panel (side-by-side PDF + text) -->
<DocumentReviewPanel
	open={documentReviewOpen}
	document={documentReviewDoc}
	{caseId}
	onClose={() => { documentReviewOpen = false; documentReviewDoc = null; }}
	onVerify={handleVerify}
	onReExtract={handleReExtract}
	onTextEdit={(doc) => editingDocument = doc}
/>

<!-- Signature Review Panel -->
<SignatureReviewPanel
	open={signatureReviewOpen}
	documents={signatureReviewQueue}
	currentIndex={signatureReviewIndex}
	{caseId}
	onClose={() => signatureReviewOpen = false}
	onVerdictSaved={handleSignatureVerdictFromPanel}
	onNavigate={(i) => signatureReviewIndex = i}
/>

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
