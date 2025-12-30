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

	let { 
		doc, 
		onVerify, 
		onEdit, 
		onReExtract, 
		onDelete, 
		onAlwaysDelete, // Now expects (name: string, id: string) => void
		onReplace,
		onSkip,
		onView,
		onToggleExclusion,
		isProcessing = false
	}: { 
		doc: any; 
		onVerify?: (id: string) => void;
		onEdit?: (doc: any) => void;
		onReExtract?: (id: string) => void;
		onDelete?: (id: string) => void;
		onAlwaysDelete?: (name: string, id: string) => void;
		onReplace?: (id: string) => void;
		onSkip?: (id: string) => void;
		onView?: (doc: any) => void;
		onToggleExclusion?: (id: string, excluded: boolean) => void;
		isProcessing?: boolean;
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
				<div class="min-w-0">
					<h4 class={`text-sm font-bold truncate ${config.textColor}`}>
						{doc.file_name}
					</h4>
					<div class="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1">
						<span class="text-xs text-gray-500">{doc.file_type?.split('/')[1]?.toUpperCase() || 'FILE'}</span>
						<span class="text-xs text-gray-400">•</span>
						<span class="text-xs text-gray-500">{formatSize(doc.file_size)}</span>
						{#if doc.extraction_quality && doc.status === 'ready'}
							<span class="text-xs text-gray-400">•</span>
							<span class={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${getQualityColor(doc.extraction_quality === 'high' ? 9 : doc.extraction_quality === 'medium' ? 6 : 3)}`}>
								{doc.extraction_quality} Quality
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
					<div class={`flex items-center gap-2 px-2.5 py-1 rounded-lg border ${
						calculatedQuality.score === 0 
							? 'bg-red-100 border-red-300 text-red-700' 
							: calculatedQuality.level === 'low' 
								? 'bg-red-50 border-red-200 text-red-600'
								: calculatedQuality.level === 'medium'
									? 'bg-amber-50 border-amber-200 text-amber-600'
									: 'bg-green-50 border-green-200 text-green-600'
					}`}>
						<span class="text-xs font-bold">{calculatedQuality.score.toFixed(1)}/10</span>
						{#if calculatedQuality.score === 0}
							<span class="text-[10px] font-bold uppercase tracking-wide">NO TEXT</span>
						{:else}
							<span class="text-[10px] font-bold uppercase tracking-wide">{calculatedQuality.level}</span>
						{/if}
					</div>
					{#if calculatedQuality.score === 0}
						<span class="text-xs font-medium text-red-600">⚠️ Needs text extraction or manual input</span>
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
						class={`inline-flex items-center px-3 py-1.5 text-xs font-bold rounded-lg transition-colors shadow-sm ${
							isExcluded 
								? 'bg-green-600 text-white hover:bg-green-700' 
								: 'bg-purple-100 border border-purple-300 text-purple-700 hover:bg-purple-200'
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
						class="inline-flex items-center px-3 py-1.5 text-xs font-bold rounded-lg bg-accent text-white hover:bg-accent-hover transition-colors shadow-sm"
					>
						<RefreshCw class="w-3.5 h-3.5 mr-1.5" />
						Try Vision OCR
					</button>
				{/if}

				{#if doc.status === 'download_failed' || doc.status === 'corrupted'}
					<button 
						onclick={() => onReplace?.(doc.id)}
						class="inline-flex items-center px-3 py-1.5 text-xs font-bold rounded-lg bg-accent text-white hover:bg-accent-hover transition-colors shadow-sm"
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
						class={`inline-flex items-center px-3 py-1.5 text-xs font-bold rounded-lg transition-colors shadow-sm ${
							!doc.extracted_text && !doc.manual_text
								? 'bg-gray-100 text-gray-400 cursor-not-allowed border border-gray-200 shadow-none'
								: 'bg-green-600 text-white hover:bg-green-700'
						}`}
					>
						<CheckCircle2 class="w-3.5 h-3.5 mr-1.5" />
						Mark Verified
					</button>
				{/if}

				{#if doc.status !== 'ready' && doc.status !== 'skipped'}
					<button 
						onclick={() => onSkip?.(doc.id)}
						class="inline-flex items-center px-3 py-1.5 text-xs font-bold rounded-lg bg-white border border-gray-200 text-gray-500 hover:bg-gray-50 transition-colors"
					>
						Skip
					</button>
				{/if}
				
				{#if doc.storage_path}
					<button 
						onclick={() => onView?.(doc)}
						class="inline-flex items-center px-3 py-1.5 text-xs font-bold rounded-lg bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
					>
						<Eye class="w-3.5 h-3.5 mr-1.5" />
						Preview
					</button>
				{/if}
			</div>
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

