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
	import { letterHtmlToPlainText, letterHtmlToRichFragment, normalizeLetterHtml } from '$lib/utils/letterCopy';
	import { SSEEventParser } from '$lib/utils/sseEventParser';
	import type { GapResolutionRefreshRequest, RecommendedLetterType } from '$lib/types';
	import { onMount, onDestroy, tick } from 'svelte';
	import SkippedDocumentsAlert from '$lib/components/SkippedDocumentsAlert.svelte';
	import DocumentSummaryCard from '$lib/components/DocumentSummaryCard.svelte';
	import DocumentViewerModal from '$lib/components/DocumentViewerModal.svelte';
	import GapAnalysisPanel from '$lib/components/GapAnalysisPanel.svelte';
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
	let findingsLetter = $state<string | null>(null);
	type FindingsGenerationState =
		| 'idle'
		| 'connecting'
		| 'strategy'
		| 'context_build'
		| 'draft_generation'
		| 'lint_validation'
		| 'repair'
		| 'polishing'
		| 'finalizing'
		| 'complete'
		| 'error'
		| 'cancelled';
	let findingsGenerationState = $state<FindingsGenerationState>('idle');
	let findingsPhaseMessage = $state('');
	let findingsGenerationPercent = $state(0);

	const FINDINGS_PHASE_ORDER: FindingsGenerationState[] = [
		'strategy', 'context_build', 'draft_generation',
		'lint_validation', 'polishing', 'finalizing'
	];
	const FINDINGS_PHASE_LABELS: Record<string, string> = {
		strategy: 'Preparing strategy',
		context_build: 'Prioritizing key documents',
		draft_generation: 'Drafting letter',
		lint_validation: 'Reviewing for accuracy',
		repair: 'Fixing issues',
		polishing: 'Final polish',
		finalizing: 'Saving'
	};
	let findingsQualityReport = $state<Record<string, any> | null>(null);
	let findingsGenerationMetrics = $state<Record<string, any> | null>(null);
	let findingsRecoverableError = $state<string | null>(null);
	let findingsDraftStarted = $state(false);
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
	type ActiveGapAnalysisRequest = {
		requestId: number;
		controller: AbortController;
	};
	type ActiveChatRequest = {
		requestId: number;
		controller: AbortController;
		messageIndex: number;
	};
	type ActiveFindingsRequest = {
		requestId: number;
		controller: AbortController;
	};
	let activeGapAnalysisRequest: ActiveGapAnalysisRequest | null = null;
	let gapAnalysisRequestCounter = 0;
	let activeChatRequest: ActiveChatRequest | null = null;
	let chatRequestCounter = 0;
	let activeFindingsRequest: ActiveFindingsRequest | null = null;
	let findingsRequestCounter = 0;
	
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
	let forceGeneration = $state(false);
	let generatingRecommendationLetter = $state(false);
	let recommendationLetters = $state<Record<string, string>>({});
	let insufficientDocError = $state<{ completeness_score: number; critical_gaps: number } | null>(null);
	
	// Document coverage stats (derived from summaries and documents)
	let docCoverageStats = $derived.by(() => {
		const totalDocs = documents?.length || 0;
		const summaries = results?.document_summaries;
		if (!Array.isArray(summaries) || totalDocs === 0) {
			return { total: totalDocs, fullyAnalyzed: 0, grouped: 0, groupCount: 0, metadataOnly: 0, skipped: 0 };
		}

		// Count group summaries vs individual summaries
		let groupSummaryCount = 0;
		let groupedDocCount = 0;
		let individualCount = 0;

		for (const s of summaries) {
			if (s.group_type && s.member_count && s.member_count > 1) {
				groupSummaryCount++;
				groupedDocCount += s.member_count;
			} else {
				individualCount++;
			}
		}

		const skippedArr = results?.artifacts?.skipped_documents || [];
		const metadataOnly = Math.max(0, totalDocs - individualCount - groupedDocCount - skippedArr.length);

		return {
			total: totalDocs,
			fullyAnalyzed: individualCount,
			grouped: groupedDocCount,
			groupCount: groupSummaryCount,
			metadataOnly: metadataOnly > 0 ? metadataOnly : 0,
			skipped: skippedArr.length,
		};
	});

	// Viability data
	let deepAnalysis = $derived(multiStageResult?.deep_analysis);
	let isViable = $derived(deepAnalysis?.is_viable ?? true);
	let viabilityReasoning = $derived(deepAnalysis?.viability_reasoning ?? '');

	// Attorney information for letters
	let attorneyName = $state('');
	let firmName = $state('');
	let contactPhone = $state('');
	let contactEmail = $state('');
	let profileLoaded = $state(false);

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
				if (res.generated_letters.findings_meta) {
					findingsQualityReport = res.generated_letters.findings_meta.quality_report ?? null;
					findingsGenerationMetrics = res.generated_letters.findings_meta.generation_metrics ?? null;
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
				// Load recommendation letters
				const recommendationEntries = Object.entries(res.generated_letters).filter(([key]) =>
					key.startsWith('recommendation_')
				);
				if (recommendationEntries.length) {
					recommendationLetters = recommendationEntries.reduce<Record<string, string>>((acc, [key, value]) => {
						const letterType = key.replace('recommendation_', '');
						acc[letterType] = value as string;
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
		activeFindingsRequest?.controller.abort();
		activeFindingsRequest = null;
		activeChatRequest?.controller.abort();
		activeChatRequest = null;
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

	async function generateFindingsLetter() {
		const previousRequest = activeFindingsRequest;
		if (previousRequest) {
			previousRequest.controller.abort();
		}

		const controller = new AbortController();
		const requestId = ++findingsRequestCounter;
		activeFindingsRequest = { requestId, controller };
		const isCurrentRequest = () => activeFindingsRequest?.requestId === requestId;

		generatingFindings = true;
		findingsGenerationState = 'connecting';
		findingsPhaseMessage = 'Connecting...';
		findingsGenerationPercent = 0;
		findingsRecoverableError = null;
		findingsDraftStarted = false;
		insufficientDocError = null;
		findingsQualityReport = null;
		findingsGenerationMetrics = null;

		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const params = new URLSearchParams({
				schema_version: '2',
				mode: 'strict_quality'
			});
			if (forceGeneration) {
				params.set('force_generation', 'true');
			}

			const response = await fetchWithRetry(`${apiUrl}/api/analysis/${results.analysis_id}/letter/stream?${params.toString()}`, {
				headers: { Authorization: `Bearer ${session.access_token}` },
				signal: controller.signal
			});

			if (!response.ok) {
				const detail = await response.json().catch(() => ({}));
				if (detail?.detail?.error === 'documentation_insufficient') {
					if (isCurrentRequest()) {
						insufficientDocError = {
							completeness_score: detail.detail.completeness_score,
							critical_gaps: detail.detail.critical_gaps
						};
						toastStore.warning('Case documentation is insufficient. Review gaps or enable force override.');
						findingsGenerationState = 'idle';
						findingsPhaseMessage = '';
					}
					return;
				}
				throw new Error(detail?.detail?.message || detail?.detail || 'Failed to stream findings email');
			}

			const reader = response.body?.getReader();
			if (!reader) throw new Error('No reader available');

			const decoder = new TextDecoder();
			const parser = new SSEEventParser();
			let markdownBuffer = '';
			let pendingTokens = '';
			let flushTimer: ReturnType<typeof setTimeout> | null = null;
			let processedEventCount = 0;
			let streamDone = false;
			let hadUnrecoverableError = false;

			const renderFindingsPreview = () => {
				if (!isCurrentRequest()) return;
				findingsLetter = `<div class="legal-letter">${parseMarkdown(markdownBuffer)}</div>`;
			};

			const flushPendingTokens = () => {
				if (!isCurrentRequest()) return;
				if (pendingTokens) {
					markdownBuffer += pendingTokens;
					pendingTokens = '';
					renderFindingsPreview();
				}
				if (flushTimer) {
					clearTimeout(flushTimer);
					flushTimer = null;
				}
			};

			const queueToken = (token: string) => {
				if (!isCurrentRequest()) return;
				if (!findingsDraftStarted) {
					findingsDraftStarted = true;
					markdownBuffer = '';
					pendingTokens = '';
					findingsLetter = '';
				}
				pendingTokens += token;
				if (flushTimer) return;
				flushTimer = setTimeout(() => {
					if (!isCurrentRequest()) {
						pendingTokens = '';
						flushTimer = null;
						return;
					}
					if (!pendingTokens) {
						flushTimer = null;
						return;
					}
					markdownBuffer += pendingTokens;
					pendingTokens = '';
					flushTimer = null;
					renderFindingsPreview();
				}, 80);
			};

			const applyPhase = (phase: string, message?: string, percent?: number) => {
				if (!isCurrentRequest()) return;
				const allowed: FindingsGenerationState[] = [
					'strategy',
					'context_build',
					'draft_generation',
					'lint_validation',
					'repair',
					'polishing',
					'finalizing'
				];
				if (allowed.includes(phase as FindingsGenerationState)) {
					findingsGenerationState = phase as FindingsGenerationState;
				}
				if (message) {
					findingsPhaseMessage = message;
				}
				if (typeof percent === 'number' && percent > findingsGenerationPercent) {
					findingsGenerationPercent = percent;
				}
			};

			while (true) {
				if (!isCurrentRequest()) {
					throw new DOMException('Findings request superseded', 'AbortError');
				}
				const { done, value } = await reader.read();
				if (done) {
					flushPendingTokens();
					break;
				}

				const chunk = decoder.decode(value, { stream: true });
				const events = parser.push(chunk);

				for (const data of events) {
					const eventType =
						(typeof data.event === 'string' && data.event) ||
						(typeof data.type === 'string' && data.type) ||
						(data.token ? 'token' : data.done ? 'done' : data.error ? 'error' : '');

					if (eventType === 'phase') {
						applyPhase(String(data.phase || ''), typeof data.message === 'string' ? data.message : undefined, typeof data.percent === 'number' ? data.percent : undefined);
					} else if (eventType === 'token' && typeof data.token === 'string') {
						findingsGenerationState = 'draft_generation';
						queueToken(data.token);
					} else if (eventType === 'quality') {
						if (data.quality_report && typeof data.quality_report === 'object') {
							findingsQualityReport = data.quality_report as Record<string, any>;
						}
						if (data.generation_metrics && typeof data.generation_metrics === 'object') {
							findingsGenerationMetrics = data.generation_metrics as Record<string, any>;
						}
					} else if (eventType === 'final') {
						flushPendingTokens();
						const content = data.content as Record<string, unknown> | undefined;
						if (content && typeof content.html === 'string') {
							findingsLetter = content.html;
						} else if (content && typeof content.markdown === 'string') {
							findingsLetter = `<div class="legal-letter">${parseMarkdown(content.markdown)}</div>`;
						}
						if (data.quality_report && typeof data.quality_report === 'object') {
							findingsQualityReport = data.quality_report as Record<string, any>;
						}
						if (data.generation_metrics && typeof data.generation_metrics === 'object') {
							findingsGenerationMetrics = data.generation_metrics as Record<string, any>;
						}
						findingsGenerationState = 'complete';
						findingsPhaseMessage = 'Complete';
					} else if (eventType === 'error') {
						const message =
							(typeof data.error === 'string' && data.error) || 'Findings email generation failed';
						const recoverable = Boolean(data.recoverable);
						if (recoverable) {
							findingsRecoverableError = message;
						} else {
							findingsGenerationState = 'error';
							findingsPhaseMessage = message;
							hadUnrecoverableError = true;
							throw new Error(message);
						}
					} else if (eventType === 'done') {
						flushPendingTokens();
						streamDone = true;
						break;
					}

					processedEventCount += 1;
					if (processedEventCount % 120 === 0) {
						await new Promise((resolve) => setTimeout(resolve, 0));
					}
				}

				if (streamDone) {
					break;
				}
			}

			flushPendingTokens();
			if (isCurrentRequest() && !hadUnrecoverableError) {
				findingsGenerationState = 'complete';
				findingsPhaseMessage = 'Complete';
			}
		} catch (err: any) {
			if (err?.name !== 'AbortError') {
				toastStore.error(err.message || 'Findings email generation failed');
				if (isCurrentRequest()) {
					findingsGenerationState = 'error';
					findingsPhaseMessage = err.message || 'Findings email generation failed';
				}
			} else if (isCurrentRequest()) {
				findingsGenerationState = 'cancelled';
				findingsPhaseMessage = 'Cancelled';
			}
		} finally {
			if (activeFindingsRequest?.requestId === requestId) {
				activeFindingsRequest = null;
				generatingFindings = false;
				if (findingsGenerationState === 'connecting') {
					findingsGenerationState = 'idle';
					findingsPhaseMessage = '';
				}
			}
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

async function fetchWithRetry(
		url: string,
		options: RequestInit,
		retries = 2
	): Promise<Response> {
		for (let attempt = 0; attempt <= retries; attempt++) {
			try {
				const response = await fetch(url, options);
				if (response.status === 502 || response.status === 503) {
					if (attempt < retries) {
						console.warn(`[fetchWithRetry] ${response.status} on attempt ${attempt + 1}, retrying...`);
						await new Promise((r) => setTimeout(r, 1000 * 2 ** attempt));
						continue;
					}
				}
				return response;
			} catch (err) {
				const isNetworkError =
					err instanceof TypeError && /fetch|network/i.test(err.message);
				if (isNetworkError && attempt < retries) {
					console.warn(`[fetchWithRetry] Network error on attempt ${attempt + 1}, retrying...`, err);
					await new Promise((r) => setTimeout(r, 1000 * 2 ** attempt));
					continue;
				}
				throw err;
			}
		}
		throw new Error('fetchWithRetry: should not reach here');
	}

	async function generateLetterRequest(body: Record<string, any>) {
		try {
			const { session, user } = await getSecureSession();

			if (!session || !user) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const response = await fetchWithRetry(`${apiUrl}/api/analysis/generate-letter`, {
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
			applyLetterResult(data, body);
		} catch (err: any) {
			// Network errors that survived retries — backend may have completed
			// but browser lost the response. Check the DB as last resort.
			if (err instanceof TypeError && /fetch|network/i.test(err.message)) {
				console.warn('Network error during letter generation — checking if letter was saved...', err);
				const recovered = await tryRecoverSavedLetter(body);
				if (recovered) return;
			}
			alert(err.message || 'Letter generation failed');
		}
	}

	function applyLetterResult(data: any, body: Record<string, any>) {
		if (data.letter_type === 'findings' || body.letter_type === 'findings') {
			findingsLetter = data.letter_html;
			findingsQualityReport = data.quality_report ?? null;
			findingsGenerationMetrics = data.generation_metrics ?? null;
			findingsGenerationState = 'complete';
			findingsPhaseMessage = 'Complete';
		} else if (data.target_party_name) {
			demandLetters = {
				...demandLetters,
				[data.target_party_name]: data.letter_html
			};
		}
	}

	async function tryRecoverSavedLetter(body: Record<string, any>): Promise<boolean> {
		// Wait a few seconds for the backend to finish saving
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

			if (body.letter_type === 'demand' && body.target_party_name) {
				const key = `demand_${body.target_party_name.replace(/\s+/g, '_')}`;
				if (letters[key]) {
					demandLetters = { ...demandLetters, [body.target_party_name]: letters[key] };
					toastStore.success('Letter recovered after network interruption');
					return true;
				}
			} else if (body.letter_type === 'findings' && letters.findings) {
				findingsLetter = letters.findings;
				if (letters.findings_meta) {
					findingsQualityReport = letters.findings_meta.quality_report ?? null;
					findingsGenerationMetrics = letters.findings_meta.generation_metrics ?? null;
				}
				findingsGenerationState = 'complete';
				findingsPhaseMessage = 'Complete';
				toastStore.success('Letter recovered after network interruption');
				return true;
			}
		} catch (e) {
			console.warn('Recovery fetch also failed:', e);
		}
		return false;
	}

	async function sendChatMessage() {
		if (!chatInput.trim()) return;

		const message = chatInput.trim();
		chatInput = '';

		const previousRequest = activeChatRequest;
		if (previousRequest) {
			previousRequest.controller.abort();
			chatMessages = chatMessages.filter((_, idx) => idx !== previousRequest.messageIndex);
			activeChatRequest = null;
		}

		sendingMessage = true;

		// Add user message and placeholder for assistant
		const currentMessageIndex = chatMessages.length;
		chatMessages = [...chatMessages, { user: message, assistant: '' }];
		const controller = new AbortController();
		const requestId = ++chatRequestCounter;
		activeChatRequest = { requestId, controller, messageIndex: currentMessageIndex };
		const isCurrentRequest = () => activeChatRequest?.requestId === requestId;

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
				signal: controller.signal,
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
			let pendingAssistantTokens = '';
			let flushTimer: ReturnType<typeof setTimeout> | null = null;
			let processedEventCount = 0;

			const updateAssistantMessage = () => {
				if (!isCurrentRequest()) return;
				const nextMessages = [...chatMessages];
				const currentMessage = nextMessages[currentMessageIndex];
				if (!currentMessage) return;
				nextMessages[currentMessageIndex] = {
					...currentMessage,
					assistant: assistantResponse
				};
				chatMessages = nextMessages;
			};

			const flushAssistantTokens = () => {
				if (!isCurrentRequest()) return;
				if (pendingAssistantTokens) {
					assistantResponse += pendingAssistantTokens;
					pendingAssistantTokens = '';
					updateAssistantMessage();
				}
				if (flushTimer) {
					clearTimeout(flushTimer);
					flushTimer = null;
				}
			};

			const queueAssistantToken = (token: string) => {
				if (!isCurrentRequest()) return;
				pendingAssistantTokens += token;
				if (flushTimer) return;
				flushTimer = setTimeout(() => {
					if (!isCurrentRequest()) {
						pendingAssistantTokens = '';
						flushTimer = null;
						return;
					}
					if (!pendingAssistantTokens) {
						flushTimer = null;
						return;
					}
					assistantResponse += pendingAssistantTokens;
					pendingAssistantTokens = '';
					flushTimer = null;
					updateAssistantMessage();
				}, 50);
			};

			while (true) {
				if (!isCurrentRequest()) {
					throw new DOMException('Chat request superseded', 'AbortError');
				}
				const { done, value } = await reader.read();
				if (done) {
					flushAssistantTokens();
					break;
				}

				const chunk = decoder.decode(value);
				const lines = chunk.split('\n');

				for (const line of lines) {
					if (line.startsWith('data: ')) {
						try {
							const data = JSON.parse(line.slice(6));
							if (data.token) {
								queueAssistantToken(data.token);
							}
							if (data.done) {
								flushAssistantTokens();
								break;
							}
						} catch (e) {
							// Ignore parse errors for incomplete chunks
						}
					}

					processedEventCount += 1;
					if (processedEventCount % 150 === 0) {
						await new Promise((resolve) => setTimeout(resolve, 0));
					}
				}
			}
			flushAssistantTokens();
		} catch (err: any) {
			if (err?.name !== 'AbortError') {
				toastStore.error(err.message || 'Chat failed');
				if (isCurrentRequest()) {
					chatMessages = chatMessages.filter((_, idx) => idx !== currentMessageIndex);
				}
			}
		} finally {
			if (activeChatRequest?.requestId === requestId) {
				activeChatRequest = null;
				sendingMessage = false;
			}
		}
	}

	type ChatMessageResponse = {
		response: string;
		context_used?: Record<string, any>;
	};

	function downloadLetter(letter: string, filename: string) {
		const cleanedLetter = normalizeLetterHtml(letter);
		const blob = new Blob([cleanedLetter], { type: 'text/html' });
		const url = URL.createObjectURL(blob);
		const link = document.createElement('a');
		link.href = url;
		link.download = filename;
		link.click();
		URL.revokeObjectURL(url);
	}

	async function copyLetterPlainText(letter: string, label: string) {
		try {
			const text = letterHtmlToPlainText(letter);
			if (!text) throw new Error('No text content available');
			await navigator.clipboard.writeText(text);
			toastStore.success(`${label} copied as plain text`);
		} catch (err: any) {
			toastStore.error(err?.message || `Failed to copy ${label.toLowerCase()}`);
		}
	}

	async function copyLetterRichText(letter: string, label: string) {
		try {
			const richHtml = letterHtmlToRichFragment(letter);
			const plainText = letterHtmlToPlainText(letter);
			if (!plainText) throw new Error('No text content available');

			if (typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write) {
				const payload = new ClipboardItem({
					'text/html': new Blob([richHtml], { type: 'text/html' }),
					'text/plain': new Blob([plainText], { type: 'text/plain' })
				});
				await navigator.clipboard.write([payload]);
			} else {
				await navigator.clipboard.writeText(plainText);
			}

			toastStore.success(`${label} copied`);
		} catch (err: any) {
			toastStore.error(err?.message || `Failed to copy ${label.toLowerCase()}`);
		}
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
		{:else if activeTab === 'fullAnalysis'}
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
		{:else if activeTab === 'documents'}
			<!-- Signature status is now set in Verification Hub. This is read-only. -->
			{#if results.document_summaries && results.document_summaries.length > 0}
				{@const groupSummaries = results.document_summaries.filter((s: any) => s.group_type && s.member_count && s.member_count > 1)}
				{@const individualSummaries = results.document_summaries.filter((s: any) => !(s.group_type && s.member_count && s.member_count > 1))}

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

				<!-- Individual document summaries -->
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
								{#if findingsGenerationMetrics?.repair_applied}
									<div class="mt-2 inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
										Quality pass applied
									</div>
								{/if}
								{#if findingsGenerationMetrics?.critic_applied}
									<div class="mt-2 ml-2 inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold bg-sky-50 text-sky-700 border border-sky-200">
										Critic-guided repair
									</div>
								{/if}
								{#if findingsQualityReport?.quality_report_v2}
									<div class="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-600">
										<span class="px-2 py-1 rounded border border-gray-200 bg-gray-50">
											Micro-explainers: {findingsQualityReport.quality_report_v2.term_explainer_passed ? 'Pass' : 'Needs review'}
										</span>
										<span class="px-2 py-1 rounded border border-gray-200 bg-gray-50">
											Evidence linkage: {Math.round((findingsQualityReport.quality_report_v2.evidence_linkage_score ?? 0) * 100)}%
										</span>
									</div>
								{/if}
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

						{#if generatingFindings || (findingsGenerationState !== 'idle' && findingsGenerationState !== 'complete' && findingsGenerationState !== 'error' && findingsGenerationState !== 'cancelled')}
							<div class="mb-4">
								<div class="flex items-center gap-2 text-sm text-gray-600 mb-2">
									<div class="h-2.5 w-2.5 rounded-full bg-accent animate-pulse"></div>
									<span>{findingsPhaseMessage || FINDINGS_PHASE_LABELS[findingsGenerationState] || findingsGenerationState.replace(/_/g, ' ')}</span>
								</div>
								<!-- Phase progress steps -->
								<div class="flex items-center gap-1 ml-5">
									{#each FINDINGS_PHASE_ORDER as phase, i}
										{@const phaseIdx = FINDINGS_PHASE_ORDER.indexOf(findingsGenerationState as any)}
										{@const isPast = i < phaseIdx}
										{@const isCurrent = findingsGenerationState === phase}
										<div class="h-1 flex-1 rounded-full transition-all duration-300 {isPast ? 'bg-accent' : isCurrent ? 'bg-accent/50 animate-pulse' : 'bg-gray-200'}"></div>
									{/each}
								</div>
							</div>
						{/if}

						{#if findingsRecoverableError}
							<div class="mb-4 p-3 rounded-lg border border-blue-200 bg-blue-50 text-sm text-blue-800">
								{findingsRecoverableError} You can review the current draft while we finalize output.
							</div>
						{/if}

						<!-- Insufficient Documentation Warning -->
						{#if insufficientDocError}
							<div class="mb-6 p-4 bg-amber-50 border border-amber-300 rounded-lg">
								<div class="flex items-start gap-3">
									<AlertTriangle class="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
									<div class="flex-1">
										<h4 class="font-semibold text-amber-900 mb-1">Insufficient Documentation</h4>
										<p class="text-sm text-amber-800 mb-3">
											Case completeness is {insufficientDocError.completeness_score.toFixed(0)}% with {insufficientDocError.critical_gaps} critical gap(s).
											Review the Gap Analysis tab to identify missing documents, or enable force generation to proceed anyway.
										</p>
										<label class="flex items-center gap-2 cursor-pointer">
											<input
												type="checkbox"
												bind:checked={forceGeneration}
												class="w-4 h-4 rounded border-amber-400 text-amber-600 focus:ring-amber-500"
											/>
											<span class="text-sm font-medium text-amber-900">
												Force generation despite insufficient documentation
											</span>
										</label>
										{#if forceGeneration}
											<p class="text-xs text-amber-700 mt-2 italic">
												Warning: Generated letter may contain gaps or require significant manual review.
											</p>
										{/if}
									</div>
								</div>
							</div>
						{:else if gapAnalysis && gapAnalysis.overall_completeness_score < 60}
							<div class="mb-6 p-4 bg-yellow-50 border border-yellow-300 rounded-lg">
								<div class="flex items-start gap-3">
									<AlertTriangle class="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
									<div>
										<h4 class="font-semibold text-yellow-900 mb-1">Low Completeness Warning</h4>
										<p class="text-sm text-yellow-800">
											Case completeness is {gapAnalysis.overall_completeness_score.toFixed(0)}%. 
											Consider reviewing the Gap Analysis tab before generating letters.
										</p>
									</div>
								</div>
							</div>
						{/if}

						{#if generatingFindings && !findingsDraftStarted && !findingsLetter}
							<div class="space-y-4 animate-fade-in-up">
								<!-- Progress bar -->
								<div class="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
									<div
										class="h-full bg-accent rounded-full transition-all duration-700 ease-out"
										style="width: {findingsGenerationPercent}%"
									></div>
								</div>
								<!-- Phase step list -->
								<div class="flex flex-col gap-2 py-2">
									{#each FINDINGS_PHASE_ORDER as phase}
										{@const phaseIdx = FINDINGS_PHASE_ORDER.indexOf(phase)}
										{@const activeIdx = FINDINGS_PHASE_ORDER.indexOf(findingsGenerationState as any)}
										{@const isDone = activeIdx > phaseIdx}
										{@const isActive = activeIdx === phaseIdx}
										{@const label = isActive && findingsPhaseMessage && phase === 'draft_generation'
											? findingsPhaseMessage
											: FINDINGS_PHASE_LABELS[phase]}
										<div class="flex items-center gap-2.5 text-sm {isActive ? 'text-accent font-medium' : isDone ? 'text-green-600' : 'text-gray-400'}">
											{#if isDone}
												<svg class="h-4 w-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
													<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
												</svg>
											{:else if isActive}
												<div class="h-4 w-4 flex-shrink-0 animate-spin rounded-full border-2 border-accent border-t-transparent"></div>
											{:else}
												<div class="h-4 w-4 flex-shrink-0 rounded-full border-2 border-gray-200"></div>
											{/if}
											<span>{label}</span>
										</div>
									{/each}
								</div>
								<div class="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-inner p-6 h-[600px] flex items-center justify-center text-gray-500">
									Waiting for first token...
								</div>
							</div>
						{:else if generatingFindings && findingsDraftStarted && findingsLetter && findingsGenerationState !== 'complete'}
							<!-- Streaming preview - shows text to avoid iframe blinking -->
							<div class="space-y-4 animate-fade-in-up">
								<!-- Progress bar -->
								<div class="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
									<div
										class="h-full bg-accent rounded-full transition-all duration-700 ease-out"
										style="width: {findingsGenerationPercent}%"
									></div>
								</div>
								<div class="flex items-center gap-2 text-sm text-accent font-medium">
									<div class="animate-spin rounded-full h-4 w-4 border-2 border-accent border-t-transparent"></div>
									{findingsPhaseMessage || 'Generating email...'}
								</div>
								<div class="relative border border-gray-200 rounded-lg overflow-hidden bg-white shadow-inner">
									{#if findingsGenerationState === 'polishing'}
										<div class="absolute inset-0 z-10 flex flex-col items-center justify-center bg-white/80 backdrop-blur-sm rounded-lg">
											<div class="animate-spin rounded-full h-8 w-8 border-2 border-accent border-t-transparent mb-3"></div>
											<span class="text-sm font-medium text-accent">Polishing letter...</span>
										</div>
									{/if}
									<div class="p-6 h-[600px] overflow-y-auto prose prose-sm max-w-none">
										{@html findingsLetter}
									</div>
								</div>
							</div>
							{:else if findingsLetter}
								<!-- Completed findings email - show in iframe -->
								<div class="space-y-4 animate-fade-in-up">
									<div class="flex justify-end gap-2">
										<button
											class="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-bold rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent transition-all shadow-sm"
											onclick={() => copyLetterPlainText(findingsLetter!, 'Findings email')}
										>
											Copy Plain Text
										</button>
										<button
											class="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-bold rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent transition-all shadow-sm"
											onclick={() => downloadLetter(findingsLetter!, `findings-email-${caseId}.html`)}
										>
											Download HTML
									</button>
								</div>
								<div class="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-inner">
									<iframe srcdoc={findingsLetter.replace(/\\n/g, '\n')} title="Findings Email" class="w-full h-[600px] border-0" sandbox=""></iframe>
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
									<label for="opposing-party" class="block text-sm font-bold text-contrast mb-1.5">Opposing Party</label>
									<select
										id="opposing-party"
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
									<label for="demand-amount" class="block text-sm font-bold text-contrast mb-1.5">Demand Amount ($)</label>
									<div class="flex gap-2">
										<input
											id="demand-amount"
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
									<label for="response-deadline" class="block text-sm font-bold text-contrast mb-1.5">Response Deadline</label>
									<select
										id="response-deadline"
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
									<label for="specific-demands" class="block text-sm font-bold text-contrast mb-1.5">Specific Demands (one per line)</label>
									<textarea
										id="specific-demands"
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
												<div class="flex items-center gap-2">
													<button
														class="inline-flex items-center px-3 py-1.5 border border-gray-300 text-xs font-bold rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent transition-all"
														onclick={() => copyLetterRichText(letterHtml, `Demand letter for ${partyName}`)}
													>
														Copy Rich Text
													</button>
													<button
														class="inline-flex items-center px-3 py-1.5 border border-gray-300 text-xs font-bold rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent transition-all"
														onclick={() => downloadLetter(letterHtml, `demand-letter-${partyName}.html`)}
													>
														Download HTML
													</button>
												</div>
											</div>
											<div class="p-4">
												<div class="border border-gray-200 rounded-lg bg-white overflow-hidden shadow-inner">
													<iframe srcdoc={letterHtml.replace(/\\n/g, '\n')} title={`Demand Letter ${partyName}`} class="w-full h-[400px] border-0" sandbox=""></iframe>
											</div>
										</div>
									</div>
								{/each}
							</div>
						{/if}
					</section>

					<!-- Recommendation Letters Section -->
					{#if Object.keys(recommendationLetters).length > 0}
						<section class="card-standard">
							<h3 class="text-xl font-heading font-bold text-contrast mb-6">Advisory Letters</h3>
							<div class="space-y-6">
									{#each Object.entries(recommendationLetters) as [letterType, letterHtml]}
										<div class="border border-gray-200 rounded-xl overflow-hidden bg-gray-50 shadow-sm animate-fade-in-up">
											<div class="flex items-center justify-between p-4 bg-white border-b border-gray-200">
												<h4 class="font-bold text-contrast capitalize">{letterType.replace(/_/g, ' ')} Letter</h4>
												<div class="flex items-center gap-2">
													{#if letterType === 'request_documents'}
														<button
															class="inline-flex items-center px-3 py-1.5 border border-gray-300 text-xs font-bold rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent transition-all"
															onclick={() => copyLetterPlainText(letterHtml, 'Request documents letter')}
														>
															Copy Plain Text
														</button>
													{/if}
													<button
														class="inline-flex items-center px-3 py-1.5 border border-gray-300 text-xs font-bold rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent transition-all"
														onclick={() => downloadLetter(letterHtml, `${letterType}-letter-${caseId}.html`)}
													>
														Download HTML
													</button>
												</div>
											</div>
										<div class="p-4">
											<div class="border border-gray-200 rounded-lg bg-white overflow-hidden shadow-inner">
												<iframe srcdoc={letterHtml.replace(/\\n/g, '\n')} title={`${letterType} Letter`} class="w-full h-[400px] border-0" sandbox=""></iframe>
											</div>
										</div>
									</div>
								{/each}
							</div>
						</section>
					{/if}
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
					<textarea
					class="flex-1 border-0 focus:ring-0 text-sm py-3 px-4 text-contrast placeholder-gray-400 font-medium resize-none min-h-[48px] max-h-[200px]"
					rows="1"
					placeholder="Ask a question about case facts, documents, or legal strategy..."
					bind:value={chatInput}
					onkeydown={(event) => {
						if (event.key === 'Enter' && !event.shiftKey) {
							event.preventDefault();
							sendChatMessage();
						}
					}}
					disabled={sendingMessage}
				></textarea>
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
