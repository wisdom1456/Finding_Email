<script lang="ts">
	import { AlertCircle, ChevronDown, ChevronUp, Upload, FileX, Info, FileQuestion } from 'lucide-svelte';
	import { slide } from 'svelte/transition';
	import RecoveryModal from './RecoveryModal.svelte';

	let { 
		documents = [], 
		onDocumentsUpdated 
	}: { 
		documents: any[]; 
		onDocumentsUpdated: () => void 
	} = $props();

	let failedDocs = $derived(
		documents.filter(
			(doc) =>
				(doc.status === 'download_failed' ||
					doc.status === 'download_timeout' ||
					doc.status === 'corrupted') &&
				doc.metadata?.clio_source === true
		)
	);

	let isExpanded = $state(false);
	let showRecoveryModal = $state(false);
	let recoveryDocument = $state<any>(null);

	// Automatically expand if there are a few files, collapse if many
	$effect(() => {
		if (failedDocs.length > 0 && failedDocs.length <= 5) {
			isExpanded = true;
		}
	});

	function openRecovery(doc: any) {
		recoveryDocument = doc;
		showRecoveryModal = true;
	}

	function formatSize(bytes: number) {
		if (!bytes) return 'Unknown size';
		const mb = bytes / (1024 * 1024);
		if (mb < 0.1) {
			return `${(bytes / 1024).toFixed(1)} KB`;
		}
		return `${mb.toFixed(2)} MB`;
	}

	function getErrorLabel(status: string) {
		switch (status) {
			case 'download_failed':
				return 'Download Failed';
			case 'download_timeout':
				return 'Download Timeout';
			case 'corrupted':
				return 'File Corrupted';
			default:
				return 'Import Error';
		}
	}
</script>

{#if failedDocs.length > 0}
	<div class="mb-6 overflow-hidden bg-red-50 border border-red-200 rounded-2xl shadow-sm">
		<div class="p-4 sm:p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
			<div class="flex items-start gap-4">
				<div class="mt-1 p-2 rounded-xl bg-red-100 text-red-600">
					<AlertCircle class="w-6 h-6" />
				</div>
				<div>
					<h3 class="text-lg font-bold text-red-900">
						{failedDocs.length} Clio {failedDocs.length === 1 ? 'document was' : 'documents were'} not imported
					</h3>
					<p class="text-sm font-medium text-red-700 mt-1">
						Large files like videos or heavy ZIPs often fail to download from Clio. You can manually upload these files below.
					</p>
				</div>
			</div>

			<div class="flex items-center gap-3 w-full sm:w-auto">
				<button
					onclick={() => (isExpanded = !isExpanded)}
					class="flex-1 sm:flex-none inline-flex items-center justify-center px-4 py-2 text-sm font-bold rounded-xl bg-white border border-red-200 text-red-700 hover:bg-red-100/50 transition-colors shadow-sm"
				>
					{isExpanded ? 'Hide List' : 'View Failed Files'}
					{#if isExpanded}
						<ChevronUp class="w-4 h-4 ml-2" />
					{:else}
						<ChevronDown class="w-4 h-4 ml-2" />
					{/if}
				</button>
			</div>
		</div>

		{#if isExpanded}
			<div transition:slide={{ duration: 300 }} class="border-t border-red-200 bg-white/50">
				<div class="p-4 sm:p-6">
					<div class="grid grid-cols-1 gap-4">
						{#each failedDocs as doc}
							<div class="p-4 rounded-xl border border-red-100 bg-white flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-sm">
								<div class="flex items-start gap-4 min-w-0 flex-1">
									<div class="mt-1 p-2 rounded-lg bg-gray-50 text-gray-400">
										<FileQuestion class="w-5 h-5" />
									</div>
									<div class="min-w-0">
										<h4 class="text-sm font-bold text-gray-900 truncate" title={doc.file_name}>
											{doc.file_name}
										</h4>
										<div class="mt-1 flex flex-wrap items-center gap-2">
											<span class="px-1.5 py-0.5 rounded text-[10px] font-black uppercase tracking-wider bg-red-100 text-red-700">
												{getErrorLabel(doc.status)}
											</span>
											<span class="text-xs font-medium text-gray-400">•</span>
											<span class="text-xs font-medium text-gray-600">{formatSize(doc.file_size)}</span>
											{#if doc.metadata?.clio_id}
												<span class="text-xs font-medium text-gray-400">•</span>
												<span class="text-[10px] text-gray-400 font-mono">ID: {doc.metadata.clio_id}</span>
											{/if}
										</div>
									</div>
								</div>

								<button
									onclick={() => openRecovery(doc)}
									class="inline-flex items-center justify-center px-4 py-2 text-xs font-bold rounded-lg bg-accent text-white hover:bg-accent-hover transition-colors shadow-sm"
								>
									<Upload class="w-3.5 h-3.5 mr-1.5" />
									Replace with Manual Upload
								</button>
							</div>
						{/each}
					</div>

					<div class="mt-6 flex items-start gap-3 p-4 rounded-xl bg-blue-50 border border-blue-100 text-blue-800">
						<Info class="w-5 h-5 mt-0.5 shrink-0" />
						<p class="text-xs font-medium leading-relaxed">
							<strong>Why did this happen?</strong> Clio's API often times out when transferring very large files (>50MB) or media formats. Replacing them manually ensures they are included in your legal analysis.
						</p>
					</div>
				</div>
			</div>
		{/if}
	</div>
{/if}

{#if showRecoveryModal && recoveryDocument}
	<RecoveryModal
		bind:isOpen={showRecoveryModal}
		doc={recoveryDocument}
		onSuccess={async () => {
			await onDocumentsUpdated();
		}}
	/>
{/if}

