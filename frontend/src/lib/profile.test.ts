import { describe, it, expect } from 'vitest';
import { isProfileCompleteForLetters, type LetterProfile } from './profile';

const base: LetterProfile = {
	full_name: 'Franklin Riley',
	default_jurisdiction: 'Florida'
};

describe('isProfileCompleteForLetters', () => {
	it('returns true when full_name has a space and jurisdiction is set', () => {
		expect(isProfileCompleteForLetters(base)).toBe(true);
	});

	it('returns false when profile is null', () => {
		expect(isProfileCompleteForLetters(null)).toBe(false);
	});

	it('returns false when full_name is null', () => {
		expect(isProfileCompleteForLetters({ ...base, full_name: null })).toBe(false);
	});

	it('returns false when full_name is empty string', () => {
		expect(isProfileCompleteForLetters({ ...base, full_name: '' })).toBe(false);
	});

	it('returns false when full_name is only whitespace', () => {
		expect(isProfileCompleteForLetters({ ...base, full_name: '   ' })).toBe(false);
	});

	it('returns false when full_name is a single word (catches "Ceryn" case)', () => {
		expect(isProfileCompleteForLetters({ ...base, full_name: 'Ceryn' })).toBe(false);
	});

	it('returns false when full_name is an email address (catches signup-trigger fallback)', () => {
		expect(isProfileCompleteForLetters({ ...base, full_name: 'ceryn@brflorida.com' })).toBe(
			false
		);
	});

	it('returns false when default_jurisdiction is missing', () => {
		const { default_jurisdiction, ...withoutJur } = base;
		expect(isProfileCompleteForLetters(withoutJur as LetterProfile)).toBe(false);
	});

	it('returns false when default_jurisdiction is empty string', () => {
		expect(isProfileCompleteForLetters({ ...base, default_jurisdiction: '' })).toBe(false);
	});

	it('accepts New Mexico as jurisdiction', () => {
		expect(
			isProfileCompleteForLetters({ ...base, default_jurisdiction: 'New Mexico' })
		).toBe(true);
	});

	it('accepts full names with multiple spaces (middle name)', () => {
		expect(
			isProfileCompleteForLetters({ ...base, full_name: 'Franklin Edward Riley' })
		).toBe(true);
	});

	it('trims surrounding whitespace before checking', () => {
		expect(
			isProfileCompleteForLetters({ ...base, full_name: '  Franklin Riley  ' })
		).toBe(true);
	});

	it('rejects a name with a trailing space and no last name', () => {
		expect(isProfileCompleteForLetters({ ...base, full_name: 'Ceryn ' })).toBe(false);
	});
});
