<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { PUBLIC_API_URL } from '$env/static/public';
	import { supabase } from '$lib/supabase';

	const caseId = $derived($page.params.id);

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

			// Check if already has intake metadata
			if (caseData.metadata?.intake_processed) {
				// Load existing data
				clientName = caseData.client_name || '';
				selectedPracticeAreas = caseData.metadata.practice_areas || [];
				qaPairs = caseData.metadata.qa_pairs || [];
				rawContent = caseData.metadata.raw_intake_content || '';
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

			const response = await fetch(`${PUBLIC_API_URL}/api/intake/process`, {
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
			const response = await fetch(`${PUBLIC_API_URL}/api/intake/confirm`, {
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

<div class="space-y-6">
	<!-- Header -->
	<div>
		<a href="/app/cases/{caseId}" class="text-blue-600 hover:text-blue-800 flex items-center mb-4">
			← Back to Case
		</a>
		<h2 class="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl">Review Intake Form</h2>
		<p class="mt-2 text-sm text-gray-600">
			Review and edit the information extracted from the intake form before starting analysis.
		</p>
	</div>

	{#if loading}
		<div class="flex items-center justify-center p-8">
			<div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
			<span class="ml-2 text-gray-600">Loading intake data...</span>
		</div>
	{:else}
		<!-- File Upload (if no data yet) -->
		{#if qaPairs.length === 0}
			<div class="bg-white shadow rounded-lg p-6">
				<h3 class="text-lg font-medium text-gray-900 mb-4">Upload Intake Form</h3>
				<div class="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
					<svg
						class="mx-auto h-12 w-12 text-gray-400"
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
					<div class="mt-4">
						<label class="cursor-pointer">
							<span class="text-blue-600 hover:text-blue-500 font-medium">Upload intake form</span>
							<input
								type="file"
								accept=".pdf,.docx,.doc,.txt"
								onchange={handleFileUpload}
								class="hidden"
								disabled={processing}
							/>
						</label>
					</div>
					<p class="text-xs text-gray-500 mt-2">PDF, DOCX, DOC, or TXT up to 50MB</p>
				</div>
				{#if processing}
					<div class="mt-4 flex items-center justify-center">
						<div class="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
						<span class="ml-2 text-sm text-gray-600">Processing intake form...</span>
					</div>
				{/if}
			</div>
		{:else}
			<!-- Client Name -->
			<div class="bg-white shadow rounded-lg p-6">
				<h3 class="text-lg font-medium text-gray-900 mb-4">Client Information</h3>
				<div>
					<label for="client-name" class="block text-sm font-medium text-gray-700">
						Client Name <span class="text-red-500">*</span>
					</label>
					<input
						id="client-name"
						type="text"
						bind:value={clientName}
						required
						class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
						placeholder="John Doe"
					/>
				</div>
			</div>

			<!-- Practice Areas -->
			<div class="bg-white shadow rounded-lg p-6">
				<h3 class="text-lg font-medium text-gray-900 mb-4">Practice Areas</h3>
				<p class="text-sm text-gray-600 mb-4">Select all relevant practice areas for this case:</p>
				<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
					{#each availablePracticeAreas as area}
						<label class="flex items-center p-3 border rounded-lg cursor-pointer hover:bg-gray-50 {selectedPracticeAreas.includes(area) ? 'border-blue-500 bg-blue-50' : 'border-gray-200'}">
							<input
								type="checkbox"
								checked={selectedPracticeAreas.includes(area)}
								onchange={() => togglePracticeArea(area)}
								class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
							/>
							<span class="ml-2 text-sm text-gray-900">{area}</span>
						</label>
					{/each}
				</div>
			</div>

			<!-- Q&A Pairs -->
			<div class="bg-white shadow rounded-lg p-6">
				<div class="flex justify-between items-center mb-4">
					<h3 class="text-lg font-medium text-gray-900">Questions & Answers</h3>
					<button
						onclick={addQAPair}
						class="inline-flex items-center px-3 py-1.5 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700"
					>
						<svg class="h-4 w-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
						</svg>
						Add Q&A
					</button>
				</div>

				<div class="space-y-4">
					{#each qaPairs as pair, index}
						<div class="border border-gray-200 rounded-lg p-4">
							<div class="flex justify-between items-start mb-2">
								<span class="text-sm font-medium text-gray-700">Q&A #{index + 1}</span>
								<button
									onclick={() => removeQAPair(index)}
									class="text-red-600 hover:text-red-800"
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
							<div class="space-y-2">
								<div>
									<label class="block text-xs font-medium text-gray-600 mb-1">Question</label>
									<input
										type="text"
										bind:value={pair.question}
										class="block w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
										placeholder="Enter question..."
									/>
								</div>
								<div>
									<label class="block text-xs font-medium text-gray-600 mb-1">Answer</label>
									<textarea
										bind:value={pair.answer}
										rows="3"
										class="block w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
										placeholder="Enter answer..."
									></textarea>
								</div>
							</div>
						</div>
					{/each}

					{#if qaPairs.length === 0}
						<div class="text-center py-8 text-gray-500">
							<p class="text-sm">No Q&A pairs yet. Click "Add Q&A" to create one.</p>
						</div>
					{/if}
				</div>
			</div>

			<!-- Actions -->
			<div class="flex justify-end space-x-3 pt-4">
				<a
					href="/app/cases/{caseId}"
					class="inline-flex items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
				>
					Cancel
				</a>
				<button
					onclick={confirmAndAnalyze}
					disabled={confirming || !clientName.trim() || qaPairs.length === 0}
					class="inline-flex items-center px-6 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 disabled:opacity-50 disabled:cursor-not-allowed"
				>
					{#if confirming}
						<svg
							class="animate-spin h-5 w-5 mr-2"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<circle
								class="opacity-25"
								cx="12"
								cy="12"
								r="10"
								stroke="currentColor"
								stroke-width="4"
							></circle>
							<path
								class="opacity-75"
								fill="currentColor"
								d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
							></path>
						</svg>
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

