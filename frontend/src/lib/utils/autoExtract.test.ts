import { describe, it, expect } from 'vitest';
import { shouldAutoExtract } from './autoExtract';

const needing = [{ status: 'pending', extracted_at: null, extracted_text: null }];
const healthy = [{ status: 'ready', extracted_at: '2026-01-01', extracted_text: 'x' }];
const skipped = [{ status: 'skipped_small_image', extracted_at: null, extracted_text: null }];
const base = {
	flagEnabled: true,
	analysisInProgress: false,
	importInProgress: false,
	alreadyRanThisLoad: false,
};

describe('shouldAutoExtract', () => {
	it('runs when flag on and docs need extraction', () => {
		expect(shouldAutoExtract(needing as any, base)).toBe(true);
	});
	it('never runs when flag off', () => {
		expect(shouldAutoExtract(needing as any, { ...base, flagEnabled: false })).toBe(false);
	});
	it('does not run when all docs healthy', () => {
		expect(shouldAutoExtract(healthy as any, base)).toBe(false);
	});
	it('ignores skipped documents', () => {
		expect(shouldAutoExtract(skipped as any, base)).toBe(false);
	});
	it('does not run during analysis', () => {
		expect(shouldAutoExtract(needing as any, { ...base, analysisInProgress: true })).toBe(false);
	});
	it('does not run during an import', () => {
		expect(shouldAutoExtract(needing as any, { ...base, importInProgress: true })).toBe(false);
	});
	it('runs at most once per page load', () => {
		expect(shouldAutoExtract(needing as any, { ...base, alreadyRanThisLoad: true })).toBe(false);
	});
});
