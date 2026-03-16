import { render, screen } from '@testing-library/svelte';
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

function makeParties() {
	return [
		{ name: 'Acme Corp', role: 'Defendant' },
		{ name: 'Smith LLC', role: 'Co-Defendant' },
	];
}

describe('DemandLetterSection', () => {
	it('renders party dropdown with options', () => {
		render(DemandLetterSection, {
			props: { caseId: 'case-1', opposingParties: makeParties() },
		});
		const select = document.querySelector('[data-testid="party-select"]') as HTMLSelectElement;
		expect(select).toBeTruthy();
		// Default "Select party" + 2 parties
		expect(select.options.length).toBe(3);
	});

	it('disables generate without party selected', () => {
		render(DemandLetterSection, {
			props: { caseId: 'case-1', opposingParties: [] },
		});
		const generateBtn = document.querySelector('[data-testid="generate-btn"]') as HTMLButtonElement;
		expect(generateBtn.disabled).toBe(true);
	});

	it('shows demand amount input', () => {
		render(DemandLetterSection, {
			props: { caseId: 'case-1', opposingParties: makeParties() },
		});
		const input = document.querySelector('#demand-amount') as HTMLInputElement;
		expect(input).toBeTruthy();
		expect(input.type).toBe('number');
	});

	it('renders attorney info fields', () => {
		render(DemandLetterSection, {
			props: { caseId: 'case-1', opposingParties: makeParties() },
		});
		const inputs = document.querySelectorAll('input[type="text"], input[type="tel"], input[type="email"]');
		// attorneyName, firmName, contactPhone, contactEmail
		expect(inputs.length).toBeGreaterThanOrEqual(4);
	});

	it('shows generated letter in iframe when initialDemandLetters provided', () => {
		render(DemandLetterSection, {
			props: {
				caseId: 'case-1',
				opposingParties: makeParties(),
				initialDemandLetters: { 'Acme Corp': '<html><body>Demand</body></html>' },
			},
		});
		const iframe = document.querySelector('iframe') as HTMLIFrameElement;
		expect(iframe).toBeTruthy();
		expect(iframe.title).toContain('Acme Corp');
	});

	it('shows copy and download buttons for generated letter', () => {
		render(DemandLetterSection, {
			props: {
				caseId: 'case-1',
				opposingParties: makeParties(),
				initialDemandLetters: { 'Acme Corp': '<html>Letter</html>' },
			},
		});
		expect(screen.getByText('Copy Rich Text')).toBeTruthy();
		expect(screen.getByText('Download HTML')).toBeTruthy();
	});

	it('populates initial demand amount from prop', () => {
		render(DemandLetterSection, {
			props: {
				caseId: 'case-1',
				opposingParties: makeParties(),
				initialDemandAmount: 50000,
			},
		});
		const input = document.querySelector('#demand-amount') as HTMLInputElement;
		expect(input).toBeTruthy();
		expect(Number(input.value)).toBe(50000);
	});

	it('populates initial specific demands from prop', () => {
		render(DemandLetterSection, {
			props: {
				caseId: 'case-1',
				opposingParties: makeParties(),
				initialSpecificDemands: 'Return the deposit',
			},
		});
		const textarea = document.querySelector('#specific-demands') as HTMLTextAreaElement;
		expect(textarea).toBeTruthy();
		expect(textarea.value).toBe('Return the deposit');
	});
});
