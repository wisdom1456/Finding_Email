import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import IntakeFormSelector from './IntakeFormSelector.svelte';

vi.mock('$lib/utils/documentClassification', () => ({
	isCaseSummary: (doc: any) => doc.file_name?.includes('Summary'),
}));

vi.mock('$lib/utils/formatters', () => ({
	formatFileSize: (size: number) => `${Math.round(size / 1024)} KB`,
}));

function makeDoc(overrides: Record<string, any> = {}) {
	return {
		id: 'doc-1',
		file_name: 'Intake_Form.pdf',
		file_type: 'application/pdf',
		file_size: 51200,
		extracted_at: '2025-01-01T00:00:00Z',
		metadata: {},
		...overrides,
	};
}

describe('IntakeFormSelector', () => {
	it('renders document list with radio buttons', () => {
		const docs = [makeDoc(), makeDoc({ id: 'doc-2', file_name: 'Summary.pdf' })];
		render(IntakeFormSelector, {
			props: { intakeCandidates: docs, onconfirm: vi.fn(), oncancel: vi.fn() },
		});
		const radios = document.querySelectorAll('input[type="radio"]');
		expect(radios.length).toBe(2);
	});

	it('shows heading prompt', () => {
		render(IntakeFormSelector, {
			props: { intakeCandidates: [makeDoc()], onconfirm: vi.fn(), oncancel: vi.fn() },
		});
		expect(screen.getByText('Select Primary Intake Document')).toBeTruthy();
	});

	it('calls oncancel when cancel button clicked', async () => {
		const oncancel = vi.fn();
		render(IntakeFormSelector, {
			props: { intakeCandidates: [makeDoc()], onconfirm: vi.fn(), oncancel },
		});
		const cancelBtn = screen.getByText('Cancel');
		await fireEvent.click(cancelBtn);
		expect(oncancel).toHaveBeenCalled();
	});

	it('disables confirm when no selection', () => {
		render(IntakeFormSelector, {
			props: { intakeCandidates: [makeDoc()], selectedIntakeDocId: null, onconfirm: vi.fn(), oncancel: vi.fn() },
		});
		const confirmBtn = document.querySelector('[data-testid="async-button"]') as HTMLButtonElement;
		expect(confirmBtn.disabled).toBe(true);
	});
});
