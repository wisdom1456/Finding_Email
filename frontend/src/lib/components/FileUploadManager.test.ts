import { render, screen } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import FileUploadManager from './FileUploadManager.svelte';

vi.mock('$lib/config', () => ({
	getApiUrl: () => 'http://localhost:8000',
}));

vi.mock('$lib/supabase', () => ({
	getSecureSession: vi.fn().mockResolvedValue({ session: null, user: null }),
}));

vi.mock('$lib/stores/toastStore', () => ({
	toastStore: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

vi.mock('$lib/utils/formatters', () => ({
	formatFileSize: (size: number) => `${Math.round(size / 1024)} KB`,
}));

function baseProps(overrides: Record<string, any> = {}) {
	return {
		caseId: 'case-1',
		documents: [],
		onuploaded: vi.fn(),
		onerror: vi.fn(),
		...overrides,
	};
}

describe('FileUploadManager', () => {
	it('renders upload zone', () => {
		render(FileUploadManager, { props: baseProps() });
		const zone = document.querySelector('[data-testid="upload-zone"]');
		expect(zone).toBeTruthy();
	});

	it('shows file input', () => {
		render(FileUploadManager, { props: baseProps() });
		const input = document.querySelector('input[type="file"]');
		expect(input).toBeTruthy();
	});

	it('shows click to upload text', () => {
		render(FileUploadManager, { props: baseProps() });
		expect(screen.getByText('Click to upload')).toBeTruthy();
	});

	it('shows drag and drop text', () => {
		render(FileUploadManager, { props: baseProps() });
		expect(screen.getByText(/or drag and drop/)).toBeTruthy();
	});

	it('shows allowed file types', () => {
		render(FileUploadManager, { props: baseProps() });
		expect(screen.getByText(/PDF, DOCX, DOC, TXT/)).toBeTruthy();
	});

	it('accepts multiple files', () => {
		render(FileUploadManager, { props: baseProps() });
		const input = document.querySelector('input[type="file"]') as HTMLInputElement;
		expect(input.multiple).toBe(true);
	});
});
