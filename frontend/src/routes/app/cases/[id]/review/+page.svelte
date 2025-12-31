<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { getApiUrl } from '$lib/config';
	import { supabase } from '$lib/supabase';

	const caseId = $derived($page.params.id as string);

	let loading = $state(true);
	let processing = $state(false);
	let confirming = $state(false);
	let errorMessage = $state('');
	
	// Extracted data
	let clientName = $state('');
	let selectedPracticeAreas = $state<string[]>([]);
	let qaPairs = $state<Array<{question: string, answer: string}>>([]);
	let rawContent = $state('');
	
	// Available practice areas (from legacy app)
	const availablePracticeAreas = [
		'Contract Disputes',
		'Consumer Protection (FDUTPA)',
		'Business Organization Disputes',
		'Timeshare Disputes',
		'Landlord-Tenant Disputes',
		'Foreclosure Defense',
		'Property Damage & Insurance',
		'Construction Defects',
		'Mechanics Liens',
		'Administrative Law',
		'Statutes of Limitation',
		'Attorney Fees & Sanctions',
		'Motorcycle Accidents',
		'Medical Malpractice',
		'Other'
	];

	onMount(async () => {
		// Check if we have intake data from file upload or need to fetch from case
		const urlParams = new URLSearchParams(window.location.search);
		const hasIntakeData = urlParams.get('intake_uploaded');
		
		if (hasIntakeData) {
			// Data should be in session storage or we need to re-process
			await processIntakeFromCase();
		} else {
			loading = false;
		}
	});

	async function processIntakeFromCase() {
		loading = true;
		errorMessage = '';

		try {
			const {
				data: { session }
			} = await supabase.auth.getSession();

			if (!session) {
				throw new Error('Not authenticated');
			}

			// Get case with intake document
			const { data: caseData, error: caseError } = await supabase
				.from('cases')
				.select('*')
				.eq('id', caseId)
				.single();

			if (caseError) throw caseError;

			// Cast case data to expected shape
			const data = caseData as { 
				client_name?: string;
				metadata?: { 
					intake_processed?: boolean;
					practice_areas?: string[];
					qa_pairs?: Array<{question: string, answer: string}>;
					raw_intake_content?: string;
				};
			};

			// Check if already has intake metadata
			if (data.metadata?.intake_processed) {
				// Load existing data
				clientName = data.client_name || '';
				selectedPracticeAreas = data.metadata.practice_areas || [];
				qaPairs = data.metadata.qa_pairs || [];
				rawContent = data.metadata.raw_intake_content || '';
			} else {
				errorMessage = 'No intake form has been uploaded yet. Please upload an intake form first.';
			}
		} catch (error: any) {
			errorMessage = error.message || 'Failed to load intake data';
		} finally {
			loading = false;
		}
	}

	async function handleFileUpload(event: Event) {
		const target = event.target as HTMLInputElement;
		if (!target.files || target.files.length === 0) return;

		const file = target.files[0];
		processing = true;
		errorMessage = '';

		try {
			const {
				data: { session }
			} = await supabase.auth.getSession();

			if (!session) {
				throw new Error('Not authenticated');
			}

			const formData = new FormData();
			formData.append('file', file);

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/intake/process`, {
				method: 'POST',
				headers: {
					Authorization: `Bearer ${session.access_token}`
				},
				body: formData
			});

			if (!response.ok) {
				const error = await response.json();
				throw new Error(error.detail || 'Failed to process intake form');
			}

			const result = await response.json();

			// Populate form with extracted data
			clientName = result.client_name;
			selectedPracticeAreas = result.practice_areas;
			qaPairs = result.qa_pairs.map((qa: any) => ({
				question: qa.question,
				answer: qa.answer
			}));
			rawContent = result.raw_content;
		} catch (error: any) {
			errorMessage = error.message || 'Failed to process intake form';
		} finally {
			processing = false;
			target.value = ''; // Reset file input
		}
	}

	function addQAPair() {
		qaPairs = [...qaPairs, { question: '', answer: '' }];
	}

	function removeQAPair(index: number) {
		qaPairs = qaPairs.filter((_, i) => i !== index);
	}

	function togglePracticeArea(area: string) {
		if (selectedPracticeAreas.includes(area)) {
			selectedPracticeAreas = selectedPracticeAreas.filter((a) => a !== area);
		} else {
			selectedPracticeAreas = [...selectedPracticeAreas, area];
		}
	}

	async function confirmAndAnalyze() {
		if (!clientName.trim()) {
			errorMessage = 'Client name is required';
			return;
		}

		if (qaPairs.length === 0) {
			errorMessage = 'At least one Q&A pair is required';
			return;
		}

		confirming = true;
		errorMessage = '';

		try {
			const {
				data: { session }
			} = await supabase.auth.getSession();

			if (!session) {
				throw new Error('Not authenticated');
			}

			// Save confirmed data
			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/intake/confirm`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`
				},
				body: JSON.stringify({
					case_id: caseId,
					client_name: clientName,
					practice_areas: selectedPracticeAreas,
					qa_pairs: qaPairs,
					raw_content: rawContent
				})
			});

			if (!response.ok) {
				const error = await response.json();
				throw new Error(error.detail || 'Failed to save intake data');
			}

			// Redirect back to case page to start analysis
			goto(`/app/cases/${caseId}?intake_confirmed=true`);
		} catch (error: any) {
			errorMessage = error.message || 'Failed to confirm intake data';
		} finally {
			confirming = false;
		}
	}
</script>

<div class="page-spacing">
	<!-- Header -->
	<div class="flex flex-col">
		<a href="/app/cases/{caseId}" class="text-accent hover:text-accent-hover font-bold flex items-center mb-4 transition-colors">
			<span class="mr-2">←</span> Back to Case
		</a>
		<h2 class="text-3xl font-heading font-bold text-contrast">Review Intake Form</h2>
		<p class="mt-2 text-sm text-gray-500 font-medium">
			Review and edit the information extracted from the intake form before starting analysis.
		</p>
	</div>

	{#if loading}
		<div class="flex items-center justify-center py-20">
			<div class="inline-block animate-spin rounded-full h-10 w-10 border-b-2 border-accent"></div>
			<span class="ml-4 text-gray-500 font-bold tracking-wide uppercase text-xs">Loading intake data...</span>
		</div>
	{:else}
		<!-- File Upload (if no data yet) -->
		{#if qaPairs.length === 0}
			<div class="card-standard">
				<h3 class="text-lg font-heading font-bold text-contrast mb-6">Upload Intake Form</h3>
				<div class="border-2 border-dashed border-gray-200 rounded-xl p-12 text-center bg-gray-50/50 hover:bg-gray-50 hover:border-accent/30 transition-all group">
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
					<div class="mt-6">
						<label class="cursor-pointer">
							<span class="btn btn-primary px-6 py-3 shadow-lg shadow-accent/20">
								Choose Intake File
							</span>
							<input
								type="file"
								accept=".pdf,.docx,.doc,.txt"
								onchange={handleFileUpload}
								class="hidden"
								disabled={processing}
							/>
						</label>
					</div>
					<p class="text-xs text-gray-400 mt-4 font-medium italic">Supported: PDF, DOCX, DOC, or TXT up to 50MB</p>
				</div>
				{#if processing}
					<div class="mt-8 flex flex-col items-center justify-center animate-fade-in-up">
						<div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-accent"></div>
						<span class="mt-3 text-xs font-bold text-accent uppercase tracking-widest">AI Extraction in progress...</span>
					</div>
				{/if}
			</div>
		{:else}
			<!-- Client Name -->
			<div class="card-standard">
				<h3 class="text-lg font-heading font-bold text-contrast mb-6">Client Information</h3>
				<div class="max-w-xl">
					<label for="client-name" class="block text-sm font-bold text-contrast mb-1.5">
						Client Name <span class="text-red-500">*</span>
					</label>
					<input
						id="client-name"
						type="text"
						bind:value={clientName}
						required
						class="input-standard focus:ring-accent"
						placeholder="John Doe"
					/>
				</div>
			</div>

			<!-- Practice Areas -->
			<div class="card-standard">
				<h3 class="text-lg font-heading font-bold text-contrast mb-2">Practice Areas</h3>
				<p class="text-sm text-gray-500 mb-6 font-medium">Select all relevant practice areas for this case:</p>
				<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
					{#each availablePracticeAreas as area}
						<label class="flex items-center p-4 border rounded-xl cursor-pointer transition-all {selectedPracticeAreas.includes(area) ? 'border-accent bg-accent/5 ring-1 ring-accent' : 'border-gray-200 hover:bg-gray-50'}">
							<input
								type="checkbox"
								checked={selectedPracticeAreas.includes(area)}
								onchange={() => togglePracticeArea(area)}
								class="h-4 w-4 text-accent focus:ring-accent border-gray-300 rounded transition-colors"
							/>
							<span class="ml-3 text-sm font-bold {selectedPracticeAreas.includes(area) ? 'text-accent' : 'text-contrast'}">{area}</span>
						</label>
					{/each}
				</div>
			</div>

			<!-- Q&A Pairs -->
			<div class="card-standard">
				<div class="flex justify-between items-center mb-8 border-b border-gray-100 pb-4">
					<h3 class="text-xl font-heading font-bold text-contrast">Questions & Answers</h3>
					<button
						onclick={addQAPair}
						class="btn btn-primary"
					>
						<Plus class="h-4 w-4 mr-2" />
						Add Q&A Pair
					</button>
				</div>

				<div class="space-y-6">
					{#each qaPairs as pair, index}
						<div class="border border-gray-200 rounded-xl p-6 bg-gray-50/30 hover:shadow-md transition-shadow relative group">
							<div class="flex justify-between items-start mb-4">
								<span class="text-[10px] font-black text-gray-400 uppercase tracking-widest bg-white px-2 py-1 rounded border border-gray-100">Entry #{index + 1}</span>
								<button
									onclick={() => removeQAPair(index)}
									class="text-gray-300 hover:text-red-600 transition-colors p-1"
									title="Remove this Q&A pair"
								>
									<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
										/>
									</svg>
								</button>
							</div>
							<div class="space-y-4">
								<div>
									<label class="block text-[10px] font-bold text-gray-500 uppercase mb-1.5 tracking-wider">Question</label>
									<input
										type="text"
										bind:value={pair.question}
										class="input-standard focus:ring-accent bg-white"
										placeholder="Enter question..."
									/>
								</div>
								<div>
									<label class="block text-[10px] font-bold text-gray-500 uppercase mb-1.5 tracking-wider">Extracted Answer</label>
									<textarea
										bind:value={pair.answer}
										rows="3"
										class="input-standard focus:ring-accent bg-white min-h-[80px]"
										placeholder="Enter answer..."
									></textarea>
								</div>
							</div>
						</div>
					{/each}

					{#if qaPairs.length === 0}
						<div class="text-center py-16 bg-gray-50 rounded-xl border-2 border-dashed border-gray-200">
							<p class="text-gray-400 font-medium italic">No Q&A pairs yet. Click "Add Q&A" to create one.</p>
						</div>
					{/if}
				</div>
			</div>

			<!-- Actions -->
			<div class="flex justify-end space-x-3 pt-4">
				<a
					href="/app/cases/{caseId}"
					class="btn btn-secondary"
				>
					Cancel
				</a>
				<button
					onclick={confirmAndAnalyze}
					disabled={confirming || !clientName.trim() || qaPairs.length === 0}
					class="btn btn-success px-6 py-2"
				>
					{#if confirming}
						<div class="animate-spin h-5 w-5 mr-2 border-2 border-white/30 border-t-white rounded-full"></div>
						Confirming...
					{:else}
						Confirm & Start Analysis
					{/if}
				</button>
			</div>
		{/if}
	{/if}

	{#if errorMessage}
		<div class="rounded-md bg-red-50 p-4">
			<p class="text-sm text-red-800">{errorMessage}</p>
		</div>
	{/if}
</div>

