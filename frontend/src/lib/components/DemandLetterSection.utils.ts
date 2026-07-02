/**
 * Extracted pure functions from DemandLetterSection for testability.
 */

export interface DemandStreamParamsInput {
	targetPartyName: string;
	demandDeadline: string;
	demandAmount: number | null;
	specificDemands: string;
	attorneyName?: string;
	firmName?: string;
	contactPhone?: string;
	contactEmail?: string;
}

/**
 * Build the query params sent to GET /api/analysis/{analysisId}/demand-letter/stream.
 *
 * Attorney identity fields use the same param names as the sync fallback
 * (POST /generate-letter, `LetterGenerationRequest`): attorney_name, firm_name,
 * contact_phone, contact_email. The streaming route
 * (src/legal_portal/api/routes/letter_routes.py::stream_demand_letter) accepts them
 * as optional query params and forwards them as identity overrides via
 * `_resolve_letter_identity_context(..., overrides=...)` — explicit values win over
 * profile/case-derived identity. Empty/missing values are omitted (matching the sync
 * fallback's `attorneyName || undefined` behavior) so the backend falls back to the
 * stored profile exactly as before.
 */
export function buildDemandStreamParams(input: DemandStreamParamsInput): Record<string, string> {
	const demandLines = input.specificDemands
		.split('\n')
		.map((line) => line.trim())
		.filter(Boolean);

	const params: Record<string, string> = {
		target_party_name: input.targetPartyName,
		demand_deadline: input.demandDeadline,
		schema_version: '2',
		mode: 'strict_quality',
	};

	if (input.demandAmount != null) {
		params.demand_amount = String(input.demandAmount);
	}
	if (demandLines.length > 0) {
		params.specific_demands = demandLines.join('|');
	}

	if (input.attorneyName) params.attorney_name = input.attorneyName;
	if (input.firmName) params.firm_name = input.firmName;
	if (input.contactPhone) params.contact_phone = input.contactPhone;
	if (input.contactEmail) params.contact_email = input.contactEmail;

	return params;
}
