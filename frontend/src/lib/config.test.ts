import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock the $env module before importing config
vi.mock('$env/static/public', () => ({
	PUBLIC_API_URL: 'http://127.0.0.1:8000',
}));

vi.mock('$app/environment', () => ({
	browser: true,
}));

describe('getApiUrl', () => {
	const originalWindow = globalThis.window;
	let getApiUrl: () => string;

	beforeEach(async () => {
		// Re-import to get fresh module
		vi.resetModules();
		const mod = await import('./config');
		getApiUrl = mod.getApiUrl;
	});

	afterEach(() => {
		// Restore window
		if (originalWindow) {
			Object.defineProperty(globalThis, 'window', {
				value: originalWindow,
				writable: true,
				configurable: true,
			});
		}
	});

	it('returns env var when on localhost', () => {
		Object.defineProperty(window, 'location', {
			value: { hostname: 'localhost', origin: 'http://localhost:5173' },
			writable: true,
			configurable: true,
		});
		expect(getApiUrl()).toBe('http://127.0.0.1:8000');
	});

	it('returns env var when on 127.0.0.1', () => {
		Object.defineProperty(window, 'location', {
			value: { hostname: '127.0.0.1', origin: 'http://127.0.0.1:5173' },
			writable: true,
			configurable: true,
		});
		expect(getApiUrl()).toBe('http://127.0.0.1:8000');
	});

	it('returns window.location.origin for production hostnames', () => {
		Object.defineProperty(window, 'location', {
			value: { hostname: 'app.example.com', origin: 'https://app.example.com' },
			writable: true,
			configurable: true,
		});
		expect(getApiUrl()).toBe('https://app.example.com');
	});

	it('returns empty string when window.location throws', () => {
		Object.defineProperty(window, 'location', {
			get() { throw new Error('no location'); },
			configurable: true,
		});
		expect(getApiUrl()).toBe('');
	});

	it('returns env var or fallback when window is undefined (server-side)', () => {
		// Simulate server-side by removing window
		const savedWindow = globalThis.window;
		// @ts-ignore - intentionally removing window
		delete globalThis.window;
		try {
			// Need to re-evaluate since window check is at call time
			expect(getApiUrl()).toBe('http://127.0.0.1:8000');
		} finally {
			Object.defineProperty(globalThis, 'window', {
				value: savedWindow,
				writable: true,
				configurable: true,
			});
		}
	});
});
