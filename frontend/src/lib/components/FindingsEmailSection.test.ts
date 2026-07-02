import { render, screen } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import FindingsEmailSection from './FindingsEmailSection.svelte';
import { FINDINGS_PHASE_ORDER } from './FindingsEmailSection.utils';

vi.mock('$lib/config', () => ({
	getApiUrl: () => 'http://localhost:8000',
}));

vi.mock('$lib/supabase', () => ({
	getSecureSession: vi.fn().mockResolvedValue({ session: null, user: null }),
}));

vi.mock('$lib/stores/toastStore', () => ({
	toastStore: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

vi.mock('$lib/utils/markdown', () => ({
	parseMarkdown: (text: string) => text,
}));

vi.mock('$lib/utils/letterCopy', () => ({
	letterHtmlToPlainText: (html: string) => html,
	normalizeLetterHtml: (html: string) => html,
}));

vi.mock('$lib/utils/sseEventParser', () => ({
	SSEEventParser: vi.fn().mockImplementation(() => ({ push: () => [] })),
}));

function baseProps(overrides: Record<string, any> = {}) {
	return {
		analysisId: 'analysis-1',
		caseId: 'case-1',
		hasMultiStageSupport: true,
		multiStageError: null,
		gapAnalysis: null,
		recommendationLetters: {},
		...overrides,
	};
}

describe('FindingsEmailSection', () => {
	it('renders generate button', () => {
		render(FindingsEmailSection, { props: baseProps() });
		expect(screen.getByText('Generate Email')).toBeTruthy();
	});

	it('shows initial letter if provided', () => {
		render(FindingsEmailSection, {
			props: baseProps({ initialFindingsLetter: '<div>Test letter</div>' }),
		});
		const iframe = document.querySelector('iframe');
		expect(iframe).toBeTruthy();
		expect(iframe?.title).toContain('Findings Email');
	});

	it('shows empty state when no letter', () => {
		render(FindingsEmailSection, { props: baseProps() });
		expect(screen.getByText(/No findings email generated yet/)).toBeTruthy();
	});

	it('shows unavailable message when no multi-stage support', () => {
		render(FindingsEmailSection, {
			props: baseProps({ hasMultiStageSupport: false }),
		});
		expect(screen.getByText(/Please re-run analysis to enable this feature/)).toBeTruthy();
	});

	it('shows recommendation letters when provided', () => {
		render(FindingsEmailSection, {
			props: baseProps({
				recommendationLetters: { proceed: '<html>Proceed letter</html>' },
			}),
		});
		expect(screen.getByText('Advisory Letters')).toBeTruthy();
	});

	it('initializes findingsLetter state from initialFindingsLetter prop', () => {
		const { container } = render(FindingsEmailSection, {
			props: baseProps({ initialFindingsLetter: '<div>Pre-existing letter</div>' }),
		});
		// When initialFindingsLetter is provided, component should render the iframe (complete state)
		const iframe = container.querySelector('iframe');
		expect(iframe).toBeTruthy();
		expect(iframe?.getAttribute('srcdoc')).toContain('Pre-existing letter');
	});

	it('shows quality badges when metrics are provided', () => {
		render(FindingsEmailSection, {
			props: baseProps({
				initialFindingsLetter: '<div>Letter</div>',
				initialFindingsMetrics: { repair_applied: true, critic_applied: true },
			}),
		});
		expect(screen.getByText('Quality pass applied')).toBeTruthy();
		expect(screen.getByText('Critic-guided repair')).toBeTruthy();
	});

	describe('FINDINGS_PHASE_ORDER', () => {
		it('includes the repair phase so indexOf never returns -1 mid-generation', () => {
			expect(FINDINGS_PHASE_ORDER.indexOf('repair')).toBeGreaterThanOrEqual(0);
		});

		it('matches the backend emission sequence from letter_routes.py::stream_letter', () => {
			// strategy -> context_build -> draft_generation -> lint_validation ->
			// repair (conditional) -> polishing -> finalizing
			expect(FINDINGS_PHASE_ORDER).toEqual([
				'strategy',
				'context_build',
				'draft_generation',
				'lint_validation',
				'repair',
				'polishing',
				'finalizing'
			]);
		});

		it('places repair between lint_validation and polishing', () => {
			const lintIdx = FINDINGS_PHASE_ORDER.indexOf('lint_validation');
			const repairIdx = FINDINGS_PHASE_ORDER.indexOf('repair');
			const polishIdx = FINDINGS_PHASE_ORDER.indexOf('polishing');
			expect(lintIdx).toBeLessThan(repairIdx);
			expect(repairIdx).toBeLessThan(polishIdx);
		});
	});
});
