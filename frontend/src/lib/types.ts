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
	clio_last_synced_at: string | null;
	needs_reanalysis: boolean;
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
 * Document Grouping Types
 * Used when related documents are processed as a single unit (e.g., bank statements, email threads).
 */

/**
 * Types of document groups detected by the pipeline.
 */
export type GroupType =
	| 'email_thread'
	| 'contract_family'
	| 'photo_sequence'
	| 'bank_statements'
	| 'credit_card_statements'
	| 'medical_records'
	| 'financial_reports'
	| 'insurance_claims'
	| 'text_messages'
	| 'real_estate_package'
	| 'generic';

/**
 * A group of related documents processed as a single unit.
 */
export interface DocumentGroup {
	group_id: string;
	group_type: GroupType;
	label: string;
	member_document_ids: string[];
	member_document_names: string[];
	member_count: number;
	group_metadata: Record<string, unknown>;
	authority_score: number | null;
	canonical_document_id: string | null;
}

/**
 * Summary generated for a document group (replaces N individual summaries with 1).
 */
export interface GroupSummary {
	group_id: string;
	group_type: GroupType;
	label: string;
	member_count: number;
	member_document_names: string[];
	combined_narrative: string;
	key_findings: string[];
	structured_data: Record<string, unknown>;
	legal_significance: string | null;
	key_quotes: string[];
	authority_score: number | null;
	extraction_quality: 'high' | 'medium' | 'low';
}

/**
 * Human-readable labels for group types.
 */
export const GROUP_TYPE_LABELS: Record<GroupType, string> = {
	email_thread: 'Email Thread',
	contract_family: 'Contract Family',
	photo_sequence: 'Photo Sequence',
	bank_statements: 'Bank Statements',
	credit_card_statements: 'Credit Card Statements',
	medical_records: 'Medical Records',
	financial_reports: 'Financial Reports',
	insurance_claims: 'Insurance Claims',
	text_messages: 'Text Messages',
	real_estate_package: 'Real Estate Package',
	generic: 'Related Documents',
};

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
	| 'hallucination_risk'
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
	reconciliation_notes?: string[];
	recommendation?: CaseRecommendation;
}

/**
 * User-provided resolution payload for selective gap refresh.
 */
export interface GapResolutionInput {
	gap_id: string;
	resolution_text: string;
	mark_resolved?: boolean;
	related_document_ids?: string[];
}

export interface GapResolutionRefreshRequest {
	case_id: string;
	resolutions: GapResolutionInput[];
	global_resolution_notes?: string;
	attached_document_ids?: string[];
	force_refresh?: boolean;
}

/**
 * Case Recommendation Types (NEW - 2025-02-03)
 * Categories for case recommendations based on gap analysis.
 */

/**
 * Categories for case recommendations based on gap analysis.
 */
export type CaseRecommendationCategory =
	| 'strong_case'
	| 'needs_documentation'
	| 'settlement_recommended'
	| 'not_viable';

/**
 * Confidence levels for recommendations.
 */
export type ConfidenceLevel = 'high' | 'medium' | 'low';

/**
 * Types of letters that can be recommended based on case analysis.
 */
export type RecommendedLetterType =
	| 'proceed'
	| 'request_documents'
	| 'settlement_advisory'
	| 'declination'
	| 'findings'
	| 'demand';

/**
 * Recommendation generated from gap analysis results.
 */
export interface CaseRecommendation {
	category: CaseRecommendationCategory;
	confidence: ConfidenceLevel;
	reasoning: string;
	next_steps: string[];
	suggested_letter_type: RecommendedLetterType;
	category_display_name: string;
	category_color: 'green' | 'yellow' | 'orange' | 'red';
}
