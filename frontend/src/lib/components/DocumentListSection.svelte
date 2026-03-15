<script lang="ts">
	import { isCaseSummary, isIntakeForm, isVideoAudioFile } from '$lib/utils/documentClassification';
	import { shouldShowSignatureBadge, getDocumentSignatureBadgeClass, getDocumentSignatureLabel } from '$lib/utils/signatureDetection';
	import { formatFileSize, getStatusColor } from '$lib/utils/formatters';

	let {
		documents,
		onview,
		ondelete,
		onpromote,
	}: {
		documents: any[];
		onview: (doc: any) => void;
		ondelete: (docId: string) => void;
		onpromote: (docId: string) => void;
	} = $props();

	let showHiddenDocs = $state(false);

	let sortedDocuments = $derived(
		[...documents].sort((a, b) => {
			const aIsPrimary = a.metadata?.is_intake_form || false;
			const bIsPrimary = b.metadata?.is_intake_form || false;
			const aIsCaseSummary = isCaseSummary(a);
			const bIsCaseSummary = isCaseSummary(b);
			const aIsIntake = isIntakeForm(a);
			const bIsIntake = isIntakeForm(b);

			if (aIsPrimary && !bIsPrimary) return -1;
			if (!aIsPrimary && bIsPrimary) return 1;
			if (aIsCaseSummary && !bIsCaseSummary) return -1;
			if (!aIsCaseSummary && bIsCaseSummary) return 1;
			if (aIsIntake && !bIsIntake) return -1;
			if (!aIsIntake && bIsIntake) return 1;
			return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
		})
	);

	let hiddenDocs = $derived(
		sortedDocuments.filter(doc => doc.status === 'duplicate' || doc.is_flagged_as_junk)
	);

	let visibleDocuments = $derived(
		showHiddenDocs ? sortedDocuments : sortedDocuments.filter(doc => doc.status !== 'duplicate' && !doc.is_flagged_as_junk)
	);
</script>

{#if documents.length === 0}
	<div data-testid="doc-list-empty" class="p-8 text-center">
		<p class="text-sm text-gray-500">No documents uploaded yet.</p>
	</div>
{:else}
	{#if hiddenDocs.length > 0}
		<div class="px-4 py-2 bg-gray-50 border-t border-b border-gray-200 flex items-center justify-between">
			<span class="text-xs text-gray-500">
				{hiddenDocs.length} duplicate/junk document{hiddenDocs.length === 1 ? '' : 's'} hidden
			</span>
			<button
				onclick={() => showHiddenDocs = !showHiddenDocs}
				class="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
			>
				{showHiddenDocs ? 'Hide' : 'Show'}
			</button>
		</div>
	{/if}
	<div data-testid="doc-list" class="border-t border-gray-200">
		<ul class="divide-y divide-gray-200">
			{#each visibleDocuments as doc}
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
							onclick={() => onview(doc)}
							onkeydown={(e) => e.key === 'Enter' && onview(doc)}
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
											onpromote(doc.id);
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
							onclick={() => ondelete(doc.id)}
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
