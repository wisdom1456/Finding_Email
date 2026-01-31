<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { getApiUrl } from '$lib/config';
	import { supabase, getSecureSession } from '$lib/supabase';
	import { toastStore } from '$lib/stores/toastStore';
	import { slide } from 'svelte/transition';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
	import { ArrowLeft } from 'lucide-svelte';
	import { parseMarkdown } from '$lib/utils/markdown';
	import type { PageData } from './$types';
	import { onMount } from 'svelte';
	import SkippedDocumentsAlert from '$lib/components/SkippedDocumentsAlert.svelte';
	import DocumentSummaryCard from '$lib/components/DocumentSummaryCard.svelte';
	import GapAnalysisPanel from '$lib/components/GapAnalysisPanel.svelte';

	// Get SSR data from load function
	let { data }: { data: PageData } = $props();

	const caseId = $derived(data.caseId);
	
	// Initialize state
	let results = $state<any>(null);
	let documents = $state<any[]>([]);
	let profile = $state<any>(null);
	let loading = $state(true);
	
	let activeTab = $state<'analysis' | 'gaps' | 'fullAnalysis' | 'documents' | 'letters' | 'chat' | 'quality'>('analysis');
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

	// Gap analysis data
	let multiStageResult = $derived(results?.multi_stage_result);
	let gapAnalysis = $derived(multiStageResult?.gap_analysis);
	let hasCriticalGaps = $derived(gapAnalysis && (gapAnalysis.critical_count > 0 || gapAnalysis.high_count > 0));
	let criticalGapCount = $derived(gapAnalysis ? gapAnalysis.critical_count + gapAnalysis.high_count : 0);
	let analyzingGaps = $state(false);
	let gapAnalysisProgress = $state('');

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
	let documentViewerTab = $state<'preview' | 'summary' | 'text'>('preview');
	let documentSummary = $state<any>(null);

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
		documentViewerTab = 'preview';
		documentSummary = findDocumentSummary(documentName);
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
			// Download from storage (validate session first)
			const { session, user } = await getSecureSession();

			if (!session || !user) {
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
		documentSummary = null;
		documentViewerTab = 'preview';
		if (pdfBlobUrl) {
			URL.revokeObjectURL(pdfBlobUrl);
			pdfBlobUrl = null;
		}
	}

	/**
	 * Find the structured summary for a document by name
	 */
	function findDocumentSummary(documentName: string): any {
		if (!results?.document_summaries || !Array.isArray(results.document_summaries)) {
			return null;
		}
		
		// Try exact match first
		let summary = results.document_summaries.find(
			(s: any) => s.document_name === documentName
		);
		
		// Try case-insensitive match
		if (!summary) {
			const lowerName = documentName.toLowerCase();
			summary = results.document_summaries.find(
				(s: any) => s.document_name?.toLowerCase() === lowerName
			);
		}
		
		return summary || null;
	}

	/**
	 * Get the raw extracted text for a document by name
	 */
	function getDocumentRawText(documentName: string): string {
		// Try to find the document in the documents array
		let doc = documents.find((d) => d.file_name === documentName);
		
		// Case-insensitive fallback
		if (!doc) {
			const lowerName = documentName.toLowerCase();
			doc = documents.find((d) => d.file_name?.toLowerCase() === lowerName);
		}
		
		return doc?.extracted_text || doc?.manual_text || '';
	}

	async function analyzeGaps() {
		analyzingGaps = true;
		gapAnalysisProgress = 'Starting gap analysis...';

		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/analysis/analyze-gaps/stream`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`
				},
				body: JSON.stringify({ case_id: caseId })
			});

			if (!response.ok) {
				const detail = await response.json().catch(() => ({}));
				throw new Error(detail?.detail || 'Gap analysis failed');
			}

			// Handle streaming response
			const reader = response.body?.getReader();
			if (!reader) throw new Error('No response body');

			const decoder = new TextDecoder();
			let buffer = '';

			while (true) {
				const { done, value } = await reader.read();
				if (done) break;

				buffer += decoder.decode(value, { stream: true });
				const lines = buffer.split('\n');
				buffer = lines.pop() || '';

				for (const line of lines) {
					if (line.startsWith('data: ')) {
						try {
							const data = JSON.parse(line.slice(6));

							if (data.type === 'phase') {
								gapAnalysisProgress = data.message;
								if (data.gaps_found !== undefined) {
									gapAnalysisProgress = `Found ${data.gaps_found} gaps. Saving...`;
								}
							} else if (data.type === 'result') {
								// Update results with gap analysis
								if (results?.multi_stage_result) {
									results.multi_stage_result.gap_analysis = data.data;
									results = results; // Trigger reactivity
								}
								toastStore.success(`Gap analysis complete! Found ${data.data.total_gaps} gaps.`);
							} else if (data.type === 'error') {
								throw new Error(data.error);
							}
						} catch (parseErr) {
							// Ignore JSON parse errors for partial data
						}
					}
				}
			}
		} catch (err: any) {
			toastStore.error(err.message || 'Gap analysis failed');
		} finally {
			analyzingGaps = false;
			gapAnalysisProgress = '';
		}
	}

	async function generateFindingsLetter() {
		generatingFindings = true;
	findingsLetter = ''; // Clear existing

	try {
		const { session, user } = await getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/analysis/${results.analysis_id}/letter/stream`, {
				headers: { Authorization: `Bearer ${session.access_token}` }
			});

			if (!response.ok) {
				const detail = await response.json().catch(() => ({}));
				throw new Error(detail?.detail || 'Failed to stream findings email');
			}

			const reader = response.body?.getReader();
			if (!reader) throw new Error('No reader available');

			const decoder = new TextDecoder();
			let markdownBuffer = '';

			while (true) {
				const { done, value } = await reader.read();
				if (done) break;

				const chunk = decoder.decode(value);
				const lines = chunk.split('\n');

				for (const line of lines) {
					if (line.startsWith('data: ')) {
						try {
							const data = JSON.parse(line.slice(6));
							if (data.token) {
								markdownBuffer += data.token;
								// Convert markdown to HTML for preview
								// Note: Wrap in legal-letter class for styling
								findingsLetter = `<div class="legal-letter">${parseMarkdown(markdownBuffer)}</div>`;
							}
							if (data.done) break;
						} catch (e) {}
					}
				}
			}
		} catch (err: any) {
			toastStore.error(err.message || 'Findings email generation failed');
		} finally {
			generatingFindings = false;
		}
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
		const { session, user } = await getSecureSession();

		if (!session || !user) throw new Error('Not authenticated');

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
		const { session, user } = await getSecureSession();

		if (!session || !user) throw new Error('Not authenticated');

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
				throw new Error(detail?.detail || 'Failed to generate findings email');
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
			alert(err.message || 'Findings email generation failed');
		}
	}

	async function sendChatMessage() {
		if (!chatInput.trim()) return;

		const message = chatInput.trim();
		chatInput = '';
		sendingMessage = true;

		// Add user message and placeholder for assistant
		const currentMessageIndex = chatMessages.length;
	chatMessages = [...chatMessages, { user: message, assistant: '' }];

	try {
		const { session, user } = await getSecureSession();
		if (!session || !user) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const chatPayload = { message };
			const response = await fetch(`${apiUrl}/api/analysis/${results.analysis_id}/chat/stream`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`
				},
				body: JSON.stringify(chatPayload)
			});

			if (!response.ok) {
				const detail = await response.json().catch(() => ({}));
				throw new Error(detail?.detail || 'Chat request failed');
			}

			const reader = response.body?.getReader();
			if (!reader) throw new Error('No reader available');

			const decoder = new TextDecoder();
			let assistantResponse = '';

			while (true) {
				const { done, value } = await reader.read();
				if (done) break;

				const chunk = decoder.decode(value);
				const lines = chunk.split('\n');

				for (const line of lines) {
					if (line.startsWith('data: ')) {
						try {
							const data = JSON.parse(line.slice(6));
							if (data.token) {
								assistantResponse += data.token;
								// Update only the last message in real-time
								chatMessages = chatMessages.map((msg, idx) => 
									idx === currentMessageIndex ? { ...msg, assistant: assistantResponse } : msg
								);
							}
							if (data.done) break;
						} catch (e) {
							// Ignore parse errors for incomplete chunks
						}
					}
				}
			}
		} catch (err: any) {
			toastStore.error(err.message || 'Chat failed');
			// Remove the failed message pair
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

<div class="page-spacing">
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
							<span class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-green-50 text-green-700 border border-green-200" title="Findings Email & Demand Letter">
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
		<div class="info-box {analysisStatus === 'error' ? 'bg-red-50 border-red-200' : 'info-box-blue'}">
			<div class="flex items-start">
				{#if analysisStatus === 'error'}
					<svg class="h-5 w-5 text-red-500 mr-3 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
					</svg>
					<div>
						<h3 class="text-sm font-bold text-red-800">Latest analysis attempt failed</h3>
						<p class="text-sm text-red-700 mt-1 font-medium">
							The most recent analysis failed with error: {results?.error || 'Unknown error'}. 
							Showing results from a previous successful analysis if available.
						</p>
					</div>
				{:else}
					<div class="animate-spin rounded-full h-5 w-5 border-b-2 border-contrast-light mr-3 mt-0.5"></div>
					<div>
						<h3 class="text-sm font-bold text-contrast-light">Analysis in progress</h3>
						<p class="text-sm text-contrast-light/80 mt-1 font-medium">
							A new analysis is currently running. These results may be outdated. 
							Please wait for the current analysis to complete for the latest insights.
						</p>
					</div>
				{/if}
			</div>
			<div class="mt-4 flex">
				<button
					onclick={() => goto(`/app/cases/${caseId}`)}
					class="text-sm font-bold {analysisStatus === 'error' ? 'text-red-800 hover:underline' : 'text-contrast-light hover:underline'}"
				>
					Return to Case Details to check progress &rarr;
				</button>
			</div>
		</div>
	{/if}

	{#if !loading && skippedDocs.length > 0}
		<SkippedDocumentsAlert {skippedDocs} />
	{/if}

	{#if results}
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
				{#if hasMultiStageSupport}
				<button
					class={`py-4 px-1 border-b-2 text-sm font-medium relative ${
						activeTab === 'gaps'
							? 'border-accent text-accent'
							: 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
					}`}
					onclick={() => (activeTab = 'gaps')}
				>
					Gaps
					{#if hasCriticalGaps}
						<span class="ml-2 inline-flex items-center justify-center px-2 py-0.5 text-xs font-bold leading-none text-white bg-red-500 rounded">
							{criticalGapCount}
						</span>
					{/if}
				</button>
				{/if}
				{#if results.streaming_analysis}
				<button
					class={`py-4 px-1 border-b-2 text-sm font-medium ${
						activeTab === 'fullAnalysis'
							? 'border-accent text-accent'
							: 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
					}`}
					onclick={() => (activeTab = 'fullAnalysis')}
				>
					Full Analysis
				</button>
				{/if}
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
					Findings & Demand
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
			<div class="card-standard">
				<h2 class="text-2xl font-heading font-bold text-contrast mb-8 border-b border-gray-100 pb-4">Case Analysis</h2>
				{#if results.case_analysis}
					<div class="space-y-10">
						{#if results.case_analysis.case_summary}
							<section class="bg-gradient-to-br from-gray-50 to-white rounded-xl p-6 border border-gray-100">
								<h3 class="text-lg font-heading font-semibold text-contrast mb-4 flex items-center gap-2">
									<svg class="w-5 h-5 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
									</svg>
									Case Summary
								</h3>
								<div class="text-gray-700 leading-relaxed prose prose-slate prose-sm max-w-none prose-p:mb-4 prose-p:leading-7 prose-strong:text-contrast prose-strong:font-semibold">
									{@html parseMarkdown(results.case_analysis.case_summary)}
								</div>
							</section>
						{/if}
						{#if results.case_analysis.practice_area}
							<section>
								<h3 class="text-lg font-heading font-semibold text-contrast mb-3 flex items-center gap-2">
									<svg class="w-5 h-5 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
									</svg>
									Practice Area
								</h3>
								<span class="inline-flex items-center px-5 py-2 rounded-lg text-sm font-bold bg-accent/10 text-accent border border-accent/20 shadow-sm">
									{results.case_analysis.practice_area}
								</span>
							</section>
						{/if}
						{#if results.case_analysis.key_issues && results.case_analysis.key_issues.length > 0}
							<section>
								<h3 class="text-lg font-heading font-semibold text-contrast mb-4 flex items-center gap-2">
									<svg class="w-5 h-5 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
									</svg>
									Key Issues
								</h3>
								<div class="grid gap-3">
									{#each results.case_analysis.key_issues as issue, index}
										<div class="flex items-start gap-4 p-4 bg-white rounded-lg border border-gray-200 hover:border-accent/30 hover:shadow-sm transition-all">
											<div class="flex-shrink-0 w-8 h-8 rounded-full bg-accent/10 text-accent font-bold text-sm flex items-center justify-center">
												{index + 1}
											</div>
											<p class="text-gray-700 leading-relaxed flex-1 pt-1">{issue}</p>
										</div>
									{/each}
								</div>
							</section>
						{/if}
						{#if results.case_analysis.relevant_statutes && results.case_analysis.relevant_statutes.length > 0}
							<section>
								<h3 class="text-lg font-heading font-semibold text-contrast mb-4 flex items-center gap-2">
									<svg class="w-5 h-5 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" />
									</svg>
									Relevant Statutes
								</h3>
								<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
									{#each results.case_analysis.relevant_statutes as statute}
										<div class="bg-gradient-to-br from-white to-gray-50 rounded-xl p-5 border border-gray-200 hover:border-accent/40 hover:shadow-md transition-all group">
											<div class="flex items-start gap-3">
												<div class="flex-shrink-0 w-10 h-10 rounded-lg bg-accent/10 text-accent flex items-center justify-center group-hover:bg-accent/20 transition-colors">
													<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
													</svg>
												</div>
												<div class="flex-1 min-w-0">
													<p class="font-bold text-contrast text-base">{statute.statute}</p>
													<p class="text-sm text-gray-600 mt-2 leading-relaxed">{statute.relevance}</p>
												</div>
											</div>
										</div>
									{/each}
								</div>
							</section>
						{/if}
						{#if results.case_analysis.additional_details}
							<section class="bg-amber-50/50 rounded-xl p-6 border border-amber-200/50">
								<h3 class="text-lg font-heading font-semibold text-contrast mb-3 flex items-center gap-2">
									<svg class="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
									</svg>
									Additional Details
								</h3>
								<div class="text-gray-700 leading-relaxed prose prose-sm max-w-none">
									{@html parseMarkdown(results.case_analysis.additional_details)}
								</div>
							</section>
						{/if}
					</div>
				{:else}
					<p class="text-gray-500">No case analysis available.</p>
				{/if}
			</div>
		{:else if activeTab === 'gaps'}
			{#if gapAnalysis}
				<GapAnalysisPanel gapAnalysis={gapAnalysis} caseId={caseId} />
			{:else}
				<div class="card-standard">
					<div class="text-center py-12">
						<svg class="mx-auto h-16 w-16 text-gray-300 mb-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
						</svg>
						<h2 class="text-2xl font-heading font-bold text-contrast mb-4">Case Gap Analysis</h2>
						<p class="text-gray-500 max-w-md mx-auto mb-8">
							Identify missing documents, factual contradictions, timeline gaps, and unverifiable claims in your case materials.
						</p>
						<AsyncButton
							variant="primary"
							onclick={analyzeGaps}
							loading={analyzingGaps}
							loadingText={gapAnalysisProgress || "Analyzing gaps..."}
							class="px-8"
						>
							Analyze Case Gaps
						</AsyncButton>
						{#if analyzingGaps && gapAnalysisProgress}
							<p class="text-sm text-blue-600 mt-4 animate-pulse">{gapAnalysisProgress}</p>
						{:else}
							<p class="text-xs text-gray-400 mt-4">Analysis typically takes 30-60 seconds</p>
						{/if}
					</div>
				</div>
			{/if}
		{:else if activeTab === 'fullAnalysis'}
			<div class="card-standard">
				<h2 class="text-2xl font-heading font-bold text-contrast mb-8 border-b border-gray-100 pb-4">Full Analysis</h2>
				{#if results.streaming_analysis}
					<div class="prose prose-slate max-w-none prose-headings:font-heading prose-h2:text-xl prose-h3:text-lg prose-p:text-gray-700 prose-li:text-gray-700 prose-strong:text-contrast">
						{@html parseMarkdown(results.streaming_analysis)}
					</div>
				{:else}
					<p class="text-gray-500">Full analysis content is not available for this case. This feature is available for new streaming analyses.</p>
				{/if}
			</div>
		{:else if activeTab === 'documents'}
			{#if results.document_summaries && results.document_summaries.length > 0}
				<div class="card-standard">
					<h2 class="text-2xl font-heading font-bold text-contrast mb-8 border-b border-gray-100 pb-4">Document Analysis</h2>
					<div class="space-y-6">
						{#each results.document_summaries as doc}
							<DocumentSummaryCard 
								summary={doc}
								rawText={getDocumentRawText(doc.document_name)}
								collapsible={true}
								defaultCollapsed={collapsedDocs.has(doc.document_name)}
							/>
						{/each}
					</div>
				</div>
			{:else}
				<div class="card-standard">
					<p class="text-gray-500">No document summaries available.</p>
				</div>
			{/if}
		{:else if activeTab === 'letters'}
			<div class="space-y-6">
				{#if !hasMultiStageSupport}
					<div class="info-box border-amber-200 bg-amber-50">
						<p class="text-amber-900 font-medium">
							{#if multiStageError}
								<strong class="font-bold">⚠️ Advanced analysis failed:</strong> {multiStageError}.
								Findings email generation is unavailable for this specific analysis run.
							{:else}
								On-demand findings emails are unavailable because this case was processed with an older workflow.
							{/if}
							Please re-run analysis to enable this feature.
						</p>
					</div>
				{:else}
					<section class="card-standard">
						<div class="flex items-center justify-between mb-6">
							<div>
								<h3 class="text-xl font-heading font-bold text-contrast">Findings Email</h3>
								<p class="text-sm text-gray-500 mt-1">Generate a client-ready findings email on demand.</p>
							</div>
							<AsyncButton
								variant="primary"
								onclick={generateFindingsLetter}
								loading={generatingFindings}
								loadingText="Generating..."
							>
								Generate Email
							</AsyncButton>
						</div>
						{#if generatingFindings && findingsLetter}
							<!-- Streaming preview - shows text to avoid iframe blinking -->
							<div class="space-y-4 animate-fade-in-up">
								<div class="flex items-center gap-2 text-sm text-accent font-medium">
									<div class="animate-spin rounded-full h-4 w-4 border-2 border-accent border-t-transparent"></div>
									Generating email...
								</div>
								<div class="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-inner p-6 h-[600px] overflow-y-auto prose prose-sm max-w-none">
									{@html findingsLetter}
								</div>
							</div>
						{:else if findingsLetter}
							<!-- Completed findings email - show in iframe -->
							<div class="space-y-4 animate-fade-in-up">
								<div class="flex justify-end">
									<button
										class="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-bold rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent transition-all shadow-sm"
										onclick={() => downloadLetter(findingsLetter!, `findings-email-${caseId}.html`)}
									>
										Download HTML
									</button>
								</div>
								<div class="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-inner">
									<iframe srcdoc={findingsLetter.replace(/\\n/g, '\n')} title="Findings Email" class="w-full h-[600px] border-0" sandbox="allow-same-origin allow-scripts"></iframe>
								</div>
							</div>
						{:else}
							<div class="bg-gray-50 rounded-lg p-12 text-center border-2 border-dashed border-gray-200">
								<p class="text-gray-400 text-sm font-medium">No findings email generated yet. Click "Generate Email" to start.</p>
							</div>
						{/if}
					</section>

					<section class="card-standard">
						<h3 class="text-xl font-heading font-bold text-contrast mb-6">Demand Letter</h3>
						<div class="grid gap-6 md:grid-cols-2">
							<div class="space-y-4">
								<div>
									<label class="block text-sm font-bold text-contrast mb-1.5">Opposing Party</label>
									<select
										bind:value={selectedParty}
										class="input-standard focus:ring-accent"
									>
										<option value="">Select party</option>
										{#each opposingParties as party}
											<option value={party.name}>{party.name} ({party.role})</option>
										{/each}
									</select>
								</div>
								<div>
									<label class="block text-sm font-bold text-contrast mb-1.5">Demand Amount ($)</label>
									<div class="flex gap-2">
										<input
											type="number"
											class="input-standard focus:ring-accent"
											min="0"
											step="100"
											bind:value={demandAmount}
										/>
										<AsyncButton
											type="button"
											onclick={calculateDemandAmount}
											disabled={!selectedParty}
											loading={calculatingAmount}
											variant="secondary"
											loadingText="Calc..."
											class="whitespace-nowrap font-bold"
											title={!selectedParty ? "Please select an opposing party first" : "Calculate suggested demand amount based on case analysis"}
										>
											Calculate
										</AsyncButton>
									</div>
									{#if calculationReasoning}
										<div class="mt-3 p-4 info-box info-box-blue text-xs leading-relaxed animate-fade-in-up">
											<p class="text-contrast font-bold mb-1 uppercase tracking-wider">AI Calculation Reasoning:</p>
											<p class="text-contrast-light font-medium">{calculationReasoning}</p>
											{#if calculationBreakdown && calculationBreakdown.length > 0}
												<details class="mt-3 border-t border-contrast-light/10 pt-2">
													<summary class="text-accent font-bold cursor-pointer hover:underline">View line-item breakdown</summary>
													<ul class="mt-3 space-y-2">
														{#each calculationBreakdown as item}
															<li class="text-contrast-light flex justify-between font-medium">
																<span>{item.description}</span>
																<span class="font-mono font-bold">${item.amount.toLocaleString()}</span>
															</li>
														{/each}
													</ul>
												</details>
											{/if}
										</div>
									{/if}
								</div>
								<div>
									<label class="block text-sm font-bold text-contrast mb-1.5">Response Deadline</label>
									<select
										class="input-standard focus:ring-accent"
										bind:value={demandDeadline}
									>
										<option>10 business days</option>
										<option>14 days</option>
										<option>30 days</option>
									</select>
								</div>
							</div>

							<div class="space-y-4">
								<div>
									<label class="block text-sm font-bold text-contrast mb-1.5">Specific Demands (one per line)</label>
									<textarea
										class="input-standard focus:ring-accent min-h-[120px]"
										rows="6"
										bind:value={specificDemands}
										placeholder="e.g. Return of full security deposit&#10;Repairs to main dwelling roof&#10;Payment of outstanding interest"
									></textarea>
								</div>
								
								<div class="pt-2">
									<h4 class="text-sm font-bold text-contrast mb-3">Attorney Information</h4>
									<div class="grid grid-cols-2 gap-3">
										<input
											type="text"
											bind:value={attorneyName}
											class="input-standard text-xs focus:ring-accent"
											placeholder="Attorney name"
										/>
										<input
											type="text"
											bind:value={firmName}
											class="input-standard text-xs focus:ring-accent"
											placeholder="Firm name"
										/>
										<input
											type="tel"
											bind:value={contactPhone}
											class="input-standard text-xs focus:ring-accent"
											placeholder="Phone number"
										/>
										<input
											type="email"
											bind:value={contactEmail}
											class="input-standard text-xs focus:ring-accent"
											placeholder="Email address"
										/>
									</div>
								</div>
							</div>
						</div>
						
						<div class="mt-8 flex justify-end border-t border-gray-100 pt-6">
							<AsyncButton
								variant="primary"
								onclick={generateDemandLetter}
								disabled={!selectedParty}
								loading={generatingDemand}
								loadingText="Generating Letter..."
								class="px-8 shadow-sm"
							>
								Generate Letter to {selectedParty || 'Party'}
							</AsyncButton>
						</div>

						{#if Object.keys(demandLetters).length > 0}
							<div class="mt-8 space-y-6">
								{#each Object.entries(demandLetters) as [partyName, letterHtml]}
									<div class="border border-gray-200 rounded-xl overflow-hidden bg-gray-50 shadow-sm animate-fade-in-up">
										<div class="flex items-center justify-between p-4 bg-white border-b border-gray-200">
											<h4 class="font-bold text-contrast">Demand Letter: {partyName}</h4>
											<button
												class="inline-flex items-center px-3 py-1.5 border border-gray-300 text-xs font-bold rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent transition-all"
												onclick={() => downloadLetter(letterHtml, `demand-letter-${partyName}.html`)}
											>
												Download
											</button>
										</div>
										<div class="p-4">
											<div class="border border-gray-200 rounded-lg bg-white overflow-hidden shadow-inner">
												<iframe srcdoc={letterHtml.replace(/\\n/g, '\n')} title={`Demand Letter ${partyName}`} class="w-full h-[400px] border-0" sandbox="allow-same-origin allow-scripts"></iframe>
											</div>
										</div>
									</div>
								{/each}
							</div>
						{/if}
					</section>
				{/if}
			</div>
		{:else if activeTab === 'chat'}
			<div class="card-standard h-[700px] flex flex-col">
				<div class="mb-6">
					<h3 class="text-xl font-heading font-bold text-contrast">Case Chat Assistant</h3>
					<p class="text-sm text-gray-500 mt-1">Ask questions about this case—responses include specific facts and citations.</p>
				</div>
				
				<div class="flex-1 overflow-y-auto space-y-6 mb-6 p-6 bg-gray-50 rounded-xl border border-gray-200 shadow-inner">
					{#if chatMessages.length === 0}
						<div class="h-full flex flex-col items-center justify-center text-center opacity-50">
							<svg class="w-12 h-12 text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
							</svg>
							<p class="text-gray-500 font-medium">No messages yet. Ask a question to get started.</p>
						</div>
					{:else}
						{#each chatMessages as message}
							<div class="space-y-3 animate-fade-in-up">
								<div class="flex justify-end">
									<div class="bg-contrast text-white rounded-2xl rounded-tr-none px-5 py-3 max-w-[85%] shadow-sm text-sm font-medium">
										{message.user}
									</div>
								</div>
								<div class="flex justify-start">
									<div class="bg-white border border-gray-200 rounded-2xl rounded-tl-none px-5 py-3 max-w-[85%] text-gray-800 shadow-sm chat-prose text-sm">
										{#if message.assistant && message.assistant !== '...'}
											{@html parseMarkdown(message.assistant)}
										{:else}
											<div class="flex gap-1 py-1">
												<span class="w-1.5 h-1.5 bg-accent rounded-full animate-bounce"></span>
												<span class="w-1.5 h-1.5 bg-accent rounded-full animate-bounce [animation-delay:0.2s]"></span>
												<span class="w-1.5 h-1.5 bg-accent rounded-full animate-bounce [animation-delay:0.4s]"></span>
											</div>
										{/if}
									</div>
								</div>
							</div>
						{/each}
					{/if}
				</div>
				
				<div class="flex gap-3 bg-white p-2 rounded-lg border border-gray-200 shadow-sm focus-within:ring-2 focus-within:ring-accent/20 focus-within:border-accent transition-all">
					<input
						class="flex-1 border-0 focus:ring-0 text-sm py-3 px-4 text-contrast placeholder-gray-400 font-medium"
						type="text"
						placeholder="Ask a question about case facts, documents, or legal strategy..."
						bind:value={chatInput}
						onkeydown={(event) => event.key === 'Enter' && sendChatMessage()}
						disabled={sendingMessage}
					/>
					<AsyncButton
						variant="primary"
						onclick={sendChatMessage}
						disabled={!chatInput.trim()}
						loading={sendingMessage}
						loadingText="..."
						class="px-6 rounded-md font-bold"
					>
						Send
					</AsyncButton>
				</div>
			</div>
		{:else if activeTab === 'quality'}
			<div class="card-standard">
				<div class="flex flex-col md:flex-row md:items-center justify-between mb-8 border-b border-gray-100 pb-6 gap-4">
					<div>
						<h3 class="text-2xl font-heading font-bold text-contrast">Quality Report</h3>
						<p class="text-sm text-gray-500 mt-1 font-medium">Review the automated extraction quality for each document.</p>
					</div>
					{#if results.quality_report && results.quality_report.length > 0}
						{@const lowQualityCount = results.quality_report.filter((item: { score?: number }) => (item.score ?? 0) < 6).length}
						{#if lowQualityCount > 0}
							<div class="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold bg-red-50 text-red-700 border border-red-200 shadow-sm animate-pulse">
								<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
									<path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
								</svg>
								{lowQualityCount} Documents Need Review
							</div>
						{/if}
					{/if}
				</div>
				
				<!-- Legend -->
				<div class="flex flex-wrap gap-6 mb-8 p-4 bg-gray-50 rounded-xl border border-gray-200">
					<div class="flex items-center gap-2">
						<span class="w-3 h-3 rounded-full bg-red-500 shadow-sm shadow-red-200"></span>
						<span class="text-xs font-bold text-gray-600 uppercase tracking-wide">Low (&lt;6)</span>
					</div>
					<div class="flex items-center gap-2">
						<span class="w-3 h-3 rounded-full bg-amber-500 shadow-sm shadow-amber-200"></span>
						<span class="text-xs font-bold text-gray-600 uppercase tracking-wide">Medium (6-8)</span>
					</div>
					<div class="flex items-center gap-2">
						<span class="w-3 h-3 rounded-full bg-green-500 shadow-sm shadow-green-200"></span>
						<span class="text-xs font-bold text-gray-600 uppercase tracking-wide">High (&gt;8)</span>
					</div>
				</div>
				
				{#if results.quality_report && results.quality_report.length > 0}
					{@const sortedReport = [...results.quality_report].sort((a: { score?: number }, b: { score?: number }) => (a.score ?? 0) - (b.score ?? 0))}
					<div class="space-y-4">
						{#each sortedReport as item}
							{@const score = item.score ?? 0}
							{@const isLowQuality = score < 6}
							{@const isMediumQuality = score >= 6 && score <= 8}
							{@const isHighQuality = score > 8}
							<div class={`border-l-4 rounded-xl p-5 transition-all shadow-sm border border-gray-200 animate-fade-in-up ${
								isLowQuality 
									? 'border-l-red-500 bg-red-50/30' 
									: isMediumQuality 
										? 'border-l-amber-500 bg-amber-50/30'
										: 'border-l-green-500 bg-green-50/30'
							}`}>
								<div class="flex items-start justify-between gap-4">
									<div class="flex-1 min-w-0">
										<div class="flex items-center gap-3 flex-wrap">
											<button
												onclick={() => viewDocument(item.document, item.document_id)}
												class="text-base font-bold text-contrast hover:text-accent hover:underline text-left truncate"
												title="Click to view document"
											>
												{item.document}
											</button>
											{#if isLowQuality}
												<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-black bg-red-600 text-white uppercase tracking-tighter">
													Review Required
												</span>
											{/if}
										</div>
										<div class="flex items-center gap-6 mt-4">
											<!-- Score Bar -->
											<div class="flex items-center gap-3 flex-1 max-w-sm">
												<div class="flex-1 h-3 bg-gray-200 rounded-full overflow-hidden shadow-inner">
													<div 
														class={`h-full rounded-full transition-all duration-700 shadow-sm ${
															isLowQuality ? 'bg-red-500' : isMediumQuality ? 'bg-amber-500' : 'bg-green-500'
														}`}
														style="width: {(score / 10) * 100}%"
													></div>
												</div>
												<span class={`text-sm font-black min-w-[3.5rem] ${
													isLowQuality ? 'text-red-700' : isMediumQuality ? 'text-amber-700' : 'text-green-700'
												}`}>
													{item.score?.toFixed ? item.score.toFixed(1) : item.score}/10
												</span>
											</div>
											<div class="flex items-center gap-1.5 text-xs font-bold text-gray-400 uppercase tracking-widest">
												<span>Confidence:</span>
												<span class={
													item.confidence_level === 'high' ? 'text-green-600' : 
													item.confidence_level === 'medium' ? 'text-amber-600' : 'text-red-600'
												}>{item.confidence_level || 'N/A'}</span>
											</div>
										</div>
									</div>
								</div>
								{#if item.issues && item.issues.length > 0}
									<div class="mt-5 p-4 bg-white/50 rounded-lg border border-gray-100">
										<p class="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Extraction Issues</p>
										<ul class={`space-y-1.5 ${isLowQuality ? 'text-red-900' : 'text-gray-700'}`}>
											{#each item.issues as issue}
												<li class="text-xs font-medium flex items-start">
													<span class={`mr-2 ${isLowQuality ? 'text-red-400' : 'text-gray-300'}`}>•</span>
													{issue}
												</li>
											{/each}
										</ul>
									</div>
								{/if}
							</div>
						{/each}
					</div>
				{:else}
					<div class="p-12 text-center bg-gray-50 rounded-xl border-2 border-dashed border-gray-200">
						<p class="text-gray-400 font-medium italic">No quality report data for this analysis.</p>
					</div>
				{/if}
			</div>
		{/if}
	{/if}
</div>

<!-- Document Viewer Modal -->
{#if viewingDocument}
	<div
		class="modal-overlay"
		onclick={closeDocumentViewer}
	>
		<div
			class="relative bg-white rounded-lg shadow-2xl max-w-5xl w-full max-h-[90vh] flex flex-col"
			onclick={(e) => e.stopPropagation()}
		>
			<!-- Header -->
			<div class="flex items-start justify-between p-6 border-b border-gray-100">
				<div class="flex-1 min-w-0">
					<h3 class="text-xl font-heading font-bold text-contrast truncate">
						{viewingDocument.file_name}
					</h3>
					<p class="text-xs font-bold text-gray-400 mt-1 uppercase tracking-widest">
						{viewingDocument.file_type}
					</p>
				</div>
				<button
					onclick={closeDocumentViewer}
					class="ml-4 p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors"
				>
					<span class="sr-only">Close</span>
					<svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>

			<!-- Tabs -->
			<div class="px-6 border-b border-gray-200">
				<nav class="-mb-px flex space-x-6" aria-label="Tabs">
					<button
						onclick={() => (documentViewerTab = 'preview')}
						class="whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm {documentViewerTab === 'preview' ? 'border-accent text-accent' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}"
					>
						Preview
					</button>
					<button
						onclick={() => (documentViewerTab = 'summary')}
						class="whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center gap-2 {documentViewerTab === 'summary' ? 'border-accent text-accent' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}"
					>
						Summary
						{#if documentSummary}
							<span class="w-2 h-2 rounded-full bg-green-500"></span>
						{/if}
					</button>
					<button
						onclick={() => (documentViewerTab = 'text')}
						class="whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm {documentViewerTab === 'text' ? 'border-accent text-accent' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}"
					>
						Raw Text
					</button>
				</nav>
			</div>

			<!-- Content -->
			<div class="flex-1 overflow-y-auto p-6">
				{#if documentViewerTab === 'preview'}
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
					{:else}
						<div class="flex flex-col items-center justify-center h-64 text-gray-400">
							<svg class="h-12 w-12 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
							</svg>
							<p class="font-medium text-gray-600">No file preview available</p>
							<p class="text-sm mt-2">Use the Summary or Raw Text tabs to view the content.</p>
						</div>
					{/if}
				{:else if documentViewerTab === 'summary'}
					{#if documentSummary}
						<DocumentSummaryCard 
							summary={documentSummary}
							rawText={viewingDocument?.extracted_text || ''}
							collapsible={false}
							showHeader={false}
						/>
					{:else}
						<div class="flex flex-col items-center justify-center h-64 text-gray-400">
							<svg class="h-12 w-12 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
							</svg>
							<p class="font-medium text-gray-600">No analysis available</p>
							<p class="text-sm mt-2 text-center max-w-sm">
								Run case analysis to generate a structured summary of this document with key facts, legal significance, and evidence quotes.
							</p>
						</div>
					{/if}
				{:else if documentViewerTab === 'text'}
					{#if viewingDocument.extracted_text}
						<div class="bg-gray-900 rounded-lg p-4 max-h-[600px] overflow-auto">
							<pre class="whitespace-pre-wrap font-mono text-xs text-gray-300 leading-relaxed">{viewingDocument.extracted_text}</pre>
						</div>
					{:else}
						<div class="flex flex-col items-center justify-center h-64 text-gray-400">
							<svg class="h-12 w-12 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
							</svg>
							<p class="font-medium text-gray-600">No extracted text available</p>
							<p class="text-sm mt-2">This document hasn't been processed for text extraction.</p>
						</div>
					{/if}
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
