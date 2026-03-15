/**
 * Signature detection utility functions.
 *
 * Pure helpers for determining signature status, labels, and badge styling
 * from document metadata. Extracted from cases/[id]/+page.svelte.
 */

export type SignatureStatus = 'signed' | 'not_detected' | 'review_required' | 'other' | 'none';

const signatureRequiredKeywords = [
	'agreement',
	'contract',
	'lease',
	'addendum',
	'amendment',
	'settlement',
	'release',
	'authorization',
	'consent',
	'affidavit',
	'declaration',
	'stipulation',
	'promissory note',
	'guaranty',
	'power of attorney',
	'poa',
	'signature page',
	'executed'
];

const _NO_SIG_EXTENSIONS = new Set([
	'.eml', '.txt', '.csv', '.doc', '.jpg', '.jpeg', '.png', '.heic', '.gif', '.bmp', '.tiff', '.tif',
]);
const _NO_SIG_TYPES = new Set([
	'correspondence', 'email', 'photo/media', 'note', 'communication',
]);

export function requiresSignatureReview(doc: any): boolean {
	const fileName = String(doc?.file_name || '').toLowerCase();
	const ext = fileName.includes('.') ? '.' + fileName.split('.').pop() : '';
	if (_NO_SIG_EXTENSIONS.has(ext)) return false;
	if (fileName.startsWith('clio note') || fileName.startsWith('clio communication')) return false;
	const docType = (doc?.document_type_label || doc?.metadata?.registry?.document_type || '').toLowerCase();
	if (_NO_SIG_TYPES.has(docType)) return false;
	return signatureRequiredKeywords.some((keyword) => fileName.includes(keyword));
}

export function getDocumentSignatureDetection(doc: any): any | null {
	const sig = doc?.metadata?.signature_detection;
	return sig && typeof sig === 'object' ? sig : null;
}

export function getDocumentSignatureVerificationStatus(doc: any): 'signed' | 'not_signed' | 'unknown' | 'none' {
	const verification = doc?.metadata?.signature_verification;
	if (!verification || typeof verification !== 'object') return 'none';
	const status = String(verification.status || '').toLowerCase().trim();
	if (status === 'signed') return 'signed';
	if (status === 'not_signed' || status === 'unsigned' || status === 'not_detected' || status === 'not signed') {
		return 'not_signed';
	}
	if (status === 'unknown' || status === 'unclear') return 'unknown';
	return 'none';
}

export function getDocumentSignatureStatus(doc: any): SignatureStatus {
	const verifiedStatus = getDocumentSignatureVerificationStatus(doc);
	if (verifiedStatus === 'signed') return 'signed';
	if (verifiedStatus === 'not_signed') return 'not_detected';
	if (verifiedStatus === 'unknown') return 'review_required';

	const signatureDetection = getDocumentSignatureDetection(doc);
	if (!signatureDetection) return requiresSignatureReview(doc) ? 'review_required' : 'none';
	const status = String(signatureDetection.status || '').toLowerCase();
	if (status === 'signed') return 'signed';
	if (status === 'not_detected') return 'not_detected';
	return 'other';
}

export function getDocumentSignatureLabel(doc: any): string {
	const verifiedStatus = getDocumentSignatureVerificationStatus(doc);
	if (verifiedStatus === 'signed') return 'SIGNED (ATTORNEY VERIFIED)';
	if (verifiedStatus === 'not_signed') return 'NOT SIGNED (ATTORNEY VERIFIED)';
	if (verifiedStatus === 'unknown') return 'SIGNATURE REVIEWED (UNCLEAR)';

	const signatureDetection = getDocumentSignatureDetection(doc);
	if (!signatureDetection) {
		if (requiresSignatureReview(doc)) return 'SIGNATURE REVIEW RECOMMENDED';
		return '';
	}
	const status = getDocumentSignatureStatus(doc);
	const confidence = signatureDetection?.confidence
		? ` (${String(signatureDetection.confidence).toUpperCase()})`
		: '';
	if (status === 'signed') return `SIGNED${confidence}`;
	if (status === 'not_detected') return `NO SIGNATURE DETECTED${confidence}`;
	if (status === 'review_required') return 'SIGNATURE REVIEW RECOMMENDED';
	return `SIGNATURE: ${String(signatureDetection.status || 'UNKNOWN').toUpperCase()}${confidence}`;
}

export function getDocumentSignatureBadgeClass(doc: any): string {
	const status = getDocumentSignatureStatus(doc);
	if (status === 'signed') {
		return 'bg-emerald-100 text-emerald-800 border-emerald-300';
	}
	if (status === 'not_detected') {
		return 'bg-amber-100 text-amber-800 border-amber-300';
	}
	if (status === 'review_required') {
		return 'bg-yellow-100 text-yellow-900 border-yellow-300';
	}
	return 'bg-gray-100 text-gray-700 border-gray-300';
}

export function shouldShowSignatureBadge(doc: any): boolean {
	return getDocumentSignatureStatus(doc) !== 'none';
}
