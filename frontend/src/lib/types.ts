/**
 * TypeScript type definitions for the Legal Document Analysis application.
 */

/**
 * User profile data structure from the database.
 */
export interface Profile {
	id: string;
	email: string;
	full_name: string | null;
	avatar_url: string | null;
	approved: boolean;
	role: 'user' | 'admin';
	default_jurisdiction?: string;
	created_at: string;
	updated_at: string;
}

/**
 * Clio matter data stored in the database after import.
 */
export interface ClioMatterData {
	matter_id: number;
	display_number: string;
	client_name: string;
	description: string | null;
	practice_area: string | null;
	status: string;
	imported_at: string;
	communications_count: number;
	notes_count: number;
	documents_count: number;
}

/**
 * Case data structure from the database.
 */
export interface CaseData {
	id: string;
	user_id: string;
	client_name: string;
	reference_number: string | null;
	description: string | null;
	status: string;
	jurisdiction?: string;
	created_at: string;
	updated_at: string;
	clio_matter_id: string | null;
	clio_matter_data: ClioMatterData | null;
}

/**
 * Document data structure from the database.
 */
export interface DocumentData {
	id: string;
	case_id: string;
	file_name: string;
	file_type: string;
	file_size: number;
	storage_path: string;
	status: string;
	extracted_text: string | null;
	metadata: {
		clio_source?: boolean;
		clio_type?: 'communication' | 'note' | 'document';
		clio_id?: number;
		clio_subject?: string;
		clio_date?: string;
		[key: string]: unknown;
	};
	created_at: string;
	updated_at: string;
}

/**
 * Gap Analysis Types (NEW - 2025-01-30)
 * Used to identify missing documents, contradictions, and weaknesses in case materials.
 */

/**
 * Severity levels for identified gaps.
 */
export type GapSeverity = 'critical' | 'high' | 'medium' | 'low';

/**
 * Categories of gaps that can be identified.
 */
export type GapCategory =
	| 'missing_document'
	| 'factual_contradiction'
	| 'timeline_gap'
	| 'unverifiable_claim'
	| 'incomplete_info';

/**
 * A specific gap or issue identified in the case.
 */
export interface GapItem {
	gap_id: string;
	category: GapCategory;
	severity: GapSeverity;
	title: string;
	description: string;
	affected_issue?: string;
	related_documents: string[];
	recommendations: string[];
	impact_on_case: string;
}

/**
 * Complete gap analysis result.
 */
export interface GapAnalysisResult {
	total_gaps: number;
	critical_count: number;
	high_count: number;
	medium_count: number;
	low_count: number;
	gaps_by_category: Record<GapCategory, GapItem[]>;
	overall_completeness_score: number;
	attorney_summary: string;
}

