import { render, screen } from '@testing-library/svelte';
import { describe, it, expect } from 'vitest';
import DocumentCoverageSection from './DocumentCoverageSection.svelte';

describe('DocumentCoverageSection', () => {
	it('renders without errors with numeric props', () => {
		render(DocumentCoverageSection, {
			props: { totalDocuments: 10, fullyAnalyzed: 8 },
		});
		expect(screen.getByText('Document Coverage')).toBeTruthy();
	});

	it('shows coverage percentage', () => {
		render(DocumentCoverageSection, {
			props: { totalDocuments: 10, fullyAnalyzed: 8 },
		});
		expect(screen.getByText('80%')).toBeTruthy();
	});

	it('renders fully analyzed count', () => {
		render(DocumentCoverageSection, {
			props: { totalDocuments: 10, fullyAnalyzed: 7 },
		});
		expect(screen.getByText('7 fully analyzed')).toBeTruthy();
	});

	it('shows grouped documents when provided', () => {
		render(DocumentCoverageSection, {
			props: {
				totalDocuments: 10,
				fullyAnalyzed: 5,
				groupedDocuments: 3,
				groupCount: 2,
			},
		});
		expect(screen.getByText(/3 in 2 groups/)).toBeTruthy();
	});

	it('shows 0% when totalDocuments is 0', () => {
		render(DocumentCoverageSection, {
			props: { totalDocuments: 0, fullyAnalyzed: 0 },
		});
		expect(screen.getByText('0%')).toBeTruthy();
	});

	it('shows skipped count when provided', () => {
		render(DocumentCoverageSection, {
			props: { totalDocuments: 10, fullyAnalyzed: 8, skipped: 2 },
		});
		expect(screen.getByText('2 skipped')).toBeTruthy();
	});
});
