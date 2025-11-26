import type { PageServerLoad } from './$types';
import { error } from '@sveltejs/kit';
import { PUBLIC_API_URL } from '$env/static/public';
import { env } from '$env/dynamic/private';

// Type definitions for API data structures
interface FinancialDataItem {
	amount?: number;
	payment_type?: string;
	category?: string;
	description?: string;
}

interface PrimaryIssue {
	issue_name: string;
}

interface IssueMap {
	primary_issues?: PrimaryIssue[];
}

interface FactMatrix {
	financial_data?: FinancialDataItem[];
}

interface MultiStageResult {
	fact_matrix?: FactMatrix;
	issue_map?: IssueMap;
}

interface IntakeAnalysis {
	financial_impact?: string;
}

interface CaseAnalysis {
	intake_analysis?: IntakeAnalysis;
}

interface KeyAmount {
	amount?: string;
	description?: string;
}

interface DocumentSummary {
	document_name: string;
	key_amounts?: KeyAmount[];
}

interface OpposingParty {
	name: string;
}

interface GeneratedLetters {
	findings?: string;
	[key: string]: string | undefined;
}

interface AnalysisResults {
	case_analysis?: string | CaseAnalysis;
	document_summaries?: string | DocumentSummary[];
	generated_letters?: GeneratedLetters;
	opposing_parties?: OpposingParty[];
	multi_stage_result?: MultiStageResult;
}

interface ProfileResponse {
	full_name?: string;
	firm_name?: string;
	phone?: string;
	email?: string;
}

export const load: PageServerLoad = async ({ params, locals, fetch }) => {
	const { session, supabase } = locals;

	if (!session) {
		throw error(401, 'Unauthorized');
	}

	const caseId = params.id;
	
	// Determine API URL for server-side fetch
	// CRITICAL: On Vercel, use relative paths so SvelteKit's fetch can route internally
	// without hitting the external edge network which requires authentication
	let API_URL = 'http://127.0.0.1:8000';
	
	if (env.VERCEL_URL) {
		// On Vercel: Use empty string for relative paths (same as client-side)
		API_URL = '';
	} else if (PUBLIC_API_URL && !PUBLIC_API_URL.includes('supabase.co')) {
		// Only use PUBLIC_API_URL if it's NOT a Supabase URL (common misconfiguration)
		API_URL = PUBLIC_API_URL;
	}

	try {
		// Fetch all data in parallel - READ BODIES IMMEDIATELY in .then() chains
		// This prevents SvelteKit's fetch wrapper from consuming the body before we can read it
		const [resultsData, documentsResponse, profileData] = await Promise.all([
			// Fetch and read results immediately
			fetch(`${API_URL}/api/analysis/results/${caseId}`, {
				headers: {
					Authorization: `Bearer ${session.access_token}`
				}
			}).then(async (res) => {
				const text = await res.text();
				return { ok: res.ok, status: res.status, text };
			}),
			
			// Fetch documents (Supabase query - unchanged)
			supabase
				.from('documents')
				.select('*')
				.eq('case_id', caseId)
				.order('created_at', { ascending: true }),
			
			// Fetch and read profile immediately
			fetch(`${API_URL}/api/profile`, {
				headers: {
					Authorization: `Bearer ${session.access_token}`
				}
			}).then(async (res) => {
				const text = await res.text();
				return { ok: res.ok, status: res.status, text };
			})
		]);

		// Handle results - body already read as text
		let results: AnalysisResults;
		if (!resultsData.ok) {
			console.error('Failed to load results:', resultsData.status, resultsData.text);
			throw error(resultsData.status, `Failed to load results: ${resultsData.text}`);
		}

		try {
			results = JSON.parse(resultsData.text) as AnalysisResults;
		} catch (parseError) {
			console.error('Failed to parse results JSON:', parseError);
			throw error(500, 'Failed to parse analysis results');
		}

		// Parse case_analysis if it's a JSON string
		if (results.case_analysis && typeof results.case_analysis === 'string') {
			try {
				results.case_analysis = JSON.parse(results.case_analysis);
			} catch (e) {
				console.error('Failed to parse case_analysis:', e);
			}
		}

		// Parse document_summaries if it's a JSON string
		if (results.document_summaries && typeof results.document_summaries === 'string') {
			try {
				results.document_summaries = JSON.parse(results.document_summaries);
			} catch (e) {
				console.error('Failed to parse document_summaries:', e);
			}
		}

		// Parse generated letters
		let findingsLetter: string | null = null;
		let demandLetters: Record<string, string> = {};

		if (results.generated_letters) {
			if (results.generated_letters.findings) {
				findingsLetter = results.generated_letters.findings;
			}
			const demandEntries = Object.entries(results.generated_letters).filter(([key]) =>
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
		let selectedParty = '';
		let demandAmount: number | null = null;
		let specificDemands = '';

		if (results.opposing_parties && results.opposing_parties.length > 0) {
			selectedParty = results.opposing_parties[0].name;
		}

		// Try to find demand amount from various sources
		let foundAmount = false;

		// 1. Try multi_stage_result first (most structured)
		if (results.multi_stage_result && !foundAmount) {
			const factMatrix = results.multi_stage_result.fact_matrix || {};
			const financialData = factMatrix.financial_data || [];

			// Look for claimed/owed amounts first
			const claimedAmount = financialData.find(
				(item) => item.payment_type === 'claimed' || item.category === 'damages_claimed'
			);

			if (claimedAmount?.amount) {
				demandAmount = claimedAmount.amount;
				foundAmount = true;
			} else {
				// Try any "owed" amount
				const owedAmount = financialData.find(
					(item) =>
						item.payment_type === 'owed' ||
						item.description?.toLowerCase().includes('owed') ||
						item.description?.toLowerCase().includes('damage')
				);
				if (owedAmount?.amount) {
					demandAmount = owedAmount.amount;
					foundAmount = true;
				} else if (financialData.length > 0) {
					// Fallback: use the largest amount found
					const maxAmountItem = financialData.reduce((prev, current) =>
						(prev.amount ?? 0) > (current.amount ?? 0) ? prev : current
					);
					if (maxAmountItem?.amount) {
						demandAmount = maxAmountItem.amount;
						foundAmount = true;
					}
				}
			}

			// Primary issues for specific demands
			const issueMap = results.multi_stage_result.issue_map || {};
			const primaryIssues = issueMap.primary_issues || [];
			if (primaryIssues.length > 0) {
				specificDemands = primaryIssues
					.map((issue) => `Resolve the issue of ${issue.issue_name} by providing appropriate remedies.`)
					.join('\n');
			} else {
				specificDemands = 'Provide full and timely compliance with all outstanding obligations.';
			}
		}

		// 2. Fall back to case_analysis financial_impact
		if (!foundAmount && typeof results.case_analysis === 'object') {
			const financialText = results.case_analysis.intake_analysis?.financial_impact;
			if (financialText) {
				// Extract dollar amounts from text
				const amountMatch = financialText.match(/\$[\d,]+(?:\.\d{2})?/);
				if (amountMatch) {
					const amountStr = amountMatch[0].replace(/[$,]/g, '');
					demandAmount = parseFloat(amountStr);
					foundAmount = true;
				}
			}
		}

		// 3. Fall back to document summaries key_amounts
		if (!foundAmount && results.document_summaries && Array.isArray(results.document_summaries)) {
			for (const doc of results.document_summaries) {
				if (doc.key_amounts && Array.isArray(doc.key_amounts)) {
					for (const amount of doc.key_amounts) {
						if (
							amount.description?.toLowerCase().includes('damage') ||
							amount.description?.toLowerCase().includes('owed') ||
							amount.description?.toLowerCase().includes('claim')
						) {
							// Extract numeric value from formatted string
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

		// 4. Last resort: use any financial amount from documents
		if (!foundAmount && results.document_summaries && Array.isArray(results.document_summaries)) {
			for (const doc of results.document_summaries) {
				if (doc.key_amounts && Array.isArray(doc.key_amounts) && doc.key_amounts.length > 0) {
					const firstAmount = doc.key_amounts[0];
					const amountStr = firstAmount.amount?.replace(/[$,]/g, '');
					if (amountStr) {
						demandAmount = parseFloat(amountStr);
						foundAmount = true;
						break;
					}
				}
			}
		}

		// Initialize all documents as collapsed
		const collapsedDocs = new Set<string>();
		if (Array.isArray(results.document_summaries) && results.document_summaries.length > 0) {
			results.document_summaries.forEach((doc) => {
				collapsedDocs.add(doc.document_name);
			});
		}

		// Handle documents response
		const documents = documentsResponse.error ? [] : documentsResponse.data || [];

		// Handle profile - body already read as text
		let profile: ProfileResponse | null = null;
		if (profileData.ok) {
			try {
				profile = JSON.parse(profileData.text) as ProfileResponse;
			} catch (e) {
				console.error('Failed to parse profile JSON:', e);
			}
		}

		return {
			caseId,
			results,
			documents,
			findingsLetter,
			demandLetters,
			selectedParty,
			demandAmount,
			specificDemands,
			demandDeadline: '10 business days',
			collapsedDocs: Array.from(collapsedDocs),
			profile: profile
				? {
						attorneyName: profile.full_name || '',
						firmName: profile.firm_name || '',
						contactPhone: profile.phone || '',
						contactEmail: profile.email || ''
				  }
				: null
		};
	} catch (err) {
		console.error('Error loading results page data:', err);
		const message = err instanceof Error ? err.message : 'Failed to load results';
		throw error(500, message);
	}
};

