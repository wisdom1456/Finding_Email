<script lang="ts">
	interface UploadFailure {
		fileName: string;
		reason: string;
		fileSizeMB?: number;
		errorCode: string;
		file?: File;
	}

	let {
		failures = [],
		totalAttempted = 0,
		onClose,
		onRetry
	}: {
		failures: UploadFailure[];
		totalAttempted: number;
		onClose: () => void;
		onRetry?: () => void;
	} = $props();

	let successCount = $derived(totalAttempted - failures.length);
	let expandedIndex = $state<number | null>(null);

	// Group failures by error type
	let groupedFailures = $derived(() => {
		const groups: Record<string, UploadFailure[]> = {};
		failures.forEach(failure => {
			if (!groups[failure.errorCode]) {
				groups[failure.errorCode] = [];
			}
			groups[failure.errorCode].push(failure);
		});
		return groups;
	});

	function getErrorTypeLabel(errorCode: string): string {
		const labels: Record<string, string> = {
			FILE_TOO_LARGE: 'File Too Large',
			INVALID_TYPE: 'Invalid File Type',
			CONTENT_VALIDATION: 'Content Validation Failed',
			SECURITY_VIOLATION: 'Security Check Failed',
			CORRUPTED: 'File Corrupted or Empty',
			UNKNOWN: 'Unknown Error'
		};
		return labels[errorCode] || errorCode;
	}

	function getErrorTypeIcon(errorCode: string): string {
		const icons: Record<string, string> = {
			FILE_TOO_LARGE: '📦',
			INVALID_TYPE: '🚫',
			CONTENT_VALIDATION: '⚠️',
			SECURITY_VIOLATION: '🔒',
			CORRUPTED: '💔',
			UNKNOWN: '❓'
		};
		return icons[errorCode] || '❓';
	}

	function toggleExpanded(index: number) {
		expandedIndex = expandedIndex === index ? null : index;
	}

	function downloadSummary() {
		const summary = [
			`Upload Summary - ${new Date().toLocaleString()}`,
			``,
			`Total Files: ${totalAttempted}`,
			`Successful: ${successCount}`,
			`Failed: ${failures.length}`,
			``,
			`Failed Files:`,
			`-----------`,
			...failures.map(f => 
				`${f.fileName}\n  Error: ${f.reason}\n  Type: ${getErrorTypeLabel(f.errorCode)}${f.fileSizeMB ? `\n  Size: ${f.fileSizeMB.toFixed(2)}MB` : ''}`
			)
		].join('\n');

		const blob = new Blob([summary], { type: 'text/plain' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `upload-failures-${Date.now()}.txt`;
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	}
</script>

<!-- Modal Overlay -->
<div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
	<div class="card-standard shadow-xl max-w-2xl w-full max-h-[90vh] flex flex-col p-0">
		<!-- Header -->
		<div class="px-6 py-4 border-b border-gray-200">
			<div class="flex items-center justify-between">
				<h2 class="text-xl font-semibold text-gray-900">
					Upload Summary
				</h2>
				<button
					onclick={onClose}
					class="text-gray-400 hover:text-gray-600 transition-colors"
					aria-label="Close"
				>
					<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
		</div>

		<!-- Stats -->
		<div class="px-6 py-4 bg-gray-50 border-b border-gray-200">
			<div class="grid grid-cols-3 gap-4">
				<div class="text-center">
					<div class="text-2xl font-bold text-gray-900">{totalAttempted}</div>
					<div class="text-sm text-gray-600">Total Files</div>
				</div>
				<div class="text-center">
					<div class="text-2xl font-bold text-green-600">{successCount}</div>
					<div class="text-sm text-gray-600">Successful</div>
				</div>
				<div class="text-center">
					<div class="text-2xl font-bold text-red-600">{failures.length}</div>
					<div class="text-sm text-gray-600">Failed</div>
				</div>
			</div>
		</div>

		<!-- Failure List -->
		<div class="flex-1 overflow-y-auto px-6 py-4">
			<h3 class="font-semibold text-gray-900 mb-3">Failed Uploads</h3>
			
			{#each Object.entries(groupedFailures()) as [errorCode, groupFailures], groupIndex}
				<div class="mb-4">
					<div class="flex items-center gap-2 mb-2 text-sm font-medium text-gray-700">
						<span class="text-lg">{getErrorTypeIcon(errorCode)}</span>
						<span>{getErrorTypeLabel(errorCode)}</span>
						<span class="text-gray-500">({groupFailures.length})</span>
					</div>
					
					<div class="space-y-2">
						{#each groupFailures as failure, index}
							<div class="border border-gray-200 rounded-lg overflow-hidden">
								<button
									onclick={() => toggleExpanded(groupIndex * 100 + index)}
									class="w-full px-4 py-3 bg-white hover:bg-gray-50 transition-colors text-left flex items-center justify-between"
								>
									<div class="flex-1 min-w-0">
										<div class="font-medium text-gray-900 truncate">{failure.fileName}</div>
										{#if failure.fileSizeMB}
											<div class="text-sm text-gray-500">{failure.fileSizeMB.toFixed(2)} MB</div>
										{/if}
									</div>
									<svg
										class="w-5 h-5 text-gray-400 transition-transform {expandedIndex === groupIndex * 100 + index ? 'rotate-180' : ''}"
										fill="none"
										stroke="currentColor"
										viewBox="0 0 24 24"
									>
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
									</svg>
								</button>
								
								{#if expandedIndex === groupIndex * 100 + index}
									<div class="px-4 py-3 bg-gray-50 border-t border-gray-200">
										<div class="text-sm text-gray-700">
											<strong>Error:</strong> {failure.reason}
										</div>
									</div>
								{/if}
							</div>
						{/each}
					</div>
				</div>
			{/each}
		</div>

		<!-- Actions -->
		<div class="px-6 py-4 border-t border-gray-200 bg-gray-50 flex items-center justify-between gap-3">
			<button
				onclick={downloadSummary}
				class="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 transition-colors"
			>
				<svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
				</svg>
				Download Summary
			</button>
			
			<div class="flex gap-3">
				{#if onRetry && failures.some(f => f.file)}
					<button
						onclick={onRetry}
						class="inline-flex items-center px-4 py-2 border border-transparent rounded-md text-sm font-medium text-white bg-accent hover:bg-accent-hover transition-colors"
					>
						<svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
						</svg>
						Retry Failed
					</button>
				{/if}
				<button
					onclick={onClose}
					class="inline-flex items-center px-4 py-2 border border-transparent rounded-md text-sm font-medium text-white bg-gray-600 hover:bg-gray-700 transition-colors"
				>
					Close
				</button>
			</div>
		</div>
	</div>
</div>



