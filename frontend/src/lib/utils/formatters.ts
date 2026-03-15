/**
 * Shared formatting utility functions.
 *
 * Pure helpers for dates, file sizes, and status colors.
 * Extracted from cases/[id]/+page.svelte and results/+page.svelte.
 */

export function formatDate(dateString: string): string {
	return new Date(dateString).toLocaleDateString('en-US', {
		year: 'numeric',
		month: 'short',
		day: 'numeric',
		hour: '2-digit',
		minute: '2-digit'
	});
}

export function formatFileSize(bytes: number): string {
	if (bytes < 1024) return bytes + ' B';
	if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
	return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

export function getStatusColor(status: string): string {
	switch (status) {
		case 'completed':
			return 'bg-accent/10 text-accent';
		case 'processing':
			return 'bg-contrast-light/10 text-contrast-light';
		case 'error':
			return 'bg-red-100 text-red-700';
		default:
			return 'bg-gray-100 text-gray-700';
	}
}
