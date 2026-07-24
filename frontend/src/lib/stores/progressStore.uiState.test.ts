import { describe, it, expect } from 'vitest';
import { mapJobStatusToUi } from './progressStore';

describe('mapJobStatusToUi', () => {
  it('carries the trustworthy-wait fields from the job payload', () => {
    const out = mapJobStatusToUi({
      ui_state: 'running', step_index: 5, step_total: 6, step_label: 'Running deep analysis',
      items_done: 40, items_total: 71, eta_seconds: 380, healthy: true, cancel_reason: null,
    });
    expect(out.uiState).toBe('running');
    expect(out.stepIndex).toBe(5);
    expect(out.stepLabel).toBe('Running deep analysis');
    expect(out.itemsDone).toBe(40);
    expect(out.etaSeconds).toBe(380);
    expect(out.healthy).toBe(true);
  });

  it('tolerates a legacy payload without the new fields', () => {
    const out = mapJobStatusToUi({ status: 'running', stage: 'deep_analysis', percent: 86 });
    expect(out.uiState).toBeUndefined();
    expect(out.stepTotal).toBe(6); // sensible default
  });
});
