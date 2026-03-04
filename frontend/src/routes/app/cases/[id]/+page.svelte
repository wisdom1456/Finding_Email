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
	import UploadFailureSummary from '$lib/components/UploadFailureSummary.svelte';
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
	import DocumentSummaryCard from '$lib/components/DocumentSummaryCard.svelte';
	import DocumentPreviewPane from '$lib/components/DocumentPreviewPane.svelte';
	import { syncClioMatter, type ClioSyncResponse } from '$lib/api/cases';

	let caseData = $state<CaseData | null>(null);
	let documents = $state<any[]>([]);
	let analysisStatus = $state<any>(null);
	let loading = $state(true);
	let uploading = $state(false);
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
	let uploadProgress = $state(0);
	let currentUploadFile = $state<string>('');
	let uploadedCount = $state(0);
	let totalUploadCount = $state(0);

	// Pre-flight validation state
	let showMissingTextWarning = $state(false);
	let runningBulkOcr = $state(false);

	// Clio sync state
	let syncLoading = $state(false);
	let syncResult = $state<ClioSyncResponse | null>(null);
	let syncError = $state<string | null>(null);

	// Documents that are ready but missing extracted text (will be skipped in analysis)
	let docsWithoutText = $derived(
		documents.filter(doc => 
			doc.status === 'ready' && 
			!doc.extracted_at && 
			!doc.is_flagged_as_junk
		)
	);

	// Helper functions to check document types
	function isCaseSummary(doc: any): boolean {
		return doc.file_name.toLowerCase().includes('case summary') || 
		       doc.file_name.toLowerCase().includes('case_summary') ||
		       doc.file_name.toLowerCase().includes('casesummary');
	}
	
	function isIntakeForm(doc: any): boolean {
		return doc.file_name.toLowerCase().includes('intake');
	}
	
	function isPrimaryIntakeCandidate(doc: any): boolean {
		return isCaseSummary(doc) || isIntakeForm(doc);
	}

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
	let sortedDocuments = $derived(
		[...documents].sort((a, b) => {
			const aIsPrimary = a.metadata?.is_intake_form || false;
			const bIsPrimary = b.metadata?.is_intake_form || false;
			const aIsCaseSummary = isCaseSummary(a);
			const bIsCaseSummary = isCaseSummary(b);
			const aIsIntake = isIntakeForm(a);
			const bIsIntake = isIntakeForm(b);
			
			// Primary intake first
			if (aIsPrimary && !bIsPrimary) return -1;
			if (!aIsPrimary && bIsPrimary) return 1;
			
			// Then case summaries
			if (aIsCaseSummary && !bIsCaseSummary) return -1;
			if (!aIsCaseSummary && bIsCaseSummary) return 1;
			
			// Then intake forms
			if (aIsIntake && !bIsIntake) return -1;
			if (!aIsIntake && bIsIntake) return 1;
			
			// Otherwise by date (oldest first)
			return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
		})
	);

	// Document viewer modal state
	let viewingDocument = $state<any>(null);
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
	let isPdfDocument = $derived(isPdfLikeDocument(viewingDocument));
	let isImageDocument = $derived(isImageLikeDocument(viewingDocument));

	// Intake document selection state
	let showIntakeDocumentSelector = $state(false);
	let selectedIntakeDocId = $state<string | null>(null);

	// New state for enhanced upload
	let selectedFiles = $state<File[]>([]);
	let intakeFormIndex = $state<number | null>(null);
	let showIntakeSelector = $state(false);
	let dragActive = $state(false);
	let duplicateFiles = $state<Set<number>>(new Set());

	// Upload failure tracking
	interface UploadFailure {
		fileName: string;
		reason: string;
		fileSizeMB?: number;
		errorCode: string;
		file?: File; // Keep file for retry
	}
	let uploadFailures = $state<UploadFailure[]>([]);
	let showFailureSummary = $state(false);
	let maxFileSizeMB = $state(100); // Default, will be fetched from settings

	// Delete confirmation state
	let deleteConfirmDoc = $state<string | null>(null);
	let deleteConfirmCase = $state(false);
	let deleteCaseText = $state('');

	// Edit case state
	let editingCase = $state(false);
	let editClientName = $state('');
	let editReferenceNumber = $state('');
	let editDescription = $state('');
	let savingCase = $state(false);

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
		if (viewingDocument && documentViewerTab === 'text' && !extractedTextData && !loadingExtractedText) {
			loadExtractedText(viewingDocument.id);
		}
	});

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

	async function loadSettings() {
		try {
			const response = await fetch(`${getApiUrl()}/api/settings/limits`);
			if (response.ok) {
				const data = await response.json();
				maxFileSizeMB = data.max_file_size_mb;
			}
		} catch (error) {
			console.error('Failed to load settings:', error);
			// Keep default value
		}
	}

	function categorizeError(errorMessage: string, errorCode?: string): string {
		if (errorCode) return errorCode;
		
		// Fallback categorization based on message
		if (errorMessage.includes('MB') || errorMessage.toLowerCase().includes('size')) 
			return 'FILE_TOO_LARGE';
		if (errorMessage.toLowerCase().includes('extension') || errorMessage.toLowerCase().includes('type')) 
			return 'INVALID_TYPE';
		if (errorMessage.toLowerCase().includes('content') || errorMessage.toLowerCase().includes('magic')) 
			return 'CONTENT_VALIDATION';
		if (errorMessage.toLowerCase().includes('empty')) 
			return 'CORRUPTED';
		if (errorMessage.toLowerCase().includes('security'))
			return 'SECURITY_VIOLATION';
		return 'UNKNOWN';
	}

	function validateFileBeforeUpload(file: File): { valid: boolean; error?: string; errorCode?: string } {
		// Check file size
		const fileSizeMB = file.size / (1024 * 1024);
		if (fileSizeMB > maxFileSizeMB) {
			return {
				valid: false,
				error: `File size (${fileSizeMB.toFixed(2)}MB) exceeds maximum allowed size (${maxFileSizeMB}MB)`,
				errorCode: 'FILE_TOO_LARGE'
			};
		}

		// Check file type
		const allowedExtensions = ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.eml', '.jpg', '.jpeg', '.png', '.csv'];
		const fileName = file.name.toLowerCase();
		const hasValidExtension = allowedExtensions.some(ext => fileName.endsWith(ext));
		
		if (!hasValidExtension) {
			return {
				valid: false,
				error: `File type not allowed. Allowed types: ${allowedExtensions.join(', ')}`,
				errorCode: 'INVALID_TYPE'
			};
		}

		// Check if empty
		if (file.size === 0) {
			return {
				valid: false,
				error: 'Empty files are not allowed',
				errorCode: 'CORRUPTED'
			};
		}

		return { valid: true };
	}

	async function loadCase() {
		try {
			const { data, error } = await withRetry(() =>
				supabase
					.from('cases')
					.select('*')
					.eq('id', caseId)
					.single()
			);

			if (error) throw error;
			
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

	function handleFileInput(event: Event) {
		const input = event.target as HTMLInputElement;
		if (input.files && input.files.length > 0) {
			const files = Array.from(input.files);
			processSelectedFiles(files);
		}
	}

	function handleDrop(event: DragEvent) {
		event.preventDefault();
		dragActive = false;

		if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
			const files = Array.from(event.dataTransfer.files);
			processSelectedFiles(files);
		}
	}

	function handleDragOver(event: DragEvent) {
		event.preventDefault();
		dragActive = true;
	}

	function handleDragLeave(event: DragEvent) {
		event.preventDefault();
		dragActive = false;
	}

	function processSelectedFiles(files: File[]) {
		// Check for duplicates
		const existingFileNames = new Set(documents.map(doc => doc.file_name));
		const newDuplicates = new Set<number>();

		files.forEach((file, index) => {
			if (existingFileNames.has(file.name)) {
				newDuplicates.add(index);
			}
		});

		duplicateFiles = newDuplicates;
		selectedFiles = files;

		// If there are files with "intake" in the name, show intake selector
		const intakeFiles = files.filter((f, idx) => 
			!newDuplicates.has(idx) && f.name.toLowerCase().includes('intake')
		);

		if (intakeFiles.length > 0) {
			showIntakeSelector = true;
		}
	}

	function removeSelectedFile(index: number) {
		if (index < 0 || index >= selectedFiles.length) return;

		const nextSelectedFiles = selectedFiles.filter((_, i) => i !== index);
		selectedFiles = nextSelectedFiles;

		const adjustedDuplicates = new Set<number>();
		for (const duplicateIndex of duplicateFiles) {
			if (duplicateIndex === index) continue;
			adjustedDuplicates.add(duplicateIndex > index ? duplicateIndex - 1 : duplicateIndex);
		}
		duplicateFiles = adjustedDuplicates;

		if (intakeFormIndex !== null) {
			if (intakeFormIndex === index) {
				intakeFormIndex = null;
			} else if (intakeFormIndex > index) {
				intakeFormIndex -= 1;
			}
		}

		showIntakeSelector = nextSelectedFiles.some(
			(file, i) => !adjustedDuplicates.has(i) && file.name.toLowerCase().includes('intake')
		);
	}

	function selectIntakeForm(index: number | null) {
		intakeFormIndex = index;
		showIntakeSelector = false;
	}

	function retryFailedUploads() {
		const retryFiles = uploadFailures
			.map((failure) => failure.file)
			.filter((file): file is File => file instanceof File);

		if (retryFiles.length === 0) {
			toastStore.warning('No retryable files were included in the failed upload list.');
			return;
		}

		showFailureSummary = false;
		uploadFailures = [];
		processSelectedFiles(retryFiles);
	}

	async function uploadSelectedFiles() {
		if (selectedFiles.length === 0) return;

		uploading = true;
		uploadProgress = 0;
		uploadedCount = 0;
		totalUploadCount = selectedFiles.length;
		uploadFailures = [];

		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			for (let originalIndex = 0; originalIndex < selectedFiles.length; originalIndex++) {
				const file = selectedFiles[originalIndex];
				currentUploadFile = file.name;

				// Skip duplicates
				if (duplicateFiles.has(originalIndex)) {
					uploadFailures.push({
						fileName: file.name,
						reason: 'Duplicate file name already exists',
						errorCode: 'DUPLICATE'
					});
					continue;
				}

				// Validate file
				const validation = validateFileBeforeUpload(file);
				if (!validation.valid) {
					uploadFailures.push({
						fileName: file.name,
						reason: validation.error || 'Validation failed',
						errorCode: validation.errorCode || 'VALIDATION_FAILED',
						fileSizeMB: file.size / (1024 * 1024),
						file: file
					});
					continue;
				}

				// Upload file
				const formData = new FormData();
				formData.append('file', file);
			formData.append('case_id', caseId as string);
			formData.append('is_intake_form', (originalIndex === intakeFormIndex).toString());

			const response = await fetch(`${getApiUrl()}/api/documents/upload`, {
					method: 'POST',
					headers: {
						Authorization: `Bearer ${session.access_token}`
					},
					body: formData
				});

				if (!response.ok) {
					const errorData = await response.json().catch(() => ({ detail: 'Upload failed' }));
					uploadFailures.push({
						fileName: file.name,
						reason: errorData.detail || 'Upload failed',
						errorCode: categorizeError(errorData.detail || ''),
						file: file
					});
				} else {
					uploadedCount++;
				}

				uploadProgress = ((originalIndex + 1) / totalUploadCount) * 100;
			}

			// Reload documents
			await loadDocuments();

			// Show summary if there were failures
			if (uploadFailures.length > 0) {
				showFailureSummary = true;
			} else {
				toastStore.success(`Uploaded ${uploadedCount} file(s) successfully`);
			}

			// Clear selection
			selectedFiles = [];
			intakeFormIndex = null;
			showIntakeSelector = false;
			duplicateFiles = new Set();

		} catch (error: any) {
			errorMessage = error.message || 'Upload failed';
			toastStore.error(errorMessage);
		} finally {
			uploading = false;
			currentUploadFile = '';
		}
	}

	async function viewDocument(doc: any) {
		viewingDocument = doc;
		documentViewerContent = '';
		documentViewerTab = 'preview';
		documentSummary = null;
		loadingPreview = false;
		extractedTextData = null;

		// Clean up previous blob URL if it exists
		if (pdfBlobUrl) {
			URL.revokeObjectURL(pdfBlobUrl);
			pdfBlobUrl = null;
		}
		previewBlobDocumentId = null;

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

			// If document has text extracted (indicated by extracted_at), fetch it on demand
			// as it is no longer loaded in the initial documents list to prevent timeouts.
			if (doc.extracted_at) {
				const { data: textData, error: textError } = await supabase
					.from('documents')
					.select('extracted_text')
					.eq('id', doc.id)
					.single();
				
				const typedData = textData as any;
				if (!textError && typedData?.extracted_text) {
					documentViewerContent = typedData.extracted_text;
					return;
				}
			}

			if (!isTextLikeDocument(doc)) {
				documentViewerContent = `Unable to display this document. File type: ${doc.file_type}`;
				return;
			}

			const { session, user } = await getSecureSession();
			if (!session || !user) {
				documentViewerContent = 'Error: Not authenticated';
				return;
			}

			const { data, error } = await supabase.storage
				.from('documents')
				.download(doc.storage_path);

			if (error) throw error;

			documentViewerContent = await data.text();
		} catch (error: any) {
			console.error('Failed to load document:', error);
			documentViewerContent = `Unable to display this document. File type: ${doc.file_type}`;
		}
	}

	function isPdfLikeDocument(doc: any): boolean {
		if (!doc) return false;
		const fileType = String(doc.file_type || '').toLowerCase();
		const fileName = String(doc.file_name || '').toLowerCase();
		return fileType === 'application/pdf' || fileName.endsWith('.pdf');
	}

	function isImageLikeDocument(doc: any): boolean {
		if (!doc) return false;
		return String(doc.file_type || '').toLowerCase().startsWith('image/');
	}

	function isTextLikeDocument(doc: any): boolean {
		if (!doc) return false;
		const fileType = String(doc.file_type || '').toLowerCase();
		const fileName = String(doc.file_name || '').toLowerCase();
		return (
			fileType.startsWith('text/') ||
			fileName.endsWith('.txt') ||
			fileName.endsWith('.md') ||
			fileName.endsWith('.csv') ||
			fileName.endsWith('.log')
		);
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
			if (!session || !user) {
				documentViewerContent = 'Error: Not authenticated';
				return;
			}

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

	function closeDocumentViewer() {
		// Clean up blob URL to prevent memory leaks
		if (pdfBlobUrl) {
			URL.revokeObjectURL(pdfBlobUrl);
			pdfBlobUrl = null;
		}
		previewBlobDocumentId = null;
		viewingDocument = null;
		documentViewerContent = '';
		documentViewerTab = 'preview';
		loadingPreview = false;
		extractedTextData = null;
		loadingExtractedText = false;
		documentSummary = null;
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
			alert('Please select an intake document');
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

	async function reExtractDocument(docId: string, forceMethod: 'ocr' | 'vision') {
		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			const methodLabel = forceMethod === 'vision' ? 'Image Analysis' : 'Text Extraction';
			toastStore.info(`Starting ${methodLabel}...`);

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

			// Update viewing document if it's currently being viewed
			if (viewingDocument?.id === docId) {
				const updatedDoc = documents.find(d => d.id === docId);
				if (updatedDoc) {
					viewingDocument = updatedDoc;
					// Reload extracted text
					if (documentViewerTab === 'text') {
						await loadExtractedText(docId);
					}
				}
			}

			toastStore.success(`${methodLabel} completed successfully`);
		} catch (error: any) {
			console.error('Failed to re-extract document:', error);
			toastStore.error(error.message || 'Re-extraction failed');
		}
	}

	async function deleteCase() {
		if (deleteCaseText !== 'DELETE') return;

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

	function startEditCase() {
		const data = caseData;
		if (!data) return;
		editClientName = data.client_name;
		editReferenceNumber = data.reference_number || '';
		editDescription = data.description || '';
		editingCase = true;
		errorMessage = '';
	}

	function cancelEditCase() {
		editingCase = false;
		editClientName = '';
		editReferenceNumber = '';
		editDescription = '';
	}

	async function saveCase() {
		savingCase = true;
		errorMessage = '';

		try {
			const { session, user } = await getSecureSession();

		if (!session || !user) throw new Error('Not authenticated');

		const response = await fetch(`${getApiUrl()}/api/cases/${caseId}`, {
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`
				},
				body: JSON.stringify({
					client_name: editClientName,
					reference_number: editReferenceNumber || null,
					description: editDescription || null
				})
			});

			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || 'Failed to update case');
			}

			// Reload case data
			await loadCase();
			editingCase = false;
		} catch (error: any) {
			errorMessage = error.message || 'Failed to update case';
		} finally {
			savingCase = false;
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

	function formatDate(dateString: string) {
		return new Date(dateString).toLocaleDateString('en-US', {
			year: 'numeric',
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function formatFileSize(bytes: number) {
		if (bytes < 1024) return bytes + ' B';
		if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
		return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
	}

	type SignatureStatus = 'signed' | 'not_detected' | 'review_required' | 'other' | 'none';

	const signatureRequiredKeywords = [
		'agreement',
		'contract',
		'lease',
		'addendum',
		'amendment',
		'settlement',
		'release',
		'authorization',
		'consent',
		'affidavit',
		'declaration',
		'stipulation',
		'promissory note',
		'guaranty',
		'power of attorney',
		'poa',
		'signature page',
		'executed'
	];

	function requiresSignatureReview(doc: any): boolean {
		const fileName = String(doc?.file_name || '').toLowerCase();
		return signatureRequiredKeywords.some((keyword) => fileName.includes(keyword));
	}

	function getDocumentSignatureDetection(doc: any): any | null {
		const sig = doc?.metadata?.signature_detection;
		return sig && typeof sig === 'object' ? sig : null;
	}

	function getDocumentSignatureVerificationStatus(doc: any): 'signed' | 'not_signed' | 'unknown' | 'none' {
		const verification = doc?.metadata?.signature_verification;
		if (!verification || typeof verification !== 'object') return 'none';
		const status = String(verification.status || '').toLowerCase().trim();
		if (status === 'signed') return 'signed';
		if (status === 'not_signed' || status === 'unsigned' || status === 'not_detected' || status === 'not signed') {
			return 'not_signed';
		}
		if (status === 'unknown' || status === 'unclear') return 'unknown';
		return 'none';
	}

	function getDocumentSignatureStatus(doc: any): SignatureStatus {
		const verifiedStatus = getDocumentSignatureVerificationStatus(doc);
		if (verifiedStatus === 'signed') return 'signed';
		if (verifiedStatus === 'not_signed') return 'not_detected';
		if (verifiedStatus === 'unknown') return 'review_required';

		const signatureDetection = getDocumentSignatureDetection(doc);
		if (!signatureDetection) return requiresSignatureReview(doc) ? 'review_required' : 'none';
		const status = String(signatureDetection.status || '').toLowerCase();
		if (status === 'signed') return 'signed';
		if (status === 'not_detected') return 'not_detected';
		return 'other';
	}

	function getDocumentSignatureLabel(doc: any): string {
		const verifiedStatus = getDocumentSignatureVerificationStatus(doc);
		if (verifiedStatus === 'signed') return 'SIGNED (ATTORNEY VERIFIED)';
		if (verifiedStatus === 'not_signed') return 'NOT SIGNED (ATTORNEY VERIFIED)';
		if (verifiedStatus === 'unknown') return 'SIGNATURE REVIEWED (UNCLEAR)';

		const signatureDetection = getDocumentSignatureDetection(doc);
		if (!signatureDetection) {
			if (requiresSignatureReview(doc)) return 'SIGNATURE REVIEW RECOMMENDED';
			return '';
		}
		const status = getDocumentSignatureStatus(doc);
		const confidence = signatureDetection?.confidence
			? ` (${String(signatureDetection.confidence).toUpperCase()})`
			: '';
		if (status === 'signed') return `SIGNED${confidence}`;
		if (status === 'not_detected') return `NO SIGNATURE DETECTED${confidence}`;
		if (status === 'review_required') return 'SIGNATURE REVIEW RECOMMENDED';
		return `SIGNATURE: ${String(signatureDetection.status || 'UNKNOWN').toUpperCase()}${confidence}`;
	}

	function getDocumentSignatureBadgeClass(doc: any): string {
		const status = getDocumentSignatureStatus(doc);
		if (status === 'signed') {
			return 'bg-emerald-100 text-emerald-800 border-emerald-300';
		}
		if (status === 'not_detected') {
			return 'bg-amber-100 text-amber-800 border-amber-300';
		}
		if (status === 'review_required') {
			return 'bg-yellow-100 text-yellow-900 border-yellow-300';
		}
		return 'bg-gray-100 text-gray-700 border-gray-300';
	}

	function shouldShowSignatureBadge(doc: any): boolean {
		return getDocumentSignatureStatus(doc) !== 'none';
	}

	// Start streaming analysis (fast single-pass)
	async function startStreamingAnalysis(skipMissingTextCheck = false) {
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
		if (!componentActive) return;
		streamedContent = content;
		toastStore.success('Analysis complete! Loading results workspace...');
		if (!componentActive) return;

		// Save is now awaited in AnalysisStreamPanel.emitComplete, no delay needed
		await loadAnalysisStatus();
		navigatingToResults = true;
		showStreamingPanel = false;
		activeTab = 'analysis';
		showingEmbeddedResults = true;
		autoRunGapAnalysis = true;
		await loadEmbeddedResults(true);
		persistAnalysisViewToUrl();
		navigatingToResults = false;
	}

	function handleStreamingError(error: string) {
		toastStore.error(`Streaming analysis failed: ${error}`);
		showStreamingPanel = false;
	}

	function getStatusColor(status: string) {
		switch (status) {
			case 'completed':
				return 'bg-accent/10 text-accent';
			case 'processing':
				return 'bg-contrast-light/10 text-contrast-light';
			case 'error':
				return 'bg-red-100 text-red-700';
			default:
				return 'bg-gray-100 text-gray-700';
		}
	}

	function isVideoAudioFile(fileName: string): boolean {
		const videoAudioExtensions = [
			'.mov', '.mp4', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v',  // Video
			'.mp3', '.wav', '.aac', '.flac', '.m4a', '.ogg', '.wma', '.aiff',  // Audio
		];
		return videoAudioExtensions.some(ext => fileName.toLowerCase().endsWith(ext));
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
							onclick={startEditCase}
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
						<div class="card-standard">
							<div class="flex justify-between items-center mb-4">
								<h3 class="text-lg font-semibold text-contrast">Case Details</h3>
							</div>

			{#if editingCase}
				<!-- Edit Form -->
				<form onsubmit={(e) => { e.preventDefault(); saveCase(); }} class="space-y-4">
					<div>
						<label for="edit-client-name" class="block text-sm font-medium text-contrast">
							Client Name <span class="text-red-500">*</span>
						</label>
						<input
							id="edit-client-name"
							type="text"
							bind:value={editClientName}
							required
							class="input-standard focus:ring-accent focus:border-accent"
						/>
					</div>

					<div>
						<label for="edit-reference-number" class="block text-sm font-medium text-contrast">
							Reference Number
						</label>
						<input
							id="edit-reference-number"
							type="text"
							bind:value={editReferenceNumber}
							class="input-standard focus:ring-accent focus:border-accent"
						/>
					</div>

					<div>
						<label for="edit-description" class="block text-sm font-medium text-contrast">
							Description
						</label>
						<textarea
							id="edit-description"
							bind:value={editDescription}
							rows="3"
							class="input-standard focus:ring-accent focus:border-accent"
						></textarea>
					</div>

					<div class="flex justify-end space-x-3 pt-2">
						<button
							type="button"
							onclick={cancelEditCase}
							disabled={savingCase}
							class="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
						>
							Cancel
						</button>
						<AsyncButton
							type="submit"
							disabled={!editClientName.trim()}
							loading={savingCase}
							variant="primary"
							loadingText="Saving..."
						>
							Save Changes
						</AsyncButton>
					</div>
				</form>
			{:else}
				<!-- View Mode -->
				<dl class="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2">
					<div>
						<dt class="text-sm font-medium text-gray-500">Client Name</dt>
						<dd class="mt-1 text-sm text-gray-900">{data.client_name}</dd>
					</div>
					<div>
						<dt class="text-sm font-medium text-gray-500">Jurisdiction</dt>
						<dd class="mt-1 text-sm text-gray-900">
							<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium {data.jurisdiction === 'New Mexico' ? 'bg-indigo-100 text-indigo-800' : 'bg-orange-100 text-orange-800'}">
								{data.jurisdiction || 'Florida'}
							</span>
						</dd>
					</div>
					{#if data.reference_number}
						<div>
							<dt class="text-sm font-medium text-gray-500">Reference Number</dt>
							<dd class="mt-1 text-sm text-gray-900">{data.reference_number}</dd>
						</div>
					{/if}
					<div>
						<dt class="text-sm font-medium text-gray-500">Created</dt>
						<dd class="mt-1 text-sm text-gray-900">{formatDate(data.created_at)}</dd>
					</div>
					<div>
						<dt class="text-sm font-medium text-gray-500">Last Updated</dt>
						<dd class="mt-1 text-sm text-gray-900">{formatDate(data.updated_at)}</dd>
					</div>
					{#if data.description}
						<div class="sm:col-span-2">
							<dt class="text-sm font-medium text-gray-500">Description</dt>
							<dd class="mt-1 text-sm text-gray-900">{data.description}</dd>
						</div>
					{/if}
				</dl>
					{/if}
				</div>

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
					{/if}
					</div>
				{/if}

				<!-- Documents Tab -->
				{#if activeTab === 'documents'}
					<div class="page-spacing">
						<!-- Enhanced Documents Section -->
		<div class="card-standard !p-0 overflow-hidden">
			<div class="px-6 py-5 border-b border-gray-100">
				<div class="flex justify-between items-center">
					<h3 class="text-lg font-heading font-semibold text-contrast">Documents</h3>

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

			<!-- Drag and Drop Upload Zone -->
			{#if selectedFiles.length === 0}
				<div
					role="button"
					tabindex="0"
					aria-label="Upload documents by dragging and dropping here or clicking the upload button"
					class="p-8 border-2 border-dashed rounded-lg m-4 transition-colors {dragActive ? 'border-accent bg-accent/10' : 'border-gray-300 bg-gray-50'}"
					ondrop={handleDrop}
					ondragover={handleDragOver}
					ondragleave={handleDragLeave}
					onkeydown={(e) => e.key === 'Enter' && document.getElementById('file-upload-input')?.click()}
				>
					<div class="text-center">
						<svg class="mx-auto h-12 w-12 text-gray-400" stroke="currentColor" fill="none" viewBox="0 0 48 48">
							<path d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
						</svg>
						<div class="mt-4">
							<label class="cursor-pointer">
								<span class="text-accent hover:text-accent-hover font-medium">Click to upload</span>
								<span class="text-gray-600"> or drag and drop</span>
								<input
									id="file-upload-input"
									type="file"
									multiple
									accept=".pdf,.docx,.doc,.txt,.png,.jpg,.jpeg,.zip"
									onchange={handleFileInput}
									class="hidden"
								/>
							</label>
						</div>
						<p class="text-xs text-gray-500 mt-2">PDF, DOCX, DOC, TXT, PNG, JPG, ZIP up to 50MB</p>
					</div>
				</div>
			{:else}
				<!-- Selected Files List -->
				<div class="p-4 space-y-3">
					<div class="flex justify-between items-center mb-2">
						<div>
							<h4 class="text-sm font-medium text-gray-700">{selectedFiles.length} file(s) selected</h4>
							{#if duplicateFiles.size > 0}
								<p class="text-xs text-amber-600 mt-1">
									⚠️ {duplicateFiles.size} duplicate file(s) detected
								</p>
							{/if}
						</div>
						<button
							onclick={() => {
								selectedFiles = [];
								intakeFormIndex = null;
								showIntakeSelector = false;
								duplicateFiles = new Set();
							}}
							class="text-sm text-gray-600 hover:text-gray-800"
						>
							Clear all
						</button>
					</div>
					
					{#each selectedFiles as file, index}
						<div class="flex items-center justify-between p-3 rounded-lg border {duplicateFiles.has(index) ? 'bg-amber-50 border-amber-300' : 'bg-gray-50 border-gray-200'}">
							<div class="flex items-center space-x-3 flex-1 min-w-0">
								<svg class="h-8 w-8 {duplicateFiles.has(index) ? 'text-amber-500' : 'text-gray-400'}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
								</svg>
								<div class="flex-1 min-w-0">
									<p class="text-sm font-medium text-gray-900 truncate">{file.name}</p>
									<p class="text-xs {duplicateFiles.has(index) ? 'text-amber-600' : 'text-gray-500'}">
										{formatFileSize(file.size)}
										{#if duplicateFiles.has(index)}
											• Duplicate
										{/if}
									</p>
								</div>
								{#if index === intakeFormIndex}
									<span class="px-2 py-1 text-xs font-semibold rounded-full bg-accent/20 text-contrast">
										INTAKE FORM
									</span>
								{/if}
								{#if duplicateFiles.has(index)}
									<span class="px-2 py-1 text-xs font-semibold rounded-full bg-amber-100 text-amber-800">
										DUPLICATE
									</span>
								{/if}
							</div>
							<button
								onclick={() => removeSelectedFile(index)}
								class="ml-3 text-gray-400 hover:text-red-600"
								title={duplicateFiles.has(index) ? 'Remove duplicate file' : 'Remove file'}
							>
								<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
								</svg>
							</button>
						</div>
					{/each}

					<div class="flex justify-end space-x-3 pt-3">
						{#if showIntakeSelector}
							<button
								onclick={() => (showIntakeSelector = true)}
								class="inline-flex items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
							>
								Select Intake Form
							</button>
						{/if}
					<AsyncButton
						onclick={uploadSelectedFiles}
						loading={uploading}
						variant="primary"
						loadingText="Uploading..."
					>
						Upload Files
					</AsyncButton>
					</div>
				</div>
			{/if}

			{#if uploading}
				<div class="px-4 pb-4 space-y-3">
					<div class="flex items-center justify-between text-sm">
						<span class="text-gray-700 font-medium">
							Uploading file {uploadedCount + 1} of {totalUploadCount}
						</span>
						<span class="text-gray-500">{Math.round(uploadProgress)}%</span>
					</div>
					
					{#if currentUploadFile}
						<p class="text-xs text-gray-600 truncate">
							📄 {currentUploadFile}
						</p>
					{/if}
					
					<div class="w-full bg-gray-200 rounded-full h-2.5">
						<div
							class="bg-accent h-2.5 rounded-full transition-all duration-300"
							style="width: {uploadProgress}%"
						></div>
					</div>
					
					<div class="flex items-center justify-center space-x-2 text-xs text-gray-500">
						<svg class="animate-spin h-4 w-4 text-accent" fill="none" viewBox="0 0 24 24">
							<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
							<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
						</svg>
						<span>Processing and uploading files...</span>
					</div>
				</div>
			{/if}

			<!-- Uploaded Documents List -->
			{#if documents.length === 0 && selectedFiles.length === 0}
				<div class="p-8 text-center">
					<p class="text-sm text-gray-500">No documents uploaded yet.</p>
				</div>
			{:else if documents.length > 0}
				<div class="border-t border-gray-200">
					<ul class="divide-y divide-gray-200">
					{#each sortedDocuments as doc}
							<li 
								class="px-4 py-4 sm:px-6 group transition-colors {isVideoAudioFile(doc.file_name) ? 'bg-red-50 hover:bg-red-100 border-l-4 border-red-500 opacity-75' : doc.metadata?.is_intake_form ? (isCaseSummary(doc) ? 'bg-gradient-to-r from-indigo-50 to-purple-50 hover:from-indigo-100 hover:to-purple-100 border-l-[6px] border-indigo-600' : 'bg-gradient-to-r from-green-50 to-green-100 hover:from-green-100 hover:to-green-150 border-l-[6px] border-green-600') : (isCaseSummary(doc) ? 'bg-indigo-50 hover:bg-indigo-100 border-l-4 border-indigo-400' : isIntakeForm(doc) ? 'bg-yellow-50 hover:bg-yellow-100 border-l-4 border-yellow-400' : 'hover:bg-gray-50')}"
								role={doc.metadata?.is_intake_form ? 'article' : undefined}
								aria-label={isVideoAudioFile(doc.file_name) ? 'Video/audio file - not analyzed' : doc.metadata?.is_intake_form ? (isCaseSummary(doc) ? 'Primary intake - Case summary' : 'Primary intake form') : (isCaseSummary(doc) ? 'Case summary document' : isIntakeForm(doc) ? 'Intake form candidate' : undefined)}
								aria-describedby={doc.metadata?.is_intake_form ? `intake-desc-${doc.id}` : undefined}
							>
								{#if doc.metadata?.is_intake_form}
									<span id="intake-desc-${doc.id}" class="sr-only">This is the intake form for this case</span>
								{:else if doc.metadata?.is_intake_candidate}
									<span id="intake-alt-desc-${doc.id}" class="sr-only">This is an alternate intake form candidate</span>
								{/if}
								<div class="flex items-center justify-between">
									<div
										role="button"
										tabindex="0"
										onclick={() => viewDocument(doc)}
										onkeydown={(e) => e.key === 'Enter' && viewDocument(doc)}
										class="flex-1 min-w-0 flex items-center space-x-3 text-left cursor-pointer"
									>
										<div class="flex-1 min-w-0">
											<div class="flex items-center space-x-2">
												{#if isVideoAudioFile(doc.file_name)}
													<svg class="h-5 w-5 text-red-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
														<title>Video/Audio - Not Analyzed</title>
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
													</svg>
												{:else if doc.metadata?.is_intake_form && isCaseSummary(doc)}
													<svg class="h-6 w-6 text-indigo-600 shrink-0 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
														<title>Primary Intake - Case Summary</title>
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
													</svg>
												{:else if doc.metadata?.is_intake_form}
													<svg class="h-6 w-6 text-green-600 shrink-0 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
														<title>Primary Intake Form</title>
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
													</svg>
												{:else if isCaseSummary(doc)}
													<svg class="h-5 w-5 text-indigo-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
														<title>Case Summary</title>
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
													</svg>
												{:else if isIntakeForm(doc)}
													<svg class="h-5 w-5 text-yellow-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
														<title>Intake Form</title>
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
													</svg>
												{:else if doc.metadata?.clio_source}
													<svg class="h-4 w-4 text-accent shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
														<title>Imported from Clio</title>
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
													</svg>
												{/if}
												<p class="text-sm font-medium {isVideoAudioFile(doc.file_name) ? 'text-red-900 line-through' : doc.metadata?.is_intake_form ? (isCaseSummary(doc) ? 'text-indigo-900' : 'text-green-900') : (isCaseSummary(doc) ? 'text-indigo-900' : isIntakeForm(doc) ? 'text-yellow-900' : 'text-gray-900')} truncate hover:underline">
													{doc.file_name}
												</p>
												{#if isVideoAudioFile(doc.file_name)}
													<span class="px-2 py-0.5 text-xs font-bold rounded-full bg-red-600 text-white shadow-sm">
														⏭️ NOT ANALYZED
													</span>
												{:else if doc.metadata?.is_intake_form && isCaseSummary(doc)}
													<span class="px-3 py-1 text-base font-bold rounded-full bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-sm">
														✓ PRIMARY INTAKE (SUMMARY)
													</span>
												{:else if doc.metadata?.is_intake_form}
													<span class="px-3 py-1 text-base font-bold rounded-full bg-green-600 text-white shadow-sm">
														✓ PRIMARY INTAKE
													</span>
												{:else if isCaseSummary(doc)}
													<span class="px-2 py-0.5 text-sm font-semibold rounded-full bg-indigo-500 text-white">
														CASE SUMMARY
													</span>
												{:else if isIntakeForm(doc)}
													<span class="px-2 py-0.5 text-sm font-semibold rounded-full bg-yellow-500 text-white">
														INTAKE FORM
													</span>
												{/if}
												{#if shouldShowSignatureBadge(doc)}
													<span
														class="px-2 py-0.5 text-xs font-semibold rounded-full border {getDocumentSignatureBadgeClass(doc)}"
														title={`Signature status: ${getDocumentSignatureLabel(doc)}`}
													>
														{getDocumentSignatureLabel(doc)}
													</span>
												{/if}
												{#if doc.metadata?.clio_source}
													<span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-purple-100 text-purple-800">
														{doc.metadata.clio_type?.toUpperCase() || 'CLIO'}
													</span>
												{/if}
											</div>
											<p class="text-sm {isVideoAudioFile(doc.file_name) ? 'text-red-700 font-semibold' : doc.metadata?.is_intake_form ? (isCaseSummary(doc) ? 'text-indigo-600' : 'text-accent') : (isCaseSummary(doc) ? 'text-indigo-600' : isIntakeForm(doc) ? 'text-yellow-700' : 'text-gray-500')}">
												{formatFileSize(doc.file_size)} • {doc.file_type}
												{#if isVideoAudioFile(doc.file_name)}
													• Video/audio files are excluded from analysis
												{:else if doc.metadata?.is_intake_form && isCaseSummary(doc)}
													• Primary case context (preferred)
												{:else if doc.metadata?.is_intake_form}
													• Primary case context
												{:else if isCaseSummary(doc)}
													• Comprehensive case overview (recommended for primary intake)
												{:else if isIntakeForm(doc)}
													• Intake form available for selection
												{/if}
											</p>
											{#if (isCaseSummary(doc) || isIntakeForm(doc)) && !doc.metadata?.is_intake_form}
												<button
													onclick={(e) => {
														e.stopPropagation();
														promoteToIntakeForm(doc.id);
													}}
													class="mt-2 text-xs {isCaseSummary(doc) ? 'text-indigo-600 hover:text-indigo-800' : 'text-accent hover:text-accent-hover'} hover:underline font-medium"
												>
													{isCaseSummary(doc) ? '⭐ Use as Primary Intake (Recommended)' : '✓ Use as Primary Intake'}
												</button>
											{/if}
										</div>
										<span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full {getStatusColor(doc.status)}">
											{doc.status}
										</span>
									</div>
									<button
										onclick={() => (deleteConfirmDoc = doc.id)}
										aria-label="Delete document"
										class="ml-4 opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-red-600"
									>
										<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
										</svg>
									</button>
								</div>
							</li>
								{/each}
					</ul>
				</div>
			{/if}
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

						<!-- Streaming Analysis Panel -->
						{#if showStreamingPanel}
							<div class="mb-6">
								<AnalysisStreamPanel
									caseId={caseId}
									bind:this={streamingAnalysisRef}
									onComplete={handleStreamingComplete}
									onError={handleStreamingError}
								/>
							</div>
						{/if}

						<!-- Inline Progress (when analysis is running) -->
						{#if showProgressModal && currentAnalysisId}
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

<!-- Intake Form Selector Modal -->
{#if showIntakeSelector && selectedFiles.length > 0}
	<div class="modal-overlay">
		<div class="bg-white rounded-lg shadow-xl max-w-lg w-full p-6">
			<h3 class="text-lg font-heading font-semibold text-contrast mb-4">Select Intake Form</h3>
			<p class="text-sm text-gray-600 mb-4">
				{#if selectedFiles.filter(f => f.name.toLowerCase().includes('intake')).length > 1}
					Multiple files contain 'intake' in the name. Please select which is the intake form:
				{:else}
					No intake form detected. Please select which file should be used as the intake form:
				{/if}
			</p>
			
			<div class="space-y-2 mb-4">
				{#each selectedFiles as file, index}
					<label class="flex items-center p-3 border rounded-lg cursor-pointer hover:bg-gray-50 {index === intakeFormIndex ? 'border-accent bg-accent/10' : 'border-gray-200'}">
						<input
							type="radio"
							name="intake-form"
							value={index}
							checked={index === intakeFormIndex}
							onchange={() => (intakeFormIndex = index)}
							class="h-4 w-4 text-accent focus:ring-accent border-gray-300"
						/>
						<span class="ml-3 text-sm font-medium text-gray-900 truncate">{file.name}</span>
					</label>
				{/each}
				<label class="flex items-center p-3 border rounded-lg cursor-pointer hover:bg-gray-50 {intakeFormIndex === null ? 'border-accent bg-accent/10' : 'border-gray-200'}">
					<input
						type="radio"
						name="intake-form"
						value="none"
						checked={intakeFormIndex === null}
						onchange={() => (intakeFormIndex = null)}
						class="h-4 w-4 text-accent focus:ring-accent border-gray-300"
					/>
					<span class="ml-3 text-sm font-medium text-gray-900">No intake form - analyze all equally</span>
				</label>
			</div>

			<div class="flex justify-end space-x-3">
				<button
					onclick={() => (showIntakeSelector = false)}
					class="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
				>
					Cancel
				</button>
				<button
					onclick={() => selectIntakeForm(intakeFormIndex)}
					class="px-4 py-2 border border-transparent rounded-md text-sm font-medium text-white bg-accent hover:bg-accent-hover"
				>
					Confirm
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Document Delete Confirmation Modal -->
{#if deleteConfirmDoc}
	<div class="modal-overlay">
		<div class="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
			<h3 class="text-lg font-heading font-semibold text-contrast mb-4">Delete Document</h3>
			<p class="text-sm text-gray-600 mb-4">
				Are you sure you want to delete this document? This action cannot be undone.
			</p>
			<p class="text-sm font-semibold text-contrast mb-4">
				{documents.find(d => d.id === deleteConfirmDoc)?.file_name}
			</p>

			<div class="flex justify-end space-x-3">
				<button
					onclick={() => (deleteConfirmDoc = null)}
					class="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
				>
					Cancel
				</button>
				<AsyncButton
					onclick={() => deleteDocument(deleteConfirmDoc!)}
					variant="danger"
					loadingText="Deleting..."
					class="min-w-[100px]"
				>
					Delete
				</AsyncButton>
			</div>
		</div>
	</div>
{/if}

<!-- Case Delete Confirmation Modal -->
{#if deleteConfirmCase}
	<div class="modal-overlay">
		<div class="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
			<h3 class="text-lg font-heading font-semibold text-contrast mb-4">Delete Case</h3>
			<div class="text-sm text-gray-600 space-y-3 mb-4">
				<p><strong class="text-contrast">Case:</strong> {caseData?.client_name}</p>
				{#if caseData?.reference_number}
					<p><strong class="text-contrast">Reference:</strong> {caseData.reference_number}</p>
				{/if}
				<p class="text-red-600 font-semibold bg-red-50 p-3 rounded-md border border-red-100">
					⚠️ This will permanently delete the case and all {documents.length} associated document(s).
				</p>
				<p>This action cannot be undone.</p>
			</div>

			<div class="mb-4">
				<label for="delete-confirm" class="block text-sm font-semibold text-contrast mb-2">
					Type <span class="font-mono font-bold text-red-600">DELETE</span> to confirm:
				</label>
				<input
					id="delete-confirm"
					type="text"
					bind:value={deleteCaseText}
					placeholder="DELETE"
					class="input-standard focus:ring-red-500 border-gray-300"
				/>
			</div>

			<div class="flex justify-end space-x-3">
				<button
					onclick={() => {
						deleteConfirmCase = false;
						deleteCaseText = '';
					}}
					class="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
				>
					Cancel
				</button>
				<AsyncButton
					onclick={deleteCase}
					disabled={deleteCaseText !== 'DELETE'}
					variant="danger"
					loadingText="Deleting..."
					class="min-w-[120px]"
				>
					Delete Case
				</AsyncButton>
			</div>
		</div>
	</div>
{/if}

<!-- Document Viewer Modal -->
{#if viewingDocument}
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
						{#if viewingDocument.metadata?.is_intake_form}
							<svg class="h-5 w-5 text-accent shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
							</svg>
							<span class="px-2 py-0.5 text-[10px] font-bold tracking-wider rounded-full bg-accent text-white uppercase">
								Primary Intake
							</span>
						{/if}
						{#if viewingDocument.metadata?.clio_source}
							<span class="px-2 py-0.5 text-[10px] font-bold tracking-wider rounded-full bg-contrast/10 text-contrast uppercase">
								{viewingDocument.metadata.clio_type || 'CLIO'}
							</span>
						{/if}
					</div>
					<h3 class="text-xl font-heading font-bold text-contrast truncate">
						{viewingDocument.file_name}
					</h3>
					<p class="text-xs font-medium text-gray-500 mt-1">
						{formatFileSize(viewingDocument.file_size)} • {viewingDocument.file_type}
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
						fileName={viewingDocument.file_name}
						fileType={viewingDocument.file_type}
						documentId={viewingDocument.id}
						hasStoragePath={Boolean(viewingDocument.storage_path)}
						previewUrl={pdfBlobUrl}
						loading={loadingPreview}
						isPdf={isPdfDocument}
						isImage={isImageDocument}
						isTextDocument={!isPdfDocument && !isImageDocument}
						textPreview={documentViewerContent}
						onLoadPreview={() => loadDocumentBinaryPreview(viewingDocument)}
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
							signatureDetection={viewingDocument?.metadata?.signature_detection || null}
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

<!-- Intake Document Selector Modal -->
{#if showIntakeDocumentSelector}
	<div class="fixed inset-0 bg-gray-500 bg-opacity-75 flex items-center justify-center p-4 z-50">
		<div class="bg-white rounded-lg max-w-2xl w-full p-6 max-h-[80vh] overflow-y-auto">
			<div class="mb-6">
				<h3 class="text-lg font-medium text-gray-900 mb-2">Select Primary Intake Document</h3>
				<p class="text-sm text-gray-600 mb-3">
					The primary intake document provides essential case context for analysis. 
					<strong>Case summaries</strong> are preferred as they typically contain more comprehensive information than intake forms.
				</p>
				<div class="bg-blue-50 border border-blue-200 rounded-lg p-3">
					<p class="text-xs text-blue-800">
						<strong>💡 Recommendation:</strong> If you have a case summary document, select it for the most accurate analysis context.
					</p>
				</div>
			</div>
			
			<div class="space-y-2 mb-6">
				{#each [...intakeCandidates].sort((a, b) => {
					// Sort: case summaries first, then intake forms
					const aIsSummary = isCaseSummary(a);
					const bIsSummary = isCaseSummary(b);
					if (aIsSummary && !bIsSummary) return -1;
					if (!aIsSummary && bIsSummary) return 1;
					return 0;
				}) as doc}
					<label class="flex items-start p-4 border rounded-lg cursor-pointer hover:bg-gray-50 transition-colors {selectedIntakeDocId === doc.id ? (isCaseSummary(doc) ? 'border-indigo-500 bg-indigo-50' : 'border-accent bg-accent/10') : (isCaseSummary(doc) ? 'border-indigo-200 bg-indigo-50/50' : 'border-gray-200')}">
						<input
							type="radio"
							name="intake-document"
							value={doc.id}
							checked={selectedIntakeDocId === doc.id}
							onchange={() => (selectedIntakeDocId = doc.id)}
							class="mt-1 h-4 w-4 {isCaseSummary(doc) ? 'text-indigo-600 focus:ring-indigo-500' : 'text-accent focus:ring-accent'} border-gray-300"
						/>
						<div class="ml-3 flex-1 min-w-0">
							<div class="flex items-center space-x-2 mb-1 flex-wrap">
								{#if isCaseSummary(doc)}
									<svg class="h-4 w-4 text-indigo-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
									</svg>
								{:else if doc.metadata?.clio_source}
									<svg class="h-4 w-4 text-accent shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
									</svg>
								{/if}
								<p class="text-sm font-medium {isCaseSummary(doc) ? 'text-indigo-900' : 'text-gray-900'} truncate">{doc.file_name}</p>
								{#if isCaseSummary(doc)}
									<span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-indigo-500 text-white">
										⭐ CASE SUMMARY (RECOMMENDED)
									</span>
								{:else if doc.metadata?.clio_source}
									<span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-purple-100 text-purple-800">
										{doc.metadata.clio_type?.toUpperCase() || 'CLIO'}
									</span>
								{/if}
								{#if doc.metadata?.is_intake_form}
									<span class="px-2 py-0.5 text-xs font-semibold rounded-full {isCaseSummary(doc) ? 'bg-indigo-600' : 'bg-accent'} text-white">
										CURRENT PRIMARY
									</span>
								{/if}
							</div>
							<p class="text-xs {isCaseSummary(doc) ? 'text-indigo-600' : 'text-gray-500'}">{formatFileSize(doc.file_size)} • {doc.file_type}</p>
							{#if isCaseSummary(doc)}
								<p class="text-xs text-indigo-700 mt-1 font-medium">
									✓ Comprehensive case overview - best for analysis context
								</p>
							{/if}
							{#if doc.extracted_at}
								<p class="text-xs text-gray-600 mt-1 italic">
									<span class="inline-block w-2 h-2 rounded-full bg-green-500 mr-1"></span>
									Text extracted and ready
								</p>
							{:else}
								<p class="text-xs text-amber-600 mt-1 italic">
									No text extracted yet
								</p>
							{/if}
						</div>
					</label>
				{/each}
			</div>

			<div class="flex justify-end space-x-3">
				<button
					onclick={() => (showIntakeDocumentSelector = false)}
					class="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
				>
					Cancel
				</button>
			<AsyncButton
				onclick={confirmIntakeSelection}
				disabled={!selectedIntakeDocId}
				variant="primary"
				loadingText="Saving..."
			>
				{#if intakeCandidates.find(d => d.id === selectedIntakeDocId)?.metadata?.is_intake_form}
					Close
				{:else}
					Confirm Selection
				{/if}
			</AsyncButton>
			</div>
		</div>
	</div>
{/if}

<!-- Upload Failure Summary Modal -->
{#if showFailureSummary && uploadFailures.length > 0}
	<UploadFailureSummary 
		failures={uploadFailures}
		totalAttempted={selectedFiles.length}
		onClose={() => {
			showFailureSummary = false;
			selectedFiles = [];
			intakeFormIndex = null;
			showIntakeSelector = false;
			duplicateFiles = new Set();
			uploadFailures = [];
		}}
		onRetry={retryFailedUploads}
	/>
{/if}

<!-- Missing Text Warning Modal -->
{#if showMissingTextWarning}
	<div
		class="modal-overlay"
		role="dialog"
		aria-modal="true"
		tabindex="-1"
		onclick={() => showMissingTextWarning = false}
		onkeydown={(e) => { if (e.key === 'Escape') showMissingTextWarning = false; }}
	>
		<div
			class="card-standard max-w-lg w-full mx-4"
			role="presentation"
			onclick={(e) => e.stopPropagation()}
			onkeydown={(e) => e.stopPropagation()}
		>
			<h3 class="text-lg font-heading font-semibold text-contrast mb-2">Documents Missing Text</h3>
			<p class="text-sm text-gray-600 mb-4">
				{docsWithoutText.length} document{docsWithoutText.length === 1 ? '' : 's'} {docsWithoutText.length === 1 ? "doesn't" : "don't"} have extracted text and will be <strong>skipped</strong> during analysis.
			</p>
			
			<div class="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4 max-h-40 overflow-auto">
				<ul class="text-sm text-amber-800 space-y-1">
					{#each docsWithoutText as doc}
						<li class="flex items-center gap-2">
							<span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
							<span class="truncate">{doc.file_name}</span>
						</li>
					{/each}
				</ul>
			</div>

			<p class="text-xs text-gray-500 mb-4">
				Run OCR to extract text from these documents, or proceed without them.
			</p>

			<div class="flex flex-col sm:flex-row gap-3 justify-end">
				<button 
					onclick={() => showMissingTextWarning = false}
					class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
				>
					Cancel
				</button>
				<button 
					onclick={proceedWithoutMissingDocs}
					class="px-4 py-2 text-sm font-medium text-amber-700 bg-amber-100 border border-amber-300 rounded-md hover:bg-amber-200 transition-colors"
				>
					Skip These Documents
				</button>
				<button 
					onclick={runOcrOnMissingDocs}
					disabled={runningBulkOcr}
					class="px-4 py-2 text-sm font-medium text-white bg-accent rounded-md hover:bg-accent-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
				>
					{#if runningBulkOcr}
						<svg class="animate-spin h-4 w-4" viewBox="0 0 24 24">
							<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"></circle>
							<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
						</svg>
						Running OCR...
					{:else}
						Run OCR on All
					{/if}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Analysis progress is now shown inline on the Analysis tab -->
