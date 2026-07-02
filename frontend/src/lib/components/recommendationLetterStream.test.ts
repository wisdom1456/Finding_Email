import { describe, it, expect } from 'vitest';
import {
	initialRecommendationStreamState,
	reduceRecommendationStreamEvent,
	type RecommendationStreamState
} from '../utils/recommendationLetterStream';

describe('reduceRecommendationStreamEvent', () => {
	it('updates phaseLabel and percent on a phase event', () => {
		const state = reduceRecommendationStreamEvent(initialRecommendationStreamState(), {
			event: 'phase',
			phase: 'context_build',
			message: 'Building context',
			percent: 8
		});
		expect(state.phaseLabel).toBe('Building context');
		expect(state.percent).toBe(8);
	});

	it('leaves percent unchanged when a phase event omits it', () => {
		let state = reduceRecommendationStreamEvent(initialRecommendationStreamState(), {
			event: 'phase',
			phase: 'context_build',
			message: 'Building context',
			percent: 8
		});
		state = reduceRecommendationStreamEvent(state, {
			event: 'phase',
			phase: 'draft_generation',
			message: 'Generating draft'
		});
		expect(state.phaseLabel).toBe('Generating draft');
		expect(state.percent).toBe(8);
	});

	it('accumulates token events into markdownBuffer', () => {
		let state = initialRecommendationStreamState();
		state = reduceRecommendationStreamEvent(state, { event: 'token', token: 'Hello ' });
		state = reduceRecommendationStreamEvent(state, { event: 'token', token: 'world' });
		expect(state.markdownBuffer).toBe('Hello world');
	});

	it('ignores token events with a non-string token', () => {
		let state = initialRecommendationStreamState();
		state = reduceRecommendationStreamEvent(state, { event: 'token', token: 'abc' });
		state = reduceRecommendationStreamEvent(state, { event: 'token' });
		expect(state.markdownBuffer).toBe('abc');
	});

	it('sets content and done on a final event, discarding the buffer', () => {
		let state = initialRecommendationStreamState();
		state = reduceRecommendationStreamEvent(state, { event: 'token', token: 'draft text' });
		state = reduceRecommendationStreamEvent(state, {
			event: 'final',
			content: { format: 'html', html: '<p>Final</p>', markdown: 'Final' }
		});
		expect(state.done).toBe(true);
		expect(state.content).toEqual({ format: 'html', html: '<p>Final</p>', markdown: 'Final' });
		expect(state.recovered).toBe(false);
		expect(state.error).toBeNull();
	});

	it('final wins over an accumulated buffer even if final arrives with a different buffer state', () => {
		let state = initialRecommendationStreamState();
		state = reduceRecommendationStreamEvent(state, { event: 'token', token: 'partial' });
		state = reduceRecommendationStreamEvent(state, {
			event: 'final',
			content: { format: 'markdown', markdown: 'complete letter' }
		});
		expect(state.content).toEqual({ format: 'markdown', markdown: 'complete letter' });
		expect(state.markdownBuffer).toBe('partial');
	});

	it('salvages the buffer on error after tokens have accumulated, marking recovered', () => {
		let state = initialRecommendationStreamState();
		state = reduceRecommendationStreamEvent(state, { event: 'token', token: 'Some draft ' });
		state = reduceRecommendationStreamEvent(state, { event: 'token', token: 'content' });
		state = reduceRecommendationStreamEvent(state, {
			event: 'error',
			error: 'Model timed out',
			code: 'timeout'
		});
		expect(state.recovered).toBe(true);
		expect(state.done).toBe(true);
		expect(state.error).toBeNull();
		expect(state.content).toEqual({ format: 'markdown', markdown: 'Some draft content' });
	});

	it('sets error state when the buffer is empty on an error event', () => {
		let state = initialRecommendationStreamState();
		state = reduceRecommendationStreamEvent(state, {
			event: 'error',
			error: 'Recommendation letter generation failed'
		});
		expect(state.recovered).toBe(false);
		expect(state.done).toBe(true);
		expect(state.error).toBe('Recommendation letter generation failed');
		expect(state.content).toBeNull();
	});

	it('ignores a recoverable error event and keeps streaming (backend still finishes to `final`)', () => {
		let state = initialRecommendationStreamState();
		state = reduceRecommendationStreamEvent(state, { event: 'token', token: 'partial draft' });
		const beforeError = state;
		state = reduceRecommendationStreamEvent(state, {
			event: 'error',
			error: 'Draft generation exceeded time budget; finalizing best available content.',
			code: 'draft_budget_exceeded',
			recoverable: true
		});
		expect(state).toEqual(beforeError);
		expect(state.done).toBe(false);
		expect(state.error).toBeNull();
		expect(state.recovered).toBe(false);

		// Stream continues past the recoverable error to a real final event.
		state = reduceRecommendationStreamEvent(state, {
			event: 'final',
			content: { format: 'html', html: '<p>Finalized letter</p>' }
		});
		expect(state.done).toBe(true);
		expect(state.recovered).toBe(false);
		expect(state.content).toEqual({ format: 'html', html: '<p>Finalized letter</p>' });
	});

	it('treats a whitespace-only buffer as empty for salvage purposes', () => {
		let state = initialRecommendationStreamState();
		state = reduceRecommendationStreamEvent(state, { event: 'token', token: '   \n  ' });
		state = reduceRecommendationStreamEvent(state, { event: 'error', error: 'boom' });
		expect(state.recovered).toBe(false);
		expect(state.error).toBe('boom');
	});

	it('marks done on a done event without altering content/error', () => {
		let state = initialRecommendationStreamState();
		state = reduceRecommendationStreamEvent(state, { event: 'done' });
		expect(state.done).toBe(true);
		expect(state.content).toBeNull();
		expect(state.error).toBeNull();
	});

	it('is a pure function: does not mutate the input state', () => {
		const state = initialRecommendationStreamState();
		const next = reduceRecommendationStreamEvent(state, { event: 'token', token: 'x' });
		expect(state.markdownBuffer).toBe('');
		expect(next).not.toBe(state);
	});

	it('returns a fully-typed RecommendationStreamState', () => {
		const state: RecommendationStreamState = initialRecommendationStreamState();
		expect(state).toEqual({
			phaseLabel: '',
			percent: null,
			markdownBuffer: '',
			content: null,
			done: false,
			error: null,
			recovered: false
		});
	});
});
