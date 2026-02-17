import { describe, expect, it } from 'vitest';

import { deriveBlacklistRule, isNameBlacklisted, toCanonicalBlacklistTerm } from './blacklist';

describe('blacklist utilities', () => {
	it('derives a generalized rule from parenthetical filenames', () => {
		const rule = deriveBlacklistRule(
			'Attorney Representation Agreement (Metlife ELIGIBILITY ID) (Mary Ann Rivera).pdf'
		);
		expect(rule).toBe('attorney representation agreement');
	});

	it('canonicalizes names consistently', () => {
		expect(toCanonicalBlacklistTerm('What to Expect in a Demand (MC).PDF')).toBe(
			'what to expect in a demand'
		);
	});

	it('matches similar variants of the same document family', () => {
		const blacklist = [
			'Attorney Representation Agreement (Metlife ELIGIBILITY ID) (Mary Ann Rivera).pdf'
		];
		expect(
			isNameBlacklisted(
				'Attorney Representation Agreement (Metlife ELIGIBILITY ID) (Clifton Price).pdf',
				blacklist
			)
		).toBe(true);
	});
});

