import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import QualityTab from './QualityTab.svelte';

function makeItem(overrides: Record<string, any> = {}) {
	return {
		document: 'Contract.pdf',
		document_id: 'doc-1',
		score: 7.5,
		confidence_level: 'high',
		issues: [],
		...overrides,
	};
}

describe('QualityTab', () => {
	it('renders quality report heading', () => {
		render(QualityTab, { props: { qualityReport: [], onviewdocument: vi.fn() } });
		const heading = document.querySelector('[data-testid="quality-heading"]');
		expect(heading).toBeTruthy();
		expect(heading?.textContent).toContain('Quality Report');
	});

	it('shows empty state when no data', () => {
		render(QualityTab, { props: { qualityReport: null, onviewdocument: vi.fn() } });
		const empty = document.querySelector('[data-testid="quality-empty"]');
		expect(empty).toBeTruthy();
		expect(empty?.textContent).toContain('No quality report data');
	});

	it('sorts items by score ascending', () => {
		const items = [
			makeItem({ document: 'High.pdf', score: 9 }),
			makeItem({ document: 'Low.pdf', score: 3 }),
			makeItem({ document: 'Mid.pdf', score: 6 }),
		];
		render(QualityTab, { props: { qualityReport: items, onviewdocument: vi.fn() } });
		const qualityItems = document.querySelectorAll('[data-testid="quality-item"]');
		expect(qualityItems.length).toBe(3);
		// First item should be the lowest score
		expect(qualityItems[0].textContent).toContain('Low.pdf');
		expect(qualityItems[2].textContent).toContain('High.pdf');
	});

	it('applies red styling for low scores', () => {
		const items = [makeItem({ score: 3 })];
		render(QualityTab, { props: { qualityReport: items, onviewdocument: vi.fn() } });
		const item = document.querySelector('[data-testid="quality-item"]');
		expect(item?.className).toContain('border-l-red-500');
		expect(item?.textContent).toContain('Review Required');
	});

	it('calls onviewdocument on click', async () => {
		const onviewdocument = vi.fn();
		const items = [makeItem({ document: 'Contract.pdf', document_id: 'doc-1' })];
		render(QualityTab, { props: { qualityReport: items, onviewdocument } });
		const button = screen.getByText('Contract.pdf');
		await fireEvent.click(button);
		expect(onviewdocument).toHaveBeenCalledWith('Contract.pdf', 'doc-1');
	});
});
