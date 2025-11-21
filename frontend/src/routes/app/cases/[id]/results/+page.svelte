<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { PUBLIC_API_URL } from '$env/static/public';
	import { supabase } from '$lib/supabase';

	const caseId = $derived($page.params.id);
	
	let loading = $state(true);
	let results = $state<any>(null);
	let error = $state('');

	onMount(async () => {
		await loadResults();
	});

	async function loadResults() {
		try {
			const {
				data: { session }
			} = await supabase.auth.getSession();

			if (!session) {
				throw new Error('Not authenticated');
			}

		const response = await fetch(`${PUBLIC_API_URL}/api/analysis/results/${caseId}`, {
			headers: {
				Authorization: `Bearer ${session.access_token}`
			}
		});

		if (!response.ok) {
			throw new Error('Failed to load results');
		}

		const data = await response.json();
		
		// Parse case_analysis if it's a JSON string
		if (data.case_analysis && typeof data.case_analysis === 'string') {
			try {
				data.case_analysis = JSON.parse(data.case_analysis);
			} catch (e) {
				console.error('Failed to parse case_analysis:', e);
			}
		}
		
		// Parse document_summaries if it's a JSON string
		if (data.document_summaries && typeof data.document_summaries === 'string') {
			try {
				data.document_summaries = JSON.parse(data.document_summaries);
			} catch (e) {
				console.error('Failed to parse document_summaries:', e);
			}
		}
		
		// Debug: Check if citations are present
		console.log('DEBUG: Checking for citations in letters...');
		if (data.main_letter) {
			const citationCount = (data.main_letter.match(/\[Source:/g) || []).length;
			const statuteCount = (data.main_letter.match(/Fla\.\s*Stat\.\s*§/g) || []).length;
			console.log(`Main letter: ${citationCount} document citations, ${statuteCount} statute citations`);
		}
		if (data.main_letter_with_citations) {
			const citationCount = (data.main_letter_with_citations.match(/\[Source:/g) || []).length;
			const statuteCount = (data.main_letter_with_citations.match(/Fla\.\s*Stat\.\s*§/g) || []).length;
			console.log(`Cited letter: ${citationCount} document citations, ${statuteCount} statute citations`);
			console.log(`Letters are identical: ${data.main_letter === data.main_letter_with_citations}`);
		}
		
		results = data;
		} catch (err: any) {
			error = err.message;
		} finally {
			loading = false;
		}
	}
</script>

<div class="max-w-7xl mx-auto">
	<div class="mb-6">
		<button
			onclick={() => goto(`/app/cases/${caseId}`)}
			class="inline-flex items-center text-sm text-gray-600 hover:text-gray-900"
		>
			<svg class="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M15 19l-7-7 7-7"
				/>
			</svg>
			Back to Case
		</button>
	</div>

	{#if loading}
		<div class="flex items-center justify-center py-12">
			<div class="text-center">
				<svg
					class="animate-spin h-8 w-8 text-blue-600 mx-auto mb-4"
					fill="none"
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
				<p class="text-sm text-gray-600">Loading results...</p>
			</div>
		</div>
	{:else if error}
		<div class="bg-red-50 border border-red-200 rounded-lg p-6">
			<p class="text-red-800">{error}</p>
		</div>
	{:else if results}
		<!-- Case Analysis -->
		<div class="bg-white shadow rounded-lg p-6 mb-6">
			<h2 class="text-2xl font-bold text-gray-900 mb-6">Case Analysis</h2>

			{#if results.case_analysis}
				<div class="space-y-6">
					<!-- Case Summary -->
					{#if results.case_analysis.case_summary}
						<div>
							<h3 class="text-lg font-semibold text-gray-900 mb-3">Case Summary</h3>
							<div class="prose max-w-none">
								<p class="text-gray-700 whitespace-pre-wrap">{results.case_analysis.case_summary}</p>
							</div>
						</div>
					{/if}

					<!-- Practice Area -->
					{#if results.case_analysis.practice_area}
						<div>
							<h3 class="text-lg font-semibold text-gray-900 mb-3">Practice Area</h3>
							<span class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-blue-100 text-blue-800">
								{results.case_analysis.practice_area}
							</span>
						</div>
					{/if}

					<!-- Key Issues -->
					{#if results.case_analysis.key_issues && results.case_analysis.key_issues.length > 0}
						<div>
							<h3 class="text-lg font-semibold text-gray-900 mb-3">Key Issues</h3>
							<ul class="list-disc list-inside space-y-2">
								{#each results.case_analysis.key_issues as issue}
									<li class="text-gray-700">{issue}</li>
								{/each}
							</ul>
						</div>
					{/if}

					<!-- Relevant Statutes -->
					{#if results.case_analysis.relevant_statutes && results.case_analysis.relevant_statutes.length > 0}
						<div>
							<h3 class="text-lg font-semibold text-gray-900 mb-3">Relevant Statutes</h3>
							<div class="space-y-3">
								{#each results.case_analysis.relevant_statutes as statute}
									<div class="bg-gray-50 rounded-lg p-4">
										<p class="font-medium text-gray-900">{statute.statute}</p>
										<p class="text-sm text-gray-600 mt-1">{statute.relevance}</p>
									</div>
								{/each}
							</div>
						</div>
					{/if}

					<!-- Additional Details -->
					{#if results.case_analysis.additional_details}
						<div>
							<h3 class="text-lg font-semibold text-gray-900 mb-3">Additional Details</h3>
							<div class="prose max-w-none">
								<p class="text-gray-700 whitespace-pre-wrap">{results.case_analysis.additional_details}</p>
							</div>
						</div>
					{/if}
				</div>
			{/if}
		</div>

		<!-- Client Letter (Clean) -->
		{#if results.main_letter}
			<div class="bg-white shadow rounded-lg p-6 mb-6">
				<!-- Info Banner -->
				<div class="bg-blue-50 border-l-4 border-blue-400 p-4 mb-6 rounded">
					<div class="flex">
						<div class="flex-shrink-0">
							<svg class="h-5 w-5 text-blue-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
								<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd" />
							</svg>
						</div>
						<div class="ml-3">
							<p class="text-sm text-blue-700">
								<strong>Client-Ready Letter:</strong> Clean version without source citations - ready to send to the client.
							</p>
						</div>
					</div>
				</div>
				
				<div class="flex items-center justify-between mb-6">
					<h2 class="text-2xl font-bold text-gray-900">📧 Client Letter (Clean)</h2>
					<button
						onclick={() => {
							const blob = new Blob([results.main_letter], { type: 'text/html' });
							const url = URL.createObjectURL(blob);
							const a = document.createElement('a');
							a.href = url;
							a.download = `findings-letter-${caseId}.html`;
							a.click();
							URL.revokeObjectURL(url);
						}}
						class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
					>
						<svg class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
						</svg>
						Download
					</button>
				</div>
				
				<div class="border rounded-lg overflow-hidden bg-white">
					<iframe
						srcdoc={results.main_letter}
						title="Findings Letter"
						class="w-full h-[800px] border-0"
						sandbox="allow-same-origin"
					></iframe>
				</div>
			</div>
		{/if}

		<!-- Attorney Letter (With Citations) - Show if it exists and is different -->
		{#if results.main_letter_with_citations && results.main_letter_with_citations !== results.main_letter}
			<div class="bg-white shadow rounded-lg p-6 mb-6">
				<!-- Info Banner -->
				<div class="bg-orange-50 border-l-4 border-orange-400 p-4 mb-6 rounded">
					<div class="flex">
						<div class="flex-shrink-0">
							<svg class="h-5 w-5 text-orange-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
								<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd" />
							</svg>
						</div>
						<div class="ml-3">
							<p class="text-sm text-orange-700">
								<strong>Attorney Review Version:</strong> Contains inline source citations (Source: filename.pdf) for fact verification. Use this version to review the evidence supporting each statement.
							</p>
						</div>
					</div>
				</div>
				
				<div class="flex items-center justify-between mb-6">
					<h2 class="text-2xl font-bold text-gray-900">📚 Attorney Letter (With Citations)</h2>
					<button
						onclick={() => {
							const blob = new Blob([results.main_letter_with_citations], { type: 'text/html' });
							const url = URL.createObjectURL(blob);
							const a = document.createElement('a');
							a.href = url;
							a.download = `findings-letter-cited-${caseId}.html`;
							a.click();
							URL.revokeObjectURL(url);
						}}
						class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
					>
						<svg class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
						</svg>
						Download
					</button>
				</div>
				
				<div class="border rounded-lg overflow-hidden bg-white">
					<iframe
						srcdoc={results.main_letter_with_citations}
						title="Findings Letter with Citations"
						class="w-full h-[800px] border-0"
						sandbox="allow-same-origin"
					></iframe>
				</div>
			</div>
		{/if}

		<!-- Document Summaries -->
		{#if results.document_summaries && results.document_summaries.length > 0}
			<div class="bg-white shadow rounded-lg p-6 mb-6">
				<h2 class="text-2xl font-bold text-gray-900 mb-6">📄 Document Summaries</h2>

				<div class="space-y-6">
					{#each results.document_summaries as doc}
						<div class="border-l-4 border-blue-500 bg-gray-50 p-4 rounded-r-lg">
							<h3 class="text-lg font-semibold text-gray-900 mb-2">{doc.document_name}</h3>
							
							<!-- Document Type Badge -->
							{#if doc.document_type}
								<span class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-purple-100 text-purple-800 mb-3">
									{doc.document_type}
								</span>
							{/if}
							
							<!-- NEW: Executive Summary -->
							{#if doc.executive_summary}
								<div class="bg-blue-50 border border-blue-200 rounded-md p-3 mb-4">
									<p class="text-sm font-medium text-blue-900 mb-1">📋 Executive Summary</p>
									<p class="text-sm text-blue-800">{doc.executive_summary}</p>
								</div>
							{/if}
							
							<!-- NEW: Key Content (Primary Information) -->
							{#if doc.key_content}
								<div class="prose max-w-none mb-4">
									<h4 class="text-sm font-semibold text-gray-900 mb-2">Key Content:</h4>
									<p class="text-gray-700 whitespace-pre-wrap leading-relaxed">{doc.key_content}</p>
								</div>
							{/if}
							
							<!-- NEW: Important Details -->
							{#if doc.important_details && doc.important_details.length > 0}
								<div class="mt-4 bg-yellow-50 border border-yellow-200 rounded-md p-3">
									<h4 class="text-sm font-semibold text-yellow-900 mb-2">⚠️ Important Details:</h4>
									<ul class="list-disc list-inside space-y-1">
										{#each doc.important_details as detail}
											<li class="text-sm text-yellow-800">{detail}</li>
										{/each}
									</ul>
								</div>
							{/if}
							
							<!-- Structured Data Section (if present) -->
							{#if doc.structured_data}
								<div class="mt-4 pt-4 border-t border-gray-200">
									<h4 class="text-sm font-semibold text-gray-900 mb-3">📊 Structured Data:</h4>
									
									<!-- Parties -->
									{#if doc.structured_data.parties && doc.structured_data.parties.length > 0}
										<div class="mb-3">
											<p class="text-xs font-medium text-gray-500 uppercase mb-1">Parties:</p>
											<div class="flex flex-wrap gap-2">
												{#each doc.structured_data.parties as party}
													<span class="inline-flex items-center px-2 py-1 rounded text-xs bg-gray-100 text-gray-800">{party}</span>
												{/each}
											</div>
										</div>
									{/if}
									
									<!-- Dates -->
									{#if doc.structured_data.dates && doc.structured_data.dates.length > 0}
										<div class="mb-3">
											<p class="text-xs font-medium text-gray-500 uppercase mb-1">Key Dates:</p>
											<div class="space-y-1">
												{#each doc.structured_data.dates as date}
													<p class="text-sm text-gray-700">
														<span class="font-medium">{date.date}:</span> {date.event}
														{#if date.source}
															<span class="text-xs text-gray-500">({date.source})</span>
														{/if}
													</p>
												{/each}
											</div>
										</div>
									{/if}
									
									<!-- Amounts -->
									{#if doc.structured_data.amounts && doc.structured_data.amounts.length > 0}
										<div class="mb-3">
											<p class="text-xs font-medium text-gray-500 uppercase mb-1">Amounts:</p>
											<div class="space-y-1">
												{#each doc.structured_data.amounts as amount}
													<p class="text-sm text-gray-700">
														<span class="font-semibold text-green-700">{amount.amount}:</span> {amount.description}
														{#if amount.source}
															<span class="text-xs text-gray-500">({amount.source})</span>
														{/if}
													</p>
												{/each}
											</div>
										</div>
									{/if}
									
									<!-- Contract Clauses -->
									{#if doc.structured_data.contract_clauses && doc.structured_data.contract_clauses.length > 0}
										<div class="mb-3">
											<p class="text-xs font-medium text-gray-500 uppercase mb-1">Contract Clauses:</p>
											<div class="space-y-2">
												{#each doc.structured_data.contract_clauses as clause}
													<div class="text-sm">
														{#if clause.clause_id}
															<span class="font-medium text-gray-900">{clause.clause_id}:</span>
														{/if}
														{clause.description}
														{#if clause.snippet}
															<p class="text-xs text-gray-600 italic ml-4 mt-1">"{clause.snippet}"</p>
														{/if}
													</div>
												{/each}
											</div>
										</div>
									{/if}
								</div>
							{/if}
							
							<!-- LEGACY: Fallback for old format -->
							{#if !doc.key_content && doc.relevance_to_case}
								<div class="prose max-w-none mb-3">
									<p class="text-gray-700 whitespace-pre-wrap">{doc.relevance_to_case}</p>
								</div>
							{/if}
							
							<!-- Issues Identified (Legacy format) -->
							{#if doc.issues_identified && doc.issues_identified.length > 0 && !doc.important_details}
								<div class="mt-3">
									<h4 class="font-medium text-gray-900 mb-2">Issues Identified:</h4>
									<ul class="list-disc list-inside space-y-1">
										{#each doc.issues_identified as issue}
											<li class="text-sm text-gray-700">{issue}</li>
										{/each}
									</ul>
								</div>
							{/if}
							
							<!-- Key Dates (Legacy format) -->
							{#if doc.key_dates && doc.key_dates.length > 0 && !doc.structured_data}
								<div class="mt-3">
									<h4 class="font-medium text-gray-900 mb-2">Key Dates:</h4>
									<div class="space-y-1">
										{#each doc.key_dates as date}
											<p class="text-sm text-gray-700">
												<span class="font-medium">{date.date}:</span> {date.description || date.event}
											</p>
										{/each}
									</div>
								</div>
							{/if}
							
							<!-- Parties (Legacy format) -->
							{#if doc.parties && doc.parties.length > 0 && !doc.structured_data}
								<div class="mt-3">
									<h4 class="font-medium text-gray-900 mb-2">Parties:</h4>
									<div class="flex flex-wrap gap-2">
										{#each doc.parties as party}
											<span class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-blue-100 text-blue-800">
												{party}
											</span>
										{/each}
									</div>
								</div>
							{/if}
							
							<!-- Key Amounts -->
							{#if doc.key_amounts && doc.key_amounts.length > 0}
								<div class="mt-3">
									<h4 class="font-medium text-gray-900 mb-2">Key Amounts:</h4>
									<div class="space-y-1">
										{#each doc.key_amounts as amount}
											<p class="text-sm text-gray-700">
												<span class="font-medium">{amount.amount}:</span> {amount.description}
											</p>
										{/each}
									</div>
								</div>
							{/if}
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Intake Form Content -->
		{#if results.intake_form_content}
			<div class="bg-white shadow rounded-lg p-6 mb-6">
				<h2 class="text-2xl font-bold text-gray-900 mb-6">Intake Form Content</h2>
				<div class="prose max-w-none">
					<pre class="whitespace-pre-wrap text-sm text-gray-700 bg-gray-50 p-4 rounded-lg">{results.intake_form_content}</pre>
				</div>
			</div>
		{/if}

		<!-- Processing Notes -->
		{#if results.processing_notes}
			<div class="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
				<h3 class="text-lg font-semibold text-yellow-900 mb-3 flex items-center">
					<svg class="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
					</svg>
					Processing Notes
				</h3>
				<p class="text-yellow-800 whitespace-pre-wrap">{results.processing_notes}</p>
			</div>
		{/if}
	{/if}
</div>
