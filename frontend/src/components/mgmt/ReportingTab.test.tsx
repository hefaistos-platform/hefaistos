import React from 'react';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { buildHistoricalData, orderCategories, WORKFLOW_ORDER } from './reportingData';
const mockUseQuery = jest.fn();
const mockExport = jest.fn();
let mockTheme = 'light';
jest.mock('@apollo/client', () => ({ gql: (s: TemplateStringsArray) => s[0], useQuery: (...args: unknown[]) => mockUseQuery(...args), useMutation: () => [mockExport, { loading: false }] }));
jest.mock('../../context/ThemeContext', () => ({ useTheme: () => ({ resolvedTheme: mockTheme }) }));
import { ReportingTab } from './ReportingTab';
const stats = {
  ach: { total: 5, createdLast30d: 1, byStatus: [{ status: 'RESEARCH', count: 3 }, { status: 'FINISHED', count: 2 }] },
  advops: { total: 4, createdLast30d: 2, byStatus: [{ status: 'DEPLOYED', count: 1 }, { status: 'RESEARCH', count: 3 }], byPriority: [{ status: 'HIGH', count: 1 }, { status: 'LOW', count: 3 }] },
  workbench: { total: 6, createdLast30d: 2, activeCount: 1, byStatus: [{ status: 'DEPLOYED', count: 1 }, { status: 'REVIEW', count: 2 }, { status: 'TESTING', count: 3 }], byRobustness: [{ status: '0', count: 1 }, { status: '4', count: 5 }] },
  rules: { total: 8, createdLast30d: 2, activeCount: 3, deprecatedCount: 1, withPlaybooksCount: 6, standaloneCount: 2 },
};
const snapshots = [
  { year: 2026, month: 10, label: 'Oct 2026', stats: JSON.stringify({ workbench: { active_count: 3, total: 6 }, rules: { active_count: 5, total: 8 } }) },
  { year: 2026, month: 9, label: 'Sep 2026', stats: JSON.stringify({ workbench: { active_count: 1, total: 4 }, rules: { total: 5 } }) },
];
const luminance = (color: string) => {
  const hex = color.startsWith('#') ? color : '#' + color.match(/\d+/g)!.slice(0, 3).map(v => Number(v).toString(16).padStart(2, '0')).join('');
  const c = hex.slice(1).match(/../g)!.map(v => parseInt(v, 16) / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
  return c[0] * .2126 + c[1] * .7152 + c[2] * .0722;
};
const readable = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  expect((hi + .05) / (lo + .05)).toBeGreaterThanOrEqual(4.5);
};
describe('Reporting', () => {
  beforeEach(() => {
    window.localStorage.clear(); mockExport.mockReset(); mockTheme = 'light';
    const historicalResult = { data: { monthlyTrends: snapshots }, loading: false };
    const currentResult = { data: { mgmtCaveStats: stats }, loading: false, refetch: jest.fn() };
    mockUseQuery.mockImplementation(query => String(query).includes('GetMonthlyTrends') ? historicalResult : currentResult);
    jest.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 600, height: 340 } as DOMRect);
  });
  afterEach(() => jest.restoreAllMocks());
  test.each(['light', 'dark'])('renders management order and readable valid SVG in %s', theme => {
    mockTheme = theme;
    const { container } = render(<ReportingTab />);
    expect(Array.from(container.querySelectorAll('section')).map(s => s.getAttribute('aria-label'))).toEqual(['Portfolio Summary', 'Deployment & Attention', 'Detection Workbenches', 'Detection Rules', 'AdvOps Hunts', 'ACH Analyses', 'Portfolio Comparison']);
    expect(container.querySelectorAll('.recharts-pie-sector').length).toBeGreaterThan(0);
    expect(container.querySelectorAll('.recharts-bar-rectangle').length).toBeGreaterThan(0);
    expect(container.innerHTML).not.toContain('NaN');
    container.querySelectorAll('text[fill]').forEach(t => readable(t.getAttribute('fill')!, theme === 'dark' ? '#141414' : '#ffffff'));
    expect(screen.getByRole('checkbox', { name: /sort by count/i })).not.toBeChecked();
    expect(within(screen.getByRole('region', { name: 'Deployment & Attention' })).getByText('5')).toBeInTheDocument();
  });
  test.each(['light', 'dark'])('historical deployment is first with gaps and readable legends in %s', theme => {
    mockTheme = theme;
    const { container } = render(<ReportingTab />);
    fireEvent.click(screen.getByText('Historical Trends', { selector: 'button span' }));
    expect(Array.from(container.querySelectorAll('.ant-card-head-title')).map(t => t.textContent)).toEqual(['Recorded Deployment Trends', 'Portfolio Inventory Trends']);
    expect(container.innerHTML).not.toContain('NaN');
    expect(container.querySelectorAll('.recharts-line-curve').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0);
    container.querySelectorAll('.recharts-legend-item-text span').forEach(el => readable((el as HTMLElement).style.color, theme === 'dark' ? '#141414' : '#ffffff'));
  });
  test('preserves workflow order, zeroes, and unclassified counts', () => {
    const categories = orderCategories([{ status: 'DEPLOYED', count: 1 }, { status: 'REVIEW', count: 2 }], WORKFLOW_ORDER, 4, true, false);
    expect(categories.find(d => d.status === 'IDEA')?.count).toBe(0);
    expect(categories[categories.length - 1]).toEqual({ status: 'UNCLASSIFIED', count: 1 });
    expect(categories.findIndex(d => d.status === 'REVIEW')).toBeLessThan(categories.findIndex(d => d.status === 'DEPLOYED'));
  });
  test('charts fit a narrow container and update after a theme switch', () => {
    jest.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 280, height: 340 } as DOMRect);
    const { container, rerender } = render(<ReportingTab />);
    container.querySelectorAll('svg.recharts-surface').forEach(svg => expect(Number(svg.getAttribute('width'))).toBe(280));
    const before = container.querySelector('text[fill]')!.getAttribute('fill');
    mockTheme = 'dark';
    rerender(<ReportingTab />);
    expect(container.querySelector('text[fill]')!.getAttribute('fill')).not.toBe(before);
    expect(container.innerHTML).not.toContain('NaN');
  });
  test('sorts snapshots and preserves unavailable counts', () => {
    const result = buildHistoricalData([...snapshots, { year: 2026, month: 8, label: 'Aug 2026', stats: 'invalid' }]);
    expect(result.map(d => d.label)).toEqual(['Aug 2026', 'Sep 2026', 'Oct 2026']);
    expect(result[0].wbActive).toBeNull(); expect(result[1].rulesActive).toBeNull(); expect(result[2].wbActive).toBe(3);
  });
  test('custom selectors and exports follow dashboard order', async () => {
    mockExport.mockResolvedValue({ data: { exportReportExcel: { success: false, message: 'No file' } } });
    render(<ReportingTab />);
    fireEvent.click(screen.getByText('Custom Report', { selector: 'button span' }));
    expect(screen.getAllByRole('checkbox').map(c => c.closest('label')?.textContent)).toEqual(['Detection Workbenches', 'Detection Rules', 'AdvOps Hunts', 'ACH Analyses']);
    fireEvent.click(screen.getByRole('checkbox', { name: 'ACH Analyses' }));
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Export selected sections' })); });
    expect(mockExport).toHaveBeenCalledWith({ variables: { sections: ['workbench', 'rules', 'advops'] } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Export all sections' })); });
    expect(mockExport).toHaveBeenLastCalledWith({ variables: { sections: null } });
  });
  test('shows query failure and retry', () => {
    mockUseQuery.mockReturnValue({ loading: false, error: { message: 'backend unavailable' }, refetch: jest.fn() });
    render(<ReportingTab />);
    expect(screen.getByText('Failed to load report data')).toBeInTheDocument();
    expect(screen.getByText('backend unavailable')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
