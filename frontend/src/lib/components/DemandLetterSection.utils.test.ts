import { describe, it, expect } from 'vitest';
import { buildDemandStreamParams } from './DemandLetterSection.utils';

describe('buildDemandStreamParams', () => {
	it('builds base params with schema_version 2 and strict_quality mode', () => {
		const params = buildDemandStreamParams({
			targetPartyName: 'Acme Corp',
			demandDeadline: '10 business days',
			demandAmount: null,
			specificDemands: '',
		});
		expect(params).toEqual({
			target_party_name: 'Acme Corp',
			demand_deadline: '10 business days',
			schema_version: '2',
			mode: 'strict_quality',
		});
	});

	it('includes demand_amount when provided', () => {
		const params = buildDemandStreamParams({
			targetPartyName: 'Acme Corp',
			demandDeadline: '14 days',
			demandAmount: 5000,
			specificDemands: '',
		});
		expect(params.demand_amount).toBe('5000');
	});

	it('omits demand_amount when null', () => {
		const params = buildDemandStreamParams({
			targetPartyName: 'Acme Corp',
			demandDeadline: '14 days',
			demandAmount: null,
			specificDemands: '',
		});
		expect(params.demand_amount).toBeUndefined();
	});

	it('joins non-empty specific demand lines with a pipe, trimming and dropping blanks', () => {
		const params = buildDemandStreamParams({
			targetPartyName: 'Acme Corp',
			demandDeadline: '14 days',
			demandAmount: null,
			specificDemands: 'Return deposit\n\n  Repair roof  \n',
		});
		expect(params.specific_demands).toBe('Return deposit|Repair roof');
	});

	it('omits specific_demands when there are no non-empty lines', () => {
		const params = buildDemandStreamParams({
			targetPartyName: 'Acme Corp',
			demandDeadline: '14 days',
			demandAmount: null,
			specificDemands: '   \n  \n',
		});
		expect(params.specific_demands).toBeUndefined();
	});

	it('includes attorney identity fields under the sync-route param names when provided', () => {
		const params = buildDemandStreamParams({
			targetPartyName: 'Acme Corp',
			demandDeadline: '14 days',
			demandAmount: null,
			specificDemands: '',
			attorneyName: 'Jane Doe',
			firmName: 'Doe & Associates',
			contactPhone: '555-1234',
			contactEmail: 'jane@doe.com',
		});
		expect(params.attorney_name).toBe('Jane Doe');
		expect(params.firm_name).toBe('Doe & Associates');
		expect(params.contact_phone).toBe('555-1234');
		expect(params.contact_email).toBe('jane@doe.com');
	});

	it('omits attorney identity fields that are empty or missing (matching sync fallback `|| undefined`)', () => {
		const params = buildDemandStreamParams({
			targetPartyName: 'Acme Corp',
			demandDeadline: '14 days',
			demandAmount: null,
			specificDemands: '',
			attorneyName: 'Jane Doe',
			firmName: '',
		});
		expect(params.attorney_name).toBe('Jane Doe');
		expect(params).not.toHaveProperty('firm_name');
		expect(params).not.toHaveProperty('contact_phone');
		expect(params).not.toHaveProperty('contact_email');
	});
});
