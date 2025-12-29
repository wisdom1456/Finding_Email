/**
 * Vitest setup file for SvelteKit frontend tests
 */
import '@testing-library/jest-dom';
import { vi, beforeEach } from 'vitest';

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
	writable: true,
	value: vi.fn().mockImplementation((query) => ({
		matches: false,
		media: query,
		onchange: null,
		addListener: vi.fn(),
		removeListener: vi.fn(),
		addEventListener: vi.fn(),
		removeEventListener: vi.fn(),
		dispatchEvent: vi.fn(),
	})),
});

// Mock IntersectionObserver
global.IntersectionObserver = class IntersectionObserver {
	constructor() {}
	disconnect() {}
	observe() {}
	takeRecords() {
		return [];
	}
	unobserve() {}
} as any;

// Mock Element.animate for Svelte transitions (Web Animations API)
Element.prototype.animate = vi.fn().mockImplementation(() => ({
	onfinish: null,
	cancel: vi.fn(),
	finish: vi.fn(),
	play: vi.fn(),
	pause: vi.fn(),
	reverse: vi.fn(),
	addEventListener: vi.fn(),
	removeEventListener: vi.fn(),
	finished: Promise.resolve(),
}));

// Mock fetch if needed
global.fetch = vi.fn();

// Reset mocks before each test
beforeEach(() => {
	vi.clearAllMocks();
});



