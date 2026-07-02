import { render } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import DemandLetterSection from './DemandLetterSection.svelte';

vi.mock('$lib/config', () => ({
	getApiUrl: () => 'http://localhost:8000',
}));

vi.mock('$lib/supabase', () => ({
	getSecureSession: vi.fn().mockResolvedValue({ session: null, user: null }),
}));

vi.mock('$lib/stores/toastStore', () => ({
	toastStore: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('$lib/utils/letterCopy', () => ({
	letterHtmlToPlainText: (html: string) => html,
	letterHtmlToRichFragment: (html: string) => html,
	normalizeLetterHtml: (html: string) => html,
}));

vi.mock('$lib/utils/markdown', () => ({
	parseMarkdown: (md: string) => md,
}));

vi.mock('$lib/utils/sseEventParser', () => ({
	SSEEventParser: vi.fn().mockImplementation(() => ({
		push: vi.fn().mockReturnValue([]),
	})),
}));

vi.mock('$lib/utils/fetchWithRetry', () => ({
	fetchWithRetry: vi.fn().mockResolvedValue(new Response('', { status: 200 })),
}));

function makeParties() {
	return [
		{ name: 'Acme Corp', role: 'Defendant' },
		{ name: 'Smith LLC', role: 'Co-Defendant' },
	];
}

describe('DemandLetterSection attorney prefill', () => {
	it('prefills attorney fields from props', () => {
		render(DemandLetterSection, {
			props: {
				analysisId: 'analysis-1',
				caseId: 'case-1',
				opposingParties: makeParties(),
				attorneyName: 'Jane Doe',
				firmName: 'Doe & Associates',
				contactPhone: '555-1234',
				contactEmail: 'jane@doe.com',
			},
		});

		const attorneyInput = document.querySelector('input[placeholder="Attorney name"]') as HTMLInputElement;
		const firmInput = document.querySelector('input[placeholder="Firm name"]') as HTMLInputElement;
		const phoneInput = document.querySelector('input[placeholder="Phone number"]') as HTMLInputElement;
		const emailInput = document.querySelector('input[placeholder="Email address"]') as HTMLInputElement;

		expect(attorneyInput.value).toBe('Jane Doe');
		expect(firmInput.value).toBe('Doe & Associates');
		expect(phoneInput.value).toBe('555-1234');
		expect(emailInput.value).toBe('jane@doe.com');
	});

	it('defaults attorney fields to empty when no props provided', () => {
		render(DemandLetterSection, {
			props: { analysisId: 'analysis-1', caseId: 'case-1', opposingParties: makeParties() },
		});

		const attorneyInput = document.querySelector('input[placeholder="Attorney name"]') as HTMLInputElement;
		const firmInput = document.querySelector('input[placeholder="Firm name"]') as HTMLInputElement;
		const phoneInput = document.querySelector('input[placeholder="Phone number"]') as HTMLInputElement;
		const emailInput = document.querySelector('input[placeholder="Email address"]') as HTMLInputElement;

		expect(attorneyInput.value).toBe('');
		expect(firmInput.value).toBe('');
		expect(phoneInput.value).toBe('');
		expect(emailInput.value).toBe('');
	});
});
