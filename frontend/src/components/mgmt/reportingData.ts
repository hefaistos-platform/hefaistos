import { MonthlySnapshot } from '../../graphql/mgmtAIPrompts';

export const WORKFLOW_ORDER = ['IDEA', 'RESEARCH', 'DEVELOPMENT', 'REVIEW', 'TESTING', 'APPROVED', 'DEPLOYED', 'TUNING'];
export const PRIORITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
export type StatusCount = { status: string; count: number };

export function orderCategories(data: StatusCount[], order: string[], total: number, showEmpty: boolean, sortByCount: boolean) {
  const values = new Map(data.map(d => [d.status, d.count]));
  const keys = [...order, ...data.map(d => d.status).filter(key => !order.includes(key))];
  const result = keys.map(status => ({ status, count: values.get(status) ?? 0 }));
  const missing = total - data.reduce((sum, d) => sum + d.count, 0);
  if (missing > 0) result.push({ status: 'UNCLASSIFIED', count: missing });
  const filtered = result.filter(d => showEmpty || d.count > 0);
  return sortByCount ? filtered.sort((a, b) => b.count - a.count || a.status.localeCompare(b.status)) : filtered;
}

export function buildHistoricalData(snapshots: MonthlySnapshot[]) {
  return [...snapshots].sort((a, b) => a.year - b.year || a.month - b.month).map(snap => {
    let stats: Record<string, any> = {};
    try {
      const parsed = typeof snap.stats === 'string' ? JSON.parse(snap.stats) : snap.stats;
      if (parsed && typeof parsed === 'object') stats = parsed;
    } catch { /* Keep unavailable values as gaps, never zero. */ }
    const count = (value: unknown) => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
    return {
      label: snap.label,
      achTotal: count(stats.ach?.total), advopsTotal: count(stats.advops?.total),
      wbTotal: count(stats.workbench?.total), wbActive: count(stats.workbench?.active_count),
      rulesTotal: count(stats.rules?.total), rulesActive: count(stats.rules?.active_count),
    };
  });
}
