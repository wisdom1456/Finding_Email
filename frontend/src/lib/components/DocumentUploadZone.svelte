<script lang="ts">
	/**
	 * DocumentUploadZone - Drag and drop file upload component
	 * Extracted from [id]/+page.svelte for better maintainability
	 */

	interface Props {
		accept?: string;
		maxFileSizeMB?: number;
		disabled?: boolean;
		onFilesSelected: (files: File[]) => void;
	}

	let {
		accept = '.pdf,.docx,.doc,.txt,.png,.jpg,.jpeg,.csv,.eml',
		maxFileSizeMB = 50,
		disabled = false,
		onFilesSelected
	}: Props = $props();

	let dragActive = $state(false);
	let fileInput: HTMLInputElement;

	function handleDragOver(e: DragEvent) {
		e.preventDefault();
		if (!disabled) {
			dragActive = true;
		}
	}

	function handleDragLeave(e: DragEvent) {
		e.preventDefault();
		dragActive = false;
	}

	function handleDrop(e: DragEvent) {
		e.preventDefault();
		dragActive = false;

		if (disabled) return;

		const files = e.dataTransfer?.files;
		if (files && files.length > 0) {
			processFiles(Array.from(files));
		}
	}

	function handleFileInput(e: Event) {
		const target = e.target as HTMLInputElement;
		if (target.files && target.files.length > 0) {
			processFiles(Array.from(target.files));
			// Reset input to allow selecting same file again
			target.value = '';
		}
	}

	function processFiles(files: File[]) {
		// Filter out files that are too large
		const validFiles = files.filter((file) => {
			const sizeMB = file.size / (1024 * 1024);
			if (sizeMB > maxFileSizeMB) {
				console.warn(`File ${file.name} exceeds ${maxFileSizeMB}MB limit`);
				return false;
			}
			return true;
		});

		if (validFiles.length > 0) {
			onFilesSelected(validFiles);
		}
	}

	function openFileDialog() {
		fileInput?.click();
	}
</script>

<div
	class="p-12 border-2 border-dashed rounded-xl transition-all cursor-pointer group
		{dragActive ? 'border-accent bg-accent/5 ring-1 ring-accent' : 'border-gray-200 bg-gray-50/50'}
		{disabled ? 'opacity-50 cursor-not-allowed' : 'hover:border-accent/30 hover:bg-gray-50'}"
	ondrop={handleDrop}
	ondragover={handleDragOver}
	ondragleave={handleDragLeave}
	onclick={openFileDialog}
	onkeydown={(e) => e.key === 'Enter' && openFileDialog()}
	role="button"
	tabindex="0"
>
	<div class="text-center">
		<svg
			class="mx-auto h-16 w-16 text-gray-300 group-hover:text-accent/50 transition-colors"
			stroke="currentColor"
			fill="none"
			viewBox="0 0 48 48"
		>
			<path
				d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
				stroke-width="2"
				stroke-linecap="round"
				stroke-linejoin="round"
			/>
		</svg>
		<div class="mt-6 flex flex-col items-center">
			<span class="inline-flex items-center px-6 py-3 border border-transparent text-sm font-bold rounded-md text-white bg-accent hover:bg-accent-hover transition-all shadow-sm shadow-accent/20">
				Choose Files to Upload
			</span>
			<span class="mt-3 text-sm font-medium text-gray-500">or drag and drop here</span>
			<input
				bind:this={fileInput}
				type="file"
				multiple
				{accept}
				onchange={handleFileInput}
				class="hidden"
				{disabled}
			/>
		</div>
		<p class="text-[10px] font-bold text-gray-400 mt-4 uppercase tracking-widest italic">
			Supported: PDF, DOCX, DOC, TXT, PNG, JPG, CSV, EML up to {maxFileSizeMB}MB
		</p>
	</div>
</div>


