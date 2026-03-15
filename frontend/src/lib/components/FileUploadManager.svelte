<script lang="ts">
	import { getApiUrl } from '$lib/config';
	import { getSecureSession } from '$lib/supabase';
	import { formatFileSize } from '$lib/utils/formatters';
	import { toastStore } from '$lib/stores/toastStore';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
	import UploadFailureSummary from '$lib/components/UploadFailureSummary.svelte';

	interface UploadFailure {
		fileName: string;
		reason: string;
		fileSizeMB?: number;
		errorCode: string;
		file?: File; // Keep file for retry
	}

	interface Props {
		caseId: string;
		documents: any[]; // for duplicate checking
		maxFileSizeMB?: number; // default 100
		onuploaded: () => void; // triggers loadDocuments() in parent
		onerror: (message: string) => void; // sets errorMessage in parent
	}

	let {
		caseId,
		documents,
		maxFileSizeMB = 100,
		onuploaded,
		onerror
	}: Props = $props();

	// Internal state
	let selectedFiles = $state<File[]>([]);
	let intakeFormIndex = $state<number | null>(null);
	let showIntakeSelector = $state(false);
	let dragActive = $state(false);
	let duplicateFiles = $state<Set<number>>(new Set());
	let uploading = $state(false);
	let uploadProgress = $state(0);
	let currentUploadFile = $state('');
	let uploadedCount = $state(0);
	let totalUploadCount = $state(0);
	let uploadFailures = $state<UploadFailure[]>([]);
	let showFailureSummary = $state(false);

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

			// Reload documents via parent callback
			onuploaded();

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
			const msg = error.message || 'Upload failed';
			onerror(msg);
			toastStore.error(msg);
		} finally {
			uploading = false;
			currentUploadFile = '';
		}
	}
</script>

<!-- Drag and Drop Upload Zone -->
{#if selectedFiles.length === 0}
	<div
		data-testid="upload-zone"
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
			onuploaded();
		}}
		onRetry={retryFailedUploads}
	/>
{/if}
