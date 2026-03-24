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

	it('shows coverage percentage with AI-analyzed label', () => {
		render(DocumentCoverageSection, {
			props: { totalDocuments: 10, fullyAnalyzed: 8 },
		});
		expect(screen.getByText('80% AI-analyzed')).toBeTruthy();
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
		expect(screen.getByText('0% AI-analyzed')).toBeTruthy();
	});

	it('shows excluded count when skipped docs provided', () => {
		render(DocumentCoverageSection, {
			props: { totalDocuments: 10, fullyAnalyzed: 8, skipped: 2 },
		});
		expect(screen.getByText('2 excluded')).toBeTruthy();
	});

	it('shows metadata-only count when provided', () => {
		render(DocumentCoverageSection, {
			props: { totalDocuments: 10, fullyAnalyzed: 5, metadataOnly: 3 },
		});
		expect(screen.getByText(/3 catalogued/)).toBeTruthy();
	});

	it('shows skipped bar segment in progress bar', () => {
		render(DocumentCoverageSection, {
			props: { totalDocuments: 10, fullyAnalyzed: 5, skipped: 3, metadataOnly: 2 },
		});
		// All categories should be visible
		expect(screen.getByText('5 fully analyzed')).toBeTruthy();
		expect(screen.getByText(/2 catalogued/)).toBeTruthy();
		expect(screen.getByText('3 excluded')).toBeTruthy();
	});

	it('shows accounted-for message when all docs classified', () => {
		render(DocumentCoverageSection, {
			props: { totalDocuments: 10, fullyAnalyzed: 5, metadataOnly: 3, skipped: 2 },
		});
		expect(screen.getByText(/All 10 documents are accounted for/)).toBeTruthy();
	});
});
