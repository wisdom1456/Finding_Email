import { describe, it, expect } from 'vitest';
import { shouldAutoRunGapAnalysis } from '$lib/utils/gapAutoRun';

describe('shouldAutoRunGapAnalysis', () => {
	it('returns false when no multi-stage support', () => {
		expect(shouldAutoRunGapAnalysis({
			hasMultiStageSupport: false,
			hasGapAnalysis: false,
			autoRunEnabled: true
		})).toBe(false);
	});

	it('returns true when multi-stage supported, no gap analysis, and auto-run enabled', () => {
		expect(shouldAutoRunGapAnalysis({
			hasMultiStageSupport: true,
			hasGapAnalysis: false,
			autoRunEnabled: true
		})).toBe(true);
	});

	it('returns false when gap analysis already exists', () => {
		expect(shouldAutoRunGapAnalysis({
			hasMultiStageSupport: true,
			hasGapAnalysis: true,
			autoRunEnabled: true
		})).toBe(false);
	});

	it('returns false when auto-run is disabled', () => {
		expect(shouldAutoRunGapAnalysis({
			hasMultiStageSupport: true,
			hasGapAnalysis: false,
			autoRunEnabled: false
		})).toBe(false);
	});
});
