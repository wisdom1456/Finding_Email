<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { getApiUrl } from '$lib/config';
	import { supabase } from '$lib/supabase';
	import { toastStore } from '$lib/stores/toastStore';
	import { slide } from 'svelte/transition';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { ArrowLeft } from 'lucide-svelte';
	import { parseMarkdown } from '$lib/utils/markdown';
	import type { PageData } from './$types';
	import { onMount } from 'svelte';
	import SkippedDocumentsAlert from '$lib/components/SkippedDocumentsAlert.svelte';

	// Get SSR data from load function
	let { data }: { data: PageData } = $props();

	const caseId = $derived(data.caseId);
	
	// Initialize state
	let results = $state<any>(null);
	let documents = $state<any[]>([]);
	let profile = $state<any>(null);
	let loading = $state(true);
	
	let activeTab = $state<'analysis' | 'documents' | 'letters' | 'chat' | 'quality'>('analysis');
	let findingsLetter = $state<string | null>(null);
	let demandLetters = $state<Record<string, string>>({});
	let generatingFindings = $state(false);
	let generatingDemand = $state(false);
	let selectedParty = $state('');
	let demandAmount = $state<number | null>(null);
	let demandDeadline = $state('10 business days');
	let specificDemands = $state('');
	let chatMessages = $state<Array<{ user: string; assistant: string }>>([]);
	let chatInput = $state('');
	let sendingMessage = $state(false);
	
	// Derived state (using $derived since results starts as null)
	let hasMultiStageSupport = $derived(!!results?.multi_stage_result);
	let multiStageError = $derived(results?.artifacts?.multi_stage_error);
	let opposingParties = $derived(results?.opposing_parties ?? []);
	let analysisStatus = $derived(results?.status ?? 'completed');
	let analysisCreatedAt = $derived(results?.created_at ? new Date(results.created_at) : new Date());
	let isStale = $derived(analysisStatus !== 'completed' || (new Date().getTime() - analysisCreatedAt.getTime() > 1000 * 60 * 60 * 24 * 7));
	let modelsUsed = $derived(results?.artifacts?.models_used ?? null);
	let skippedDocs = $derived(results?.artifacts?.skipped_documents ?? []);

	// Attorney information for letters
	let attorneyName = $state('');
	let firmName = $state('');
	let contactPhone = $state('');
	let contactEmail = $state('');
	let profileLoaded = $state(false);

	// Document viewer for quality report
	let viewingDocument = $state<any>(null);
	let pdfBlobUrl = $state<string | null>(null);
	let loadingPdf = $state(false);

	// Collapsible document analysis state
	let collapsedDocs = $state<Set<string>>(new Set());

	// Initialize from streamed data
	onMount(async () => {
		try {
			// Start loading streamed data
			const [resultsVal, docsVal, profileVal] = await Promise.all([
				data.streamed.results,
				data.streamed.documents,
				data.streamed.profile
			]);

			documents = docsVal;
			profile = profileVal;
			
			if (profileVal) {
				attorneyName = profileVal.full_name || '';
				firmName = profileVal.firm_name || '';
				contactPhone = profileVal.phone || '';
				contactEmail = profileVal.email || '';
				profileLoaded = true;
			}

			// Process results
			let res = resultsVal;
			
			// Parse case_analysis if it's a JSON string
			if (res.case_analysis && typeof res.case_analysis === 'string') {
				try {
					res.case_analysis = JSON.parse(res.case_analysis);
				} catch (e) {
					console.error('Failed to parse case_analysis:', e);
				}
			}

			// Parse document_summaries if it's a JSON string
			if (res.document_summaries && typeof res.document_summaries === 'string') {
				try {
					res.document_summaries = JSON.parse(res.document_summaries);
				} catch (e) {
					console.error('Failed to parse document_summaries:', e);
				}
			}

			// Parse generated letters
			if (res.generated_letters) {
				if (res.generated_letters.findings) {
					findingsLetter = res.generated_letters.findings;
				}
				const demandEntries = Object.entries(res.generated_letters).filter(([key]) =>
					key.startsWith('demand_')
				);
				if (demandEntries.length) {
					demandLetters = demandEntries.reduce<Record<string, string>>((acc, [key, value]) => {
						const partyName = key.replace('demand_', '').replace(/_/g, ' ');
						acc[partyName] = value as string;
						return acc;
					}, {});
				}
			}

			// Pre-fill demand letter fields
			if (res.opposing_parties && res.opposing_parties.length > 0) {
				selectedParty = res.opposing_parties[0].name;
			}

			// Try to find demand amount from various sources
			let foundAmount = false;

			// 1. Try multi_stage_result first
			if (res.multi_stage_result) {
				const factMatrix = res.multi_stage_result.fact_matrix || {};
				const financialData = factMatrix.financial_data || [];
				const claimedAmount = financialData.find(
					(item: any) => item.payment_type === 'claimed' || item.category === 'damages_claimed'
				);

				if (claimedAmount?.amount) {
					demandAmount = claimedAmount.amount;
					foundAmount = true;
				} else {
					const owedAmount = financialData.find(
						(item: any) =>
							item.payment_type === 'owed' ||
							item.description?.toLowerCase().includes('owed') ||
							item.description?.toLowerCase().includes('damage')
					);
					if (owedAmount?.amount) {
						demandAmount = owedAmount.amount;
						foundAmount = true;
					}
				}

				const issueMap = res.multi_stage_result.issue_map || {};
				const primaryIssues = issueMap.primary_issues || [];
				if (primaryIssues.length > 0) {
					specificDemands = primaryIssues
						.map((issue: any) => `Resolve the issue of ${issue.issue_name} by providing appropriate remedies.`)
						.join('\n');
				} else {
					specificDemands = 'Provide full and timely compliance with all outstanding obligations.';
				}
			}

			// 2. Fall back to case_analysis financial_impact
			if (!foundAmount && typeof res.case_analysis === 'object') {
				const financialText = res.case_analysis.intake_analysis?.financial_impact;
				if (financialText) {
					const amountMatch = financialText.match(/\$[\d,]+(?:\.\d{2})?/);
					if (amountMatch) {
						const amountStr = amountMatch[0].replace(/[$,]/g, '');
						demandAmount = parseFloat(amountStr);
						foundAmount = true;
					}
				}
			}

			// 3. Fall back to document summaries key_amounts
			if (!foundAmount && res.document_summaries && Array.isArray(res.document_summaries)) {
				for (const doc of res.document_summaries) {
					if (doc.key_amounts && Array.isArray(doc.key_amounts)) {
						for (const amount of doc.key_amounts) {
							if (
								amount.description?.toLowerCase().includes('damage') ||
								amount.description?.toLowerCase().includes('owed') ||
								amount.description?.toLowerCase().includes('claim')
							) {
								const amountStr = amount.amount?.replace(/[$,]/g, '');
								if (amountStr) {
									demandAmount = parseFloat(amountStr);
									foundAmount = true;
									break;
								}
							}
						}
						if (foundAmount) break;
					}
				}
			}

			// Initialize all documents as collapsed
			const newCollapsed = new Set<string>();
			if (Array.isArray(res.document_summaries) && res.document_summaries.length > 0) {
				res.document_summaries.forEach((doc: any) => {
					newCollapsed.add(doc.document_name);
				});
			}
			collapsedDocs = newCollapsed;
			
			results = res;
		} catch (err) {
			console.error('Error processing results:', err);
		} finally {
			loading = false;
		}
	});

	// Demand calculation state
	let calculatingAmount = $state(false);
	let calculationReasoning = $state('');
	let calculationBreakdown = $state<Array<{ description: string; amount: number }>>([]);

	function toggleDoc(docName: string) {
		const newSet = new Set(collapsedDocs);
		if (newSet.has(docName)) {
			newSet.delete(docName);
		} else {
			newSet.add(docName);
		}
		collapsedDocs = newSet;
	}

	async function viewDocument(documentName: string, documentId?: string) {
		// Priority 1: Use document_id if available
		let doc = documentId 
			? documents.find((d) => d.id === documentId)
			: null;
		
		// Priority 2: Exact file_name match
		if (!doc) {
			doc = documents.find((d) => d.file_name === documentName);
		}
		
		// Priority 3: Case-insensitive match
		if (!doc) {
			const lowerName = documentName.toLowerCase();
			doc = documents.find((d) => d.file_name.toLowerCase() === lowerName);
		}
		
		// Priority 4: Basename match (partial)
		if (!doc) {
			const baseName = documentName.split('/').pop()?.toLowerCase();
			if (baseName) {
				doc = documents.find((d) => 
					d.file_name.toLowerCase().includes(baseName) || 
					baseName.includes(d.file_name.toLowerCase())
				);
			}
		}

		if (!doc) {
			toastStore.error(`Document "${documentName}" not found`);
			return;
		}
		
		viewingDocument = doc;
		loadingPdf = true;

		// Clean up previous blob URL if it exists
		if (pdfBlobUrl) {
			URL.revokeObjectURL(pdfBlobUrl);
			pdfBlobUrl = null;
		}

		try {
			// Check if it's a PDF or image - need to download as blob
			const isPdf = doc.file_type === 'application/pdf' || doc.file_name.toLowerCase().endswith('.pdf');
			const isImage = doc.file_type?.startsWith('image/');

			if ((isPdf || isImage) && doc.storage_path) {
				// Download from storage
				const {
					data: { session }
				} = await supabase.auth.getSession();

				if (!session) {
					console.error('Not authenticated');
					return;
				}

				const { data, error } = await supabase.storage
					.from('documents')
					.download(doc.storage_path);

				if (error) throw error;

				// Create blob URL for PDF or image
				pdfBlobUrl = URL.createObjectURL(data);
			}
		} catch (error: any) {
			console.error('Failed to load document preview:', error);
		} finally {
			loadingPdf = false;
		}
	}

	function closeDocumentViewer() {
		viewingDocument = null;
		if (pdfBlobUrl) {
			URL.revokeObjectURL(pdfBlobUrl);
			pdfBlobUrl = null;
		}
	}

	async function generateFindingsLetter() {
		generatingFindings = true;
		await generateLetterRequest({
			letter_type: 'findings',
			attorney_name: attorneyName || undefined,
			firm_name: firmName || undefined,
			contact_phone: contactPhone || undefined,
			contact_email: contactEmail || undefined
		});
		generatingFindings = false;
	}

	async function calculateDemandAmount() {
		if (!selectedParty) {
			alert('Please select an opposing party first');
			return;
		}

		calculatingAmount = true;
		calculationReasoning = '';
		calculationBreakdown = [];

		try {
			const {
				data: { session }
			} = await supabase.auth.getSession();

			if (!session) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/analysis/calculate-demand-amount`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`
				},
				body: JSON.stringify({
					case_id: caseId,
					target_party_name: selectedParty
				})
			});

			if (!response.ok) {
				const detail = await response.json().catch(() => ({}));
				throw new Error(detail?.detail || 'Failed to calculate demand amount');
			}

			const data = await response.json();
			demandAmount = data.amount;
			calculationReasoning = data.reasoning;
			calculationBreakdown = data.breakdown || [];
		} catch (err: any) {
			alert(err.message || 'Failed to calculate demand amount');
			console.error('Demand calculation error:', err);
		} finally {
			calculatingAmount = false;
		}
	}

	async function generateDemandLetter() {
		if (!selectedParty) {
			alert('Please select an opposing party');
			return;
		}

		const demandLines = specificDemands
			.split('\n')
			.map((line) => line.trim())
			.filter(Boolean);

		generatingDemand = true;
		await generateLetterRequest({
			letter_type: 'demand',
			target_party_name: selectedParty,
			demand_amount: demandAmount ?? undefined,
			demand_deadline: demandDeadline,
			specific_demands: demandLines,
			attorney_name: attorneyName || undefined,
			firm_name: firmName || undefined,
			contact_phone: contactPhone || undefined,
			contact_email: contactEmail || undefined
		});
		generatingDemand = false;
	}

	async function generateLetterRequest(body: Record<string, any>) {
		try {
			const {
				data: { session }
			} = await supabase.auth.getSession();
			// ... (rest of function)

			if (!session) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/analysis/generate-letter`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`
				},
				body: JSON.stringify({
					case_id: caseId,
					...body
				})
			});

			if (!response.ok) {
				const detail = await response.json().catch(() => ({}));
				throw new Error(detail?.detail || 'Failed to generate letter');
			}

			const data = await response.json();
			if (data.letter_type === 'findings') {
				findingsLetter = data.letter_html;
			} else if (data.target_party_name) {
				demandLetters = {
					...demandLetters,
					[data.target_party_name]: data.letter_html
				};
			}
		} catch (err: any) {
			alert(err.message || 'Letter generation failed');
		}
	}

	async function sendChatMessage() {
		if (!chatInput.trim()) return;

		const message = chatInput.trim();
		chatInput = '';
		sendingMessage = true;

		chatMessages = [...chatMessages, { user: message, assistant: '...' }];

		try {
			const {
				data: { session }
			} = await supabase.auth.getSession();
			if (!session) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/analysis/chat`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`
				},
				body: JSON.stringify({ case_id: caseId, message })
			});

			if (!response.ok) {
				const detail = await response.json().catch(() => ({}));
				throw new Error(detail?.detail || 'Chat request failed');
			}

			const data: ChatMessageResponse = await response.json();
			chatMessages = chatMessages.map((entry, idx, arr) => {
				if (idx === arr.length - 1) {
					return { ...entry, assistant: data.response };
				}
				return entry;
			});
		} catch (err: any) {
			alert(err.message || 'Chat failed');
			chatMessages = chatMessages.slice(0, -1);
		} finally {
			sendingMessage = false;
		}
	}

	type ChatMessageResponse = {
		response: string;
		context_used?: Record<string, any>;
	};

	function downloadLetter(letter: string, filename: string) {
		// Unescape newline characters for proper HTML formatting
		const cleanedLetter = letter.replace(/\\n/g, '\n');
		const blob = new Blob([cleanedLetter], { type: 'text/html' });
		const url = URL.createObjectURL(blob);
		const link = document.createElement('a');
		link.href = url;
		link.download = filename;
		link.click();
		URL.revokeObjectURL(url);
	}
</script>

<!-- Back Button -->
<button
	onclick={() => goto(`/app/cases/${caseId}`)}
	class="inline-flex items-center text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors mb-6"
>
	<ArrowLeft class="h-4 w-4 mr-2" />
	Back to Case
</button>

<PageHeader
	title="Analysis Results"
	breadcrumbs={[
		{ label: 'Dashboard', href: '/app' },
		{ label: 'Cases', href: '/app/cases' },
		{ label: 'Case Details', href: `/app/cases/${caseId}` },
		{ label: 'Results' }
	]}
>

		{#snippet children()}
			<!-- AI Models Info -->
			{#if modelsUsed}
				<div class="flex items-center gap-2">
					<span class="text-xs text-gray-500">AI Models:</span>
					<div class="flex gap-2 flex-wrap">
						{#if modelsUsed.document_analysis}
							<span class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-accent/10 text-accent border border-accent/30" title="Document Analysis">
								<svg class="h-3 w-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
								</svg>
								{modelsUsed.document_analysis}
							</span>
						{/if}
						{#if modelsUsed.letter_generation}
							<span class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-green-50 text-green-700 border border-green-200" title="Letter Generation">
								<svg class="h-3 w-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
								</svg>
								{modelsUsed.letter_generation}
							</span>
						{/if}
						{#if modelsUsed.multi_stage_analysis}
							<span class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-purple-50 text-purple-700 border border-purple-200" title="Multi-Stage Analysis">
								<svg class="h-3 w-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
								</svg>
								{modelsUsed.multi_stage_analysis}
							</span>
						{/if}
					</div>
				</div>
			{/if}
		{/snippet}
	</PageHeader>

	{#if loading}
		<div class="flex flex-col items-center justify-center py-20">
			<div class="animate-spin rounded-full h-12 w-12 border-b-2 border-accent"></div>
			<p class="mt-4 text-gray-500 font-medium">Loading and preparing analysis results...</p>
		</div>
	{:else if analysisStatus !== 'completed'}
		<div class="mb-6 p-4 rounded-lg {analysisStatus === 'error' ? 'bg-red-50 border border-red-200' : 'bg-blue-50 border border-blue-200'}">
			<div class="flex items-center">
				{#if analysisStatus === 'error'}
					<svg class="h-5 w-5 text-red-400 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
					</svg>
					<div>
						<h3 class="text-sm font-medium text-red-800">Latest analysis attempt failed</h3>
						<p class="text-sm text-red-700 mt-1">
							The most recent analysis failed with error: {results?.error || 'Unknown error'}. 
							Showing results from a previous successful analysis if available.
						</p>
					</div>
				{:else}
					<div class="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600 mr-3"></div>
					<div>
						<h3 class="text-sm font-medium text-blue-800">Analysis in progress</h3>
						<p class="text-sm text-blue-700 mt-1">
							A new analysis is currently running. These results may be outdated. 
							Please wait for the current analysis to complete for the latest insights.
						</p>
					</div>
				{/if}
			</div>
			<div class="mt-3">
				<button
					onclick={() => goto(`/app/cases/${caseId}`)}
					class="text-sm font-medium {analysisStatus === 'error' ? 'text-red-800 hover:text-red-900' : 'text-blue-800 hover:text-blue-900'} underline"
				>
					Return to Case Details to check progress
				</button>
			</div>
		</div>
	{/if}

	{#if !loading && skippedDocs.length > 0}
		<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-6">
			<SkippedDocumentsAlert {skippedDocs} />
		</div>
	{/if}

	{#if results}
		<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
			<div class="border-b border-gray-200 mb-6">
			<nav class="-mb-px flex flex-wrap gap-4">
				<button
					class={`py-4 px-1 border-b-2 text-sm font-medium ${
						activeTab === 'analysis'
							? 'border-accent text-accent'
							: 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
					}`}
					onclick={() => (activeTab = 'analysis')}
				>
					Case Analysis
				</button>
				<button
					class={`py-4 px-1 border-b-2 text-sm font-medium ${
						activeTab === 'documents'
							? 'border-accent text-accent'
							: 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
					}`}
					onclick={() => (activeTab = 'documents')}
				>
					Document Review
				</button>
				<button
					class={`py-4 px-1 border-b-2 text-sm font-medium ${
						activeTab === 'letters'
							? 'border-accent text-accent'
							: 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
					}`}
					onclick={() => (activeTab = 'letters')}
				>
					Generate Letters
				</button>
				<button
					class={`py-4 px-1 border-b-2 text-sm font-medium ${
						activeTab === 'chat'
							? 'border-accent text-accent'
							: 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
					}`}
					onclick={() => (activeTab = 'chat')}
				>
					Case Chat
				</button>
				<button
					class={`py-4 px-1 border-b-2 text-sm font-medium ${
						activeTab === 'quality'
							? 'border-accent text-accent'
							: 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
					}`}
					onclick={() => (activeTab = 'quality')}
				>
					Quality Report
				</button>
			</nav>
		</div>

		{#if activeTab === 'analysis'}
			<div class="bg-white shadow rounded-lg p-6 mb-6">
				<h2 class="text-2xl font-bold text-gray-900 mb-6">Case Analysis</h2>
				{#if results.case_analysis}
					<div class="space-y-6">
						{#if results.case_analysis.case_summary}
							<section>
								<h3 class="text-lg font-semibold text-gray-900 mb-3">Case Summary</h3>
								<p class="text-gray-700 whitespace-pre-wrap">{results.case_analysis.case_summary}</p>
							</section>
						{/if}
						{#if results.case_analysis.practice_area}
							<section>
								<h3 class="text-lg font-semibold text-gray-900 mb-3">Practice Area</h3>
								<span class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-accent/20 text-contrast">
									{results.case_analysis.practice_area}
								</span>
							</section>
						{/if}
						{#if results.case_analysis.key_issues && results.case_analysis.key_issues.length > 0}
							<section>
								<h3 class="text-lg font-semibold text-gray-900 mb-3">Key Issues</h3>
								<ul class="list-disc list-inside space-y-2 text-gray-700">
									{#each results.case_analysis.key_issues as issue}
										<li>{issue}</li>
									{/each}
								</ul>
							</section>
						{/if}
						{#if results.case_analysis.relevant_statutes && results.case_analysis.relevant_statutes.length > 0}
							<section>
								<h3 class="text-lg font-semibold text-gray-900 mb-3">Relevant Statutes</h3>
								<div class="space-y-3">
									{#each results.case_analysis.relevant_statutes as statute}
										<div class="bg-gray-50 rounded-lg p-4">
											<p class="font-medium text-gray-900">{statute.statute}</p>
											<p class="text-sm text-gray-600 mt-1">{statute.relevance}</p>
										</div>
									{/each}
								</div>
							</section>
						{/if}
						{#if results.case_analysis.additional_details}
							<section>
								<h3 class="text-lg font-semibold text-gray-900 mb-3">Additional Details</h3>
								<p class="text-gray-700 whitespace-pre-wrap">{results.case_analysis.additional_details}</p>
							</section>
						{/if}
					</div>
				{:else}
					<p class="text-gray-500">No case analysis available.</p>
				{/if}
			</div>
		{:else if activeTab === 'documents'}
			{#if results.document_summaries && results.document_summaries.length > 0}
				<div class="bg-white shadow rounded-lg p-6 mb-6">
					<h2 class="text-2xl font-bold text-gray-900 mb-6">📄 Document Analysis</h2>
					<div class="space-y-6">
						{#each results.document_summaries as doc}
							<div class="border border-gray-300 rounded-lg overflow-hidden">
								<!-- Clickable Header -->
								<button
									onclick={() => toggleDoc(doc.document_name)}
									class="w-full bg-gradient-to-r from-accent/10 to-accent/20 p-4 border-b border-gray-300 hover:from-accent/20 hover:to-accent/30 transition-colors text-left"
								>
									<div class="flex items-center justify-between">
										<div class="flex-1">
											<div class="flex items-center gap-3 mb-2">
												<!-- Expand/Collapse Icon -->
												<svg 
													class="w-5 h-5 text-gray-600 transition-transform {collapsedDocs.has(doc.document_name) ? '' : 'rotate-90'}"
													fill="none" 
													viewBox="0 0 24 24" 
													stroke="currentColor"
												>
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
												</svg>
												<h3 class="text-lg font-semibold text-gray-900">{doc.document_name}</h3>
											</div>
											<div class="flex flex-wrap gap-2 ml-8">
												{#if doc.document_type}
													<span class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-purple-100 text-purple-800">
														{doc.document_type}
													</span>
												{/if}
												{#if doc.extraction_quality}
													<span class={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${
														doc.extraction_quality === 'high' ? 'bg-green-100 text-green-800' : 
														doc.extraction_quality === 'medium' ? 'bg-yellow-100 text-yellow-800' : 'bg-red-100 text-red-800'
													}`}>
														Quality: {doc.extraction_quality}
													</span>
												{/if}
												{#if doc.relevance_to_case}
													<span class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-green-100 text-green-800">
														Relevant
													</span>
												{/if}
											</div>
										</div>
									</div>
								</button>

								<!-- Collapsible Content -->
								{#if !collapsedDocs.has(doc.document_name)}
									<div transition:slide class="p-4 space-y-4 border-t border-gray-200">
									<!-- Executive Summary -->
									{#if doc.executive_summary}
										<div>
											<p class="text-sm text-gray-800 leading-relaxed italic">{doc.executive_summary}</p>
										</div>
									{/if}

									<!-- Key Content -->
									{#if doc.key_content}
										<div class="bg-gray-50 rounded-lg p-3 border border-gray-200">
											<p class="text-xs font-semibold text-gray-700 uppercase mb-2">Key Content</p>
											<p class="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">{doc.key_content}</p>
										</div>
									{/if}

									<!-- Key Quotes (Evidence) -->
									{#if doc.key_quotes && doc.key_quotes.length > 0}
										<div>
											<p class="text-xs font-semibold text-accent uppercase mb-2">Evidence Quotes</p>
											<div class="space-y-2">
												{#each doc.key_quotes as quote}
													<blockquote class="border-l-4 border-accent pl-4 py-2 bg-accent/10 rounded-r italic text-sm text-gray-800">
														"{quote}"
													</blockquote>
												{/each}
											</div>
										</div>
									{/if}

									<!-- Statute Citations -->
									{#if doc.statute_citations && doc.statute_citations.length > 0}
										<div>
											<p class="text-xs font-semibold text-purple-800 uppercase mb-2">Relevant Statutes</p>
											<div class="flex flex-wrap gap-2">
												{#each doc.statute_citations as statute}
													<span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-800 border border-purple-300">
														⚖️ {statute}
													</span>
												{/each}
											</div>
										</div>
									{/if}

									<!-- Important Details -->
									{#if doc.important_details && doc.important_details.length > 0}
										<div>
											<p class="text-xs font-semibold text-orange-800 uppercase mb-2">Important Details</p>
											<ul class="list-disc list-inside space-y-1">
												{#each doc.important_details as detail}
													<li class="text-sm text-gray-700">{detail}</li>
												{/each}
											</ul>
										</div>
									{/if}

									<!-- Legal Significance -->
									{#if doc.legal_significance}
										<div class="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
											<p class="text-xs font-semibold text-yellow-900 uppercase mb-1">Legal Significance</p>
											<p class="text-sm text-gray-800">{doc.legal_significance}</p>
										</div>
									{/if}

									<!-- Structured Data (Dates, Amounts, Parties) -->
									<div class="grid grid-cols-1 md:grid-cols-3 gap-4 pt-3 border-t border-gray-200">
										{#if doc.key_dates && doc.key_dates.length > 0}
											<div>
												<p class="text-xs font-semibold text-gray-600 uppercase mb-2">Key Dates</p>
												<ul class="space-y-1">
													{#each doc.key_dates as date}
														<li class="text-xs text-gray-700">
															<span class="font-medium">{date.date}</span><br />
															{date.event}
														</li>
													{/each}
												</ul>
											</div>
										{/if}

										{#if doc.key_amounts && doc.key_amounts.length > 0}
											<div>
												<p class="text-xs font-semibold text-gray-600 uppercase mb-2">Key Amounts</p>
												<ul class="space-y-1">
													{#each doc.key_amounts as amount}
														<li class="text-xs text-gray-700">
															<span class="font-medium">{amount.amount}</span><br />
															{amount.description}
														</li>
													{/each}
												</ul>
											</div>
										{/if}

										{#if doc.parties && doc.parties.length > 0}
											<div>
												<p class="text-xs font-semibold text-gray-600 uppercase mb-2">Parties</p>
												<div class="flex flex-wrap gap-1">
													{#each doc.parties as party}
														<span class="inline-flex items-center px-2 py-1 rounded text-xs bg-gray-200 text-gray-700">{party}</span>
													{/each}
												</div>
											</div>
										{/if}
									</div>
								</div>
								{/if}
							</div>
						{/each}
					</div>
				</div>
			{:else}
				<p class="text-gray-500">No document summaries available.</p>
			{/if}
		{:else if activeTab === 'letters'}
			<div class="space-y-8">
				{#if !hasMultiStageSupport}
					<div class="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
						<p class="text-yellow-900">
							{#if multiStageError}
								<strong>⚠️ Advanced analysis failed:</strong> {multiStageError}.
								Letter generation is unavailable for this specific analysis run.
							{:else}
								On-demand letters are unavailable because this case was processed with an older workflow.
							{/if}
							Please re-run analysis to enable this feature.
						</p>
					</div>
				{:else}
					<section class="bg-white shadow rounded-lg p-6">
						<div class="flex items-center justify-between mb-4">
							<div>
								<h3 class="text-xl font-semibold text-gray-900">Findings Letter</h3>
								<p class="text-sm text-gray-600">Generate a client-ready findings letter on demand.</p>
							</div>
							<button
								class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-accent hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent"
								onclick={generateFindingsLetter}
								disabled={generatingFindings}
							>
								{generatingFindings ? 'Generating…' : 'Generate Letter'}
							</button>
						</div>
						{#if findingsLetter}
							<div class="space-y-4">
								<div class="flex justify-end">
									<button
										class="inline-flex items-center px-3 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent"
										onclick={() => downloadLetter(findingsLetter!, `findings-letter-${caseId}.html`)}
									>
										Download
									</button>
								</div>
								<div class="border rounded-lg overflow-hidden bg-white">
									<iframe srcdoc={findingsLetter.replace(/\\n/g, '\n')} title="Findings Letter" class="w-full h-[600px] border-0" sandbox="allow-same-origin"></iframe>
								</div>
							</div>
						{:else}
							<p class="text-gray-500 text-sm">No findings letter generated yet.</p>
						{/if}
					</section>

					<section class="bg-white shadow rounded-lg p-6">
						<h3 class="text-xl font-semibold text-gray-900 mb-4">Demand Letter</h3>
						<div class="grid gap-4 md:grid-cols-2">
							<div>
								<label class="block text-sm font-medium text-gray-700 mb-1">Opposing Party</label>
								<select
									bind:value={selectedParty}
									class="block w-full rounded-md border-gray-300 shadow-sm focus:border-accent focus:ring-accent text-sm"
								>
									<option value="">Select party</option>
									{#each opposingParties as party}
										<option value={party.name}>{party.name} ({party.role})</option>
									{/each}
								</select>
							</div>
						<div>
							<label class="block text-sm font-medium text-gray-700 mb-1">Demand Amount ($)</label>
							<div class="flex gap-2">
								<input
									type="number"
									class="block w-full rounded-md border-gray-300 shadow-sm focus:border-accent focus:ring-accent text-sm"
									min="0"
									step="100"
									bind:value={demandAmount}
								/>
								<button
									type="button"
									onclick={calculateDemandAmount}
									disabled={!selectedParty || calculatingAmount}
									class="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap text-sm font-medium"
									title={!selectedParty ? "Please select an opposing party first" : "Calculate suggested demand amount based on case analysis"}
								>
									{calculatingAmount ? 'Calculating...' : 'Calculate'}
								</button>
							</div>
							{#if calculationReasoning}
								<div class="mt-2 p-3 bg-accent/10 border border-accent/30 rounded-md">
									<p class="text-sm text-contrast font-medium">AI Calculation:</p>
									<p class="text-sm text-gray-700 mt-1">{calculationReasoning}</p>
									{#if calculationBreakdown && calculationBreakdown.length > 0}
										<details class="mt-2">
											<summary class="text-xs text-accent cursor-pointer hover:text-accent-hover">View breakdown</summary>
											<ul class="mt-2 space-y-1">
												{#each calculationBreakdown as item}
													<li class="text-xs text-gray-700 flex justify-between">
														<span>{item.description}</span>
														<span class="font-mono">${item.amount.toLocaleString()}</span>
													</li>
												{/each}
											</ul>
										</details>
									{/if}
								</div>
							{/if}
						</div>
							<div>
								<label class="block text-sm font-medium text-gray-700 mb-1">Response Deadline</label>
								<select
									class="block w-full rounded-md border-gray-300 shadow-sm focus:border-accent focus:ring-accent text-sm"
									bind:value={demandDeadline}
								>
									<option>10 business days</option>
									<option>14 days</option>
									<option>30 days</option>
								</select>
							</div>
						</div>

						<!-- Attorney Information Section -->
						<div class="mt-6 border-t pt-6">
							<h4 class="text-lg font-medium text-gray-900 mb-4">Attorney Information</h4>
							<div class="grid gap-4 md:grid-cols-2">
								<div>
									<label class="block text-sm font-medium text-gray-700 mb-1">
										Attorney Name
										{#if profileLoaded && attorneyName}
											<span class="text-xs text-gray-500 ml-1">(from profile)</span>
										{/if}
									</label>
									<input
										type="text"
										bind:value={attorneyName}
										class="block w-full rounded-md border-gray-300 shadow-sm focus:border-accent focus:ring-accent text-sm"
										placeholder="Attorney name"
									/>
								</div>
								<div>
									<label class="block text-sm font-medium text-gray-700 mb-1">
										Firm Name
										{#if profileLoaded && firmName}
											<span class="text-xs text-gray-500 ml-1">(from profile)</span>
										{/if}
									</label>
									<input
										type="text"
										bind:value={firmName}
										class="block w-full rounded-md border-gray-300 shadow-sm focus:border-accent focus:ring-accent text-sm"
										placeholder="Firm name"
									/>
								</div>
								<div>
									<label class="block text-sm font-medium text-gray-700 mb-1">
										Contact Phone
										{#if profileLoaded && contactPhone}
											<span class="text-xs text-gray-500 ml-1">(from profile)</span>
										{/if}
									</label>
									<input
										type="tel"
										bind:value={contactPhone}
										class="block w-full rounded-md border-gray-300 shadow-sm focus:border-accent focus:ring-accent text-sm"
										placeholder="Phone number"
									/>
								</div>
								<div>
									<label class="block text-sm font-medium text-gray-700 mb-1">
										Contact Email
										{#if profileLoaded && contactEmail}
											<span class="text-xs text-gray-500 ml-1">(from profile)</span>
										{/if}
									</label>
									<input
										type="email"
										bind:value={contactEmail}
										class="block w-full rounded-md border-gray-300 shadow-sm focus:border-accent focus:ring-accent text-sm"
										placeholder="Email address"
									/>
								</div>
							</div>
						</div>

						<div class="mt-6 grid gap-4 md:grid-cols-2">
							<div>
								<label class="block text-sm font-medium text-gray-700 mb-1">Specific Demands (one per line)</label>
								<textarea
									class="block w-full rounded-md border-gray-300 shadow-sm focus:border-accent focus:ring-accent text-sm"
									rows="4"
									bind:value={specificDemands}
								></textarea>
							</div>
						</div>
						<div class="mt-4 flex justify-end">
							<button
								class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-accent hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent"
								onclick={generateDemandLetter}
								disabled={generatingDemand || !selectedParty}
							>
								{generatingDemand ? 'Generating…' : `Generate Letter to ${selectedParty || 'Party'}`}
							</button>
						</div>

						{#if Object.keys(demandLetters).length > 0}
							<div class="mt-6 space-y-4">
								{#each Object.entries(demandLetters) as [partyName, letterHtml]}
									<div class="border rounded-lg p-4 bg-gray-50">
										<div class="flex items-center justify-between mb-3">
											<h4 class="font-semibold text-gray-900">Demand Letter to {partyName}</h4>
											<button
												class="inline-flex items-center px-3 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent"
												onclick={() => downloadLetter(letterHtml, `demand-letter-${partyName}.html`)}
											>
												Download
											</button>
										</div>
										<div class="border rounded bg-white overflow-hidden">
											<iframe srcdoc={letterHtml.replace(/\\n/g, '\n')} title={`Demand Letter ${partyName}`} class="w-full h-[400px] border-0" sandbox="allow-same-origin"></iframe>
										</div>
									</div>
								{/each}
							</div>
						{/if}
					</section>
				{/if}
			</div>
		{:else if activeTab === 'chat'}
			<div class="bg-white shadow rounded-lg p-6 h-[600px] flex flex-col">
				<h3 class="text-xl font-semibold text-gray-900 mb-2">Case Chat Assistant</h3>
				<p class="text-sm text-gray-600 mb-4">Ask questions about this case—responses include specific facts and citations.</p>
				<div class="flex-1 overflow-y-auto space-y-4 mb-4 p-4 bg-gray-50 rounded">
					{#if chatMessages.length === 0}
						<p class="text-center text-gray-500 text-sm">No messages yet. Ask a question to get started.</p>
					{:else}
						{#each chatMessages as message}
							<div class="space-y-2">
								<div class="flex justify-end">
									<div class="bg-accent text-white rounded-lg px-4 py-2 max-w-[70%]">{message.user}</div>
								</div>
								<div class="flex justify-start">
									<div class="bg-white border rounded-lg px-4 py-2 max-w-[70%] text-gray-800 chat-prose">
										{#if message.assistant && message.assistant !== '...'}
											{@html parseMarkdown(message.assistant)}
										{:else}
											<span class="text-gray-400">…</span>
										{/if}
									</div>
								</div>
							</div>
						{/each}
					{/if}
				</div>
				<div class="flex gap-2">
					<input
						class="flex-1 rounded-md border-gray-300 shadow-sm focus:border-accent focus:ring-accent text-sm"
						type="text"
						placeholder="Ask about this case..."
						bind:value={chatInput}
						onkeydown={(event) => event.key === 'Enter' && sendChatMessage()}
						disabled={sendingMessage}
					/>
					<button
						class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-accent hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent"
						onclick={sendChatMessage}
						disabled={sendingMessage || !chatInput.trim()}
					>
						{sendingMessage ? 'Sending…' : 'Send'}
					</button>
				</div>
			</div>
		{:else if activeTab === 'quality'}
			<div class="bg-white shadow rounded-lg p-6">
				<div class="flex items-center justify-between mb-4">
					<h3 class="text-xl font-semibold text-gray-900">Quality Report</h3>
					{#if results.quality_report && results.quality_report.length > 0}
						{@const lowQualityCount = results.quality_report.filter((item: { score?: number }) => (item.score ?? 0) < 6).length}
						{#if lowQualityCount > 0}
							<span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium bg-red-100 text-red-800 border border-red-200">
								<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
									<path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
								</svg>
								{lowQualityCount} need{lowQualityCount === 1 ? 's' : ''} review
							</span>
						{/if}
					{/if}
				</div>
				
				<!-- Legend -->
				<div class="flex flex-wrap gap-4 mb-4 text-sm">
					<div class="flex items-center gap-2">
						<span class="w-3 h-3 rounded-full bg-red-500"></span>
						<span class="text-gray-600">Low Quality (&lt;6) - Manual Review Required</span>
					</div>
					<div class="flex items-center gap-2">
						<span class="w-3 h-3 rounded-full bg-amber-500"></span>
						<span class="text-gray-600">Medium Quality (6-8)</span>
					</div>
					<div class="flex items-center gap-2">
						<span class="w-3 h-3 rounded-full bg-green-500"></span>
						<span class="text-gray-600">High Quality (&gt;8)</span>
					</div>
				</div>
				
				{#if results.quality_report && results.quality_report.length > 0}
					{@const sortedReport = [...results.quality_report].sort((a: { score?: number }, b: { score?: number }) => (a.score ?? 0) - (b.score ?? 0))}
					<div class="space-y-3">
						{#each sortedReport as item}
							{@const score = item.score ?? 0}
							{@const isLowQuality = score < 6}
							{@const isMediumQuality = score >= 6 && score <= 8}
							{@const isHighQuality = score > 8}
							<div class={`border-l-4 rounded-lg p-4 transition-all ${
								isLowQuality 
									? 'border-l-red-500 bg-red-50 border border-red-200' 
									: isMediumQuality 
										? 'border-l-amber-500 bg-amber-50 border border-amber-200'
										: 'border-l-green-500 bg-green-50 border border-green-200'
							}`}>
								<div class="flex items-start justify-between gap-4">
									<div class="flex-1 min-w-0">
										<div class="flex items-center gap-2 flex-wrap">
											<button
												onclick={() => viewDocument(item.document, item.document_id)}
												class="font-semibold text-accent hover:text-accent-hover hover:underline text-left truncate"
												title="Click to view document"
											>
												{item.document}
											</button>
											{#if isLowQuality}
												<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold bg-red-600 text-white animate-pulse">
													<svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
														<path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
													</svg>
													NEEDS REVIEW
												</span>
											{/if}
										</div>
										<div class="flex items-center gap-3 mt-2">
											<!-- Score Bar -->
											<div class="flex items-center gap-2 flex-1 max-w-xs">
												<div class="flex-1 h-2.5 bg-gray-200 rounded-full overflow-hidden">
													<div 
														class={`h-full rounded-full transition-all ${
															isLowQuality ? 'bg-red-500' : isMediumQuality ? 'bg-amber-500' : 'bg-green-500'
														}`}
														style="width: {(score / 10) * 100}%"
													></div>
												</div>
												<span class={`text-sm font-bold min-w-[3.5rem] ${
													isLowQuality ? 'text-red-700' : isMediumQuality ? 'text-amber-700' : 'text-green-700'
												}`}>
													{item.score?.toFixed ? item.score.toFixed(1) : item.score}/10
												</span>
											</div>
											<span class="text-sm text-gray-500">
												Confidence: {item.confidence_level || 'N/A'}
											</span>
										</div>
									</div>
								</div>
								{#if item.issues && item.issues.length > 0}
									<ul class={`list-disc list-inside text-sm mt-3 space-y-1 ${
										isLowQuality ? 'text-red-800' : 'text-gray-700'
									}`}>
										{#each item.issues as issue}
											<li>{issue}</li>
										{/each}
									</ul>
								{/if}
							</div>
						{/each}
					</div>
				{:else}
					<p class="text-gray-500 text-sm">No quality report data for this analysis.</p>
				{/if}
			</div>
		{/if}
		</div>
	{/if}

<!-- Document Viewer Modal -->
{#if viewingDocument}
	<div
		class="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50 flex items-center justify-center p-4"
		onclick={closeDocumentViewer}
	>
		<div
			class="relative bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] flex flex-col"
			onclick={(e) => e.stopPropagation()}
		>
			<!-- Header -->
			<div class="flex items-start justify-between p-6 border-b border-gray-200">
				<div class="flex-1 min-w-0">
					<h3 class="text-lg font-medium text-gray-900 truncate">
						{viewingDocument.file_name}
					</h3>
					<p class="text-sm text-gray-500 mt-1">
						{viewingDocument.file_type}
					</p>
				</div>
				<button
					onclick={closeDocumentViewer}
					class="ml-4 text-gray-400 hover:text-gray-500 transition-colors"
				>
					<span class="sr-only">Close</span>
					<svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>

			<!-- Content -->
			<div class="flex-1 overflow-y-auto p-6">
				{#if viewingDocument.file_type === 'application/pdf' || viewingDocument.file_name.toLowerCase().endsWith('.pdf')}
					{#if loadingPdf}
						<div class="flex items-center justify-center h-64">
							<div class="text-center">
								<svg class="mx-auto h-12 w-12 text-gray-400 animate-spin" fill="none" viewBox="0 0 24 24">
									<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
									<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
								</svg>
								<p class="mt-2 text-sm text-gray-500">Loading PDF preview...</p>
							</div>
						</div>
					{:else if pdfBlobUrl}
						<iframe 
							src={pdfBlobUrl} 
							title="PDF Viewer" 
							class="w-full h-[600px] border border-gray-300 rounded-lg"
						></iframe>
					{:else}
						<div class="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4">
							<p class="text-amber-800 text-sm">
								<strong>Preview unavailable:</strong> The original file could not be retrieved from storage. 
								This usually happens if the file failed to download from Clio.
							</p>
						</div>
						<p class="text-gray-500 text-sm mb-4">You can still try to download the file directly if it exists:</p>
						<a 
							href={`/api/documents/${viewingDocument.id}/download`}
							class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-accent hover:bg-accent-hover"
							download
						>
							Download PDF
						</a>
					{/if}
				{:else if viewingDocument.file_type?.startsWith('image/')}
					{#if loadingPdf}
						<div class="flex items-center justify-center h-64">
							<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-accent"></div>
						</div>
					{:else if pdfBlobUrl}
						<div class="flex items-center justify-center">
							<img src={pdfBlobUrl} alt={viewingDocument.file_name} class="max-w-full h-auto rounded-lg shadow-lg" />
						</div>
					{:else}
						<p class="text-red-500">Failed to load image preview.</p>
					{/if}
				{:else if viewingDocument.extracted_text}
					<pre class="whitespace-pre-wrap font-mono text-sm text-gray-800 bg-gray-50 p-4 rounded-lg">{viewingDocument.extracted_text}</pre>
				{:else}
					<p class="text-gray-500 text-sm">No preview available for this document type.</p>
				{/if}
			</div>

			<!-- Footer -->
			<div class="flex justify-end space-x-3 px-6 py-4 border-t border-gray-200">
				<button
					onclick={closeDocumentViewer}
					class="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent"
				>
					Close
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	/* Scoped prose styles for chat markdown rendering */
	:global(.chat-prose) {
		line-height: 1.6;
	}
	
	:global(.chat-prose p) {
		margin-bottom: 0.75rem;
	}
	
	:global(.chat-prose p:last-child) {
		margin-bottom: 0;
	}
	
	:global(.chat-prose strong) {
		font-weight: 600;
		color: inherit;
	}
	
	:global(.chat-prose em) {
		font-style: italic;
	}
	
	:global(.chat-prose ul),
	:global(.chat-prose ol) {
		margin: 0.5rem 0;
		padding-left: 1.5rem;
	}
	
	:global(.chat-prose ul) {
		list-style-type: disc;
	}
	
	:global(.chat-prose ol) {
		list-style-type: decimal;
	}
	
	:global(.chat-prose li) {
		margin-bottom: 0.25rem;
	}
	
	:global(.chat-prose li:last-child) {
		margin-bottom: 0;
	}
	
	:global(.chat-prose a) {
		color: #2563eb;
		text-decoration: underline;
	}
	
	:global(.chat-prose a:hover) {
		color: #1d4ed8;
	}
	
	:global(.chat-prose code) {
		background-color: #f3f4f6;
		padding: 0.125rem 0.375rem;
		border-radius: 0.25rem;
		font-size: 0.875em;
		font-family: ui-monospace, monospace;
	}
	
	:global(.chat-prose blockquote) {
		border-left: 3px solid #d1d5db;
		padding-left: 1rem;
		margin: 0.5rem 0;
		color: #6b7280;
		font-style: italic;
	}
</style>
