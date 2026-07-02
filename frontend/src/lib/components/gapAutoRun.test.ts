import { describe, it, expect } from 'vitest';
import { shouldAutoRunGapAnalysis } from '$lib/utils/gapAutoRun';

// Matrix mirrors the page's original `autoRunGapAnalysis || !gapAnalysis`
// condition with the new multi-stage gate in front of it.
describe('shouldAutoRunGapAnalysis', () => {
	it('returns false when no multi-stage support, even with auto-run requested', () => {
		expect(shouldAutoRunGapAnalysis({
			hasMultiStageSupport: false,
			hasGapAnalysis: false,
			autoRunEnabled: true
		})).toBe(false);
	});

	it('returns false when no multi-stage support, regardless of other flags', () => {
		expect(shouldAutoRunGapAnalysis({
			hasMultiStageSupport: false,
			hasGapAnalysis: false,
			autoRunEnabled: false
		})).toBe(false);
		expect(shouldAutoRunGapAnalysis({
			hasMultiStageSupport: false,
			hasGapAnalysis: true,
			autoRunEnabled: true
		})).toBe(false);
		expect(shouldAutoRunGapAnalysis({
			hasMultiStageSupport: false,
			hasGapAnalysis: true,
			autoRunEnabled: false
		})).toBe(false);
	});

	it('returns true when multi-stage supported, no gap analysis, and auto-run requested', () => {
		expect(shouldAutoRunGapAnalysis({
			hasMultiStageSupport: true,
			hasGapAnalysis: false,
			autoRunEnabled: true
		})).toBe(true);
	});

	it('returns true on first visit (no gap analysis yet) even without an explicit request', () => {
		expect(shouldAutoRunGapAnalysis({
			hasMultiStageSupport: true,
			hasGapAnalysis: false,
			autoRunEnabled: false
		})).toBe(true);
	});

	it('returns true when explicitly requested even if a gap analysis already exists', () => {
		// Matches the original OR: autoRunGapAnalysis=true forced a run
		expect(shouldAutoRunGapAnalysis({
			hasMultiStageSupport: true,
			hasGapAnalysis: true,
			autoRunEnabled: true
		})).toBe(true);
	});

	it('returns false when gap analysis exists and no explicit request', () => {
		expect(shouldAutoRunGapAnalysis({
			hasMultiStageSupport: true,
			hasGapAnalysis: true,
			autoRunEnabled: false
		})).toBe(false);
	});
});
