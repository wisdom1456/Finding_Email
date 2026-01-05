<script lang="ts">
	import { 
		X, 
		AlertTriangle, 
		RefreshCw,
		SkipForward,
		FileX,
		Clock,
		AlertCircle,
		CheckCircle2
	} from 'lucide-svelte';
	import { slide, fade } from 'svelte/transition';
	import { getApiUrl } from '$lib/config';
	import { getSecureSession } from '$lib/supabase';
	import Modal from './ui/Modal.svelte';
	import Badge from './ui/Badge.svelte';

	interface FailedDocument {
		id: string;
		name: string;
		error: string;
		error_type?: string;
	}

	let { 
		analysisId,
		failedDocs = [],
		isOpen = $bindable(false), 
		onRetry,
		onSkip,
		onClose
	}: { 
		analysisId: string;
		failedDocs: FailedDocument[];
		isOpen: boolean;
		onRetry?: (docIds: string[]) => void;
		onSkip?: (docIds: string[]) => void;
		onClose?: () => void;
	} = $props();

	let selectedDocs = $state<Set<string>>(new Set());
	let isSubmitting = $state(false);
	let error = $state<string | null>(null);
	let successMessage = $state<string | null>(null);

	// Select all by default
	$effect(() => {
		if (isOpen && failedDocs.length > 0) {
			selectedDocs = new Set(failedDocs.map(d => d.id));
		}
	});

	function toggleDoc(docId: string) {
		const newSet = new Set(selectedDocs);
		if (newSet.has(docId)) {
			newSet.delete(docId);
		} else {
			newSet.add(docId);
		}
		selectedDocs = newSet;
	}

	function selectAll() {
		selectedDocs = new Set(failedDocs.map(d => d.id));
	}

	function selectNone() {
		selectedDocs = new Set();
	}

	async function handleRetry() {
		if (selectedDocs.size === 0) {
			error = 'Please select at least one document to retry';
			return;
		}

		isSubmitting = true;
		error = null;
		successMessage = null;

		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/analysis/${analysisId}/retry`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'Authorization': `Bearer ${session.access_token}`
				},
				body: JSON.stringify({
					document_ids: Array.from(selectedDocs)
				})
			});

			if (!response.ok) {
				const detail = await response.json().catch(() => ({}));
				throw new Error(detail?.detail || 'Failed to retry documents');
			}

			const result = await response.json();
			successMessage = result.message;
			
			// Notify parent
			onRetry?.(Array.from(selectedDocs));
			
			// Close modal after short delay
			setTimeout(() => {
				isOpen = false;
			}, 1500);
		} catch (err: any) {
			error = err.message;
		} finally {
			isSubmitting = false;
		}
	}

	async function handleSkip() {
		if (selectedDocs.size === 0) {
			error = 'Please select at least one document to skip';
			return;
		}

		isSubmitting = true;
		error = null;
		successMessage = null;

		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/analysis/${analysisId}/skip`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'Authorization': `Bearer ${session.access_token}`
				},
				body: JSON.stringify({
					document_ids: Array.from(selectedDocs)
				})
			});

			if (!response.ok) {
				const detail = await response.json().catch(() => ({}));
				throw new Error(detail?.detail || 'Failed to skip documents');
			}

			const result = await response.json();
			successMessage = result.message;
			
			// Notify parent
			onSkip?.(Array.from(selectedDocs));
			
			// Close modal after short delay
			setTimeout(() => {
				isOpen = false;
			}, 1500);
		} catch (err: any) {
			error = err.message;
		} finally {
			isSubmitting = false;
		}
	}

	async function handleSkipAll() {
		selectAll();
		await handleSkip();
	}

	function getErrorIcon(errorType?: string) {
		switch (errorType) {
			case 'TIMEOUT':
				return Clock;
			case 'API_ERROR':
			case 'RATE_LIMIT':
				return AlertCircle;
			default:
				return FileX;
		}
	}

	function getErrorBadgeVariant(errorType?: string): 'warning' | 'error' | 'neutral' {
		switch (errorType) {
			case 'TIMEOUT':
				return 'warning';
			case 'API_ERROR':
			case 'RATE_LIMIT':
				return 'error';
			default:
				return 'neutral';
		}
	}
</script>

<Modal
	bind:open={isOpen}
	title="Document Analysis Failed"
	size="lg"
>
	<!-- Header info -->
	<div class="mb-6">
		<div class="flex items-center gap-3 p-4 rounded-xl bg-amber-50 border border-amber-200">
			<AlertTriangle class="w-6 h-6 text-amber-500 shrink-0" />
			<div>
				<h4 class="text-sm font-bold text-amber-800">
					{failedDocs.length} Document{failedDocs.length === 1 ? '' : 's'} Failed
				</h4>
				<p class="text-xs text-amber-700 mt-0.5">
					You can retry the failed documents or skip them to continue with the analysis.
				</p>
			</div>
		</div>
	</div>

	<!-- Success/Error messages -->
	{#if error}
		<div transition:slide class="mb-4 p-4 rounded-xl bg-red-50 border border-red-100 flex items-start gap-3 text-red-700">
			<AlertTriangle class="w-5 h-5 mt-0.5 shrink-0" />
			<p class="text-sm font-medium">{error}</p>
		</div>
	{/if}

	{#if successMessage}
		<div transition:slide class="mb-4 p-4 rounded-xl bg-green-50 border border-green-100 flex items-start gap-3 text-green-700">
			<CheckCircle2 class="w-5 h-5 mt-0.5 shrink-0" />
			<p class="text-sm font-medium">{successMessage}</p>
		</div>
	{/if}

	<!-- Selection controls -->
	<div class="flex items-center justify-between mb-4">
		<span class="text-sm text-gray-600">
			{selectedDocs.size} of {failedDocs.length} selected
		</span>
		<div class="flex gap-2">
			<button 
				onclick={selectAll}
				class="text-xs text-accent hover:underline font-medium"
			>
				Select All
			</button>
			<span class="text-gray-300">|</span>
			<button 
				onclick={selectNone}
				class="text-xs text-gray-500 hover:underline font-medium"
			>
				Select None
			</button>
		</div>
	</div>

	<!-- Failed documents list -->
	<div class="space-y-2 max-h-80 overflow-y-auto pr-1">
		{#each failedDocs as doc (doc.id)}
			{@const ErrorIcon = getErrorIcon(doc.error_type)}
			<button
				onclick={() => toggleDoc(doc.id)}
				class="w-full p-4 rounded-xl border-2 transition-all text-left {
					selectedDocs.has(doc.id) 
						? 'border-accent bg-accent/5' 
						: 'border-gray-100 hover:border-gray-200 bg-white'
				}"
			>
				<div class="flex items-start gap-3">
					<!-- Checkbox indicator -->
					<div class="mt-0.5 w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 {
						selectedDocs.has(doc.id) 
							? 'border-accent bg-accent' 
							: 'border-gray-300 bg-white'
					}">
						{#if selectedDocs.has(doc.id)}
							<svg class="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3">
								<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
							</svg>
						{/if}
					</div>
					
					<div class="flex-1 min-w-0">
						<div class="flex items-center gap-2">
							<ErrorIcon class="w-4 h-4 text-red-500 shrink-0" />
							<span class="text-sm font-semibold text-gray-900 truncate">
								{doc.name}
							</span>
						</div>
						<p class="text-xs text-gray-500 mt-1 line-clamp-2">
							{doc.error}
						</p>
						{#if doc.error_type}
							<Badge variant={getErrorBadgeVariant(doc.error_type)} class="mt-2 text-xs">
								{doc.error_type}
							</Badge>
						{/if}
					</div>
				</div>
			</button>
		{/each}
	</div>

	<!-- Action buttons -->
	<div class="mt-6 flex flex-col sm:flex-row gap-3">
		<button
			onclick={handleRetry}
			disabled={selectedDocs.size === 0 || isSubmitting}
			class="btn btn-primary flex-1 py-3 gap-2"
		>
			{#if isSubmitting}
				<div class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
			{:else}
				<RefreshCw class="w-4 h-4" />
			{/if}
			Retry Selected ({selectedDocs.size})
		</button>
		
		<button
			onclick={handleSkipAll}
			disabled={isSubmitting}
			class="btn btn-secondary flex-1 py-3 gap-2"
		>
			<SkipForward class="w-4 h-4" />
			Skip All & Continue
		</button>
	</div>

	<!-- Help text -->
	<p class="mt-4 text-xs text-gray-400 text-center">
		Skipped documents will not be included in the final analysis.
	</p>
</Modal>

