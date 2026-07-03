import { describe, it, expect } from 'vitest';
import { shouldAutoExtract, docNeedsExtraction } from './autoExtract';

const needing = [{ status: 'pending', extracted_at: null, extracted_text: null }];
const healthy = [{ status: 'ready', extracted_at: '2026-01-01', extracted_text: 'x' }];
const skipped = [{ status: 'skipped_small_image', extracted_at: null, extracted_text: null }];
const junk = [{ status: 'pending', extracted_at: null, extracted_text: null, is_flagged_as_junk: true }];
// Clio-imported text docs: 'ready' with text but no extracted_at, and the list
// payload omits extracted_text — extracted_at must NOT be treated as "no text".
const clioReadyNoStamp = [{ status: 'ready', extracted_at: null, extracted_text: null }];
const reviewNoStamp = [{ status: 'needs_review', extracted_at: null, extracted_text: null }];
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
	it('ignores junk-flagged documents', () => {
		expect(shouldAutoExtract(junk as any, base)).toBe(false);
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
	it('does NOT run for ready Clio text docs lacking extracted_at (regression)', () => {
		expect(shouldAutoExtract(clioReadyNoStamp as any, base)).toBe(false);
	});
});

describe('docNeedsExtraction', () => {
	it('flags a pending doc with no text', () => {
		expect(docNeedsExtraction(needing[0] as any)).toBe(true);
	});
	it('does NOT flag a ready doc that has no extracted_at (Clio text doc)', () => {
		expect(docNeedsExtraction(clioReadyNoStamp[0] as any)).toBe(false);
	});
	it('does NOT flag a needs_review doc lacking extracted_at (has text by construction)', () => {
		expect(docNeedsExtraction(reviewNoStamp[0] as any)).toBe(false);
	});
	it('does NOT flag a doc that already has extracted_text', () => {
		expect(docNeedsExtraction(healthy[0] as any)).toBe(false);
	});
	it('ignores junk and excluded statuses', () => {
		expect(docNeedsExtraction(junk[0] as any)).toBe(false);
		expect(docNeedsExtraction(skipped[0] as any)).toBe(false);
	});
});
