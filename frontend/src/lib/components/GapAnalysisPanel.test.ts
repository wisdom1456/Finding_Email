import { render, screen } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import GapAnalysisPanel from './GapAnalysisPanel.svelte';
import type { GapAnalysisResult } from '$lib/types';

vi.mock('$lib/components/ui/Badge.svelte', () => ({
	default: vi.fn(),
}));

vi.mock('$lib/components/CaseRecommendationCard.svelte', () => ({
	default: vi.fn(),
}));

vi.mock('$lib/components/ui/AsyncButton.svelte', () => ({
	default: vi.fn(),
}));

function makeGapAnalysis(overrides: Partial<GapAnalysisResult> = {}): GapAnalysisResult {
	return {
		total_gaps: 2,
		critical_count: 1,
		high_count: 1,
		medium_count: 0,
		low_count: 0,
		gaps_by_category: {
			missing_document: [
				{
					gap_id: 'gap-1',
					category: 'missing_document',
					severity: 'critical',
					title: 'Missing Medical Records',
					description: 'No medical records found',
					related_documents: [],
					recommendations: ['Obtain records from provider'],
					impact_on_case: 'Cannot verify injury claims',
				},
			],
			factual_contradiction: [
				{
					gap_id: 'gap-2',
					category: 'factual_contradiction',
					severity: 'high',
					title: 'Date Discrepancy',
					description: 'Dates do not match',
					related_documents: ['doc-a.pdf'],
					recommendations: ['Verify timeline'],
					impact_on_case: 'Weakens credibility',
				},
			],
			timeline_gap: [],
			unverifiable_claim: [],
			hallucination_risk: [],
			incomplete_info: [],
		},
		overall_completeness_score: 65,
		attorney_summary: 'Case has significant gaps requiring attention.',
		...overrides,
	};
}

describe('GapAnalysisPanel', () => {
	it('renders without errors with valid props', () => {
		render(GapAnalysisPanel, { props: { gapAnalysis: makeGapAnalysis() } });
		expect(screen.getByText('Case Completeness Assessment')).toBeTruthy();
	});

	it('displays completeness score', () => {
		render(GapAnalysisPanel, { props: { gapAnalysis: makeGapAnalysis() } });
		expect(screen.getByText('65/100')).toBeTruthy();
	});

	it('displays attorney summary', () => {
		render(GapAnalysisPanel, { props: { gapAnalysis: makeGapAnalysis() } });
		expect(screen.getByText('Case has significant gaps requiring attention.')).toBeTruthy();
	});

	it('renders severity filter buttons', () => {
		render(GapAnalysisPanel, { props: { gapAnalysis: makeGapAnalysis() } });
		expect(screen.getByText('All (2)')).toBeTruthy();
		expect(screen.getByText('Critical (1)')).toBeTruthy();
		expect(screen.getByText('High (1)')).toBeTruthy();
	});

	it('renders gap titles', () => {
		render(GapAnalysisPanel, { props: { gapAnalysis: makeGapAnalysis() } });
		expect(screen.getByText('Missing Medical Records')).toBeTruthy();
		expect(screen.getByText('Date Discrepancy')).toBeTruthy();
	});

	it('shows no gaps message when all filtered out', () => {
		const emptyAnalysis = makeGapAnalysis({
			total_gaps: 0,
			critical_count: 0,
			high_count: 0,
			gaps_by_category: {
				missing_document: [],
				factual_contradiction: [],
				timeline_gap: [],
				unverifiable_claim: [],
				hallucination_risk: [],
				incomplete_info: [],
			},
		});
		render(GapAnalysisPanel, { props: { gapAnalysis: emptyAnalysis } });
		expect(screen.getByText('No gaps found matching the selected filters.')).toBeTruthy();
	});

	it('renders reconciliation notes when present', () => {
		const analysis = makeGapAnalysis({
			reconciliation_notes: ['Signature verified on contract'],
		});
		render(GapAnalysisPanel, { props: { gapAnalysis: analysis } });
		expect(screen.getByText('Gap Reconciliation Notes')).toBeTruthy();
	});
});
