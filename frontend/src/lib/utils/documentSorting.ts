/**
 * Computes how much attorney attention a document needs.
 * Higher score = needs more attention (surfaced first in triage).
 *
 * Reads from registry-backed columns and metadata.registry instead of
 * phantom metadata fields. Removes penalty for missing attorney notes
 * (notes are optional enrichment, not required).
 */
export function computeAttentionScore(doc: any): number {
    let score = 0;
    const meta = doc.metadata || {};
    const registry = meta.registry || {};
    const enrichment = meta.attorney_enrichment || {};

    // Missing expected signature: +50
    // Use denormalized column (signature_expected) + signed_status column
    const sigExpected = doc.signature_expected === true || registry.signature_expected === true;
    const sigSatisfied =
        doc.signed_status === 'signed' ||
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
    // Use denormalized document_type_label column instead of phantom metadata.document_type
    const hasType = !!(doc.document_type_label || enrichment.document_type_override);
    if (!hasType) {
        score += 30;
    }

    // No key facts extracted: +20
    // Fact source resolution: attorney > ai > raw
    const hasAttorneyFacts =
        enrichment.key_facts && Object.keys(enrichment.key_facts).length > 0;
    const hasAiFacts =
        registry.quick_facts_ai &&
        (registry.quick_facts_ai.dates?.length > 0 ||
         registry.quick_facts_ai.amounts?.length > 0 ||
         registry.quick_facts_ai.parties?.length > 0);
    const hasRawFacts =
        registry.quick_facts_raw &&
        (registry.quick_facts_raw.dates?.length > 0 ||
         registry.quick_facts_raw.amounts?.length > 0);
    if (!hasAttorneyFacts && !hasAiFacts && !hasRawFacts) {
        score += 20;
    }

    // REMOVED: No attorney notes penalty (+10 was here)
    // Notes are optional enrichment, not required for triage.

    return score;
}

/**
 * Returns a list of human-readable attention needs for a document.
 *
 * Fact source resolution order:
 *   1. attorney_enrichment.key_facts  (confirmed by attorney)
 *   2. registry.quick_facts_ai        (AI-extracted)
 *   3. registry.quick_facts_raw       (regex-extracted at upload)
 */
export function getAttentionNeeds(doc: any): string[] {
    const needs: string[] = [];
    const meta = doc.metadata || {};
    const registry = meta.registry || {};
    const enrichment = meta.attorney_enrichment || {};

    const sigExpected = doc.signature_expected === true || registry.signature_expected === true;
    const sigSatisfied =
        doc.signed_status === 'signed' ||
        enrichment.signature_verification === 'signed';
    if (sigExpected && !sigSatisfied) needs.push('signature');

    const qualityScore = meta.quality_score ?? meta.extraction_quality_score ?? 10;
    if (qualityScore < 5) needs.push('ocr quality');

    const hasType = !!(doc.document_type_label || enrichment.document_type_override);
    if (!hasType) needs.push('type');

    const hasAttorneyFacts =
        enrichment.key_facts && Object.keys(enrichment.key_facts).length > 0;
    const hasAiFacts =
        registry.quick_facts_ai &&
        (registry.quick_facts_ai.dates?.length > 0 ||
         registry.quick_facts_ai.amounts?.length > 0 ||
         registry.quick_facts_ai.parties?.length > 0);
    const hasRawFacts =
        registry.quick_facts_raw &&
        (registry.quick_facts_raw.dates?.length > 0 ||
         registry.quick_facts_raw.amounts?.length > 0);
    if (!hasAttorneyFacts && !hasAiFacts && !hasRawFacts) needs.push('key facts');

    // REMOVED: notes check — notes are optional

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
