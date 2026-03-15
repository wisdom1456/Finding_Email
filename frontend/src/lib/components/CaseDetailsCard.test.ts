import { render, screen } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import CaseDetailsCard from './CaseDetailsCard.svelte';

vi.mock('$lib/config', () => ({
	getApiUrl: () => 'http://localhost:8000',
}));

vi.mock('$lib/supabase', () => ({
	getSecureSession: vi.fn().mockResolvedValue({ session: null, user: null }),
}));

vi.mock('$lib/utils/formatters', () => ({
	formatDate: (d: string) => d ?? 'N/A',
}));

function makeCaseData(overrides: Record<string, any> = {}) {
	return {
		client_name: 'John Doe',
		jurisdiction: 'Florida',
		reference_number: 'REF-123',
		created_at: '2025-01-01',
		updated_at: '2025-01-15',
		description: 'Test case description',
		...overrides,
	};
}

describe('CaseDetailsCard', () => {
	it('renders case client name', () => {
		render(CaseDetailsCard, {
			props: { caseData: makeCaseData(), caseId: 'case-1', onsaved: vi.fn(), onerror: vi.fn() },
		});
		expect(screen.getByText('John Doe')).toBeTruthy();
	});

	it('renders jurisdiction badge', () => {
		render(CaseDetailsCard, {
			props: { caseData: makeCaseData(), caseId: 'case-1', onsaved: vi.fn(), onerror: vi.fn() },
		});
		expect(screen.getByText('Florida')).toBeTruthy();
	});

	it('renders reference number', () => {
		render(CaseDetailsCard, {
			props: { caseData: makeCaseData(), caseId: 'case-1', onsaved: vi.fn(), onerror: vi.fn() },
		});
		expect(screen.getByText('REF-123')).toBeTruthy();
	});

	it('renders Case Details heading', () => {
		render(CaseDetailsCard, {
			props: { caseData: makeCaseData(), caseId: 'case-1', onsaved: vi.fn(), onerror: vi.fn() },
		});
		expect(screen.getByText('Case Details')).toBeTruthy();
	});
});
