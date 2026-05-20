<script lang="ts">
	import { goto } from '$app/navigation';
	import { getApiUrl } from '$lib/config';
	import { supabase, getSecureSession } from '$lib/supabase';
	import { toastStore } from '$lib/stores/toastStore';
	import { slide } from 'svelte/transition';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
	import { ArrowLeft } from 'lucide-svelte';
	import { parseMarkdown } from '$lib/utils/markdown';
	import { SSEEventParser } from '$lib/utils/sseEventParser';
	import { fetchWithRetry } from '$lib/utils/fetchWithRetry';
	import type { GapResolutionRefreshRequest, RecommendedLetterType } from '$lib/types';
	import { onMount, onDestroy, tick } from 'svelte';
	import SkippedDocumentsAlert from '$lib/components/SkippedDocumentsAlert.svelte';
	import DocumentSummaryCard from '$lib/components/DocumentSummaryCard.svelte';
	import DocumentViewerModal from '$lib/components/DocumentViewerModal.svelte';
	import QualityTab from '$lib/components/QualityTab.svelte';
	import ChatTab from '$lib/components/ChatTab.svelte';
	import FindingsEmailSection from '$lib/components/FindingsEmailSection.svelte';
	import DemandLetterSection from '$lib/components/DemandLetterSection.svelte';
	import GapAnalysisPanel from '$lib/components/GapAnalysisPanel.svelte';
	import CaseRecommendationCard from '$lib/components/CaseRecommendationCard.svelte';
	import FullAnalysisDisplay from '$lib/components/FullAnalysisDisplay.svelte';
	import DocumentCoverageSection from '$lib/components/DocumentCoverageSection.svelte';
	import { AlertTriangle } from 'lucide-svelte';

	type ResultsWorkspaceData = {
		caseId: string;
		streamed: {
			results: Promise<any>;
			documents: Promise<any[]>;
			profile: Promise<any>;
		};
	};

	// Get SSR data from load function (or embedded usage in /cases/[id])
	let { data, embedded = false, autoRunGapAnalysis = false }: { data: ResultsWorkspaceData; embedded?: boolean; autoRunGapAnalysis?: boolean } = $props();

	const caseId = $derived(data.caseId);
	
	// Initialize state
	let results = $state<any>(null);
	let documents = $state<any[]>([]);
	let profile = $state<any>(null);
	let loading = $state(true);
	
	let activeTab = $state<'analysis' | 'gaps' | 'fullAnalysis' | 'documents' | 'letters' | 'chat' | 'quality'>('analysis');
	let initialDemandLetters = $state<Record<string, string>>({});
	let initialDemandAmount = $state<number | null>(null);
	let initialSpecificDemands = $state('');
	let initialFindingsLetter = $state<string | null>(null);
	let initialFindingsQualityReport = $state<Record<string, any> | null>(null);
	let initialFindingsMetrics = $state<Record<string, any> | null>(null);
	type ActiveGapAnalysisRequest = {
		requestId: number;
		controller: AbortController;
	};
	let activeGapAnalysisRequest: ActiveGapAnalysisRequest | null = null;
	let gapAnalysisRequestCounter = 0;
	
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
	let streamingGapSummary = $state(''); // Streaming attorney summary
	let resolvingGaps = $state(false);
	let forceGapRefresh = $state(false);

	// Recommendation letter state
	let generatingRecommendationLetter = $state(false);
	let recommendationLetters = $state<Record<string, string>>({});
	
	// Document coverage stats (derived from summaries and documents)
	let docCoverageStats = $derived.by(() => {
		const totalDocs = documents?.length || 0;
		const summaries = results?.document_summaries;
		if (!Array.isArray(summaries) || totalDocs === 0) {
			return { total: totalDocs, fullyAnalyzed: 0, grouped: 0, groupCount: 0, metadataOnly: 0, skipped: 0 };
		}

		// Count group summaries vs individual vs metadata-only summaries
		let groupSummaryCount = 0;
		let groupedDocCount = 0;
		let individualCount = 0;
		let metadataOnlyCount = 0;

		for (const s of summaries) {
			if (s.group_type && s.member_count && s.member_count > 1) {
				groupSummaryCount++;
				groupedDocCount += s.member_count;
			} else if (s.extraction_notes?.includes('T3_METADATA')) {
				// T3 metadata-only: catalogued from metadata, not LLM-analyzed
				metadataOnlyCount++;
			} else {
				individualCount++;
			}
		}

		const skippedArr = results?.artifacts?.skipped_documents || [];

		return {
			total: totalDocs,
			fullyAnalyzed: individualCount,
			grouped: groupedDocCount,
			groupCount: groupSummaryCount,
			metadataOnly: metadataOnlyCount,
			skipped: skippedArr.length,
		};
	});

	// Viability data
	let deepAnalysis = $derived(multiStageResult?.deep_analysis);
	let isViable = $derived(deepAnalysis?.is_viable ?? true);
	let viabilityReasoning = $derived(deepAnalysis?.viability_reasoning ?? '');

	// Attorney information for letters
	let profileLoaded = $state(false);
	let attorneyName = $state('');
	let firmName = $state('');
	let contactPhone = $state('');
	let contactEmail = $state('');

	// Document viewer for quality report
	let viewingDocument = $state<any>(null);

	// Collapsible document analysis state
	let collapsedDocs = $state<Set<string>>(new Set());
	let documentById = $derived.by(() => {
		const lookup = new Map<string, any>();
		for (const doc of documents || []) {
			const id = doc?.id;
			if (!id) continue;
			lookup.set(String(id), doc);
		}
		return lookup;
	});
	let documentByName = $derived.by(() => {
		const lookup = new Map<string, any>();
		for (const doc of documents || []) {
			const name = doc?.file_name;
			if (!name) continue;
			lookup.set(String(name).toLowerCase(), doc);
		}
		return lookup;
	});
	let signatureDetectionByDocName = $derived.by(() => {
		const lookup = new Map<string, Record<string, any>>();
		for (const doc of documents || []) {
			const docName = doc?.file_name;
			const signatureDetection = doc?.metadata?.signature_detection;
			if (!docName || !signatureDetection || typeof signatureDetection !== 'object') continue;
			lookup.set(String(docName).toLowerCase(), signatureDetection as Record<string, any>);
		}
		return lookup;
	});

	function extractDemandAmount(res: any): number | null {
		// 1. Try multi_stage_result financial_data (most structured source)
		if (res.multi_stage_result) {
			const factMatrix = res.multi_stage_result.fact_matrix || {};
			const financialData = factMatrix.financial_data || [];

			// Priority: claimed > owed > damage-related > any amount
			const claimedAmount = financialData.find(
				(item: any) => item.payment_type === 'claimed' || item.category === 'damages_claimed'
			);
			if (claimedAmount?.amount) return claimedAmount.amount;

			const owedAmount = financialData.find(
				(item: any) =>
					item.payment_type === 'owed' ||
					item.description?.toLowerCase().includes('owed') ||
					item.description?.toLowerCase().includes('damage')
			);
			if (owedAmount?.amount) return owedAmount.amount;

			// Fallback: use the largest financial_data amount (e.g. appraised value, contract value)
			if (financialData.length > 0) {
				const maxEntry = financialData.reduce((max: any, item: any) =>
					(item.amount || 0) > (max.amount || 0) ? item : max, financialData[0]);
				if (maxEntry?.amount) return maxEntry.amount;
			}

			// Also try financial_items (itemized amounts from streaming extraction)
			const financialItems = factMatrix.financial_items || [];
			if (financialItems.length > 0) {
				const total = financialItems.reduce((sum: number, item: any) => sum + (item.amount || 0), 0);
				if (total > 0) return total;
			}
		}

		// 2. Fall back to case_analysis financial_impact
		if (typeof res.case_analysis === 'object') {
			const financialText = res.case_analysis.intake_analysis?.financial_impact;
			if (financialText) {
				const amountMatch = financialText.match(/\$[\d,]+(?:\.\d{2})?/);
				if (amountMatch) return parseFloat(amountMatch[0].replace(/[$,]/g, ''));
			}
		}

		// 3. Fall back to document summaries key_amounts
		if (res.document_summaries && Array.isArray(res.document_summaries)) {
			for (const doc of res.document_summaries) {
				if (doc.key_amounts && Array.isArray(doc.key_amounts)) {
					for (const amount of doc.key_amounts) {
						if (
							amount.description?.toLowerCase().includes('damage') ||
							amount.description?.toLowerCase().includes('owed') ||
							amount.description?.toLowerCase().includes('claim')
						) {
							const amountStr = amount.amount?.replace(/[$,]/g, '');
							if (amountStr) return parseFloat(amountStr);
						}
					}
				}
			}
		}

		return null;
	}

	function extractSpecificDemands(res: any): string {
		if (res.multi_stage_result) {
			const issueMap = res.multi_stage_result.issue_map || {};
			const primaryIssues = issueMap.primary_issues || [];
			if (primaryIssues.length > 0) {
				return primaryIssues
					.map((issue: any) => `Resolve the issue of ${issue.issue_name} by providing appropriate remedies.`)
					.join('\n');
			}
			return 'Provide full and timely compliance with all outstanding obligations.';
		}
		return '';
	}

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
					initialFindingsLetter = res.generated_letters.findings;
				}
				if (res.generated_letters.findings_meta) {
					initialFindingsQualityReport = res.generated_letters.findings_meta.quality_report ?? null;
					initialFindingsMetrics = res.generated_letters.findings_meta.generation_metrics ?? null;
				}
				const demandEntries = Object.entries(res.generated_letters).filter(([key]) =>
					key.startsWith('demand_') && !key.endsWith('_meta')
				);
				if (demandEntries.length) {
					initialDemandLetters = demandEntries.reduce<Record<string, string>>((acc, [key, value]) => {
						const partyName = key.replace('demand_', '').replace(/_/g, ' ');
						acc[partyName] = value as string;
						return acc;
					}, {});
				}
				// Load recommendation letters
				const recommendationEntries = Object.entries(res.generated_letters).filter(([key]) =>
					key.startsWith('recommendation_') && !key.endsWith('_meta')
				);
				if (recommendationEntries.length) {
					recommendationLetters = recommendationEntries.reduce<Record<string, string>>((acc, [key, value]) => {
						const letterType = key.replace('recommendation_', '');
						acc[letterType] = value as string;
						return acc;
					}, {});
				}
			}

				// Extract demand amount from various sources for DemandLetterSection
			initialDemandAmount = extractDemandAmount(res);
			initialSpecificDemands = extractSpecificDemands(res);

			// Initialize all documents as collapsed
			const newCollapsed = new Set<string>();
			if (Array.isArray(res.document_summaries) && res.document_summaries.length > 0) {
				res.document_summaries.forEach((doc: any) => {
					newCollapsed.add(doc.document_name);
				});
			}
			collapsedDocs = newCollapsed;

			results = res;

			// Auto-run if: explicitly requested (just ran analysis) OR no gap analysis exists yet
			if (autoRunGapAnalysis || !gapAnalysis) {
				analyzeGaps();
			}
		} catch (err) {
			console.error('Error processing results:', err);
		} finally {
			loading = false;
		}
	});

	onDestroy(() => {
		activeGapAnalysisRequest?.controller.abort();
		activeGapAnalysisRequest = null;
	});

	// Demand calculation state

	function toggleDoc(docName: string) {
		const newSet = new Set(collapsedDocs);
		if (newSet.has(docName)) {
			newSet.delete(docName);
		} else {
			newSet.add(docName);
		}
		collapsedDocs = newSet;
	}

	function viewDocument(documentName: string, documentId?: string) {
		// Priority 1: Use document_id if available
		let doc = documentId
			? documentById.get(documentId)
			: null;

		// Priority 2: Exact file_name match
		if (!doc) {
			doc = documentByName.get(documentName.toLowerCase());
		}

		// Priority 3: Basename match (partial)
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

	function getDocumentSignatureDetection(documentName: string): Record<string, any> | null {
		if (!documentName) return null;
		return signatureDetectionByDocName.get(documentName.toLowerCase()) || null;
	}

	function applyGapAnalysisResult(gapResult: any) {
		if (!results?.multi_stage_result || !gapResult) return;
		results.multi_stage_result.gap_analysis = gapResult;
		results = results; // Trigger reactivity
	}

	async function runGapAnalysisFallback(
		apiUrl: string,
		accessToken: string,
		forceRefresh: boolean,
		signal?: AbortSignal
	): Promise<any> {
		const response = await fetchWithRetry(`${apiUrl}/api/analysis/analyze-gaps`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				Authorization: `Bearer ${accessToken}`
			},
			signal,
			body: JSON.stringify({
				case_id: caseId,
				force_refresh: forceRefresh || undefined
			})
		});

		if (!response.ok) {
			const detail = await response.json().catch(() => ({}));
			throw new Error(detail?.detail || 'Gap analysis failed');
		}

		return response.json();
	}

	async function analyzeGaps(forceRefresh: boolean = forceGapRefresh) {
		const previousRequest = activeGapAnalysisRequest;
		if (previousRequest) {
			previousRequest.controller.abort();
		}

		const controller = new AbortController();
		const requestId = ++gapAnalysisRequestCounter;
		activeGapAnalysisRequest = { requestId, controller };
		const isCurrentRequest = () => activeGapAnalysisRequest?.requestId === requestId;

		analyzingGaps = true;
		gapAnalysisProgress = 'Starting gap analysis...';
		streamingGapSummary = ''; // Clear previous streaming content

		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			let receivedResult = false;
			let pendingSummaryTokens = '';
			let summaryFlushTimer: ReturnType<typeof setTimeout> | null = null;
			let processedEventCount = 0;

			const flushSummaryTokens = () => {
				if (!isCurrentRequest()) return;
				if (pendingSummaryTokens) {
					streamingGapSummary += pendingSummaryTokens;
					pendingSummaryTokens = '';
				}
				if (summaryFlushTimer) {
					clearTimeout(summaryFlushTimer);
					summaryFlushTimer = null;
				}
			};

			const queueSummaryToken = (token: string) => {
				if (!isCurrentRequest()) return;
				pendingSummaryTokens += token;
				if (summaryFlushTimer) return;
				summaryFlushTimer = setTimeout(() => {
					if (!isCurrentRequest()) {
						pendingSummaryTokens = '';
						summaryFlushTimer = null;
						return;
					}
					streamingGapSummary += pendingSummaryTokens;
					pendingSummaryTokens = '';
					summaryFlushTimer = null;
				}, 60);
			};

			try {
				const response = await fetchWithRetry(`${apiUrl}/api/analysis/analyze-gaps/stream`, {
					method: 'POST',
					headers: {
						'Content-Type': 'application/json',
						Authorization: `Bearer ${session.access_token}`
					},
					signal: controller.signal,
					body: JSON.stringify({
						case_id: caseId,
						force_refresh: forceRefresh || undefined
					})
				});

				if (!response.ok) {
					const detail = await response.json().catch(() => ({}));
					throw new Error(detail?.detail || 'Gap analysis failed');
				}

				const reader = response.body?.getReader();
				if (!reader) throw new Error('No response body');

				const decoder = new TextDecoder();
				let buffer = '';

				while (true) {
					if (!isCurrentRequest()) {
						throw new DOMException('Gap analysis request superseded', 'AbortError');
					}
					const { done, value } = await reader.read();
					if (done) break;

					buffer += decoder.decode(value, { stream: true });
					const events = buffer.split('\n\n');
					buffer = events.pop() || '';

					for (const eventText of events) {
						const dataLine = eventText
							.split('\n')
							.map((line) => line.trim())
							.find((line) => line.startsWith('data: '));

						if (!dataLine) continue;

						let data: any;
						try {
							data = JSON.parse(dataLine.slice(6));
						} catch {
							// Ignore parse errors for incomplete chunks; stream fallback handles hard failures
							continue;
						}

						if (data.type === 'phase') {
							gapAnalysisProgress = data.message;
							if (data.gaps_found !== undefined) {
								gapAnalysisProgress = `Found ${data.gaps_found} gaps. Generating summary...`;
							}
						} else if (data.type === 'token') {
							queueSummaryToken(data.token);
							gapAnalysisProgress = 'Generating attorney summary...';
						} else if (data.type === 'result') {
							flushSummaryTokens();
							applyGapAnalysisResult(data.data);
							receivedResult = true;
							toastStore.success(`Gap analysis complete! Found ${data.data.total_gaps} gaps.`);
						} else if (data.type === 'error') {
							throw new Error(data.error || 'Gap analysis failed');
						}

						processedEventCount += 1;
						// Yield occasionally to keep the main thread responsive on large event bursts.
						if (processedEventCount % 100 === 0) {
							await new Promise((resolve) => setTimeout(resolve, 0));
						}
					}
				}

				if (!receivedResult) {
					throw new Error('Gap analysis stream ended before returning results');
				}
				} catch (streamErr) {
					flushSummaryTokens();
					if (controller.signal.aborted || !isCurrentRequest()) {
						throw streamErr;
					}
					if (receivedResult) {
						console.warn('[GapAnalysis] Stream interrupted after result payload', streamErr);
					} else {
						console.warn('[GapAnalysis] Streaming failed, retrying via non-stream endpoint', streamErr);
						gapAnalysisProgress = 'Connection interrupted. Retrying...';
						try {
							const gapResult = await runGapAnalysisFallback(
								apiUrl,
								session.access_token,
								forceRefresh,
								controller.signal
							);
							if (!isCurrentRequest()) {
								throw new DOMException('Gap analysis request superseded', 'AbortError');
							}
							applyGapAnalysisResult(gapResult);
							toastStore.success(`Gap analysis complete! Found ${gapResult.total_gaps} gaps.`);
						} catch (fallbackErr: any) {
							// Both stream and fallback failed (likely network outage).
							// Wait for network recovery, then retry the non-stream endpoint
							// which will return cached results if the backend completed.
							if (controller.signal.aborted || !isCurrentRequest()) throw fallbackErr;
							console.warn('[GapAnalysis] Fallback also failed, waiting for network recovery...', fallbackErr);
							gapAnalysisProgress = 'Network interrupted. Waiting to reconnect...';

							// Wait up to 30s for network to come back, checking every 3s
							let recovered = false;
							for (let wait = 0; wait < 10; wait++) {
								await new Promise((r) => setTimeout(r, 3000));
								if (controller.signal.aborted || !isCurrentRequest()) throw fallbackErr;
								try {
									const recoveryResult = await runGapAnalysisFallback(
										apiUrl,
										session.access_token,
										false, // Don't force refresh — use cached result
										controller.signal
									);
									if (!isCurrentRequest()) {
										throw new DOMException('Gap analysis request superseded', 'AbortError');
									}
									applyGapAnalysisResult(recoveryResult);
									toastStore.success(`Gap analysis recovered! Found ${recoveryResult.total_gaps} gaps.`);
									recovered = true;
									break;
								} catch {
									gapAnalysisProgress = `Network interrupted. Retrying... (${wait + 1}/10)`;
								}
							}
							if (!recovered) throw fallbackErr;
						}
					}
				}
		} catch (err: any) {
			if (err?.name !== 'AbortError') {
				toastStore.error(err.message || 'Gap analysis failed');
			}
		} finally {
			if (activeGapAnalysisRequest?.requestId === requestId) {
				activeGapAnalysisRequest = null;
				analyzingGaps = false;
				gapAnalysisProgress = '';
				streamingGapSummary = ''; // Clear after complete
			}
		}
	}

	async function resolveGapsAndRefresh(
		payload: Omit<GapResolutionRefreshRequest, 'case_id'>
	) {
		resolvingGaps = true;

		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const response = await fetch(`${apiUrl}/api/analysis/analyze-gaps/resolve`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`
				},
				body: JSON.stringify({
					case_id: caseId,
					...payload
				})
			});

			if (!response.ok) {
				const detail = await response.json().catch(() => ({}));
				throw new Error(detail?.detail || 'Gap resolution refresh failed');
			}

			const data = await response.json();
			const updatedGap = data?.gap_analysis || data;
			if (results?.multi_stage_result && updatedGap) {
				results.multi_stage_result.gap_analysis = updatedGap;
				results = results;
			}

			if (data?.cache_hit) {
				toastStore.success('No new changes detected. Using existing refreshed gap analysis.');
			} else {
				toastStore.success(
					`Gap analysis updated. Completeness: ${updatedGap?.overall_completeness_score?.toFixed?.(0) ?? 'N/A'}`
				);
			}
		} catch (err: any) {
			toastStore.error(err.message || 'Failed to refresh gap analysis');
			throw err;
		} finally {
			resolvingGaps = false;
		}
	}

	async function generateRecommendationLetter(letterType: string) {
		generatingRecommendationLetter = true;
		let shouldSwitchToLetters = false;

		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const analysisId = results?.analysis_id;
			if (!analysisId) throw new Error('No analysis ID available');

			const response = await fetchWithRetry(
				`${apiUrl}/api/analysis/${analysisId}/recommendation-letter/stream?letter_type=${letterType}&schema_version=2`,
				{
					headers: { Authorization: `Bearer ${session.access_token}` }
				}
			);

			if (!response.ok) {
				const detail = await response.json().catch(() => ({}));
				throw new Error(detail?.detail || 'Failed to stream recommendation letter');
			}

			const reader = response.body?.getReader();
			if (!reader) throw new Error('No reader available');

			const decoder = new TextDecoder();
			const parser = new SSEEventParser();
			let markdownBuffer = '';

			while (true) {
				const { done, value } = await reader.read();
				if (done) break;

				const chunk = decoder.decode(value, { stream: true });
				const events = parser.push(chunk);

				for (const data of events) {
					const eventType =
						(typeof data.event === 'string' && data.event) ||
						(typeof data.type === 'string' && data.type) ||
						(data.token ? 'token' : data.done ? 'done' : data.error ? 'error' : '');

					if (eventType === 'token' && typeof data.token === 'string') {
						// Accumulate markdown tokens
						markdownBuffer += data.token;
					} else if (eventType === 'final') {
						// Final HTML ready
						const content = data.content as Record<string, unknown> | undefined;
						if (content && typeof content.html === 'string') {
							recommendationLetters[letterType] = content.html;
						} else if (content && typeof content.markdown === 'string') {
							recommendationLetters[letterType] = `<div class="legal-letter">${parseMarkdown(content.markdown)}</div>`;
						}
						// Flag the tab switch; defer until after loading state resets to avoid
						// unmounting CaseRecommendationCard while its button disabled state is still updating.
						shouldSwitchToLetters = true;
						toastStore.success(`${letterType.replace('_', ' ')} letter generated successfully`);
					} else if (eventType === 'done') {
						break;
					} else if (eventType === 'error') {
						const message =
							(typeof data.error === 'string' && data.error) || 'Recommendation letter generation failed';
						throw new Error(message);
					}
				}
			}
		} catch (err: any) {
			// Network errors (ERR_NETWORK_CHANGED, Failed to fetch) often mean the
			// backend completed but the browser lost the response. Check the DB.
			if (err instanceof TypeError && /fetch|network/i.test(err.message)) {
				console.warn('Network error during recommendation letter generation — checking if letter was saved...', err);
				const recovered = await tryRecoverRecommendationLetter(letterType);
				if (recovered) {
					shouldSwitchToLetters = true;
				} else {
					toastStore.error('Network interrupted. The letter may still be generating — try refreshing in a moment.');
				}
			} else {
				toastStore.error(err.message || 'Recommendation letter generation failed');
			}
		} finally {
			// Reset loading state first so Svelte can update the button's disabled prop
			// while the CaseRecommendationCard is still mounted, before we switch tabs and unmount it.
			generatingRecommendationLetter = false;
			if (shouldSwitchToLetters) {
				await tick();
				activeTab = 'letters';
			}
		}
	}

	async function tryRecoverRecommendationLetter(letterType: string): Promise<boolean> {
		// Wait for the backend to finish saving
		await new Promise((r) => setTimeout(r, 5000));

		try {
			const { session } = await getSecureSession();
			if (!session) return false;

			const apiUrl = getApiUrl();
			const res = await fetch(`${apiUrl}/api/analysis/results/${caseId}`, {
				headers: { Authorization: `Bearer ${session.access_token}` }
			});
			if (!res.ok) return false;

			const analysisResult = await res.json();
			const letters = analysisResult?.result?.generated_letters;
			if (!letters) return false;

			const key = `recommendation_${letterType}`;
			if (letters[key]) {
				recommendationLetters = { ...recommendationLetters, [letterType]: letters[key] };
				toastStore.success('Letter recovered after network interruption');
				return true;
			}
		} catch (e) {
			console.warn('Recovery fetch also failed:', e);
		}
		return false;
	}

</script>

{#if !embedded}
	<!-- Back Button -->
	<button
		onclick={() => goto(`/app/cases/${caseId}`)}
		class="inline-flex items-center text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors mb-6"
	>
		<ArrowLeft class="h-4 w-4 mr-2" />
		Back to Case
	</button>
{/if}

<div class="page-spacing">
	{#if !embedded}
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
	{/if}

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

	{#if !loading && !isViable && viabilityReasoning}
		<div class="bg-red-50 border-l-4 border-red-500 p-4 mb-6 rounded-r-lg shadow-sm" transition:slide>
			<div class="flex items-start">
				<AlertTriangle class="h-6 w-6 text-red-500 mr-3 flex-shrink-0 mt-0.5" />
				<div class="flex-1">
					<h3 class="text-red-800 font-bold text-lg">Case Viability Concern</h3>
					<p class="text-red-700 mt-2 leading-relaxed">{viabilityReasoning}</p>
					<p class="text-red-600 text-sm mt-3 font-medium">
						The analysis indicates this case may not be viable for litigation. Review the full analysis and consider whether a "No Viable Case" letter would be more appropriate than a standard findings letter.
					</p>
				</div>
			</div>
		</div>
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

		<!-- CSS toggle tabs: keep mounted to preserve in-flight state across tab switches -->
		<div class:hidden={activeTab !== 'analysis'}>
			<!-- Persistent recommendation banner (slim) — sits above the analysis content so
			     the suggested next action is visible without discovering the Gaps tab. -->
			{#if gapAnalysis?.recommendation}
				{@const rec = gapAnalysis.recommendation}
				{@const bannerColor = rec.category_color === 'green' ? 'border-green-400 bg-green-50' :
				                       rec.category_color === 'yellow' ? 'border-amber-400 bg-amber-50' :
				                       rec.category_color === 'orange' ? 'border-orange-400 bg-orange-50' :
				                       'border-red-400 bg-red-50'}
				{@const textColor = rec.category_color === 'green' ? 'text-green-900' :
				                     rec.category_color === 'yellow' ? 'text-amber-900' :
				                     rec.category_color === 'orange' ? 'text-orange-900' :
				                     'text-red-900'}
				<div class="border-l-4 {bannerColor} px-4 py-3 mb-4 rounded-r-md flex items-center gap-3"
				     role="status"
				     data-testid="analysis-recommendation-banner">
					<div class="flex-1 min-w-0">
						<p class="text-sm font-semibold {textColor}">
							Recommendation: {rec.category_display_name}
						</p>
						<p class="text-xs {textColor} opacity-90 mt-0.5 line-clamp-2">
							{rec.reasoning}
						</p>
					</div>
					<AsyncButton
						variant="primary"
						loading={generatingRecommendationLetter}
						loadingText="Generating..."
						onclick={() => generateRecommendationLetter(rec.suggested_letter_type)}
					>
						Generate Letter →
					</AsyncButton>
				</div>
			{/if}

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

			<!-- Recommended next action at the end of the analysis content.
			     Same component as the Gaps tab — placed here so users on the
			     default Analysis tab see the contextual letter CTA without
			     having to discover the Gaps tab. Clicking auto-switches to
			     the Letters tab via the existing generateRecommendationLetter
			     flow (results/+page.svelte:791). -->
			{#if gapAnalysis?.recommendation}
				<div class="mt-6" data-testid="analysis-recommendation-card">
					<CaseRecommendationCard
						recommendation={gapAnalysis.recommendation}
						onGenerateLetter={() =>
							generateRecommendationLetter(gapAnalysis.recommendation.suggested_letter_type)}
						generatingLetter={generatingRecommendationLetter}
					/>
				</div>
			{/if}
		</div>

		<div class:hidden={activeTab !== 'gaps'}>
			{#if gapAnalysis}
				<div class="card-standard mb-4">
					<div class="flex flex-wrap items-center justify-between gap-3">
						<p class="text-sm text-gray-600">
							Re-run gap analysis after document updates. Use force refresh to bypass cache.
						</p>
						<div class="flex items-center gap-3">
							<label class="inline-flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
								<input
									type="checkbox"
									class="h-4 w-4 rounded border-gray-300 text-accent focus:ring-accent"
									bind:checked={forceGapRefresh}
								/>
								Force refresh
							</label>
							<AsyncButton
								variant="secondary"
								onclick={() => analyzeGaps(forceGapRefresh)}
								loading={analyzingGaps}
								loadingText={gapAnalysisProgress || 'Refreshing gaps...'}
							>
								Re-run Gap Analysis
							</AsyncButton>
						</div>
					</div>
				</div>
				<GapAnalysisPanel
					gapAnalysis={gapAnalysis}
					availableDocuments={documents}
					onGenerateRecommendationLetter={(letterType: RecommendedLetterType) => generateRecommendationLetter(letterType)}
					{generatingRecommendationLetter}
					onResolveGaps={resolveGapsAndRefresh}
					{resolvingGaps}
					totalDocuments={docCoverageStats.total}
					fullyAnalyzed={docCoverageStats.fullyAnalyzed}
					groupedDocuments={docCoverageStats.grouped}
					groupCount={docCoverageStats.groupCount}
					metadataOnly={docCoverageStats.metadataOnly}
					skippedCount={docCoverageStats.skipped}
				/>
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
						<div class="mb-4 flex items-center justify-center">
							<label class="inline-flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
								<input
									type="checkbox"
									class="h-4 w-4 rounded border-gray-300 text-accent focus:ring-accent"
									bind:checked={forceGapRefresh}
								/>
								Force refresh
							</label>
						</div>
						<AsyncButton
							variant="primary"
							onclick={() => analyzeGaps(forceGapRefresh)}
							loading={analyzingGaps}
							loadingText={gapAnalysisProgress || "Analyzing gaps..."}
							class="px-8"
						>
							Analyze Case Gaps
						</AsyncButton>
						{#if analyzingGaps && gapAnalysisProgress}
							<p class="text-sm text-blue-600 mt-4 animate-pulse">{gapAnalysisProgress}</p>
						{:else}
							<p class="text-xs text-gray-400 mt-4">Analysis typically takes 2-5 minutes depending on case size</p>
						{/if}

						{#if streamingGapSummary}
							<div class="mt-8 p-6 bg-blue-50 border border-blue-200 rounded-lg">
								<h3 class="text-lg font-semibold text-contrast mb-4 flex items-center gap-2">
									<span class="animate-pulse">●</span>
									Attorney Summary (Generating...)
								</h3>
								<div class="prose prose-sm max-w-none">
									<div class="whitespace-pre-wrap text-gray-700 leading-relaxed">{streamingGapSummary}<span class="animate-pulse">▊</span></div>
								</div>
							</div>
						{/if}
					</div>
				</div>
			{/if}
		</div>

		<div class:hidden={activeTab !== 'letters'}>
			<div class="space-y-6">
				<FindingsEmailSection
					analysisId={results.analysis_id}
					{caseId}
					{hasMultiStageSupport}
					{multiStageError}
					{gapAnalysis}
					{recommendationLetters}
					{initialFindingsLetter}
					{initialFindingsQualityReport}
					{initialFindingsMetrics}
				/>

				{#if hasMultiStageSupport}
					<DemandLetterSection
						analysisId={results.analysis_id}
						{caseId}
						{opposingParties}
						{initialDemandLetters}
						{initialDemandAmount}
						{initialSpecificDemands}
					/>
				{/if}
			</div>
		</div>

		<div class:hidden={activeTab !== 'chat'}>
			<ChatTab analysisId={results.analysis_id} />
		</div>

		<div class:hidden={activeTab !== 'quality'}>
			<QualityTab
				qualityReport={results.quality_report}
				onviewdocument={viewDocument}
			/>
		</div>

		{#if activeTab === 'fullAnalysis'}
			{#if results.streaming_analysis}
				<FullAnalysisDisplay content={results.streaming_analysis} />
			{:else}
				<div class="card-standard">
					<div class="text-center py-16">
						<svg class="mx-auto h-20 w-20 text-gray-300 mb-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
						</svg>
						<h3 class="text-xl font-bold text-gray-700 mb-3">No Full Analysis Available</h3>
						<p class="text-gray-500 max-w-md mx-auto leading-relaxed">
							Full analysis content is not available for this case. This comprehensive narrative is generated for new streaming analyses.
						</p>
					</div>
				</div>
			{/if}
		{/if}

		{#if activeTab === 'documents'}
			<!-- Signature status is now set in Verification Hub. This is read-only. -->
			{#if results.document_summaries && results.document_summaries.length > 0}
				{@const groupSummaries = results.document_summaries.filter((s: any) => s.group_type && s.member_count && s.member_count > 1)}
				{@const individualSummaries = results.document_summaries.filter((s: any) => !(s.group_type && s.member_count && s.member_count > 1) && !s.extraction_notes?.includes('T3_METADATA'))}
				{@const metadataOnlySummaries = results.document_summaries.filter((s: any) => s.extraction_notes?.includes('T3_METADATA'))}

				<!-- Document coverage overview -->
				{#if docCoverageStats.total > 0}
					<div class="mb-6">
						<DocumentCoverageSection
							totalDocuments={docCoverageStats.total}
							fullyAnalyzed={docCoverageStats.fullyAnalyzed}
							groupedDocuments={docCoverageStats.grouped}
							groupCount={docCoverageStats.groupCount}
							metadataOnly={docCoverageStats.metadataOnly}
							skipped={docCoverageStats.skipped}
						/>
					</div>
				{/if}

				<!-- Group summaries section -->
				{#if groupSummaries.length > 0}
					<div class="card-standard mb-6">
						<h2 class="text-2xl font-heading font-bold text-contrast mb-2 border-b border-gray-100 pb-4">
							Grouped Documents
						</h2>
						<p class="text-sm text-gray-500 mb-6">
							Related documents were analyzed together for more efficient and accurate summaries.
						</p>
						<div class="space-y-6">
							{#each groupSummaries as doc}
								<DocumentSummaryCard
									summary={doc}
									collapsible={true}
									defaultCollapsed={collapsedDocs.has(doc.document_name)}
								/>
							{/each}
						</div>
					</div>
				{/if}

				<!-- Individual document summaries (fully analyzed) -->
				{#if individualSummaries.length > 0}
					<div class="card-standard">
						<h2 class="text-2xl font-heading font-bold text-contrast mb-8 border-b border-gray-100 pb-4">
							{groupSummaries.length > 0 ? 'Individual Documents' : 'Document Analysis'}
						</h2>
						<div class="space-y-6">
							{#each individualSummaries as doc}
								<DocumentSummaryCard
									summary={doc}
									rawText={getDocumentRawText(doc.document_name)}
									signatureDetection={getDocumentSignatureDetection(doc.document_name)}
									collapsible={true}
									defaultCollapsed={collapsedDocs.has(doc.document_name)}
								/>
							{/each}
						</div>
					</div>
				{/if}

				<!-- Metadata-only documents (catalogued, not LLM-analyzed) -->
				{#if metadataOnlySummaries.length > 0}
					<div class="card-standard mt-6">
						<h2 class="text-lg font-heading font-bold text-gray-600 mb-2 border-b border-gray-100 pb-3">
							Metadata-Only Documents ({metadataOnlySummaries.length})
						</h2>
						<p class="text-sm text-gray-500 mb-4">
							These documents were catalogued from their metadata (filename, file type) but were not sent for AI analysis. This typically includes photos, brief staff notes, and other low-text items.
						</p>
						<div class="space-y-4">
							{#each metadataOnlySummaries as doc}
								<DocumentSummaryCard
									summary={doc}
									collapsible={true}
									defaultCollapsed={true}
								/>
							{/each}
						</div>
					</div>
				{/if}
			{:else}
				<div class="card-standard">
					<p class="text-gray-500">No document summaries available.</p>
				</div>
			{/if}
		{/if}
	{/if}
</div>

<!-- Document Viewer Modal -->
<DocumentViewerModal
	document={viewingDocument}
	{documents}
	supabaseClient={supabase}
	{results}
	onclose={() => (viewingDocument = null)}
/>

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
