<script lang="ts">
	import {
		CheckCircle2,
		AlertTriangle,
		XCircle,
		FileQuestion,
		AlertCircle,
		FileText,
		RefreshCw,
		Trash2,
		Eye,
		Upload,
		MoreVertical,
		ChevronRight,
		ExternalLink,
		Copy,
		Check,
		X
	} from 'lucide-svelte';
	import { slide } from 'svelte/transition';
	import Badge from './ui/Badge.svelte';
	import KeyFactsChips from './KeyFactsChips.svelte';
	import DocumentRelationships from './DocumentRelationships.svelte';
	import { getAttentionNeeds } from '$lib/utils/documentSorting';

	let {
		doc,
		onVerify,
		onMarkSigned,
		onEdit,
		onReExtract,
		onDelete,
		onAlwaysDelete, // Now expects (name: string, id: string) => void
		onReplace,
		onSkip,
		onView,
		onToggleExclusion,
		isProcessing = false,
		onTypeOverride,
		onRelevanceChange,
		onNotesUpdate,
		onFactUpdate,
		onFactConfirm,
		onRelationshipAdd,
		onRelationshipRemove,
		onSignatureReview,
		availableDocuments,
		isExpanded = false,
		onToggleExpand
	}: {
		doc: any;
		onVerify?: (id: string) => void;
		onMarkSigned?: (id: string) => void;
		onEdit?: (doc: any) => void;
		onReExtract?: (id: string) => void;
		onDelete?: (id: string) => void;
		onAlwaysDelete?: (name: string, id: string) => void;
		onReplace?: (id: string) => void;
		onSkip?: (id: string) => void;
		onView?: (doc: any) => void;
		onToggleExclusion?: (id: string, excluded: boolean) => void;
		isProcessing?: boolean;
		onTypeOverride?: (id: string, type: string) => void;
		onRelevanceChange?: (id: string, level: string) => void;
		onNotesUpdate?: (id: string, notes: string) => void;
		onFactUpdate?: (id: string, key: string, value: string) => void;
		onFactConfirm?: (id: string, key: string) => void;
		onRelationshipAdd?: (id: string, relatedId: string, type: string) => void;
		onRelationshipRemove?: (id: string, relatedId: string) => void;
		onSignatureReview?: (doc: any) => void;
		availableDocuments?: Array<{ id: string; name: string }>;
		isExpanded?: boolean;
		onToggleExpand?: (id: string) => void;
	} = $props();

	let showMenu = $state(false);

	// Map status to visual styles
	const statusConfigs: Record<string, any> = {
		ready: {
			icon: CheckCircle2,
			iconColor: 'text-green-500',
			bgColor: 'bg-green-50',
			borderColor: 'border-green-200',
			label: 'Ready',
			textColor: 'text-green-700'
		},
		needs_review: {
			icon: AlertTriangle,
			iconColor: 'text-amber-500',
			bgColor: 'bg-amber-50',
			borderColor: 'border-amber-200',
			label: 'Needs Review',
			textColor: 'text-amber-700'
		},
		extraction_failed: {
			icon: XCircle,
			iconColor: 'text-red-500',
			bgColor: 'bg-red-50',
			borderColor: 'border-red-200',
			label: 'Extraction Failed',
			textColor: 'text-red-700'
		},
		download_failed: {
			icon: FileQuestion,
			iconColor: 'text-gray-500',
			bgColor: 'bg-gray-100',
			borderColor: 'border-gray-300',
			label: 'Download Failed',
			textColor: 'text-gray-700'
		},
		corrupted: {
			icon: AlertCircle,
			iconColor: 'text-red-600',
			bgColor: 'bg-red-50',
			borderColor: 'border-red-300',
			label: 'Corrupted',
			textColor: 'text-red-800'
		},
		skipped: {
			icon: XCircle,
			iconColor: 'text-gray-400',
			bgColor: 'bg-gray-50',
			borderColor: 'border-gray-200',
			label: 'Skipped',
			textColor: 'text-gray-500'
		},
		duplicate: {
			icon: Copy,
			iconColor: 'text-purple-500',
			bgColor: 'bg-purple-50',
			borderColor: 'border-purple-200',
			label: 'Duplicate',
			textColor: 'text-purple-700'
		}
	};

	// Check if this is a duplicate document
	const isDuplicate = $derived(doc.metadata?.is_duplicate === true);
	const isExcluded = $derived(doc.metadata?.excluded === true);

	const config = $derived(statusConfigs[doc.status] || statusConfigs.needs_review);
	const StatusIcon = $derived(config.icon);

	// Calculate quality score from text content (same logic as CorrectionModal)
	let calculatedQuality = $derived.by(() => {
		const text = (doc.manual_text || doc.extracted_text || '').trim();
		if (!text || text.length === 0) return { score: 0, level: 'low' as const, hasText: false };

		let score = 10;

		// Check content length
		if (text.length < 50) score -= 5;
		else if (text.length < 200) score -= 2;

		// Check word count
		const wordCount = text.split(/\s+/).filter((w: string) => w.length > 0).length;
		if (wordCount < 10) score -= 3;

		// Check for gibberish
		const wordChars = text.replace(/[^a-zA-Z0-9]/g, '').length;
		const gibberishRatio = 1 - (wordChars / text.length);
		if (gibberishRatio > 0.5) score -= 2;

		const finalScore = Math.max(0, Math.min(10, score));
		return {
			score: finalScore,
			level: finalScore >= 8 ? 'high' as const : finalScore >= 5 ? 'medium' as const : 'low' as const,
			hasText: true
		};
	});

	// Get quality score color
	function getQualityColor(score: number) {
		if (score >= 8) return 'text-green-600 bg-green-100';
		if (score >= 5) return 'text-amber-600 bg-amber-100';
		return 'text-red-600 bg-red-100';
	}

	// Human readable file size
	function formatSize(bytes: number) {
		if (bytes === 0) return '0 B';
		const k = 1024;
		const sizes = ['B', 'KB', 'MB', 'GB'];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
	}

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

	function requiresSignatureReview(fileName: string | undefined): boolean {
		const normalizedName = String(fileName || '').toLowerCase();
		return signatureRequiredKeywords.some((keyword) => normalizedName.includes(keyword));
	}

	function getSignatureVerificationStatus(): 'signed' | 'not_signed' | 'unknown' | 'none' {
		const verification = doc?.metadata?.signature_verification;
		if (!verification || typeof verification !== 'object') return 'none';
		const status = String(verification.status || '').toLowerCase().trim();
		if (status === 'signed') return 'signed';
		if (status === 'not_signed' || status === 'unsigned' || status === 'not_detected' || status === 'not detected' || status === 'not signed') {
			return 'not_signed';
		}
		if (status === 'unknown' || status === 'unclear') return 'unknown';
		return 'none';
	}

	function getSignatureStatus(): 'signed' | 'not_detected' | 'review_required' | 'other' | 'none' {
		const verificationStatus = getSignatureVerificationStatus();
		if (verificationStatus === 'signed') return 'signed';
		if (verificationStatus === 'not_signed') return 'not_detected';
		if (verificationStatus === 'unknown') return 'review_required';

		const signatureDetection = doc?.metadata?.signature_detection;
		if (!signatureDetection || typeof signatureDetection !== 'object') {
			return requiresSignatureReview(doc?.file_name) ? 'review_required' : 'none';
		}
		const status = String(signatureDetection.status || '').toLowerCase();
		if (status === 'signed') return 'signed';
		if (status === 'not_detected') return 'not_detected';
		return 'other';
	}

	function getSignatureLabel(): string {
		const verificationStatus = getSignatureVerificationStatus();
		if (verificationStatus === 'signed') return 'Signed (Attorney Verified)';
		if (verificationStatus === 'not_signed') return 'Not signed (Attorney Verified)';
		if (verificationStatus === 'unknown') return 'Signature status reviewed (unclear)';

		const signatureDetection = doc?.metadata?.signature_detection;
		if (!signatureDetection) {
			if (requiresSignatureReview(doc?.file_name)) return 'Signature review recommended';
			return '';
		}
		const status = getSignatureStatus();
		const confidence = signatureDetection?.confidence
			? ` (${String(signatureDetection.confidence).toUpperCase()})`
			: '';
		if (status === 'signed') return `Signed${confidence}`;
		if (status === 'not_detected') return `No signature detected${confidence}`;
		if (status === 'review_required') return 'Signature review recommended';
		return `Signature: ${String(signatureDetection.status || 'unknown')}${confidence}`;
	}

	function getSignatureClasses(): string {
		const status = getSignatureStatus();
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

	function shouldShowSignatureBadge(): boolean {
		return getSignatureStatus() !== 'none';
	}

	// Format flat key_facts object into the structured shape KeyFactsChips expects
	function formatKeyFacts(facts: Record<string, string> | null | undefined): Record<string, { value: string; confirmed: boolean }> {
		if (!facts) return {};
		return Object.fromEntries(
			Object.entries(facts).map(([k, v]) => [k, { value: String(v), confirmed: false }])
		);
	}

	// Derived attention needs and relevance (avoids {@const} in invalid positions)
	const attentionNeeds = $derived(getAttentionNeeds(doc));
	const relevanceLevel = $derived(doc.metadata?.attorney_enrichment?.relevance_level as string | undefined);
</script>

<div
	class={`group relative border rounded-xl overflow-hidden transition-all duration-200 ${config.bgColor} ${config.borderColor} hover:shadow-md ${isProcessing ? 'animate-pulse' : ''}`}
>
	<div class="p-4 sm:p-5 flex items-start gap-4">
		<!-- Status Icon -->
		<div class={`mt-1 p-2 rounded-lg bg-white shadow-sm ${config.iconColor}`}>
			{#if isProcessing}
				<RefreshCw class="w-5 h-5 animate-spin" />
			{:else}
				<StatusIcon class="w-5 h-5" />
			{/if}
		</div>

		<!-- Content -->
		<div class="flex-1 min-w-0">
			<div class="flex items-start justify-between gap-4">
				<div class="min-w-0 flex-1">
					<!-- Header row: filename + inline attorney actions -->
					<div class="flex items-center gap-2 flex-wrap">
						<h4 class={`text-sm font-bold truncate ${config.textColor}`}>
							{doc.file_name}
						</h4>

						<!-- Attention needs label -->
						{#if attentionNeeds.length > 0}
						<span class="text-xs text-gray-400 italic ml-1">Needs: {attentionNeeds.join(', ')}</span>
						{/if}

						<!-- Type Override Dropdown -->
						{#if onTypeOverride}
						<select
							class="text-xs font-semibold px-2 py-0.5 rounded border
								   {doc.metadata?.attorney_enrichment?.document_type_override
									   ? 'bg-blue-50 border-blue-300 text-blue-700'
									   : 'bg-gray-100 border-gray-300 text-gray-600'}
								   cursor-pointer focus:ring-1 focus:ring-accent"
							value={doc.metadata?.attorney_enrichment?.document_type_override || doc.metadata?.document_type_label || ''}
							onchange={(e) => onTypeOverride!(doc.id, (e.target as HTMLSelectElement).value)}
							title="Document type (click to change)"
						>
							<option value="">Auto-detect</option>
							<option value="contract">Contract</option>
							<option value="addendum">Addendum</option>
							<option value="inspection_report">Inspection Report</option>
							<option value="disclosure">Disclosure</option>
							<option value="correspondence">Correspondence</option>
							<option value="invoice_receipt">Invoice/Receipt</option>
							<option value="photo_media">Photo/Media</option>
							<option value="legal_filing">Legal Filing</option>
							<option value="other">Other</option>
						</select>
						{/if}

						<!-- Relevance Star Button -->
						{#if onRelevanceChange}
						<button
							class="p-0.5 rounded transition-colors"
							onclick={() => {
								const next = relevanceLevel === 'critical' ? 'supporting' :
											  relevanceLevel === 'supporting' ? 'background' : 'critical';
								onRelevanceChange!(doc.id, next);
							}}
							title={relevanceLevel ? `Relevance: ${relevanceLevel} (click to change)` : 'Set relevance'}
						>
							<!-- Star icon: filled gold for critical, gray for supporting, outline for background/none -->
							<svg class="w-4 h-4 {relevanceLevel === 'critical' ? 'text-amber-500 fill-current' : relevanceLevel === 'supporting' ? 'text-gray-400 fill-current' : 'text-gray-300'}" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" fill="none">
								<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
							</svg>
						</button>
						{/if}

						<!-- Expand/Collapse Button -->
						<button
							data-expand-btn
							class="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-all ml-auto flex-shrink-0"
							onclick={() => onToggleExpand?.(doc.id)}
							title={isExpanded ? 'Collapse' : 'Expand details'}
						>
							<svg class="w-4 h-4 transition-transform duration-200 {isExpanded ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<polyline points="6 9 12 15 18 9"/>
							</svg>
						</button>
					</div>

					<div class="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1">
						<span class="text-xs text-gray-500">{doc.file_type?.split('/')[1]?.toUpperCase() || 'FILE'}</span>
						<span class="text-xs text-gray-400">•</span>
						<span class="text-xs text-gray-500">{formatSize(doc.file_size)}</span>
						{#if doc.extraction_quality && doc.status === 'ready'}
							<span class="text-xs text-gray-400">•</span>
							<Badge variant={doc.extraction_quality === 'high' ? 'ready' : doc.extraction_quality === 'medium' ? 'needs_review' : 'error'} size="xs">
								{doc.extraction_quality} Quality
							</Badge>
						{/if}
						{#if shouldShowSignatureBadge()}
							<span class="text-xs text-gray-400">•</span>
							<span
								class={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold uppercase border ${getSignatureClasses()}`}
								title={getSignatureLabel()}
							>
								{getSignatureLabel()}
							</span>
						{/if}
					</div>
				</div>

				<!-- Quality Score Badge (if available) -->
				{#if doc.metadata?.quality_score}
					<div class={`hidden sm:flex flex-col items-center justify-center w-12 h-12 rounded-full border-2 ${getQualityColor(doc.metadata.quality_score)} border-current bg-white shadow-sm`}>
						<span class="text-xs font-black">{doc.metadata.quality_score}</span>
						<span class="text-[8px] font-bold uppercase">Score</span>
					</div>
				{/if}
			</div>

			<!-- Quality Score Alert for documents needing attention -->
			{#if (doc.status === 'needs_review' || doc.status === 'extraction_failed' || (doc.status === 'ready' && !doc.is_verified))}
				<div class="mt-3 flex items-center gap-3">
					<Badge
						variant={calculatedQuality.score === 0 ? 'error' : calculatedQuality.level === 'low' ? 'error' : calculatedQuality.level === 'medium' ? 'needs_review' : 'ready'}
						class="font-bold py-1 px-3"
					>
						{calculatedQuality.score.toFixed(1)}/10
						{#if calculatedQuality.score === 0}
							<span class="ml-1 opacity-70">NO TEXT</span>
						{:else}
							<span class="ml-1 opacity-70">{calculatedQuality.level}</span>
						{/if}
					</Badge>
					{#if calculatedQuality.score === 0}
						<span class="text-xs font-medium text-red-600">Needs text extraction or manual input</span>
					{/if}
				</div>
			{/if}

			<!-- Error / Status Message -->
			{#if doc.status !== 'ready' || isDuplicate}
				<p class="mt-2 text-xs font-medium text-gray-600 line-clamp-2">
					{#if doc.status === 'download_failed'}
						Could not download from Clio. The original file may be unavailable.
					{:else if doc.status === 'extraction_failed'}
						{doc.extraction_error || 'Text extraction failed. Try OCR or enter text manually.'}
					{:else if doc.status === 'corrupted'}
						File appears damaged or in an unsupported format.
					{:else if doc.status === 'needs_review'}
						Extraction complete but quality is low. Review and correct if needed.
					{:else if doc.status === 'skipped'}
						This document will be excluded from the next analysis.
					{:else if doc.status === 'duplicate' || isDuplicate}
						<span class="text-purple-600">
							{#if doc.metadata?.duplicate_reason === 'exists_in_case'}
								This file already exists in this case.
							{:else if doc.metadata?.duplicate_reason === 'duplicate_in_import'}
								Duplicate of another file in this import.
							{:else}
								This appears to be a duplicate document.
							{/if}
							{#if isExcluded}
								<strong>Currently excluded</strong> from analysis.
							{:else}
								<strong>Currently included</strong> in analysis.
							{/if}
						</span>
					{/if}
				</p>
			{/if}

			<!-- Actions -->
			<div class="mt-4 flex flex-wrap items-center gap-2">
				{#if isDuplicate}
					<!-- Duplicate toggle button -->
					<button
						onclick={() => onToggleExclusion?.(doc.id, !isExcluded)}
						class={`btn text-xs font-bold shadow-sm ${
							isExcluded
								? 'btn-success px-3 py-1.5'
								: 'bg-purple-100 border border-purple-300 text-purple-700 hover:bg-purple-200 px-3 py-1.5'
						}`}
					>
						{#if isExcluded}
							<Check class="w-3.5 h-3.5 mr-1.5" />
							Include in Analysis
						{:else}
							<X class="w-3.5 h-3.5 mr-1.5" />
							Exclude from Analysis
						{/if}
					</button>
				{/if}

				{#if doc.status === 'ready' || doc.status === 'needs_review' || doc.status === 'extraction_failed' || doc.status === 'duplicate'}
					<button
						onclick={() => onEdit?.(doc)}
						class="inline-flex items-center px-3 py-1.5 text-xs font-bold rounded-lg bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-colors shadow-sm"
					>
						<FileText class="w-3.5 h-3.5 mr-1.5" />
						{doc.status === 'ready' ? 'View/Edit' : 'Review Text'}
					</button>
				{/if}

				{#if doc.status === 'extraction_failed'}
					<button
						onclick={() => onReExtract?.(doc.id)}
						class="btn btn-primary px-3 py-1.5 text-xs font-bold shadow-sm"
					>
						<RefreshCw class="w-3.5 h-3.5 mr-1.5" />
						Try Vision OCR
					</button>
				{/if}

				{#if doc.status === 'download_failed' || doc.status === 'corrupted'}
					<button
						onclick={() => onReplace?.(doc.id)}
						class="btn btn-primary px-3 py-1.5 text-xs font-bold shadow-sm"
					>
						<Upload class="w-3.5 h-3.5 mr-1.5" />
						Re-upload File
					</button>
				{/if}

				{#if doc.status === 'needs_review' && !doc.is_verified}
					<button
						onclick={() => onVerify?.(doc.id)}
						disabled={!doc.extracted_text && !doc.manual_text}
						title={!doc.extracted_text && !doc.manual_text ? "Run OCR first to verify this document" : "Mark as ready for analysis"}
						class={`btn text-xs font-bold shadow-sm ${
							!doc.extracted_text && !doc.manual_text
								? 'bg-gray-100 text-gray-400 cursor-not-allowed border border-gray-200 shadow-none px-3 py-1.5'
								: 'btn-success px-3 py-1.5'
						}`}
					>
						<CheckCircle2 class="w-3.5 h-3.5 mr-1.5" />
						Mark Verified
					</button>
				{/if}

				{#if onMarkSigned && requiresSignatureReview(doc?.file_name) && getSignatureStatus() !== 'signed'}
					<button
						onclick={() => onMarkSigned?.(doc.id)}
						class="inline-flex items-center px-3 py-1.5 text-xs font-bold rounded-lg bg-emerald-50 border border-emerald-300 text-emerald-700 hover:bg-emerald-100 transition-colors shadow-sm"
					>
						<CheckCircle2 class="w-3.5 h-3.5 mr-1.5" />
						Mark Signed
					</button>
				{/if}

				{#if doc.status !== 'ready' && doc.status !== 'skipped'}
					<button
						onclick={() => onSkip?.(doc.id)}
						class="btn btn-secondary px-3 py-1.5 text-xs font-bold text-gray-500"
					>
						Skip
					</button>
				{/if}

				{#if doc.storage_path}
					<button
						onclick={() => onView?.(doc)}
						class="btn btn-secondary px-3 py-1.5 text-xs font-bold"
					>
						<Eye class="w-3.5 h-3.5 mr-1.5" />
						Preview
					</button>
				{/if}
			</div>

			<!-- Expanded panel: key facts, notes, relationships -->
			{#if isExpanded}
			<div class="mt-3 pt-3 border-t border-gray-100 space-y-3" transition:slide={{ duration: 200 }}>
				<!-- Key Facts -->
				{#if doc.metadata?.attorney_enrichment?.key_facts || Object.keys(doc.metadata?.attorney_enrichment || {}).some((k: string) => ['date','amount','parties','property'].includes(k))}
				<div>
					<div class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Key Facts</div>
					<KeyFactsChips
						facts={doc.metadata?.attorney_enrichment?.key_facts_structured || formatKeyFacts(doc.metadata?.attorney_enrichment?.key_facts)}
						onFactUpdate={(key, value) => onFactUpdate?.(doc.id, key, value)}
						onFactConfirm={(key) => onFactConfirm?.(doc.id, key)}
					/>
				</div>
				{/if}

				<!-- Attorney Notes -->
				<div>
					<div class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Notes</div>
					<textarea
						class="w-full text-sm border border-gray-200 rounded-lg p-2 resize-none focus:ring-1 focus:ring-accent focus:border-transparent bg-gray-50"
						rows="2"
						placeholder="Add notes about this document..."
						value={doc.metadata?.attorney_enrichment?.attorney_notes || ''}
						onblur={(e) => {
							const val = (e.target as HTMLTextAreaElement).value;
							if (val !== (doc.metadata?.attorney_enrichment?.attorney_notes || '')) {
								onNotesUpdate?.(doc.id, val);
							}
						}}
					></textarea>
				</div>

				<!-- Document Relationships -->
				<div>
					<div class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Related Documents</div>
					<DocumentRelationships
						documentId={doc.id}
						relationships={doc.metadata?.attorney_enrichment?.document_relationships || []}
						availableDocuments={availableDocuments || []}
						onAddRelationship={(relId, type) => onRelationshipAdd?.(doc.id, relId, type)}
						onRemoveRelationship={(relId) => onRelationshipRemove?.(doc.id, relId)}
					/>
				</div>
			</div>
			{/if}
		</div>

		<!-- Menu Toggle -->
		<div class="relative">
			<button
				onclick={() => showMenu = !showMenu}
				class="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-black/5 transition-colors"
			>
				<MoreVertical class="w-5 h-5" />
			</button>

			{#if showMenu}
				<div
					transition:slide={{ duration: 100 }}
					class="absolute right-0 mt-2 w-48 bg-white border border-gray-200 rounded-xl shadow-xl z-10 py-1"
				>
					<button
						onclick={() => { onDelete?.(doc.id); showMenu = false; }}
						class="w-full px-4 py-2 text-left text-sm font-medium text-red-600 hover:bg-red-50 flex items-center"
					>
						<Trash2 class="w-4 h-4 mr-3" />
						Delete Document
					</button>

					<button
						onclick={() => { onAlwaysDelete?.(doc.file_name, doc.id); showMenu = false; }}
						class="w-full px-4 py-2 text-left text-sm font-medium text-red-700 hover:bg-red-50 flex items-center"
					>
						<XCircle class="w-4 h-4 mr-3" />
						Always Delete
					</button>
				</div>
			{/if}
		</div>
	</div>
</div>
