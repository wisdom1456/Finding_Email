import { describe, it, expect } from 'vitest';
import { controlsFor } from './caseControls';

describe('controlsFor — G1: no Start while active', () => {
  it('running shows only cancel — NO start', () => {
    const c = controlsFor('running');
    expect(c.start).toBe(false);
    expect(c.startOver).toBe(false);
    expect(c.cancel).toBe(true);
  });
  it('queued shows only cancel — NO start', () => {
    const c = controlsFor('queued');
    expect(c.start).toBe(false);
    expect(c.cancel).toBe(true);
  });
  it('stalled offers start over (not resume — phase 2)', () => {
    const c = controlsFor('stalled');
    expect(c.startOver).toBe(true);
    expect(c.start).toBe(false);
  });
  it('idle / cancelled offer start', () => {
    expect(controlsFor('idle').start).toBe(true);
    expect(controlsFor('cancelled').start).toBe(true);
  });
  it('completed offers view + rerun', () => {
    const c = controlsFor('completed');
    expect(c.viewResults).toBe(true);
    expect(c.rerun).toBe(true);
    expect(c.start).toBe(false);
  });
});
