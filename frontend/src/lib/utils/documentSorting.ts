/**
 * Computes how much attorney attention a document needs.
 * Higher score = needs more attention (surfaced first in triage).
 */
export function computeAttentionScore(doc: any): number {
    let score = 0;
    const meta = doc.metadata || {};
    const sig = meta.signature_detection || {};
    const enrichment = meta.attorney_enrichment || {};

    // Missing expected signature: +50
    const sigExpected = sig.signature_expected === true;
    const sigSatisfied =
        sig.status === 'signed' ||
        enrichment.signature_verification === 'signed';
    if (sigExpected && !sigSatisfied) {
        score += 50;
    }

    // Low OCR quality: +40
    const qualityScore =
        meta.quality_score ??
        meta.extraction_quality_score ??
        10;
    if (qualityScore < 5) {
        score += 40;
    }

    // No document type detected: +30
    const hasType = !!(meta.document_type || enrichment.document_type_override);
    if (!hasType) {
        score += 30;
    }

    // No key facts extracted: +20
    const hasFacts =
        enrichment.key_facts && Object.keys(enrichment.key_facts).length > 0;
    if (!hasFacts) {
        score += 20;
    }

    // No attorney notes: +10
    if (!enrichment.attorney_notes) {
        score += 10;
    }

    return score;
}

/**
 * Returns a list of human-readable attention needs for a document.
 */
export function getAttentionNeeds(doc: any): string[] {
    const needs: string[] = [];
    const meta = doc.metadata || {};
    const sig = meta.signature_detection || {};
    const enrichment = meta.attorney_enrichment || {};

    const sigExpected = sig.signature_expected === true;
    const sigSatisfied =
        sig.status === 'signed' ||
        enrichment.signature_verification === 'signed';
    if (sigExpected && !sigSatisfied) needs.push('signature');

    const qualityScore = meta.quality_score ?? meta.extraction_quality_score ?? 10;
    if (qualityScore < 5) needs.push('ocr quality');

    const hasType = !!(meta.document_type || enrichment.document_type_override);
    if (!hasType) needs.push('type');

    const hasFacts =
        enrichment.key_facts && Object.keys(enrichment.key_facts).length > 0;
    if (!hasFacts) needs.push('key facts');

    if (!enrichment.attorney_notes) needs.push('notes');

    return needs;
}

/**
 * Sorts documents by attention score (highest first). Does not mutate input.
 */
export function sortByAttention(docs: any[]): any[] {
    return [...docs].sort(
        (a, b) => computeAttentionScore(b) - computeAttentionScore(a)
    );
}
