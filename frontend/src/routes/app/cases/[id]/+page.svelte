<script lang="ts">
	import { onMount, onDestroy, tick } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { supabase, getSecureSession } from '$lib/supabase';
	import { withRetry } from '$lib/utils/supabaseRetry';
	import { getApiUrl } from '$lib/config';
	import ClioMatterSearch from '$lib/components/ClioMatterSearch.svelte';
	import ClioLinkedMatter from '$lib/components/ClioLinkedMatter.svelte';
	import FailedClioDownloads from '$lib/components/FailedClioDownloads.svelte';
	import FilteredSmallImages from '$lib/components/FilteredSmallImages.svelte';
	// @ts-ignore
	import VerificationHub from '$lib/components/VerificationHub.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Tabs from '$lib/components/ui/Tabs.svelte';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
	import InlineAnalysisProgress from '$lib/components/InlineAnalysisProgress.svelte';
	import AnalysisStreamPanel from '$lib/components/AnalysisStreamPanel.svelte';
	import ResultsWorkspace from './results/+page.svelte';
	import { clioStore } from '$lib/stores/clioStore';
	import { progressStore } from '$lib/stores/progressStore';
	import { toastStore } from '$lib/stores/toastStore';
	import { Trash2, Edit, ArrowLeft } from 'lucide-svelte';
	import type { CaseData } from '$lib/types';
	import DocumentViewerModal from '$lib/components/DocumentViewerModal.svelte';
	import CaseDetailsCard from '$lib/components/CaseDetailsCard.svelte';
	import ConfirmDeleteDocumentModal from '$lib/components/ConfirmDeleteDocumentModal.svelte';
	import ConfirmDeleteCaseModal from '$lib/components/ConfirmDeleteCaseModal.svelte';
	import MissingTextWarningModal from '$lib/components/MissingTextWarningModal.svelte';
	import IntakeFormSelector from '$lib/components/IntakeFormSelector.svelte';
	import FileUploadManager from '$lib/components/FileUploadManager.svelte';
	import DocumentListSection from '$lib/components/DocumentListSection.svelte';
	import { syncClioMatter, dedupCaseDocuments, type ClioSyncResponse, type DedupResponse } from '$lib/api/cases';
	import { isCaseSummary, isIntakeForm, isPrimaryIntakeCandidate, isVideoAudioFile } from '$lib/utils/documentClassification';
	import { requiresSignatureReview, getDocumentSignatureDetection, getDocumentSignatureVerificationStatus, getDocumentSignatureStatus, getDocumentSignatureLabel, getDocumentSignatureBadgeClass, shouldShowSignatureBadge } from '$lib/utils/signatureDetection';
	import { formatDate, formatFileSize, getStatusColor } from '$lib/utils/formatters';

	let caseData = $state<CaseData | null>(null);
	let documents = $state<any[]>([]);
	let analysisStatus = $state<any>(null);
	let loading = $state(true);
	let analyzing = $state(false);
	let showProgressModal = $state(false);
	let currentAnalysisId = $state<string | null>(null);
	let navigatingToResults = $state(false);
	let showingEmbeddedResults = $state(false);
	let embeddedResultsData = $state<any | null>(null);
	let embeddedResultsKey = $state(0);
	let loadingEmbeddedResults = $state(false);
	let autoRunGapAnalysis = $state(false);
	let embeddedResultsError = $state('');
	
	// Streaming analysis state
	let showStreamingPanel = $state(false);
	let streamingAnalysisRef: AnalysisStreamPanel | null = $state(null);
	let streamedContent = $state('');
	let errorMessage = $state('');

	// Pre-flight validation state
	let showMissingTextWarning = $state(false);
	let runningBulkOcr = $state(false);

	// Clio sync state
	let syncLoading = $state(false);
	let syncResult = $state<ClioSyncResponse | null>(null);
	let syncError = $state<string | null>(null);

	// Dedup state
	let dedupLoading = $state(false);

	// Documents that are ready but missing extracted text (will be skipped in analysis)
	let docsWithoutText = $derived(
		documents.filter(doc => 
			doc.status === 'ready' && 
			!doc.extracted_at && 
			!doc.is_flagged_as_junk
		)
	);


	// Find all potential intake documents (case summaries and intake forms)
	let intakeCandidates = $derived(
		documents.filter(doc => isPrimaryIntakeCandidate(doc))
	);
	
	// Case summary documents (preferred over intake forms)
	let caseSummaryDocs = $derived(
		documents.filter(doc => isCaseSummary(doc))
	);
	
	// Current primary intake document
	let primaryIntakeDoc = $derived(
		documents.find(doc => doc.metadata?.is_intake_form)
	);
	
	// Recommended primary intake (case summary > intake form)
	let recommendedPrimaryIntake = $derived(() => {
		if (caseSummaryDocs.length > 0) {
			// Prefer newest case summary
			return [...caseSummaryDocs].sort((a, b) => 
				new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
			)[0];
		}
		const intakeForms = documents.filter(doc => isIntakeForm(doc));
		if (intakeForms.length > 0) {
			// Use oldest intake form
			return [...intakeForms].sort((a, b) => 
				new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
			)[0];
		}
		return null;
	});

	// Sort documents - primary intake first, case summaries, intake forms, then others
	// Document viewer modal state
	let viewingDocument = $state<any | null>(null);

	// Intake document selection state
	let showIntakeDocumentSelector = $state(false);
	let selectedIntakeDocId = $state<string | null>(null);

	let maxFileSizeMB = $state(100); // Default, will be fetched from settings

	// Delete confirmation state
	let deleteConfirmDoc = $state<string | null>(null);
	let deleteConfirmCase = $state(false);

	// Edit case state (bound to CaseDetailsCard)
	let editingCase = $state(false);
	let caseDetailsRef: CaseDetailsCard | undefined = $state();

	const caseId = $derived($page.params.id as string);
	
	// Tab state
	let activeTab = $state('overview');
	let componentActive = true;

	function applyViewFromUrl() {
		if (typeof window === 'undefined') return;
		const url = new URL(window.location.href);
		const tabParam = url.searchParams.get('tab');
		const viewParam = url.searchParams.get('view');

		if (tabParam && ['overview', 'documents', 'verification', 'analysis'].includes(tabParam)) {
			activeTab = tabParam;
		}
		if (viewParam === 'results') {
			showingEmbeddedResults = true;
		}
	}

	function persistAnalysisViewToUrl() {
		if (typeof window === 'undefined') return;
		const url = new URL(window.location.href);
		url.searchParams.set('tab', activeTab);
		if (activeTab === 'analysis' && showingEmbeddedResults) {
			url.searchParams.set('view', 'results');
		} else {
			url.searchParams.delete('view');
		}
		window.history.replaceState({}, '', `${url.pathname}${url.search}`);
	}

	async function loadEmbeddedResults(force = false) {
		if (!componentActive) return;
		if (loadingEmbeddedResults) return;
		if (!force && embeddedResultsData) {
			showingEmbeddedResults = true;
			return;
		}

		loadingEmbeddedResults = true;
		embeddedResultsError = '';

		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const [resultsResponse, profileResponse] = await Promise.all([
				fetch(`${apiUrl}/api/analysis/results/${caseId}`, {
					headers: { Authorization: `Bearer ${session.access_token}` }
				}),
				fetch(`${apiUrl}/api/profile`, {
					headers: { Authorization: `Bearer ${session.access_token}` }
				})
			]);

			if (!resultsResponse.ok) {
				const detail = await resultsResponse.json().catch(() => ({}));
				throw new Error(detail?.detail || 'Failed to load analysis results');
			}

			const [resultsPayload, profilePayload] = await Promise.all([
				resultsResponse.json(),
				profileResponse.ok ? profileResponse.json() : Promise.resolve(null)
			]);

			const docsSnapshot = (documents || []).map((doc: any) => ({ ...doc }));
			embeddedResultsData = {
				caseId,
				streamed: {
					results: Promise.resolve(resultsPayload),
					documents: Promise.resolve(docsSnapshot),
					profile: Promise.resolve(profilePayload)
				}
			};
			embeddedResultsKey += 1;
			showingEmbeddedResults = true;
			persistAnalysisViewToUrl();
		} catch (error: any) {
			embeddedResultsError = error.message || 'Failed to load embedded results workspace.';
		} finally {
			loadingEmbeddedResults = false;
		}
	}

	$effect(() => {
		// Keep embedded results state sticky across tab switches so returning to
		// Analysis is instant without forcing the user to reopen results.
		if (!loading) {
			persistAnalysisViewToUrl();
		}
	});

	onMount(async () => {
		applyViewFromUrl();
		await loadCase();
		await loadDocuments();
		await loadAnalysisStatus();
		await loadSettings();
		if (analysisStatus?.status === 'completed' && showingEmbeddedResults) {
			await loadEmbeddedResults(true);
		}
	});

	onDestroy(() => {
		componentActive = false;
		// Clean up SSE connection if active
		progressStore.disconnect();
	});

	async function loadSettings(retried = false) {
		try {
			const response = await fetch(`${getApiUrl()}/api/settings/limits`);
			if (response.ok) {
				const data = await response.json();
				maxFileSizeMB = data.max_file_size_mb;
			}
		} catch (error: any) {
			// Retry once on network errors (ERR_NETWORK_CHANGED)
			if (!retried && error instanceof TypeError && /fetch|network/i.test(error.message)) {
				await new Promise((r) => setTimeout(r, 1500));
				return loadSettings(true);
			}
			console.error('Failed to load settings:', error);
			// Keep default value
		}
	}

	async function loadCase() {
		try {
			// Use maybeSingle() instead of single() to avoid 406 when the row
			// doesn't exist yet (e.g., during a Clio import race) or was deleted.
			const { data, error } = await withRetry(() =>
				supabase
					.from('cases')
					.select('*')
					.eq('id', caseId)
					.maybeSingle()
			);

			if (error) throw error;

			if (!data) {
				errorMessage = 'Case not found';
				return;
			}

			// Parse clio_matter_data if it's a string
			const case_data = data as any;
			if (case_data && case_data.clio_matter_data) {
				if (typeof case_data.clio_matter_data === 'string') {
					try {
						case_data.clio_matter_data = JSON.parse(case_data.clio_matter_data);
					} catch (e) {
						console.error('Failed to parse clio_matter_data:', e);
					}
				}
			}

			caseData = case_data;
		} catch (error: any) {
			errorMessage = error.message || 'Failed to load case';
		} finally {
			loading = false;
		}
	}

	async function loadDocuments() {
		try {
			const { data, error } = await withRetry(() =>
				supabase
					.from('documents')
					.select('id, case_id, file_name, file_type, file_size, storage_path, status, extraction_method, extraction_quality, extracted_at, page_count, ocr_provider, extraction_error, is_verified, is_flagged_as_junk, text_edited_at, metadata, created_at, updated_at')
					.eq('case_id', caseId as string)
					.order('created_at', { ascending: true })
					.limit(10000)
			);

			if (error) throw error;
			// Create new object references to ensure Svelte 5 reactivity propagates to child components
			documents = (data || []).map((doc: Record<string, unknown>) => ({ ...doc }));
		} catch (error: any) {
			console.error('Failed to load documents:', error);
		}
	}

	// Track whether cross-doc enrichment has run for this case load
	let crossDocEnriched = $state(false);

	/**
	 * Run cross-document enrichment via the backend endpoint.
	 * Fires once when the verification tab is first activated,
	 * then reloads documents so suggested_relationships appear.
	 */
	async function runCrossDocEnrichment() {
		if (crossDocEnriched || !caseId || documents.length === 0) return;
		crossDocEnriched = true;
		try {
			const { session } = await getSecureSession();
			if (!session?.access_token) return;
			const resp = await fetch(`${getApiUrl()}/api/documents/case/${caseId}/enrich-cross-document`, {
				method: 'POST',
				headers: {
					'Authorization': `Bearer ${session.access_token}`,
					'Content-Type': 'application/json',
				},
			});
			if (!resp.ok) return;
			const result = await resp.json();
			if (result.enriched > 0 || result.registries_built > 0) {
				// Reload documents to pick up new registries and suggested_relationships
				await loadDocuments();
			}
		} catch (e: any) {
			// On network errors, allow retry on next trigger (e.g. tab switch)
			if (e instanceof TypeError && /fetch|network/i.test(e.message)) {
				crossDocEnriched = false;
				console.warn('Cross-document enrichment interrupted by network change — will retry', e);
			} else {
				console.error('Cross-document enrichment failed:', e);
			}
		}
	}

	// Trigger cross-doc enrichment (also auto-builds missing registries) when documents load
	$effect(() => {
		if (documents.length > 0) {
			runCrossDocEnrichment();
		}
	});

	async function loadAnalysisStatus() {
		try {
			// Fetch status fields only — the full result JSONB can be large (up to 40MB
			// for cases with many documents). The complete result is loaded separately
			// via the /api/analysis/results/{caseId} backend endpoint when needed.
			const { data, error } = await withRetry(() =>
				supabase
					.from('analysis_results')
					.select('id, status, created_at, completed_at')
					.eq('case_id', caseId as string)
					.order('created_at', { ascending: false })
					.limit(1)
					.maybeSingle()
			);

			if (error) throw error;
			analysisStatus = data;
		} catch (error: any) {
			console.error('Failed to load analysis status:', error);
			analysisStatus = null;
		}
	}

	async function handleSync() {
		if (!caseData?.clio_matter_id) {
			toastStore.error('No Clio matter linked to this case');
			return;
		}

		syncLoading = true;
		syncError = null;
		syncResult = null;

		try {
			const result = await syncClioMatter(caseId as string);
			syncResult = result;

			// Reload documents to show newly synced items
			await loadDocuments();

			if (result.summary.total_processed > 0) {
				toastStore.success(`Synced ${result.summary.total_processed} items from Clio`);
			}
		} catch (err) {
			syncError = err instanceof Error ? err.message : 'Failed to sync';
			toastStore.error(syncError);
		} finally {
			syncLoading = false;
		}
	}

	async function handleDedup() {
		dedupLoading = true;
		try {
			const result = await dedupCaseDocuments(caseId as string);
			await loadDocuments();
			if (result.duplicates_found > 0) {
				toastStore.success(`Found and removed ${result.duplicates_found} duplicate document${result.duplicates_found === 1 ? '' : 's'}`);
			} else {
				toastStore.success('No duplicate documents found');
			}
		} catch (err) {
			toastStore.error(err instanceof Error ? err.message : 'Failed to run dedup');
		} finally {
			dedupLoading = false;
		}
	}

	function viewDocument(doc: any) {
		viewingDocument = doc;
	}

	// Track whether we should start analysis after intake selection
	let startAnalysisAfterIntakeSelection = $state(false);

	async function promoteToIntakeForm(docId: string, options: { suppressToast?: boolean } = {}) {
		const targetDoc = documents.find((doc) => doc.id === docId);
		if (!targetDoc) throw new Error('Selected intake document no longer exists');

		const docsToEvaluate = documents.filter(
			(doc) => doc.id === docId || Boolean(doc.metadata?.is_intake_form)
		);

		for (const doc of docsToEvaluate) {
			const shouldBePrimary = doc.id === docId;
			const isPrimaryNow = Boolean(doc.metadata?.is_intake_form);
			if (shouldBePrimary === isPrimaryNow) continue;

			const { error } = await (supabase
				.from('documents') as any)
				.update({
					metadata: { ...(doc.metadata || {}), is_intake_form: shouldBePrimary }
				})
				.eq('id', doc.id);

			if (error) throw error;
		}

		selectedIntakeDocId = docId;
		await loadDocuments();

		if (!options.suppressToast) {
			toastStore.success(`Primary intake set to: ${targetDoc.file_name}`);
		}
	}

	async function confirmIntakeSelection() {
		if (!selectedIntakeDocId) {
			toastStore.error('Please select an intake document');
			return;
		}

		try {
			const selectedDoc = documents.find(d => d.id === selectedIntakeDocId);
			
			// If already the current primary, just close modal
			if (selectedDoc?.metadata?.is_intake_form) {
				showIntakeDocumentSelector = false;
				if (startAnalysisAfterIntakeSelection) {
					startAnalysisAfterIntakeSelection = false;
					await startStreamingAnalysis();
				}
				return;
			}

			await promoteToIntakeForm(selectedIntakeDocId);

			// Close modal
			showIntakeDocumentSelector = false;

			// Start analysis if this was triggered during analysis flow
			if (startAnalysisAfterIntakeSelection) {
				startAnalysisAfterIntakeSelection = false;
				await startStreamingAnalysis();
			}
		} catch (error: any) {
			errorMessage = error.message || 'Failed to update intake form';
		}
	}

	async function deleteDocument(docId: string) {
		try {
			const { session, user } = await getSecureSession();

		if (!session || !user) throw new Error('Not authenticated');

		const response = await fetch(`${getApiUrl()}/api/documents/${docId}`, {
				method: 'DELETE',
				headers: {
					Authorization: `Bearer ${session.access_token}`
				}
			});

			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || 'Failed to delete document');
			}

			await loadDocuments();
			deleteConfirmDoc = null;
		} catch (error: any) {
			errorMessage = error.message || 'Failed to delete document';
		}
	}

	async function reExtractDocument(docId: string, forceMethod: 'ocr' | 'vision', retried = false) {
		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			const methodLabel = forceMethod === 'vision' ? 'Image Analysis' : 'Text Extraction';
			if (!retried) toastStore.info(`Starting ${methodLabel}...`);

			const response = await fetch(`${getApiUrl()}/api/documents/${docId}/extract?force_method=${forceMethod}`, {
				method: 'POST',
				headers: {
					Authorization: `Bearer ${session.access_token}`
				}
			});

			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || `${methodLabel} failed`);
			}

			const result = await response.json();

			// Reload documents to show updated extracted text
			await loadDocuments();

			// Update viewing document if it's currently being viewed so the component reloads
			if (viewingDocument?.id === docId) {
				const updatedDoc = documents.find(d => d.id === docId);
				if (updatedDoc) {
					viewingDocument = updatedDoc;
				}
			}

			toastStore.success(`${methodLabel} completed successfully`);
		} catch (error: any) {
			// Retry once on network errors (ERR_NETWORK_CHANGED)
			if (!retried && error instanceof TypeError && /fetch|network/i.test(error.message)) {
				console.warn('Network error during extraction — retrying...', error);
				await new Promise((r) => setTimeout(r, 2000));
				return reExtractDocument(docId, forceMethod, true);
			}
			console.error('Failed to re-extract document:', error);
			toastStore.error(error.message || 'Re-extraction failed');
		}
	}

	async function deleteCase() {
		try {
			const { session, user } = await getSecureSession();

			if (!session || !user) {
				throw new Error('Not authenticated');
			}

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/cases/${caseId}`, {
				method: 'DELETE',
				headers: {
					Authorization: `Bearer ${session.access_token}`
				}
			});

			if (!response.ok) {
				let errorData;
				try {
					errorData = await response.json();
				} catch {
					errorData = { detail: `HTTP ${response.status}: ${response.statusText}` };
				}
				throw new Error(errorData.detail || 'Failed to delete case');
			}

			goto('/app/cases');
		} catch (error: any) {
			console.error('Delete case failed:', error);
			errorMessage = error.message || 'Failed to delete case';
			deleteConfirmCase = false;
		}
	}

	async function startAnalysis(skipMissingTextCheck = false) {
		// Refresh documents from database first to get latest state
		await loadDocuments();

		// Pre-flight check: Warn if any documents are missing text
		if (!skipMissingTextCheck && docsWithoutText.length > 0) {
			showMissingTextWarning = true;
			return;
		}

		// Check for multiple intake candidates before starting
		if (intakeCandidates.length > 1) {
			// Find if one is already marked
			const markedIntake = intakeCandidates.find(doc => doc.metadata?.is_intake_form);
			if (!markedIntake) {
				// No document is marked, user must choose
				startAnalysisAfterIntakeSelection = true;
				showIntakeDocumentSelector = true;
				return;
			}
			// If one is already marked, proceed with that one
		} else if (intakeCandidates.length === 1 && !intakeCandidates[0].metadata?.is_intake_form) {
			// Auto-select the only candidate
			await promoteToIntakeForm(intakeCandidates[0].id);
		}

		analyzing = true;
		errorMessage = '';

		try {
			const { session, user } = await getSecureSession();

		if (!session || !user) throw new Error('Not authenticated');

		const response = await fetch(`${getApiUrl()}/api/analysis/start`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`
				},
				body: JSON.stringify({
					case_id: caseId,
					provider: 'openai',
					intake_document_id: selectedIntakeDocId // Include if user selected
				})
			});

			if (!response.ok) {
				throw new Error('Failed to start analysis');
			}

			// Reset selection
			selectedIntakeDocId = null;

			// Check if response is SSE (Vercel) or JSON (local)
			const contentType = response.headers.get('content-type') || '';
			
			if (contentType.includes('text/event-stream')) {
				// Vercel: SSE stream - read first event to get analysis ID
				const reader = response.body?.getReader();
				if (!reader) throw new Error('No reader available');
				
				const decoder = new TextDecoder();
				let analysisId: string | null = null;
				
				// Read the first event to get the analysis ID
				const { value } = await reader.read();
				if (value) {
					const chunk = decoder.decode(value);
					const lines = chunk.split('\n');
					for (const line of lines) {
						if (line.startsWith('data: ')) {
							try {
								const data = JSON.parse(line.slice(6));
								if (data.type === 'started' && data.analysis?.id) {
									analysisId = data.analysis.id;
									break;
								}
							} catch (e) {
								console.error('Failed to parse SSE event:', e);
							}
						}
					}
				}
				
				if (!analysisId) {
					throw new Error('Failed to get analysis ID from stream');
				}
				
				currentAnalysisId = analysisId;
				showProgressModal = true;
				
				// Continue reading the SSE stream and forward events to progress store
				// This provides real-time updates without needing to poll
				(async () => {
					try {
						let buffer = '';
						while (true) {
							const { done, value } = await reader.read();
							if (done) {
								console.log('[Analysis SSE] Stream ended');
								break;
							}
							
							buffer += decoder.decode(value, { stream: true });
							const lines = buffer.split('\n');
							
							// Process complete lines, keep incomplete line in buffer
							buffer = lines.pop() || '';
							
							for (const line of lines) {
								if (line.startsWith('data: ')) {
									try {
										const data = JSON.parse(line.slice(6));
										console.log('[Analysis SSE] Event:', data.type || data.phase, data.percent || '', data.message?.slice(0, 50) || '');
										
										// Forward progress events to the store
										if (data.type === 'heartbeat') {
											// Heartbeat - just log it
											continue;
										} else if (data.type === 'completed') {
											progressStore.updateProgress({
												status: 'completed',
												message: 'Analysis complete',
												percent: 100
											});
										} else if (data.type === 'error') {
											progressStore.updateProgress({
												status: 'error',
												message: data.error || 'Analysis failed'
											});
										} else if (data.percent !== undefined || data.message) {
											// Progress update
											progressStore.updateProgress({
												status: 'progress',
												message: data.message,
												percent: data.percent,
												phase: data.phase,
												document: data.document
											});
										}
									} catch (e) {
										// Ignore parse errors for incomplete data
									}
								}
							}
						}
					} catch (e) {
						console.log('[Analysis SSE] Stream error:', e);
					}
				})();
				
			} else {
				// Local: JSON response
				const analysisData = await response.json();
				const analysisId = analysisData.id;
				currentAnalysisId = analysisId;
				showProgressModal = true;
			}

			// Reload analysis status
			await loadAnalysisStatus();
		} catch (error: any) {
			errorMessage = error.message || 'Failed to start analysis';
			analyzing = false;
		}
	}

	async function runOcrOnMissingDocs() {
		runningBulkOcr = true;
		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			// Paginated bulk-extract: process 20 docs per Vercel invocation to avoid the
			// 800s function timeout on large cases (200 docs × 45s = 9000s without pagination).
			let offset = 0;
			let hasMore = true;
			let totalExtracted = 0;
			let batchNum = 0;

			while (hasMore) {
				batchNum++;
				const response = await fetch(`${getApiUrl()}/api/documents/bulk-extract`, {
					method: 'POST',
					headers: {
						'Content-Type': 'application/json',
						Authorization: `Bearer ${session.access_token}`
					},
					body: JSON.stringify({ case_id: caseId, batch_size: 20, offset })
				});

				if (!response.ok) throw new Error(`Bulk extraction failed on batch ${batchNum}`);

				const result = await response.json();
				totalExtracted += result.extracted_count ?? 0;
				hasMore = result.has_more ?? false;
				offset = result.next_offset ?? offset;

				// Refresh document list after each batch so user sees incremental progress
				await loadDocuments();

				if (hasMore) {
					toastStore.info(`Extracted ${totalExtracted} so far, continuing...`);
				}
			}

			toastStore.success(`Extracted ${totalExtracted} document(s)`);

			// Force UI update by resetting the state flag before final checks
			runningBulkOcr = false;
			showMissingTextWarning = false;

			// Small delay to ensure UI has updated before checking
			await new Promise(resolve => setTimeout(resolve, 100));

			// If all docs now have text, proceed with analysis
			if (docsWithoutText.length === 0) {
				await startStreamingAnalysis();
			}
		} catch (error: any) {
			toastStore.error(`OCR failed: ${error.message}`);
		} finally {
			runningBulkOcr = false;
		}
	}

	async function proceedWithoutMissingDocs() {
		showMissingTextWarning = false;
		await startStreamingAnalysis(true); // Skip the missing text check and use streaming
	}

	async function resumeProcessingAnalysis() {
		// Check if the server-side collector finished and saved the analysis.
		// This handles the case where the stream disconnected mid-flight but
		// the LLM completed server-side.
		try {
			const { session } = await getSecureSession();
			if (!session) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const resp = await fetch(`${apiUrl}/api/analysis/stream/${caseId}/result`, {
				headers: { 'Authorization': `Bearer ${session.access_token}` },
			});

			if (resp.ok) {
				const data = await resp.json();
				if (data.found && data.content) {
					// Server has the result — show the streaming panel with recovered content
					showStreamingPanel = true;
					await tick();
					if (streamingAnalysisRef) {
						// Directly complete with server content
						handleStreamingComplete(data.content);
					}
					return;
				}
			}

			// No saved result — offer to restart
			toastStore.info('Server has not finished yet. Starting fresh analysis...');
			await startStreamingAnalysis();
		} catch (err: any) {
			console.error('Resume failed:', err);
			toastStore.error('Could not resume. Try starting a new analysis.');
		}
	}

	async function cancelAnalysis() {
		try {
			const { session, user } = await getSecureSession();

			if (!session || !user) throw new Error('Not authenticated');
			if (!analysisStatus?.id) throw new Error('No analysis to cancel');

			const ok = confirm('Cancel the current analysis? This will stop processing and allow you to run a new analysis.');
			if (!ok) return;

			// Stop any active progress stream immediately
			progressStore.disconnect();

			const response = await fetch(`${getApiUrl()}/api/analysis/cancel/${analysisStatus.id}`, {
				method: 'POST',
				headers: {
					Authorization: `Bearer ${session.access_token}`
				}
			});

			if (!response.ok) {
				const detail = await response.json().catch(() => ({}));
				throw new Error(detail?.detail || 'Failed to cancel analysis');
			}

			// Refresh UI state
			await loadAnalysisStatus();
			await loadCase();
			analyzing = false;
			errorMessage = '';
			toastStore.success('Analysis cancelled.');
		} catch (err: any) {
			console.error('Cancel analysis failed:', err);
			errorMessage = err.message || 'Failed to cancel analysis';
			toastStore.error(errorMessage);
		}
	}



	// Idempotency guard — prevents double completion from concurrent Resume + panel recovery
	let completionHandled = false;

	// Start streaming analysis (fast single-pass)
	async function startStreamingAnalysis(skipMissingTextCheck = false) {
		completionHandled = false;  // reset on genuinely new run
		if (!componentActive) return;

		// Pre-flight check using already-loaded documents (avoids blocking the click handler)
		if (!skipMissingTextCheck && docsWithoutText.length > 0) {
			showMissingTextWarning = true;
			return;
		}

		// Check for multiple intake candidates before starting
		if (intakeCandidates.length > 1) {
			const markedIntake = intakeCandidates.find(doc => doc.metadata?.is_intake_form);
			if (!markedIntake) {
				startAnalysisAfterIntakeSelection = true;
				showIntakeDocumentSelector = true;
				return;
			}
		} else if (intakeCandidates.length === 1 && !intakeCandidates[0].metadata?.is_intake_form) {
			await promoteToIntakeForm(intakeCandidates[0].id);
		}

		// Show panel immediately (optimistic UI), then start streaming after mount
		showStreamingPanel = true;
		// Refresh documents in background (the backend re-fetches anyway for the analysis)
		loadDocuments();
		await tick();
		if (!componentActive || !showStreamingPanel) return;
		streamingAnalysisRef?.startStreaming();
	}

	async function handleStreamingComplete(content: string) {
		if (completionHandled || !componentActive) return;
		completionHandled = true;
		streamedContent = content;
		toastStore.success('Analysis complete! Loading results workspace...');
		if (!componentActive) return;

		// Always settle the UI to a terminal state, even if sub-steps fail.
		try {
			await loadAnalysisStatus();
		} catch (e) {
			console.error('Failed to load analysis status after streaming:', e);
		}

		navigatingToResults = true;
		showStreamingPanel = false;
		activeTab = 'analysis';
		showingEmbeddedResults = true;
		autoRunGapAnalysis = true;

		try {
			await loadEmbeddedResults(true);
		} catch (e) {
			console.error('Failed to load embedded results:', e);
			toastStore.error('Results are ready but failed to load. Try refreshing the page.');
		}

		persistAnalysisViewToUrl();
		navigatingToResults = false;
	}

	function handleStreamingError(error: string) {
		toastStore.error(`Streaming analysis failed: ${error}`);
	}


</script>

<div class="page-spacing">
	{#if loading}
		<div class="p-8 text-center">
			<div class="inline-block animate-spin rounded-full h-8 w-8 border-2 border-accent border-t-transparent"></div>
		</div>
	{:else if !caseData}
		<div class="p-8 text-center">
			<p class="text-sm text-red-600">Case not found</p>
		</div>
	{:else}
		{@const data = caseData}
		<!-- Back Button -->
		<a
			href="/app/cases"
			class="inline-flex items-center text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors"
		>
			<ArrowLeft class="h-4 w-4 mr-2" />
			Back to Cases
		</a>

		<!-- Header with Actions -->
		<PageHeader
			title={data.client_name || ''}
			subtitle={data.reference_number || undefined}
			breadcrumbs={[
				{ label: 'Dashboard', href: '/app' },
				{ label: 'Cases', href: '/app/cases' },
				{ label: data.client_name || 'Case' }
			]}
		>
			{#snippet children()}
				<div class="flex items-center space-x-3">
					<span class="px-3 py-1 inline-flex text-sm leading-5 font-semibold rounded-full {getStatusColor(data.status || '')}">
						{data.status}
					</span>
					{#if !editingCase}
						<button
							onclick={() => caseDetailsRef?.startEditCase()}
							class="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent transition-colors"
						>
							<Edit class="h-4 w-4 mr-1.5" />
							Edit
						</button>
					{/if}
					<button
						onclick={() => (deleteConfirmCase = true)}
						class="inline-flex items-center px-3 py-2 border border-red-300 shadow-sm text-sm leading-4 font-medium rounded-md text-red-700 bg-white hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 transition-colors"
					>
						<Trash2 class="h-4 w-4 mr-1" />
						Delete
					</button>
				</div>
			{/snippet}
		</PageHeader>

		{#if errorMessage}
			<div class="rounded-md bg-red-50 p-4">
				<p class="text-sm text-red-800">{errorMessage}</p>
			</div>
		{/if}

		<!-- Tabs -->
		<Tabs
			tabs={[
				{ id: 'overview', label: 'Overview' },
				{ id: 'documents', label: 'Documents' },
				{ id: 'verification', label: `Verification${documents.filter(d => !d.is_verified && !d.is_flagged_as_junk).length > 0 ? ` (${documents.filter(d => !d.is_verified && !d.is_flagged_as_junk).length})` : ''}` },
				{ id: 'analysis', label: 'Analysis' }
			]}
			bind:activeTab
		>
			{#snippet children()}
				<!-- Overview Tab -->
				{#if activeTab === 'overview'}
					<div class="page-spacing">
						<!-- Case Info -->
						<CaseDetailsCard
							bind:this={caseDetailsRef}
							{caseData}
							{caseId}
							bind:editingCase
							onsaved={loadCase}
							onerror={(msg) => (errorMessage = msg)}
						/>

				<!-- Practice Area Guidance -->
				<details class="info-box info-box-teal">
			<summary class="cursor-pointer text-sm font-semibold text-contrast hover:opacity-80">
				ℹ️ Supported Practice Areas ({data.jurisdiction || 'Florida'} law)
			</summary>
			<div class="mt-4 text-sm text-gray-700 space-y-3">
				<p class="font-medium text-red-700">
					This application is optimized for {data.jurisdiction || 'Florida'} civil litigation matters only. Federal claims and other jurisdictions are not currently supported.
				</p>

				{#if (data.jurisdiction || 'Florida') === 'Florida'}
				<div>
					<h4 class="font-semibold text-green-800 mb-2">✅ Covered Florida Practice Areas:</h4>
					<ul class="space-y-2 ml-4">
						<li><strong>1. Consumer Protection & Business Misconduct</strong>
							<ul class="ml-4 mt-1 space-y-1 text-xs">
								<li>• Contract disputes and breach claims (UCC Ch. 671-672)</li>
								<li>• Consumer protection violations (FDUTPA - Ch. 501 Part II)</li>
								<li>• Business organization disputes (Ch. 605 LLC, Ch. 607 Corp)</li>
								<li>• Timeshare disputes and related matters</li>
							</ul>
						</li>
						<li><strong>2. Real Estate & Property Disputes</strong>
							<ul class="ml-4 mt-1 space-y-1 text-xs">
								<li>• Landlord-tenant disputes (Ch. 83)</li>
								<li>• Foreclosure defense and procedures (Ch. 702)</li>
								<li>• Property damage and insurance claims (Ch. 627)</li>
								<li>• Construction defects (Ch. 558)</li>
								<li>• Mechanic's liens (Ch. 713)</li>
							</ul>
						</li>
						<li><strong>3. Civil Litigation & Administrative Law</strong>
							<ul class="ml-4 mt-1 space-y-1 text-xs">
								<li>• Statutes of limitation (Ch. 95)</li>
								<li>• Administrative procedure matters (Ch. 120)</li>
								<li>• Attorney fees and sanctions (Ch. 57)</li>
							</ul>
						</li>
					</ul>
				</div>
				{:else if data.jurisdiction === 'New Mexico'}
				<div>
					<h4 class="font-semibold text-green-800 mb-2">✅ Covered New Mexico Practice Areas:</h4>
					<ul class="space-y-2 ml-4">
						<li><strong>1. Consumer Protection & Unfair Practices</strong>
							<ul class="ml-4 mt-1 space-y-1 text-xs">
								<li>• Unfair Practices Act (UPA - Ch. 57, Art. 12)</li>
								<li>• Deceptive trade practices</li>
								<li>• Consumer fraud and misrepresentation</li>
							</ul>
						</li>
						<li><strong>2. Landlord-Tenant (UORRA)</strong>
							<ul class="ml-4 mt-1 space-y-1 text-xs">
								<li>• Uniform Owner-Resident Relations Act (Ch. 47, Art. 8)</li>
								<li>• Evictions, rent disputes, and habitability</li>
								<li>• Security deposit disputes</li>
							</ul>
						</li>
						<li><strong>3. Construction & Liens</strong>
							<ul class="ml-4 mt-1 space-y-1 text-xs">
								<li>• Construction defects and anti-indemnity (Ch. 56, Art. 7)</li>
								<li>• Mechanic's liens (Ch. 48, Art. 2)</li>
								<li>• Statutes of limitation (Ch. 37, Art. 1)</li>
							</ul>
						</li>
						<li><strong>4. Real Estate & Foreclosure</strong>
							<ul class="ml-4 mt-1 space-y-1 text-xs">
								<li>• Judicial foreclosure procedures (Ch. 48, Art. 7)</li>
								<li>• Redemption of real property (Ch. 39, Art. 5)</li>
							</ul>
						</li>
						<li><strong>5. Insurance & Torts</strong>
							<ul class="ml-4 mt-1 space-y-1 text-xs">
								<li>• Unfair Claims Practices (Ch. 59A, Art. 16)</li>
								<li>• Comparative fault and several liability (Ch. 41, Art. 3A)</li>
							</ul>
						</li>
					</ul>
				</div>
				{/if}

				<div>
					<h4 class="font-semibold text-red-800 mb-2">⚠️ Not Supported:</h4>
					<ul class="ml-4 space-y-1 text-xs">
						<li>• Federal claims or federal court matters</li>
						<li>• Criminal law</li>
						<li>• Immigration law</li>
						<li>• Bankruptcy (federal jurisdiction)</li>
						<li>• Patent/trademark law (federal jurisdiction)</li>
						<li>• Out-of-state matters (non-{data.jurisdiction || 'Florida'})</li>
					</ul>
				</div>

				<p class="text-xs italic text-gray-600 mt-3">
					If your case involves federal law or multi-jurisdiction issues, please consult with the attorney before proceeding.
					</p>
				</div>
			</details>

					<!-- Clio Matter Import (only show if connected) -->
					{#if $clioStore.connected}
						<div class="card-standard">
							<h3 class="text-lg font-heading font-semibold text-contrast mb-4">
								{caseData?.clio_matter_id ? 'Clio Matter' : 'Import from Clio'}
							</h3>

							{#if data.clio_matter_id && data.clio_matter_data}
								<!-- Show linked matter display -->
								<ClioLinkedMatter
									caseId={caseId as string}
									matterData={data.clio_matter_data}
									caseData={data}
									onUnlinked={async () => {
										await loadCase();
										await loadDocuments();
									}}
									onMatterChanged={async () => {
										await loadCase();
										await loadDocuments();
									}}
								/>
							{:else}
								<!-- Show search UI (only if no matter linked) -->
								<ClioMatterSearch
									caseId={caseId as string}
									onMatterSelected={async () => {
										await loadCase();
										await loadDocuments();
									}}
								/>
							{/if}
						</div>

						<FailedClioDownloads {documents} onDocumentsUpdated={loadDocuments} />
						<FilteredSmallImages {documents} />
					{/if}
					</div>
				{/if}

				<!-- Documents Tab -->
				{#if activeTab === 'documents'}
					<div class="page-spacing">
						<!-- Enhanced Documents Section -->
		<div data-testid="documents-list" class="card-standard !p-0 overflow-hidden">
			<div class="px-6 py-5 border-b border-gray-100">
				<div class="flex justify-between items-center">
					<h3 class="text-lg font-heading font-semibold text-contrast">Documents</h3>

					<div class="flex items-center gap-2">
						<AsyncButton
							onclick={handleDedup}
							loading={dedupLoading}
							variant="secondary"
							size="sm"
							loadingText="Scanning..."
						>
							Find Duplicates
						</AsyncButton>
						{#if caseData?.clio_matter_id}
							<AsyncButton
								onclick={handleSync}
								loading={syncLoading}
								variant="secondary"
								size="sm"
								loadingText="Syncing..."
							>
								Sync from Clio
							</AsyncButton>
						{/if}
					</div>
				</div>
			</div>

			<!-- Primary Intake Document Instructions -->
			{#if intakeCandidates.length > 0}
				<div class="mx-4 mt-4 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg">
					<div class="flex items-start justify-between gap-4">
						<div class="flex-1">
							<h4 class="text-sm font-semibold text-blue-900 mb-1 flex items-center gap-2">
								<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
								</svg>
								Primary Intake Document
							</h4>
							<p class="text-xs text-blue-700 mb-2">
								The primary intake document provides case context for analysis. 
								<strong>Case summaries</strong> are preferred as they're more comprehensive than intake forms.
							</p>
							{#if primaryIntakeDoc}
								<p class="text-xs text-blue-800">
									<strong>Current:</strong> {primaryIntakeDoc.file_name}
									{#if !isCaseSummary(primaryIntakeDoc) && caseSummaryDocs.length > 0}
										<span class="text-amber-700 ml-2">💡 Consider using a case summary instead</span>
									{/if}
								</p>
							{:else if recommendedPrimaryIntake()}
								<p class="text-xs text-amber-700">
									<strong>Recommended:</strong> {recommendedPrimaryIntake().file_name}
									<span class="text-amber-600 ml-2">(Not yet selected)</span>
								</p>
							{/if}
						</div>
						<button
							onclick={() => showIntakeDocumentSelector = true}
							class="px-3 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-md transition-colors whitespace-nowrap"
						>
							{primaryIntakeDoc ? 'Change' : 'Select'} Primary Intake
						</button>
					</div>
				</div>
			{/if}

			<!-- Sync Results Display -->
			{#if syncResult}
				<div class="mx-4 mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
					<h4 class="text-sm font-semibold text-blue-900 mb-2">Sync Complete</h4>

					{#if syncResult.summary.total_processed === 0}
						<p class="text-sm text-blue-700">
							No changes detected. Your documents are up to date.
						</p>
					{:else}
						<div class="space-y-2">
							<p class="text-sm text-blue-800">
								<strong>{syncResult.summary.new_items}</strong> new item(s),
								<strong>{syncResult.summary.updated_items}</strong> updated item(s)
							</p>

							{#if syncResult.details.new.length > 0}
								<div>
									<p class="text-xs font-semibold text-blue-900 mb-1">New Items:</p>
									<ul class="text-xs text-blue-700 space-y-1 ml-4 list-disc">
										{#each syncResult.details.new as item}
											<li>
												{item.name}
												{#if item.date}
													<span class="text-blue-600">({new Date(item.date).toLocaleDateString()})</span>
												{/if}
											</li>
										{/each}
									</ul>
								</div>
							{/if}

							{#if syncResult.details.updated.length > 0}
								<div>
									<p class="text-xs font-semibold text-blue-900 mb-1">Updated Items:</p>
									<ul class="text-xs text-blue-700 space-y-1 ml-4 list-disc">
										{#each syncResult.details.updated as item}
											<li>
												{item.name}
												{#if item.date}
													<span class="text-blue-600">(updated {new Date(item.date).toLocaleDateString()})</span>
												{/if}
											</li>
										{/each}
									</ul>
								</div>
							{/if}

							{#if syncResult.needs_reanalysis}
								<p class="text-xs text-blue-800 mt-2 italic">
									Changes detected - re-run analysis to update results.
								</p>
							{/if}
						</div>
					{/if}

					<button
						onclick={() => syncResult = null}
						class="mt-3 text-xs text-blue-600 hover:text-blue-800 font-medium"
					>
						Dismiss
					</button>
				</div>
			{/if}

			<!-- Sync Error Display -->
			{#if syncError}
				<div class="mx-4 mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
					<h4 class="text-sm font-semibold text-red-900 mb-2">Sync Failed</h4>
					<p class="text-sm text-red-700 mb-3">{syncError}</p>

					{#if syncError.includes('authentication') || syncError.includes('authenticated')}
						<button
							onclick={() => goto('/app/settings?tab=integrations')}
							class="text-sm text-red-600 hover:text-red-800 font-medium underline"
						>
							Reconnect to Clio
						</button>
					{/if}

					<button
						onclick={() => syncError = null}
						class="ml-4 text-sm text-red-600 hover:text-red-800 font-medium"
					>
						Dismiss
					</button>
				</div>
			{/if}

			<!-- File Upload Manager -->
			<FileUploadManager
				{caseId}
				{documents}
				{maxFileSizeMB}
				onuploaded={loadDocuments}
				onerror={(msg) => (errorMessage = msg)}
			/>

			<!-- Uploaded Documents List -->
			<DocumentListSection
				{documents}
				onview={viewDocument}
				ondelete={(docId) => (deleteConfirmDoc = docId)}
				onpromote={(docId) => promoteToIntakeForm(docId)}
			/>
		</div>
					</div>
				{/if}

				<!-- Verification Tab -->
				{#if activeTab === 'verification'}
					<div class="page-spacing">
						<div class="card-standard">
							<div class="flex justify-between items-center mb-6">
								<div>
									<h3 class="text-lg font-heading font-semibold text-contrast">Document Verification</h3>
									<p class="text-sm text-gray-500 mt-1">
										Review extracted content and remove unnecessary documents before analysis.
									</p>
								</div>
							</div>

							{#if documents.length === 0}
								<div class="text-center py-12 text-gray-500">
									<p>No documents uploaded yet. Upload documents in the Documents tab.</p>
								</div>
							{:else}
								<VerificationHub
									{documents}
									{caseId}
									onDocumentsUpdated={loadDocuments}
								/>
							{/if}
						</div>
					</div>
				{/if}

				<!-- Streaming Analysis Panel — persists across tab switches -->
				{#if showStreamingPanel}
					<div class:hidden={activeTab !== 'analysis'} class="mb-6 page-spacing">
						<AnalysisStreamPanel
							caseId={caseId}
							bind:this={streamingAnalysisRef}
							onComplete={handleStreamingComplete}
							onError={handleStreamingError}
						/>
					</div>
				{/if}

				<!-- Inline Progress — persists across tab switches -->
				{#if showProgressModal && currentAnalysisId}
					<div class:hidden={activeTab !== 'analysis'} class="page-spacing">
						<InlineAnalysisProgress
							analysisId={currentAnalysisId}
							onComplete={async () => {
								showProgressModal = false;
								await loadAnalysisStatus();
								await loadCase();
								analyzing = false;
								activeTab = 'analysis';
								showingEmbeddedResults = true;
								await loadEmbeddedResults(true);
								persistAnalysisViewToUrl();
							}}
							onError={(error) => {
								showProgressModal = false;
								analyzing = false;
								errorMessage = error;
								toastStore.error(error);
							}}
							onCancel={cancelAnalysis}
						/>
					</div>
				{/if}

				<!-- Analysis Tab -->
				{#if activeTab === 'analysis'}
					<div class="page-spacing">
					<!-- Outdated Analysis Banner -->
					{#if caseData?.needs_reanalysis}
						<div class="rounded-lg bg-amber-50 border border-amber-300 p-4 mb-6">
							<div class="flex items-center justify-between">
								<div class="flex items-center gap-3">
									<span class="text-2xl">⚠️</span>
									<div>
										<p class="text-sm font-semibold text-amber-900">
											Analysis outdated
											{#if caseData.clio_last_synced_at}
												- new items added on {new Date(caseData.clio_last_synced_at).toLocaleDateString()}
											{:else}
												- new items available
											{/if}
										</p>
										<p class="text-xs text-amber-700 mt-1">
											Re-run analysis to include the latest documents and information.
										</p>
									</div>
								</div>
								<AsyncButton
									onclick={() => startStreamingAnalysis()}
									loading={showStreamingPanel || analyzing}
									variant="primary"
									loadingText="Starting..."
								>
									Re-run Analysis
								</AsyncButton>
							</div>
						</div>
					{/if}


						<!-- Analysis Section - hidden when streaming panel is active -->
						{#if !showStreamingPanel}
						{#if showingEmbeddedResults && analysisStatus?.status === 'completed'}
							<div class="card-standard flex flex-wrap items-center justify-between gap-3">
								<div>
									<h3 class="text-base font-heading font-semibold text-contrast">Results Workspace</h3>
									<p class="text-sm text-gray-500">You are viewing analysis results inline for this case.</p>
								</div>
								<div class="flex items-center gap-2">
									<AsyncButton
										onclick={() => {
											showingEmbeddedResults = false;
											persistAnalysisViewToUrl();
										}}
										variant="secondary"
									>
										Back to Analysis Controls
									</AsyncButton>
									<AsyncButton
										onclick={() => {
											showingEmbeddedResults = false;
											startStreamingAnalysis();
										}}
										loading={showStreamingPanel || analyzing}
										variant="primary"
										loadingText="Starting..."
									>
										Run New Analysis
									</AsyncButton>
								</div>
							</div>
						{:else}
						<div class="card-standard">
							<div class="flex justify-between items-center mb-6">
								<h3 class="text-lg font-heading font-semibold text-contrast">Analysis</h3>
								{#if documents.length > 0 && !showProgressModal}
									<div class="flex items-center gap-2">
										{#if analysisStatus?.status === 'processing'}
											<AsyncButton
												onclick={resumeProcessingAnalysis}
												loading={false}
												variant="primary"
												title="Check if the server completed the analysis"
											>
												Resume
											</AsyncButton>
											<AsyncButton
												onclick={cancelAnalysis}
												loading={false}
												variant="secondary"
												title="Cancel the current analysis"
											>
												Cancel
											</AsyncButton>
										{/if}

										<AsyncButton
											onclick={() => startStreamingAnalysis()}
											loading={analyzing || (analysisStatus && analysisStatus.status === 'processing')}
											variant="primary"
											loadingText="Analyzing..."
										>
											{#if analysisStatus && (analysisStatus.status === 'completed' || analysisStatus.status === 'failed')}
												Run New Analysis
											{:else}
												Start Analysis
											{/if}
										</AsyncButton>
									</div>
								{/if}
							</div>

			{#if !analysisStatus && documents.length === 0}
				<p class="text-sm text-gray-500">Upload documents to start analysis.</p>
			{:else if !analysisStatus}
				<p class="text-sm text-gray-500">Click "Start Analysis" button above to analyze your documents.</p>
			{:else}
				<div class="space-y-6">
					<div>
						<dt class="text-sm font-semibold text-gray-500 uppercase tracking-wider">Status</dt>
						<dd class="mt-2">
							<span class="px-3 py-1 inline-flex text-sm leading-5 font-semibold rounded-full {getStatusColor(analysisStatus.status)}">
								{analysisStatus.status}
							</span>
						</dd>
					</div>

					{#if analysisStatus.status === 'completed' && analysisStatus.result}
						<div class="flex items-center space-x-3">
							<AsyncButton
								onclick={async () => {
									navigatingToResults = true;
									showingEmbeddedResults = true;
									await loadEmbeddedResults(true);
									persistAnalysisViewToUrl();
									navigatingToResults = false;
								}}
								loading={navigatingToResults}
								variant="primary"
								loadingText="Loading Results..."
							>
							<svg class="h-4 w-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
							</svg>
								Open Results Workspace
							</AsyncButton>
					<AsyncButton
						onclick={() => startStreamingAnalysis()}
						loading={showStreamingPanel || analyzing}
						variant="secondary"
						loadingText="Re-running..."
						title="Re-run analysis with current documents"
					>
						<svg class="h-4 w-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
						</svg>
						Re-run Analysis
					</AsyncButton>
					</div>
				{/if}

					{#if analysisStatus.status === 'error'}
					<div>
						<AsyncButton
							onclick={() => startStreamingAnalysis()}
							loading={showStreamingPanel || analyzing}
							variant="primary"
							loadingText="Retrying..."
						>
							<svg class="h-4 w-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
							</svg>
							Retry Analysis
						</AsyncButton>
					</div>
					{/if}

							{#if analysisStatus.error}
								<div class="rounded-md bg-red-50 p-4">
									<p class="text-sm text-gray-800">{analysisStatus.error}</p>
								</div>
							{/if}
						</div>
					{/if}
					</div>
					{/if}
					{/if}

						{#if analysisStatus?.status === 'completed'}
							<div class="mt-6">
								{#if loadingEmbeddedResults}
									<div class="card-standard flex items-center gap-3 text-sm text-gray-600">
										<div class="animate-spin rounded-full h-4 w-4 border-b-2 border-accent"></div>
										Loading unified results workspace...
									</div>
								{:else if embeddedResultsError}
									<div class="card-standard border border-red-200 bg-red-50 text-sm text-red-700">
										{embeddedResultsError}
									</div>
								{/if}
							</div>
						{/if}
					</div>
					{/if}

				{#if analysisStatus?.status === 'completed' && showingEmbeddedResults && embeddedResultsData}
					<div class={activeTab === 'analysis' ? '' : 'hidden'} aria-hidden={activeTab !== 'analysis'}>
						<div class="mt-6">
							{#key embeddedResultsKey}
								<ResultsWorkspace data={embeddedResultsData} embedded={true} autoRunGapAnalysis={autoRunGapAnalysis} />
							{/key}
						</div>
					</div>
				{/if}
				{/snippet}
			</Tabs>
		{/if}
</div>

<!-- Document Delete Confirmation Modal -->
{#if deleteConfirmDoc}
	<ConfirmDeleteDocumentModal
		documentName={documents.find(d => d.id === deleteConfirmDoc)?.file_name ?? ''}
		onconfirm={() => deleteDocument(deleteConfirmDoc!)}
		oncancel={() => (deleteConfirmDoc = null)}
	/>
{/if}

<!-- Case Delete Confirmation Modal -->
{#if deleteConfirmCase}
	<ConfirmDeleteCaseModal
		clientName={caseData?.client_name ?? ''}
		referenceNumber={caseData?.reference_number}
		documentCount={documents.length}
		onconfirm={deleteCase}
		oncancel={() => (deleteConfirmCase = false)}
	/>
{/if}

<!-- Document Viewer Modal -->
<DocumentViewerModal
	document={viewingDocument}
	documents={documents}
	supabaseClient={supabase}
	results={embeddedResultsData}
	showReextract={true}
	onclose={() => { viewingDocument = null; }}
	onreextract={(detail) => reExtractDocument(detail.docId, detail.method)}
/>

<!-- Intake Document Selector Modal -->
{#if showIntakeDocumentSelector}
	<IntakeFormSelector
		{intakeCandidates}
		bind:selectedIntakeDocId
		onconfirm={confirmIntakeSelection}
		oncancel={() => (showIntakeDocumentSelector = false)}
	/>
{/if}

<!-- Missing Text Warning Modal -->
{#if showMissingTextWarning}
	<MissingTextWarningModal
		{docsWithoutText}
		{runningBulkOcr}
		oncancel={() => (showMissingTextWarning = false)}
		onskip={proceedWithoutMissingDocs}
		onocr={runOcrOnMissingDocs}
	/>
{/if}

<!-- Analysis progress is now shown inline on the Analysis tab -->
