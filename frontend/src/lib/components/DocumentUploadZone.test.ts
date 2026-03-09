import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import DocumentUploadZone from './DocumentUploadZone.svelte';

function makeFile(name: string, sizeMB: number, type = 'application/pdf'): File {
	const bytes = sizeMB * 1024 * 1024;
	const buffer = new ArrayBuffer(bytes);
	return new File([buffer], name, { type });
}

describe('DocumentUploadZone', () => {
	// ── Rendering ──

	it('renders upload button and instructions', () => {
		render(DocumentUploadZone, { props: { onFilesSelected: vi.fn() } });
		expect(screen.getByText(/Choose Files to Upload/i)).toBeTruthy();
		expect(screen.getByText(/drag and drop/i)).toBeTruthy();
	});

	it('shows supported formats text with default max size', () => {
		render(DocumentUploadZone, { props: { onFilesSelected: vi.fn() } });
		expect(screen.getByText(/up to 50MB/i)).toBeTruthy();
	});

	it('shows custom max size in supported formats text', () => {
		render(DocumentUploadZone, { props: { onFilesSelected: vi.fn(), maxFileSizeMB: 25 } });
		expect(screen.getByText(/up to 25MB/i)).toBeTruthy();
	});

	it('renders with role="button" and is keyboard accessible', () => {
		render(DocumentUploadZone, { props: { onFilesSelected: vi.fn() } });
		const dropZone = screen.getByRole('button');
		expect(dropZone).toBeTruthy();
		expect(dropZone.getAttribute('tabindex')).toBe('0');
	});

	// ── File selection via input ──

	it('calls onFilesSelected with valid files from input', async () => {
		const onFilesSelected = vi.fn();
		render(DocumentUploadZone, { props: { onFilesSelected } });

		const input = document.querySelector('input[type="file"]') as HTMLInputElement;
		expect(input).toBeTruthy();

		const file = makeFile('test.pdf', 1);
		Object.defineProperty(input, 'files', { value: [file], writable: false });
		await fireEvent.change(input);

		expect(onFilesSelected).toHaveBeenCalledTimes(1);
		expect(onFilesSelected).toHaveBeenCalledWith([file]);
	});

	// ── File size validation ──

	it('rejects files exceeding maxFileSizeMB', async () => {
		const onFilesSelected = vi.fn();
		const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
		render(DocumentUploadZone, { props: { onFilesSelected, maxFileSizeMB: 10 } });

		const input = document.querySelector('input[type="file"]') as HTMLInputElement;
		const oversized = makeFile('huge.pdf', 15);

		Object.defineProperty(input, 'files', { value: [oversized], writable: false });
		await fireEvent.change(input);

		// Should NOT call onFilesSelected (no valid files)
		expect(onFilesSelected).not.toHaveBeenCalled();
		expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('exceeds'));
		warnSpy.mockRestore();
	});

	it('passes only valid files when mix of valid and oversized', async () => {
		const onFilesSelected = vi.fn();
		vi.spyOn(console, 'warn').mockImplementation(() => {});
		render(DocumentUploadZone, { props: { onFilesSelected, maxFileSizeMB: 10 } });

		const input = document.querySelector('input[type="file"]') as HTMLInputElement;
		const valid = makeFile('small.pdf', 5);
		const oversized = makeFile('huge.pdf', 15);

		Object.defineProperty(input, 'files', { value: [valid, oversized], writable: false });
		await fireEvent.change(input);

		// Should only pass the valid file
		expect(onFilesSelected).toHaveBeenCalledTimes(1);
		expect(onFilesSelected).toHaveBeenCalledWith([valid]);
		vi.restoreAllMocks();
	});

	it('file exactly at limit is accepted', async () => {
		const onFilesSelected = vi.fn();
		render(DocumentUploadZone, { props: { onFilesSelected, maxFileSizeMB: 10 } });

		const input = document.querySelector('input[type="file"]') as HTMLInputElement;
		// Exactly 10MB — should pass (10 > 10 is false)
		const exactLimit = makeFile('exact.pdf', 10);

		Object.defineProperty(input, 'files', { value: [exactLimit], writable: false });
		await fireEvent.change(input);

		expect(onFilesSelected).toHaveBeenCalledWith([exactLimit]);
	});

	// ── Drag and drop ──

	it('calls onFilesSelected on drop with valid files', async () => {
		const onFilesSelected = vi.fn();
		render(DocumentUploadZone, { props: { onFilesSelected } });

		const dropZone = screen.getByRole('button');
		const file = makeFile('dropped.pdf', 2);

		await fireEvent.drop(dropZone, {
			dataTransfer: { files: [file] },
		});

		expect(onFilesSelected).toHaveBeenCalledWith([file]);
	});

	it('ignores drop when disabled', async () => {
		const onFilesSelected = vi.fn();
		render(DocumentUploadZone, { props: { onFilesSelected, disabled: true } });

		const dropZone = screen.getByRole('button');
		const file = makeFile('dropped.pdf', 2);

		await fireEvent.drop(dropZone, {
			dataTransfer: { files: [file] },
		});

		expect(onFilesSelected).not.toHaveBeenCalled();
	});

	// ── Disabled state ──

	it('file input has disabled attribute when disabled', () => {
		render(DocumentUploadZone, { props: { onFilesSelected: vi.fn(), disabled: true } });
		const input = document.querySelector('input[type="file"]') as HTMLInputElement;
		expect(input.disabled).toBe(true);
	});

	it('file input allows multiple files', () => {
		render(DocumentUploadZone, { props: { onFilesSelected: vi.fn() } });
		const input = document.querySelector('input[type="file"]') as HTMLInputElement;
		expect(input.multiple).toBe(true);
	});

	// ── Accept attribute ──

	it('applies default accept attribute to input', () => {
		render(DocumentUploadZone, { props: { onFilesSelected: vi.fn() } });
		const input = document.querySelector('input[type="file"]') as HTMLInputElement;
		expect(input.accept).toContain('.pdf');
		expect(input.accept).toContain('.docx');
	});

	it('applies custom accept attribute', () => {
		render(DocumentUploadZone, { props: { onFilesSelected: vi.fn(), accept: '.pdf,.txt' } });
		const input = document.querySelector('input[type="file"]') as HTMLInputElement;
		expect(input.accept).toBe('.pdf,.txt');
	});
});
