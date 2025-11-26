<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { supabase } from '$lib/supabase';
	import { getApiUrl } from '$lib/config';
	import ClioMatterSearch from '$lib/components/ClioMatterSearch.svelte';
	import ClioLinkedMatter from '$lib/components/ClioLinkedMatter.svelte';
	import UploadFailureSummary from '$lib/components/UploadFailureSummary.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Tabs from '$lib/components/ui/Tabs.svelte';
	import { clioStore } from '$lib/stores/clioStore';
	import { progressStore } from '$lib/stores/progressStore';
	import { Trash2, Edit, ArrowLeft } from 'lucide-svelte';
	import type { CaseData } from '$lib/types';

	let caseData = $state<CaseData | null>(null);
	let documents = $state<any[]>([]);
	let analysisStatus = $state<any>(null);
	let loading = $state(true);
	let uploading = $state(false);
	let analyzing = $state(false);
	let errorMessage = $state('');
	let uploadProgress = $state(0);
	let currentUploadFile = $state<string>('');
	let uploadedCount = $state(0);
	let totalUploadCount = $state(0);

	// Find all potential intake documents (any with "intake" in filename)
	let intakeCandidates = $derived(
		documents.filter(doc => doc.file_name.toLowerCase().includes('intake'))
	);

	// Sort documents - intake candidates first, then others
	let sortedDocuments = $derived(
		[...documents].sort((a, b) => {
			const aHasIntake = a.file_name.toLowerCase().includes('intake');
			const bHasIntake = b.file_name.toLowerCase().includes('intake');
			
			// Both have "intake" - sort by explicitly marked, then by date
			if (aHasIntake && bHasIntake) {
				const aIsMarked = a.metadata?.is_intake_form || false;
				const bIsMarked = b.metadata?.is_intake_form || false;
				if (aIsMarked && !bIsMarked) return -1;
				if (!aIsMarked && bIsMarked) return 1;
				return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
			}
			
			// Only one has "intake"
			if (aHasIntake && !bHasIntake) return -1;
			if (!aHasIntake && bHasIntake) return 1;
			
			// Neither has "intake"
			return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
		})
	);

	// Document viewer modal state
	let viewingDocument = $state<any>(null);
	let documentViewerContent = $state('');
	let pdfBlobUrl = $state<string | null>(null);
	let isPdfDocument = $derived(viewingDocument?.file_type === 'application/pdf');
	let isImageDocument = $derived(
		viewingDocument?.file_type?.startsWith('image/') || false
	);

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

	const caseId = $derived($page.params.id);
	
	// Tab state
	let activeTab = $state('overview');

	onMount(async () => {
		await loadCase();
		await loadDocuments();
		await loadAnalysisStatus();
		await loadSettings();
	});

	onDestroy(() => {
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
			const { data, error } = await supabase
				.from('cases')
				.select('*')
				.eq('id', caseId)
				.single();

			if (error) throw error;
			
			// Parse clio_matter_data if it's a string
			if (data && data.clio_matter_data) {
				if (typeof data.clio_matter_data === 'string') {
					try {
						data.clio_matter_data = JSON.parse(data.clio_matter_data);
					} catch (e) {
						console.error('Failed to parse clio_matter_data:', e);
					}
				}
			}
			
			caseData = data;
		} catch (error: any) {
			errorMessage = error.message || 'Failed to load case';
		} finally {
			loading = false;
		}
	}

	async function loadDocuments() {
		try {
			const { data, error } = await supabase
				.from('documents')
				.select('*')
				.eq('case_id', caseId)
				.order('created_at', { ascending: true });

			if (error) throw error;
			documents = data || [];
		} catch (error: any) {
			console.error('Failed to load documents:', error);
		}
	}

	async function viewDocument(doc: any) {
		viewingDocument = doc;
		documentViewerContent = '';
		
		// Clean up previous blob URL if it exists
		if (pdfBlobUrl) {
			URL.revokeObjectURL(pdfBlobUrl);
			pdfBlobUrl = null;
		}

		try {
			// Check if it's a PDF or image - need to download as blob
			const isPdf = doc.file_type === 'application/pdf';
			const isImage = doc.file_type?.startsWith('image/');

			if (isPdf || isImage) {
				// Download from storage
				const {
					data: { session }
				} = await supabase.auth.getSession();

				if (!session) {
					documentViewerContent = 'Error: Not authenticated';
					return;
				}

				const { data, error } = await supabase.storage
					.from('documents')
					.download(doc.storage_path);

				if (error) throw error;

				// Create blob URL for PDF or image
				pdfBlobUrl = URL.createObjectURL(data);
				return;
			}

			// For text files, check if document has extracted_text
			if (doc.extracted_text) {
				documentViewerContent = doc.extracted_text;
				return;
			}

			// Otherwise, try to download and display as text
			const {
				data: { session }
			} = await supabase.auth.getSession();

			if (!session) {
				documentViewerContent = 'Error: Not authenticated';
				return;
			}

			// Download from storage
			const { data, error } = await supabase.storage
				.from('documents')
				.download(doc.storage_path);

			if (error) throw error;

			// Try to read as text
			const text = await data.text();
			documentViewerContent = text;
		} catch (error: any) {
			console.error('Failed to load document:', error);
			documentViewerContent = `Unable to display this document. File type: ${doc.file_type}`;
		}
	}

	function closeDocumentViewer() {
		// Clean up blob URL to prevent memory leaks
		if (pdfBlobUrl) {
			URL.revokeObjectURL(pdfBlobUrl);
			pdfBlobUrl = null;
		}
		viewingDocument = null;
		documentViewerContent = '';
	}

	async function confirmIntakeSelection() {
		if (!selectedIntakeDocId) {
			alert('Please select an intake document');
			return;
		}

		try {
			// Update the selected document's metadata to mark it as intake form
			const { error } = await supabase
				.from('documents')
				.update({
					metadata: { ...documents.find(d => d.id === selectedIntakeDocId)?.metadata, is_intake_form: true }
				})
				.eq('id', selectedIntakeDocId);

			if (error) throw error;

			// Reload documents to reflect the change
			await loadDocuments();

			// Close modal
			showIntakeDocumentSelector = false;

			// Now start analysis
			await startAnalysis();
		} catch (error: any) {
			alert('Failed to mark intake document: ' + error.message);
		}
	}

	async function loadAnalysisStatus() {
		try {
			const { data, error } = await supabase
				.from('analysis_results')
				.select('*')
				.eq('case_id', caseId)
				.order('created_at', { ascending: false })
				.limit(1);

			if (error) {
				console.error('Failed to load analysis status:', error);
				return;
			}
			
			analysisStatus = data && data.length > 0 ? data[0] : null;
		} catch (error: any) {
			console.error('Failed to load analysis status:', error);
		}
	}

	// Enhanced file selection with drag-and-drop
	function handleFilesSelected(files: FileList | File[]) {
		// Filter out video and audio files
		const videoAudioExtensions = [
			'.mov', '.mp4', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v',  // Video
			'.mp3', '.wav', '.aac', '.flac', '.m4a', '.ogg', '.wma', '.aiff',  // Audio
		];
		
		const validFiles = Array.from(files).filter(file => {
			const isVideoAudio = videoAudioExtensions.some(ext => 
				file.name.toLowerCase().endsWith(ext)
			);
			if (isVideoAudio) {
				console.log(`Skipping video/audio file: ${file.name}`);
			}
			return !isVideoAudio;
		});
		
		// Show warning if any files were filtered out
		if (validFiles.length < files.length) {
			const skippedCount = files.length - validFiles.length;
			errorMessage = `⏭️ Skipped ${skippedCount} video/audio file(s). Only documents and images are supported.`;
			setTimeout(() => { 
				if (errorMessage.includes('Skipped')) errorMessage = ''; 
			}, 5000);
		}
		
		selectedFiles = validFiles;
		detectDuplicates();
		autoDetectIntakeForms();
	}

	function detectDuplicates() {
		const duplicates = new Set<number>();
		
		// Check against already uploaded documents
		selectedFiles.forEach((file, index) => {
			const isDuplicate = documents.some(
				(doc) => doc.file_name === file.name && doc.file_size === file.size
			);
			if (isDuplicate) {
				duplicates.add(index);
			}
		});

		// Check for duplicates within selected files
		selectedFiles.forEach((file, index) => {
			const hasDuplicateInSelection = selectedFiles.some(
				(otherFile, otherIndex) =>
					index !== otherIndex &&
					file.name === otherFile.name &&
					file.size === otherFile.size
			);
			if (hasDuplicateInSelection) {
				duplicates.add(index);
			}
		});

		duplicateFiles = duplicates;
	}

	function autoDetectIntakeForms() {
		const matches = selectedFiles
			.map((f, i) => ({ file: f, index: i }))
			.filter(({ file }) => file.name.toLowerCase().includes('intake'));
		
		if (matches.length === 0) {
			intakeFormIndex = null;
			showIntakeSelector = true; // User must select
		} else if (matches.length === 1) {
			intakeFormIndex = matches[0].index;
			showIntakeSelector = false;
		} else {
			showIntakeSelector = true; // Multiple matches, user picks
		}
	}

	function handleFileInput(event: Event) {
		const target = event.target as HTMLInputElement;
		if (target.files && target.files.length > 0) {
			handleFilesSelected(target.files);
		}
	}

	function handleDrop(event: DragEvent) {
		event.preventDefault();
		dragActive = false;
		if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
			handleFilesSelected(event.dataTransfer.files);
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

	function removeSelectedFile(index: number) {
		selectedFiles = selectedFiles.filter((_, i) => i !== index);
		if (intakeFormIndex === index) {
			intakeFormIndex = null;
		} else if (intakeFormIndex !== null && intakeFormIndex > index) {
			intakeFormIndex--;
		}
		if (selectedFiles.length > 0) {
			detectDuplicates();
			autoDetectIntakeForms();
		} else {
			duplicateFiles = new Set();
		}
	}

	function selectIntakeForm(index: number | null) {
		intakeFormIndex = index;
		showIntakeSelector = false;
	}

	async function uploadSelectedFiles() {
		if (selectedFiles.length === 0) return;

		// Filter out duplicate files
		const filesToUpload = selectedFiles.filter((_, index) => !duplicateFiles.has(index));
		
		if (filesToUpload.length === 0) {
			errorMessage = 'All selected files are duplicates. Please select different files.';
			return;
		}

		uploading = true;
		errorMessage = '';
		uploadFailures = [];
		uploadedCount = 0;
		totalUploadCount = filesToUpload.length;
		let skippedCount = duplicateFiles.size;
		let successCount = 0;

		try {
			const {
				data: { session }
			} = await supabase.auth.getSession();

			if (!session) throw new Error('Not authenticated');

			// Upload each non-duplicate file
			for (let i = 0; i < filesToUpload.length; i++) {
				const file = filesToUpload[i];
				currentUploadFile = file.name;
				uploadedCount = i;
				const originalIndex = selectedFiles.indexOf(file);

				try {
					// Pre-upload validation
					const validation = validateFileBeforeUpload(file);
					if (!validation.valid) {
						uploadFailures.push({
							fileName: file.name,
							reason: validation.error!,
							errorCode: validation.errorCode || 'UNKNOWN',
							fileSizeMB: file.size / (1024 * 1024),
							file: file
						});
						continue; // Skip this file, continue with others
					}

					// Upload file
					const formData = new FormData();
					formData.append('file', file);
				formData.append('case_id', caseId);
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
							reason: errorData.detail || `Failed to upload ${file.name}`,
							errorCode: categorizeError(errorData.detail, errorData.code),
							fileSizeMB: file.size / (1024 * 1024),
							file: file
						});
					} else {
						successCount++;
					}
				} catch (error: any) {
					uploadFailures.push({
						fileName: file.name,
						reason: error.message || 'Unknown error',
						errorCode: 'UNKNOWN',
						fileSizeMB: file.size / (1024 * 1024),
						file: file
					});
				}

				uploadProgress = ((i + 1) / filesToUpload.length) * 100;
			}

			// Reload documents
			await loadDocuments();

			// Show summary
			if (uploadFailures.length > 0) {
				showFailureSummary = true;
				if (successCount > 0) {
					errorMessage = `⚠️ Uploaded ${successCount} file(s), ${uploadFailures.length} failed. Click to see details.`;
				}
			} else {
				// All successful
				selectedFiles = [];
				intakeFormIndex = null;
				showIntakeSelector = false;
				duplicateFiles = new Set();
				
				let message = `✅ Successfully uploaded ${successCount} file(s)`;
				if (skippedCount > 0) {
					message += `. Skipped ${skippedCount} duplicate(s)`;
				}
				errorMessage = message;
				setTimeout(() => { errorMessage = ''; }, 5000);
			}
		} catch (error: any) {
			errorMessage = error.message || 'Failed to upload files';
		} finally {
			uploading = false;
			uploadProgress = 0;
			currentUploadFile = '';
			uploadedCount = 0;
			totalUploadCount = 0;
		}
	}

	async function retryFailedUploads() {
		if (uploadFailures.length === 0) return;

		// Retry only the failed files
		const filesToRetry = uploadFailures
			.filter(f => f.file)
			.map(f => f.file!);

		if (filesToRetry.length === 0) return;

		// Reset the selected files to only failed ones
		selectedFiles = filesToRetry;
		
		// Close the summary modal and retry
		showFailureSummary = false;
		await uploadSelectedFiles();
	}

	async function promoteToIntakeForm(docId: string) {
		try {
			const {
				data: { session }
			} = await supabase.auth.getSession();

			if (!session) {
				throw new Error('Not authenticated');
			}

			const apiUrl = getApiUrl();
			
			// Call backend to update intake form designation
			const response = await fetch(`${apiUrl}/api/cases/${caseId}/set-intake-form`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`
				},
				body: JSON.stringify({ document_id: docId })
			});

			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || 'Failed to update intake form');
			}

			// Reload documents to reflect changes
			await loadDocuments();
			errorMessage = '';
		} catch (error: any) {
			console.error('Error promoting to intake form:', error);
			errorMessage = error.message || 'Failed to update intake form';
		}
	}

	async function deleteDocument(docId: string) {
		try {
			const {
				data: { session }
			} = await supabase.auth.getSession();

		if (!session) throw new Error('Not authenticated');

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

	async function deleteCase() {
		if (deleteCaseText !== 'DELETE') return;

		try {
			const {
				data: { session }
			} = await supabase.auth.getSession();

			if (!session) {
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
		editClientName = caseData.client_name;
		editReferenceNumber = caseData.reference_number || '';
		editDescription = caseData.description || '';
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
			const {
				data: { session }
			} = await supabase.auth.getSession();

		if (!session) throw new Error('Not authenticated');

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

	async function startAnalysis() {
		// Check for multiple intake candidates before starting
		if (intakeCandidates.length > 1) {
			// Find if one is already marked
			const markedIntake = intakeCandidates.find(doc => doc.metadata?.is_intake_form);
			if (!markedIntake) {
				// No document is marked, user must choose
				showIntakeDocumentSelector = true;
				return;
			}
			// If one is already marked, proceed with that one
		}

		analyzing = true;
		errorMessage = '';

		try {
			const {
				data: { session }
			} = await supabase.auth.getSession();

		if (!session) throw new Error('Not authenticated');

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

			const analysisData = await response.json();
			const analysisId = analysisData.id;

			// Reload analysis status
		await loadAnalysisStatus();

		// Try SSE first, fall back to polling if not supported
		const sseUrl = `${getApiUrl()}/api/progress/analysis/${analysisId}?token=${session.access_token}`;
			const sseSupported = progressStore.isSupported();

			if (sseSupported) {
				const connected = progressStore.connect(sseUrl, async () => {
					// On completion, reload data
					await loadAnalysisStatus();
					await loadCase();
					analyzing = false;
				});

				if (!connected) {
					// SSE failed, fall back to polling
					startPolling();
				}
			} else {
				// SSE not supported, use polling
				startPolling();
			}

			function startPolling() {
			const pollInterval = setInterval(async () => {
				await loadAnalysisStatus();
				await loadCase();

				if (analysisStatus && analysisStatus.status !== 'processing' && analysisStatus.status !== 'pending') {
					clearInterval(pollInterval);
					analyzing = false;
				}
			}, 5000);
			}
		} catch (error: any) {
			errorMessage = error.message || 'Failed to start analysis';
			analyzing = false;
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

<div class="space-y-6">
	{#if loading}
		<div class="p-8 text-center">
			<div class="inline-block animate-spin rounded-full h-8 w-8 border-2 border-accent border-t-transparent"></div>
		</div>
	{:else if !caseData}
		<div class="p-8 text-center">
			<p class="text-sm text-red-600">Case not found</p>
		</div>
	{:else}
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
			title={caseData.client_name}
			subtitle={caseData.reference_number}
			breadcrumbs={[
				{ label: 'Dashboard', href: '/app' },
				{ label: 'Cases', href: '/app/cases' },
				{ label: caseData.client_name }
			]}
		>
			{#snippet children()}
				<div class="flex items-center space-x-3">
					<span class="px-3 py-1 inline-flex text-sm leading-5 font-semibold rounded-full {getStatusColor(caseData.status)}">
						{caseData.status}
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
				{ id: 'analysis', label: 'Analysis' }
			]}
			bind:activeTab
		>
			{#snippet children()}
				<!-- Overview Tab -->
				{#if activeTab === 'overview'}
					<div class="space-y-6">
						<!-- Case Info -->
						<div class="bg-white shadow rounded-lg p-6">
							<div class="flex justify-between items-center mb-4">
								<h3 class="text-lg font-medium text-gray-900">Case Details</h3>
							</div>

			{#if editingCase}
				<!-- Edit Form -->
				<form onsubmit={(e) => { e.preventDefault(); saveCase(); }} class="space-y-4">
					<div>
						<label for="edit-client-name" class="block text-sm font-medium text-gray-700">
							Client Name <span class="text-red-500">*</span>
						</label>
						<input
							id="edit-client-name"
							type="text"
							bind:value={editClientName}
							required
							class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-accent focus:border-blue-500 sm:text-sm"
						/>
					</div>

					<div>
						<label for="edit-reference-number" class="block text-sm font-medium text-gray-700">
							Reference Number
						</label>
						<input
							id="edit-reference-number"
							type="text"
							bind:value={editReferenceNumber}
							class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-accent focus:border-blue-500 sm:text-sm"
						/>
					</div>

					<div>
						<label for="edit-description" class="block text-sm font-medium text-gray-700">
							Description
						</label>
						<textarea
							id="edit-description"
							bind:value={editDescription}
							rows="3"
							class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-accent focus:border-blue-500 sm:text-sm"
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
						<button
							type="submit"
							disabled={savingCase || !editClientName.trim()}
							class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-accent hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent disabled:opacity-50 disabled:cursor-not-allowed"
						>
							{savingCase ? 'Saving...' : 'Save Changes'}
						</button>
					</div>
				</form>
			{:else}
				<!-- View Mode -->
				<dl class="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2">
					<div>
						<dt class="text-sm font-medium text-gray-500">Client Name</dt>
						<dd class="mt-1 text-sm text-gray-900">{caseData.client_name}</dd>
					</div>
					{#if caseData.reference_number}
						<div>
							<dt class="text-sm font-medium text-gray-500">Reference Number</dt>
							<dd class="mt-1 text-sm text-gray-900">{caseData.reference_number}</dd>
						</div>
					{/if}
					<div>
						<dt class="text-sm font-medium text-gray-500">Created</dt>
						<dd class="mt-1 text-sm text-gray-900">{formatDate(caseData.created_at)}</dd>
					</div>
					<div>
						<dt class="text-sm font-medium text-gray-500">Last Updated</dt>
						<dd class="mt-1 text-sm text-gray-900">{formatDate(caseData.updated_at)}</dd>
					</div>
					{#if caseData.description}
						<div class="sm:col-span-2">
							<dt class="text-sm font-medium text-gray-500">Description</dt>
							<dd class="mt-1 text-sm text-gray-900">{caseData.description}</dd>
						</div>
					{/if}
				</dl>
					{/if}
				</div>

				<!-- Practice Area Guidance -->
				<details class="bg-blue-50 border border-blue-200 rounded-lg">
			<summary class="px-4 py-3 cursor-pointer text-sm font-medium text-blue-900 hover:bg-blue-100">
				ℹ️ Supported Practice Areas (Florida law only)
			</summary>
			<div class="px-4 pb-4 text-sm text-gray-700 space-y-3">
				<p class="font-medium text-red-700">
					This application is optimized for Florida civil litigation matters only. Federal claims and non-Florida jurisdictions are not currently supported.
				</p>

				<div>
					<h4 class="font-semibold text-green-800 mb-2">✅ Covered Practice Areas:</h4>
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
						<li><strong>4. Selective Personal Injury</strong>
							<ul class="ml-4 mt-1 space-y-1 text-xs">
								<li>• Motorcycle accidents (Ch. 316 traffic law)</li>
								<li>• Limited medical malpractice matters (Ch. 766)</li>
							</ul>
						</li>
					</ul>
				</div>

				<div>
					<h4 class="font-semibold text-red-800 mb-2">⚠️ Not Supported:</h4>
					<ul class="ml-4 space-y-1 text-xs">
						<li>• Federal claims or federal court matters</li>
						<li>• Criminal law</li>
						<li>• Immigration law</li>
						<li>• Bankruptcy (federal jurisdiction)</li>
						<li>• Patent/trademark law (federal jurisdiction)</li>
						<li>• Out-of-state matters</li>
					</ul>
				</div>

				<p class="text-xs italic text-gray-600 mt-3">
					If your case involves federal law or multi-jurisdiction issues, please consult with the attorney before proceeding.
					</p>
				</div>
			</details>

					<!-- Clio Matter Import (only show if connected) -->
					{#if $clioStore.connected}
						<div class="bg-white shadow rounded-lg p-6">
			<h3 class="text-lg font-medium text-gray-900 mb-4">
				{caseData?.clio_matter_id ? 'Clio Matter' : 'Import from Clio'}
			</h3>

			{#if caseData?.clio_matter_id && caseData?.clio_matter_data}
				<!-- Show linked matter display -->
				<ClioLinkedMatter
					caseId={caseId}
					matterData={caseData.clio_matter_data}
					caseData={caseData}
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
					caseId={caseId}
					onMatterSelected={async () => {
						await loadCase();
						await loadDocuments();
					}}
					/>
				{/if}
			</div>
		{/if}
					</div>
				{/if}

				<!-- Documents Tab -->
				{#if activeTab === 'documents'}
					<div class="space-y-6">
						<!-- Enhanced Documents Section -->
		<div class="bg-white shadow rounded-lg">
			<div class="px-4 py-5 sm:px-6 border-b border-gray-200">
				<h3 class="text-lg leading-6 font-medium text-gray-900">Documents</h3>
			</div>

			<!-- Drag and Drop Upload Zone -->
			{#if selectedFiles.length === 0}
				<div
					class="p-8 border-2 border-dashed rounded-lg m-4 transition-colors {dragActive ? 'border-accent bg-accent/10' : 'border-gray-300 bg-gray-50'}"
					ondrop={handleDrop}
					ondragover={handleDragOver}
					ondragleave={handleDragLeave}
				>
					<div class="text-center">
						<svg class="mx-auto h-12 w-12 text-gray-400" stroke="currentColor" fill="none" viewBox="0 0 48 48">
							<path d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
						</svg>
						<div class="mt-4">
							<label class="cursor-pointer">
								<span class="text-accent hover:text-blue-500 font-medium">Click to upload</span>
								<span class="text-gray-600"> or drag and drop</span>
								<input
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
									<span class="px-2 py-1 text-xs font-semibold rounded-full bg-blue-100 text-blue-800">
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
						<button
							onclick={uploadSelectedFiles}
							disabled={uploading}
							class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed"
						>
							{uploading ? 'Uploading...' : 'Upload Files'}
						</button>
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
								class="px-4 py-4 sm:px-6 group transition-colors {isVideoAudioFile(doc.file_name) ? 'bg-red-50 hover:bg-red-100 border-l-4 border-red-500 opacity-75' : doc.metadata?.is_intake_form ? 'bg-gradient-to-r from-green-50 to-green-100 hover:from-green-100 hover:to-green-150 border-l-[6px] border-green-600' : doc.metadata?.is_intake_candidate ? 'bg-yellow-50 hover:bg-yellow-100 border-l-4 border-yellow-400' : 'hover:bg-gray-50'}"
								role={doc.metadata?.is_intake_form ? 'article' : undefined}
								aria-label={isVideoAudioFile(doc.file_name) ? 'Video/audio file - not analyzed' : doc.metadata?.is_intake_form ? 'Intake form document' : doc.metadata?.is_intake_candidate ? 'Alternate intake form candidate' : undefined}
								aria-describedby={doc.metadata?.is_intake_form ? `intake-desc-${doc.id}` : undefined}
							>
								{#if doc.metadata?.is_intake_form}
									<span id="intake-desc-${doc.id}" class="sr-only">This is the intake form for this case</span>
								{:else if doc.metadata?.is_intake_candidate}
									<span id="intake-alt-desc-${doc.id}" class="sr-only">This is an alternate intake form candidate</span>
								{/if}
								<div class="flex items-center justify-between">
									<button
										onclick={() => viewDocument(doc)}
										class="flex-1 min-w-0 flex items-center space-x-3 text-left"
									>
										<div class="flex-1 min-w-0">
											<div class="flex items-center space-x-2">
												{#if isVideoAudioFile(doc.file_name)}
													<svg class="h-5 w-5 text-red-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" title="Video/Audio - Not Analyzed" aria-hidden="true">
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
													</svg>
												{:else if doc.metadata?.is_intake_form}
													<svg class="h-6 w-6 text-green-600 flex-shrink-0 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor" title="Primary Intake Form" aria-hidden="true">
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
													</svg>
												{:else if doc.metadata?.is_intake_candidate}
													<svg class="h-5 w-5 text-yellow-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" title="Alternate Intake Form" aria-hidden="true">
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
													</svg>
												{:else if doc.metadata?.clio_source}
													<svg class="h-4 w-4 text-accent flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" title="Imported from Clio">
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
													</svg>
												{/if}
												<p class="text-sm font-medium {isVideoAudioFile(doc.file_name) ? 'text-red-900 line-through' : doc.metadata?.is_intake_form ? 'text-green-900' : doc.metadata?.is_intake_candidate ? 'text-yellow-900' : 'text-gray-900'} truncate hover:underline">
													{doc.file_name}
												</p>
												{#if isVideoAudioFile(doc.file_name)}
													<span class="px-2 py-0.5 text-xs font-bold rounded-full bg-red-600 text-white shadow-sm">
														⏭️ NOT ANALYZED
													</span>
												{:else if doc.metadata?.is_intake_form}
													<span class="px-3 py-1 text-base font-bold rounded-full bg-green-600 text-white shadow-sm">
														✓ PRIMARY INTAKE
													</span>
												{:else if doc.metadata?.is_intake_candidate}
													<span class="px-2 py-0.5 text-sm font-semibold rounded-full bg-yellow-500 text-white">
														ALTERNATE INTAKE
													</span>
												{/if}
												{#if doc.metadata?.clio_source}
													<span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-purple-100 text-purple-800">
														{doc.metadata.clio_type?.toUpperCase() || 'CLIO'}
													</span>
												{/if}
											</div>
											<p class="text-sm {isVideoAudioFile(doc.file_name) ? 'text-red-700 font-semibold' : doc.metadata?.is_intake_form ? 'text-blue-700' : doc.metadata?.is_intake_candidate ? 'text-yellow-700' : 'text-gray-500'}">
												{formatFileSize(doc.file_size)} • {doc.file_type}
												{#if isVideoAudioFile(doc.file_name)}
													• Video/audio files are excluded from analysis
												{:else if doc.metadata?.is_intake_form}
													• Click to view
												{:else if doc.metadata?.is_intake_candidate}
													• Alternate intake form
												{/if}
											</p>
											{#if doc.metadata?.is_intake_candidate}
												<button
													onclick={(e) => {
														e.stopPropagation();
														promoteToIntakeForm(doc.id);
													}}
													class="mt-2 text-xs text-accent hover:text-blue-800 hover:underline font-medium"
												>
													✓ Use as Primary Intake
												</button>
											{/if}
										</div>
										<span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full {getStatusColor(doc.status)}">
											{doc.status}
										</span>
									</button>
									<button
										onclick={() => (deleteConfirmDoc = doc.id)}
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

				<!-- Analysis Tab -->
				{#if activeTab === 'analysis'}
					<div class="space-y-6">
						<!-- Analysis Section -->
						<div class="bg-white shadow rounded-lg p-6">
							<h3 class="text-lg font-medium text-gray-900 mb-4">Analysis</h3>

			{#if !analysisStatus && documents.length > 0}
				<button
					onclick={startAnalysis}
					disabled={analyzing}
					class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-accent hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent disabled:opacity-50 disabled:cursor-not-allowed"
				>
					{analyzing ? 'Starting Analysis...' : 'Start Analysis'}
				</button>
			{:else if !analysisStatus}
				<p class="text-sm text-gray-500">Upload documents to start analysis.</p>
			{:else}
				<div class="space-y-4">
					<div>
						<dt class="text-sm font-medium text-gray-500">Status</dt>
						<dd class="mt-1">
							<span class="px-3 py-1 inline-flex text-sm leading-5 font-semibold rounded-full {getStatusColor(analysisStatus.status)}">
								{analysisStatus.status}
							</span>
						</dd>
					</div>

					{#if analysisStatus.status === 'processing'}
						<div class="space-y-3">
						<div class="flex items-center">
							<div class="inline-block animate-spin rounded-full h-5 w-5 border-b-2 border-accent mr-2"></div>
								<span class="text-sm text-gray-600">
									{$progressStore.message || 'Processing documents...'}
								</span>
							</div>
							
							{#if $progressStore.percent > 0}
								<div class="w-full bg-gray-200 rounded-full h-2">
									<div 
										class="bg-accent h-2 rounded-full transition-all duration-300"
										style="width: {$progressStore.percent}%"
									></div>
								</div>
								<p class="text-xs text-gray-500">{$progressStore.percent}% complete</p>
							{/if}
							
							{#if $progressStore.sub_step}
								<p class="text-xs text-gray-500 italic">{$progressStore.sub_step}</p>
							{/if}
							
							{#if $progressStore.current_doc}
								<p class="text-xs text-gray-500">
									Processing document {$progressStore.current_doc.index}/{$progressStore.current_doc.total}: 
									{$progressStore.current_doc.name}
								</p>
							{/if}
						</div>
					{/if}

					{#if analysisStatus.status === 'completed' && analysisStatus.result}
						<div class="flex items-center space-x-3">
							<a
								href="/app/cases/{caseId}/results"
								data-sveltekit-preload-data="off"
								class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-accent hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent"
							>
								View Results
							</a>
							<button
								onclick={startAnalysis}
								disabled={analyzing}
								class="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent disabled:opacity-50 disabled:cursor-not-allowed"
								title="Re-run analysis with current documents"
							>
								<svg class="h-4 w-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
								</svg>
								{analyzing ? 'Re-running...' : 'Re-run Analysis'}
							</button>
						</div>
					{/if}

					{#if analysisStatus.status === 'error'}
						<div>
							<button
								onclick={startAnalysis}
								disabled={analyzing}
								class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-accent hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent disabled:opacity-50 disabled:cursor-not-allowed"
							>
								<svg class="h-4 w-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
								</svg>
								{analyzing ? 'Retrying...' : 'Retry Analysis'}
							</button>
						</div>
					{/if}

							{#if analysisStatus.error}
								<div class="rounded-md bg-red-50 p-4">
									<p class="text-sm text-red-800">{analysisStatus.error}</p>
								</div>
							{/if}
						</div>
					{/if}
				</div>
					</div>
				{/if}
			{/snippet}
		</Tabs>
	{/if}
</div>

<!-- Intake Form Selector Modal -->
{#if showIntakeSelector && selectedFiles.length > 0}
	<div class="fixed inset-0 bg-gray-500 bg-opacity-75 flex items-center justify-center p-4 z-50">
		<div class="bg-white rounded-lg max-w-lg w-full p-6">
			<h3 class="text-lg font-medium text-gray-900 mb-4">Select Intake Form</h3>
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
	<div class="fixed inset-0 bg-gray-500 bg-opacity-75 flex items-center justify-center p-4 z-50">
		<div class="bg-white rounded-lg max-w-md w-full p-6">
			<h3 class="text-lg font-medium text-gray-900 mb-4">Delete Document</h3>
			<p class="text-sm text-gray-600 mb-4">
				Are you sure you want to delete this document? This action cannot be undone.
			</p>
			<p class="text-sm font-medium text-gray-900 mb-4">
				{documents.find(d => d.id === deleteConfirmDoc)?.file_name}
			</p>

			<div class="flex justify-end space-x-3">
				<button
					onclick={() => (deleteConfirmDoc = null)}
					class="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
				>
					Cancel
				</button>
				<button
					onclick={() => deleteDocument(deleteConfirmDoc!)}
					class="px-4 py-2 border border-transparent rounded-md text-sm font-medium text-white bg-red-600 hover:bg-red-700"
				>
					Delete
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Case Delete Confirmation Modal -->
{#if deleteConfirmCase}
	<div class="fixed inset-0 bg-gray-500 bg-opacity-75 flex items-center justify-center p-4 z-50">
		<div class="bg-white rounded-lg max-w-md w-full p-6">
			<h3 class="text-lg font-medium text-gray-900 mb-4">Delete Case</h3>
			<div class="text-sm text-gray-600 space-y-3 mb-4">
				<p><strong>Case:</strong> {caseData.client_name}</p>
				{#if caseData.reference_number}
					<p><strong>Reference:</strong> {caseData.reference_number}</p>
				{/if}
				<p class="text-red-600 font-medium">
					⚠️ This will permanently delete the case and all {documents.length} associated document(s).
				</p>
				<p>This action cannot be undone.</p>
			</div>

			<div class="mb-4">
				<label for="delete-confirm" class="block text-sm font-medium text-gray-700 mb-2">
					Type <span class="font-mono font-bold">DELETE</span> to confirm:
				</label>
				<input
					id="delete-confirm"
					type="text"
					bind:value={deleteCaseText}
					placeholder="DELETE"
					class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500"
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
				<button
					onclick={deleteCase}
					disabled={deleteCaseText !== 'DELETE'}
					class="px-4 py-2 border border-transparent rounded-md text-sm font-medium text-white bg-red-600 hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
				>
					Delete Case
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Document Viewer Modal -->
{#if viewingDocument}
	<div
		class="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50 flex items-center justify-center p-4"
		onclick={closeDocumentViewer}
	>
		<div
			class="relative bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] flex flex-col"
			onclick={(e) => e.stopPropagation()}
		>
			<!-- Header -->
			<div class="flex items-start justify-between p-6 border-b border-gray-200">
				<div class="flex-1 min-w-0">
					<div class="flex items-center space-x-2 mb-2">
						{#if viewingDocument.metadata?.is_intake_form}
							<svg class="h-5 w-5 text-accent flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
							</svg>
							<span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-accent text-white">
								INTAKE FORM
							</span>
						{/if}
						{#if viewingDocument.metadata?.clio_source}
							<span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-purple-100 text-purple-800">
								{viewingDocument.metadata.clio_type?.toUpperCase() || 'CLIO'}
							</span>
						{/if}
					</div>
					<h3 class="text-lg font-medium text-gray-900 truncate">
						{viewingDocument.file_name}
					</h3>
					<p class="text-sm text-gray-500 mt-1">
						{formatFileSize(viewingDocument.file_size)} • {viewingDocument.file_type}
					</p>
				</div>
				<button
					onclick={closeDocumentViewer}
					class="ml-4 text-gray-400 hover:text-gray-500 transition-colors"
				>
					<span class="sr-only">Close</span>
					<svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>

			<!-- Content -->
			<div class="flex-1 overflow-y-auto p-6">
				{#if isPdfDocument && pdfBlobUrl}
					<!-- PDF Viewer using browser's native PDF renderer -->
					<iframe
						src={pdfBlobUrl}
						class="w-full h-[600px] border border-gray-300 rounded-lg"
						title="PDF Viewer"
					></iframe>
				{:else if isImageDocument && pdfBlobUrl}
					<!-- Image Viewer -->
					<div class="flex items-center justify-center">
						<img
							src={pdfBlobUrl}
							alt={viewingDocument.file_name}
							class="max-w-full h-auto rounded-lg shadow-lg"
						/>
					</div>
				{:else if documentViewerContent}
					<!-- Text Content Viewer -->
					<pre class="whitespace-pre-wrap font-mono text-sm text-gray-800 bg-gray-50 p-4 rounded-lg">{documentViewerContent}</pre>
				{:else}
					<!-- Loading State -->
					<div class="flex items-center justify-center h-64">
						<div class="text-center">
							<svg class="mx-auto h-12 w-12 text-gray-400 animate-spin" fill="none" viewBox="0 0 24 24">
								<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
								<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
							</svg>
							<p class="mt-2 text-sm text-gray-500">Loading document...</p>
						</div>
					</div>
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
				<h3 class="text-lg font-medium text-gray-900 mb-2">Select Intake Document</h3>
				<p class="text-sm text-gray-600">
					Multiple documents contain "intake" in their filename. Please select which document is the actual intake form.
				</p>
			</div>
			
			<div class="space-y-2 mb-6">
				{#each intakeCandidates as doc}
					<label class="flex items-start p-4 border rounded-lg cursor-pointer hover:bg-gray-50 transition-colors {selectedIntakeDocId === doc.id ? 'border-accent bg-accent/10' : 'border-gray-200'}">
						<input
							type="radio"
							name="intake-document"
							value={doc.id}
							checked={selectedIntakeDocId === doc.id}
							onchange={() => (selectedIntakeDocId = doc.id)}
							class="mt-1 h-4 w-4 text-accent focus:ring-accent border-gray-300"
						/>
						<div class="ml-3 flex-1 min-w-0">
							<div class="flex items-center space-x-2 mb-1">
								{#if doc.metadata?.clio_source}
									<svg class="h-4 w-4 text-accent flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
									</svg>
								{/if}
								<p class="text-sm font-medium text-gray-900 truncate">{doc.file_name}</p>
								{#if doc.metadata?.clio_source}
									<span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-purple-100 text-purple-800">
										{doc.metadata.clio_type?.toUpperCase() || 'CLIO'}
									</span>
								{/if}
								{#if doc.metadata?.is_intake_form}
									<span class="px-2 py-0.5 text-xs font-semibold rounded-full bg-blue-100 text-blue-800">
										CURRENT
									</span>
								{/if}
							</div>
							<p class="text-xs text-gray-500">{formatFileSize(doc.file_size)} • {doc.file_type}</p>
							{#if doc.extracted_text}
								<p class="text-xs text-gray-600 mt-1 line-clamp-2">{doc.extracted_text.substring(0, 150)}...</p>
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
				<button
					onclick={confirmIntakeSelection}
					disabled={!selectedIntakeDocId}
					class="px-4 py-2 border border-transparent rounded-md text-sm font-medium text-white bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed"
				>
					Confirm & Start Analysis
				</button>
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
