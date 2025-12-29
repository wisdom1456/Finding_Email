<script lang="ts">
	import { 
		X, 
		Upload, 
		FileText, 
		AlertTriangle, 
		CheckCircle2, 
		ArrowRight,
		FileQuestion,
		Info
	} from 'lucide-svelte';
	import { slide, fade } from 'svelte/transition';
	import { getApiUrl } from '$lib/config';
	import { supabase } from '$lib/supabase';

	let { 
		doc, 
		isOpen = $bindable(false), 
		onSuccess 
	}: { 
		doc: any; 
		isOpen: boolean; 
		onSuccess?: (updatedDoc: any) => void;
	} = $props();

	let mode = $state<'options' | 'upload' | 'manual'>('options');
	let isSubmitting = $state(false);
	let error = $state<string | null>(null);
	let manualText = $state(doc?.manual_text || doc?.extracted_text || '');
	let fileInput = $state<HTMLInputElement>();
	let selectedFile = $state<File | null>(null);

	function reset() {
		mode = 'options';
		isSubmitting = false;
		error = null;
		selectedFile = null;
		manualText = doc?.manual_text || doc?.extracted_text || '';
	}

	$effect(() => {
		if (isOpen) reset();
	});

	async function handleFileUpload() {
		if (!selectedFile) return;
		
		isSubmitting = true;
		error = null;

		try {
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) throw new Error('Not authenticated');

			const formData = new FormData();
			formData.append('file', selectedFile);

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/documents/${doc.id}/replace`, {
				method: 'POST',
				headers: {
					'Authorization': `Bearer ${session.access_token}`
				},
				body: formData
			});

			if (!response.ok) {
				const detail = await response.json().catch(() => ({}));
				throw new Error(detail?.detail || 'Failed to replace document');
			}

			const updatedDoc = await response.json();
			onSuccess?.(updatedDoc);
			isOpen = false;
		} catch (err: any) {
			error = err.message;
		} finally {
			isSubmitting = false;
		}
	}

	async function handleManualSubmit() {
		if (!manualText.trim()) {
			error = 'Please enter some text';
			return;
		}

		isSubmitting = true;
		error = null;

		try {
			const { data: { session } } = await supabase.auth.getSession();
			if (!session) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/documents/${doc.id}/verify`, {
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json',
					'Authorization': `Bearer ${session.access_token}`
				},
				body: JSON.stringify({
					manual_text: manualText,
					is_verified: true
				})
			});

			if (!response.ok) {
				const detail = await response.json().catch(() => ({}));
				throw new Error(detail?.detail || 'Failed to update document');
			}

			const updatedDoc = await response.json();
			onSuccess?.(updatedDoc);
			isOpen = false;
		} catch (err: any) {
			error = err.message;
		} finally {
			isSubmitting = false;
		}
	}

	function onFileChange(e: Event) {
		const target = e.target as HTMLInputElement;
		if (target.files && target.files.length > 0) {
			selectedFile = target.files[0];
		}
	}
</script>

{#if isOpen}
	<div 
		transition:fade={{ duration: 200 }}
		class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
	>
		<div 
			transition:slide={{ duration: 300 }}
			class="bg-white rounded-2xl shadow-2xl w-full max-w-xl overflow-hidden"
		>
			<!-- Header -->
			<div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between bg-gray-50/50">
				<div class="flex items-center gap-3">
					<div class="p-2 rounded-lg bg-accent/10 text-accent">
						<AlertTriangle class="w-5 h-5" />
					</div>
					<div>
						<h3 class="text-lg font-bold text-gray-900">Document Recovery</h3>
						<p class="text-xs text-gray-500 font-medium truncate max-w-[300px]">
							{doc?.file_name}
						</p>
					</div>
				</div>
				<button 
					onclick={() => isOpen = false}
					class="p-2 rounded-full text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
				>
					<X class="w-5 h-5" />
				</button>
			</div>

			<!-- Body -->
			<div class="p-6">
				{#if error}
					<div transition:slide class="mb-6 p-4 rounded-xl bg-red-50 border border-red-100 flex items-start gap-3 text-red-700">
						<AlertTriangle class="w-5 h-5 mt-0.5 shrink-0" />
						<p class="text-sm font-medium">{error}</p>
					</div>
				{/if}

				{#if mode === 'options'}
					<div class="space-y-4">
						<div class="p-4 rounded-xl bg-amber-50 border border-amber-100 flex items-start gap-4 mb-6">
							<div class="p-2 rounded-lg bg-white shadow-sm text-amber-500">
								<FileQuestion class="w-5 h-5" />
							</div>
							<div>
								<h4 class="text-sm font-bold text-amber-800">What's wrong?</h4>
								<p class="text-xs text-amber-700 mt-1 leading-relaxed">
									{#if doc?.status === 'download_failed'}
										This document couldn't be retrieved from Clio. You'll need to upload it manually to continue.
									{:else if doc?.status === 'extraction_failed'}
										We couldn't extract readable text from this file. You can try re-uploading a clearer scan or enter the text manually.
									{:else if doc?.status === 'corrupted'}
										The file format is unrecognized or the file is damaged. Please re-upload a valid PDF or image.
									{/if}
								</p>
							</div>
						</div>

						<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
							<button 
								onclick={() => mode = 'upload'}
								class="flex flex-col items-center justify-center p-6 rounded-2xl border-2 border-dashed border-gray-200 hover:border-accent hover:bg-accent/5 transition-all group"
							>
								<div class="p-3 rounded-full bg-gray-100 group-hover:bg-accent/10 text-gray-500 group-hover:text-accent transition-colors">
									<Upload class="w-6 h-6" />
								</div>
								<span class="mt-3 text-sm font-bold text-gray-900">Re-upload File</span>
								<span class="text-xs text-gray-500 mt-1">PDF or Image</span>
							</button>

							<button 
								onclick={() => mode = 'manual'}
								class="flex flex-col items-center justify-center p-6 rounded-2xl border-2 border-dashed border-gray-200 hover:border-accent hover:bg-accent/5 transition-all group"
							>
								<div class="p-3 rounded-full bg-gray-100 group-hover:bg-accent/10 text-gray-500 group-hover:text-accent transition-colors">
									<FileText class="w-6 h-6" />
								</div>
								<span class="mt-3 text-sm font-bold text-gray-900">Manual Entry</span>
								<span class="text-xs text-gray-500 mt-1">Type or paste text</span>
							</button>
						</div>
					</div>
				{:else if mode === 'upload'}
					<div class="space-y-6">
						<div 
							onclick={() => fileInput?.click()}
							onkeydown={(e) => e.key === 'Enter' && fileInput?.click()}
							role="button"
							tabindex="0"
							class="flex flex-col items-center justify-center p-10 rounded-2xl border-2 border-dashed border-accent/30 bg-accent/5 hover:bg-accent/10 transition-all cursor-pointer group"
						>
							<input 
								type="file" 
								bind:this={fileInput} 
								onchange={onFileChange}
								class="hidden"
								accept=".pdf,image/*"
							/>
							{#if selectedFile}
								<CheckCircle2 class="w-10 h-10 text-green-500 mb-4" />
								<span class="text-sm font-bold text-gray-900">{selectedFile.name}</span>
								<span class="text-xs text-gray-500 mt-1">{(selectedFile.size / 1024).toFixed(1)} KB</span>
							{:else}
								<div class="p-4 rounded-full bg-white shadow-sm text-accent group-hover:scale-110 transition-transform">
									<Upload class="w-8 h-8" />
								</div>
								<span class="mt-4 text-sm font-bold text-gray-900">Click to select file</span>
								<span class="text-xs text-gray-500 mt-1">Supported: PDF, JPG, PNG</span>
							{/if}
						</div>

						<div class="flex items-center gap-3">
							<button 
								onclick={() => mode = 'options'}
								class="flex-1 px-4 py-3 rounded-xl border border-gray-200 text-sm font-bold text-gray-600 hover:bg-gray-50 transition-colors"
							>
								Back
							</button>
							<button 
								onclick={handleFileUpload}
								disabled={!selectedFile || isSubmitting}
								class="flex-[2] px-4 py-3 rounded-xl bg-accent text-white text-sm font-bold hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-accent/20 flex items-center justify-center gap-2"
							>
								{#if isSubmitting}
									<div class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
									Uploading...
								{:else}
									Complete Re-upload
									<ArrowRight class="w-4 h-4" />
								{/if}
							</button>
						</div>
					</div>
				{:else if mode === 'manual'}
					<div class="space-y-6">
						<div>
							<label for="manual-text" class="block text-sm font-bold text-gray-700 mb-2">Extracted Text</label>
							<textarea 
								id="manual-text"
								bind:value={manualText}
								placeholder="Paste the text from the document here..."
								class="w-full h-64 p-4 rounded-xl border border-gray-200 focus:ring-2 focus:ring-accent focus:border-transparent resize-none text-sm font-mono leading-relaxed"
							></textarea>
							<div class="mt-2 flex items-center gap-2 text-gray-500 text-xs font-medium">
								<Info class="w-3.5 h-3.5" />
								<span>Entering text manually will bypass the need for extraction.</span>
							</div>
						</div>

						<div class="flex items-center gap-3">
							<button 
								onclick={() => mode = 'options'}
								class="flex-1 px-4 py-3 rounded-xl border border-gray-200 text-sm font-bold text-gray-600 hover:bg-gray-50 transition-colors"
							>
								Back
							</button>
							<button 
								onclick={handleManualSubmit}
								disabled={!manualText.trim() || isSubmitting}
								class="flex-[2] px-4 py-3 rounded-xl bg-accent text-white text-sm font-bold hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-accent/20 flex items-center justify-center gap-2"
							>
								{#if isSubmitting}
									<div class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
									Saving...
								{:else}
									Save & Verify
									<ArrowRight class="w-4 h-4" />
								{/if}
							</button>
						</div>
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}

