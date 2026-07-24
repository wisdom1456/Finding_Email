import { describe, it, expect } from 'vitest';
import { formatEta, livenessLine, substanceLine } from './waitDisplay';

describe('waitDisplay', () => {
	it('rounds eta coarsely and says almost done at 0', () => {
		expect(formatEta(380)).toBe('~6 min remaining');
		expect(formatEta(35)).toBe('~1 min remaining');
		expect(formatEta(0)).toBe('almost done');
		expect(formatEta(null)).toBe('');
	});

	it('liveness from heartbeat, not percent', () => {
		expect(livenessLine(true, 4)).toContain('Working normally');
		expect(livenessLine(false, 200)).toContain('unresponsive');
	});

	it('liveness line reports the real heartbeat age', () => {
		expect(livenessLine(true, 4)).toContain('updated 4s ago');
	});

	it('substance line uses item counts when present, degrades otherwise', () => {
		expect(substanceLine(42, 71, 3)).toBe('42 of 71 documents');
		expect(substanceLine(null, null, 5)).toBe('This step takes several minutes on large cases');
	});
});
