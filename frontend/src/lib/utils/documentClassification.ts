/**
 * Document classification utility functions.
 *
 * Pure helpers for classifying documents by type, extension, and MIME type.
 * Extracted from cases/[id]/+page.svelte.
 */

export function isCaseSummary(doc: any): boolean {
	return doc.file_name.toLowerCase().includes('case summary') ||
	       doc.file_name.toLowerCase().includes('case_summary') ||
	       doc.file_name.toLowerCase().includes('casesummary');
}

export function isIntakeForm(doc: any): boolean {
	return doc.file_name.toLowerCase().includes('intake');
}

export function isPrimaryIntakeCandidate(doc: any): boolean {
	return isCaseSummary(doc) || isIntakeForm(doc);
}

export function isPdfLikeDocument(doc: any): boolean {
	if (!doc) return false;
	const fileType = String(doc.file_type || '').toLowerCase();
	const fileName = String(doc.file_name || '').toLowerCase();
	return fileType === 'application/pdf' || fileName.endsWith('.pdf');
}

export function isImageLikeDocument(doc: any): boolean {
	if (!doc) return false;
	return String(doc.file_type || '').toLowerCase().startsWith('image/');
}

export function isTextLikeDocument(doc: any): boolean {
	if (!doc) return false;
	const fileType = String(doc.file_type || '').toLowerCase();
	const fileName = String(doc.file_name || '').toLowerCase();
	return (
		fileType.startsWith('text/') ||
		fileName.endsWith('.txt') ||
		fileName.endsWith('.md') ||
		fileName.endsWith('.csv') ||
		fileName.endsWith('.log')
	);
}

export function isVideoAudioFile(fileName: string): boolean {
	const videoAudioExtensions = [
		'.mov', '.mp4', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v',  // Video
		'.mp3', '.wav', '.aac', '.flac', '.m4a', '.ogg', '.wma', '.aiff',  // Audio
	];
	return videoAudioExtensions.some(ext => fileName.toLowerCase().endsWith(ext));
}
