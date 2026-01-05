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
	document_type?: string;
	extraction_quality?: 'high' | 'medium' | 'low';
	relevance_to_case?: boolean;
	executive_summary?: string;
	key_content?: string;
	key_amounts?: KeyAmount[];
	key_quotes?: string[];
}

interface QualityReportItem {
	document: string;
	document_id?: string;
	score: number;
	confidence_level?: 'high' | 'medium' | 'low';
	issues?: string[];
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
	status?: string;
	analysis_id?: string;
	created_at?: string;
	error?: string;
	artifacts?: {
		multi_stage_error?: string;
		[key: string]: any;
	};
	// Streaming analysis fields
	quality_report?: QualityReportItem[];
	streaming_analysis?: string;  // Full markdown analysis content
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
		// Fetch results and profile - return as promises for streaming
		const resultsPromise = fetch(`${API_URL}/api/analysis/results/${caseId}`, {
			headers: {
				Authorization: `Bearer ${session.access_token}`
			}
		}).then(async (res) => {
			if (!res.ok) {
				const text = await res.text();
				throw new Error(`Failed to load results: ${text}`);
			}
			return res.json() as Promise<AnalysisResults>;
		});

		const profilePromise = fetch(`${API_URL}/api/profile`, {
			headers: {
				Authorization: `Bearer ${session.access_token}`
			}
		}).then(async (res) => {
			if (!res.ok) return null;
			return res.json() as Promise<ProfileResponse>;
		});

		// Fetch documents
		const documentsPromise = supabase
			.from('documents')
			.select('*')
			.eq('case_id', caseId)
			.order('created_at', { ascending: true })
			.then(res => res.error ? [] : res.data || []);

		return {
			caseId,
			streamed: {
				results: resultsPromise,
				documents: documentsPromise,
				profile: profilePromise
			}
		};
	} catch (err) {
		console.error('Error loading results page data:', err);
		const message = err instanceof Error ? err.message : 'Failed to load results';
		throw error(500, message);
	}
};

