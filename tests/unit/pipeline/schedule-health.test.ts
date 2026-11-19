// Schedule health (DATA_CONVENTIONS v0.1 section 14.3, owner decision D7): findings from facts
// outside the collector, at and around every PROPOSED threshold.
import { describe, expect, it } from 'vitest';
import { DEFAULT_THRESHOLDS, scheduleHealth } from '../../../pipeline/lib/schedule-health.mjs';

const NOW = '2026-11-16T15:00:00Z';
const hoursAgo = (h: number) => new Date(Date.parse(NOW) - h * 3_600_000).toISOString().replace('.000Z', 'Z');
const daysAgo = (d: number) => hoursAgo(24 * d);

function healthy() {
  return {
    now: NOW,
    workflow: { state: 'active' },
    repository: { pushed_at: daysAgo(3) },
    runs: [
      { event: 'schedule', conclusion: 'success', created_at: hoursAgo(1) },
      { event: 'schedule', conclusion: 'success', created_at: hoursAgo(2) },
    ],
    manifest: { health: { expected_next_update_by: hoursAgo(-5) }, series: { effr: { status: 'fresh', status_reason: null } } },
  };
}
const keys = (input: ReturnType<typeof healthy>) => scheduleHealth(input).map((f: { key: string; severity: string }) => `${f.severity} ${f.key}`);

describe('schedule health', () => {
  it('finds nothing when the workflow is active, recent, succeeding and the manifest is on time', () => {
    expect(scheduleHealth(healthy())).toEqual([]);
    expect(DEFAULT_THRESHOLDS).toEqual({ inactivityWarningDays: 45, inactivityCriticalDays: 55, runGapWarningHours: 9, runGapCriticalHours: 26, consecutiveFailures: 3, overdueCriticalHours: 24 });
  });

  it('reports a disabled workflow at once, whatever the reason', () => {
    for (const state of ['disabled_inactivity', 'disabled_manually', 'disabled_fork']) {
      const i = healthy();
      i.workflow.state = state;
      expect(scheduleHealth(i)[0]).toEqual({ key: 'workflow-disabled', severity: 'critical', message: `The collector workflow is ${state}, not active.` });
    }
  });

  it('warns about inactivity from day 45 and escalates at day 55, before GitHub disables at 60', () => {
    const at = (d: number) => {
      const i = healthy();
      i.repository.pushed_at = daysAgo(d);
      return keys(i);
    };
    expect(at(44.9)).toEqual([]);
    expect(at(45)).toEqual(['warning inactivity']);
    expect(at(54.9)).toEqual(['warning inactivity']);
    expect(at(55)).toEqual(['critical inactivity']);
    const i = healthy();
    i.repository.pushed_at = daysAgo(50);
    expect(scheduleHealth(i)[0].message).toBe('No repository activity for 50 days; GitHub disables scheduled workflows after 60.');
  });

  it('measures the gap since the last successful scheduled run, ignoring manual runs', () => {
    const gap = (hours: number, extra: { event: string; conclusion: string; created_at: string }[] = []) => {
      const i = healthy();
      i.runs = [...extra, { event: 'schedule', conclusion: 'success', created_at: hoursAgo(hours) }];
      return keys(i);
    };
    // v0.7 (14.3): the four-hour schedule warns after 9 hours and is critical after 26.
    expect(gap(9)).toEqual([]);
    expect(gap(9.5)).toEqual(['warning scheduled-run-gap']);
    expect(gap(26)).toEqual(['warning scheduled-run-gap']);
    expect(gap(26.5)).toEqual(['critical scheduled-run-gap']);
    // A recent successful manual run does not hide a schedule that stopped.
    expect(gap(12, [{ event: 'workflow_dispatch', conclusion: 'success', created_at: hoursAgo(1) }])).toEqual(['warning scheduled-run-gap']);
  });

  it('with no successful scheduled run, measures from the oldest run listed, and flags an empty list', () => {
    const i = healthy();
    i.runs = [{ event: 'schedule', conclusion: 'cancelled', created_at: hoursAgo(1) }, { event: 'schedule', conclusion: 'cancelled', created_at: hoursAgo(12) }];
    expect(scheduleHealth(i)).toEqual([{ key: 'scheduled-run-gap', severity: 'warning', message: '12 hours with no successful scheduled run listed.' }]);
    i.runs = [];
    expect(keys(i)).toEqual(['critical scheduled-run-gap']);
  });

  it('counts consecutive failures from the newest run, stopping at a success and skipping cancelled runs', () => {
    const runs = (conclusions: string[]) => {
      const i = healthy();
      i.runs = [...conclusions.map((c, k) => ({ event: 'schedule', conclusion: c, created_at: hoursAgo(k + 1) })), { event: 'schedule', conclusion: 'success', created_at: hoursAgo(5) }];
      return keys(i);
    };
    expect(runs(['failure', 'failure'])).toEqual([]);
    expect(runs(['failure', 'timed_out', 'failure'])).toEqual(['critical consecutive-failures']);
    expect(runs(['failure', 'cancelled', 'failure', 'failure'])).toEqual(['critical consecutive-failures']);
    expect(runs(['failure', 'failure', 'success', 'failure'])).toEqual([]);
  });

  it('reports a missing or overdue manifest, and stale or held series one by one', () => {
    const i = healthy();
    i.manifest = null as unknown as typeof i.manifest;
    expect(keys(i)).toEqual(['critical manifest-missing']);
    const late = (hours: number) => {
      const j = healthy();
      j.manifest.health.expected_next_update_by = hoursAgo(hours);
      return keys(j);
    };
    expect(late(0)).toEqual([]);
    expect(late(1)).toEqual(['warning manifest-overdue']);
    expect(late(24)).toEqual(['warning manifest-overdue']);
    expect(late(25)).toEqual(['critical manifest-overdue']);
    const j = healthy();
    j.manifest.series = { 'm2-sa': { status: 'held', status_reason: 'unexpected revision' }, effr: { status: 'stale', status_reason: null }, 'm1-sa': { status: 'fresh', status_reason: null } } as typeof j.manifest.series;
    expect(scheduleHealth(j).map((f: { key: string; message: string }) => [f.key, f.message])).toEqual([
      ['series-held:m2-sa', 'm2-sa is held for review: unexpected revision.'],
      ['series-stale:effr', 'effr is stale.'],
    ]);
  });

  it('sorts critical findings first and refuses times it cannot read', () => {
    const i = healthy();
    i.workflow.state = 'disabled_inactivity';
    i.repository.pushed_at = daysAgo(46);
    i.manifest.health.expected_next_update_by = hoursAgo(2);
    expect(keys(i)).toEqual(['critical workflow-disabled', 'warning inactivity', 'warning manifest-overdue']);
    i.repository.pushed_at = 'yesterday';
    expect(() => scheduleHealth(i)).toThrow(/repository.pushed_at: not a time/);
  });
});
