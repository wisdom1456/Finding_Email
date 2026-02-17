import { describe, expect, it } from 'vitest';

import { SSEEventParser } from './sseEventParser';

describe('SSEEventParser', () => {
	it('reconstructs events split across chunks', () => {
		const parser = new SSEEventParser();

		const first = parser.push('data: {"event":"token","token":"Hel');
		const second = parser.push('lo"}\n\ndata: {"done":true}\n\n');

		expect(first).toEqual([]);
		expect(second).toHaveLength(2);
		expect(second[0]).toMatchObject({ event: 'token', token: 'Hello' });
		expect(second[1]).toMatchObject({ done: true });
	});

	it('supports multiple data lines and ignores comment lines', () => {
		const parser = new SSEEventParser();
		const events = parser.push(
			': keepalive\n' +
				'data: {"event":"phase","phase":"context_build",\n' +
				'data: "message":"Building context"}\n\n'
		);

		expect(events).toHaveLength(1);
		expect(events[0]).toMatchObject({
			event: 'phase',
			phase: 'context_build',
			message: 'Building context'
		});
	});

	it('retains incomplete trailing payload until delimiter arrives', () => {
		const parser = new SSEEventParser();
		const first = parser.push('data: {"event":"token","token":"A"}\n\ndata: {"event":"token"');
		const second = parser.push(',"token":"B"}\n\n');

		expect(first).toHaveLength(1);
		expect(first[0]).toMatchObject({ token: 'A' });
		expect(second).toHaveLength(1);
		expect(second[0]).toMatchObject({ token: 'B' });
	});
});
