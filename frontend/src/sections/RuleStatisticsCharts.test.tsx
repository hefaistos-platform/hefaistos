import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { ChartTooltip, Doughnut, HorizontalBars, StableChart } from './RuleStatisticsCharts';
let mockTheme = 'light';
jest.mock('../context/ThemeContext', () => ({ useTheme: () => ({ resolvedTheme: mockTheme }) }));
const luminance = (hex: string) => {
  const c = hex.slice(1).match(/../g)!.map(v => parseInt(v, 16) / 255)
    .map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
  return c[0] * .2126 + c[1] * .7152 + c[2] * .0722;
};
const contrast = (a: string, b: string) => {
  const v = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (v[0] + .05) / (v[1] + .05);
};
describe('statistics chart visibility', () => {
  beforeEach(() => { jest.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 600, height: 300 } as DOMRect); });
  afterEach(() => jest.restoreAllMocks());
  test.each(['light', 'dark'])('renders actual charts with readable text in %s theme', theme => {
    mockTheme = theme;
    const { container } = render(<><Doughnut data={[{ name: 'Passed', count: 3 }, { name: 'Failed', count: 1 }]} />
      <HorizontalBars data={[{ name: 'T1059', count: 4 }]} /></>);
    expect(container.querySelectorAll('.recharts-pie-sector').length).toBe(2);
    expect(container.querySelectorAll('.recharts-bar-rectangle').length).toBeGreaterThan(0);
    expect(container.innerHTML).not.toContain('NaN');
    expect(screen.getByText('75.0%', { exact: false })).toBeInTheDocument();
    container.querySelectorAll('text[fill]').forEach(text => {
      const color = text.getAttribute('fill')!;
      if (color.startsWith('#')) expect(contrast(color, theme === 'dark' ? '#141414' : '#ffffff')).toBeGreaterThanOrEqual(4.5);
    });
  });
  test.each(['light', 'dark'])('tooltip text has sufficient contrast in %s theme', theme => {
    mockTheme = theme;
    const { container } = render(<ChartTooltip active label="KQL" payload={[{ name: 'Rules', value: 4 }]} />);
    const style = (container.firstChild as HTMLElement).style;
    const toHex = (value: string) => '#' + value.match(/\d+/g)!.slice(0, 3).map(n => Number(n).toString(16).padStart(2, '0')).join('');
    expect(contrast(toHex(style.color), toHex(style.background))).toBeGreaterThanOrEqual(4.5);
  });
  test('measures again when a hidden chart becomes visible', () => {
    let width = 0;
    jest.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(() => ({ width } as DOMRect));
    render(<StableChart height={200}>{size => <span>Chart width: {size}</span>}</StableChart>);
    expect(screen.queryByText(/Chart width/)).not.toBeInTheDocument();
    width = 600;
    act(() => window.dispatchEvent(new Event('resize')));
    expect(screen.getByText('Chart width: 600')).toBeInTheDocument();
  });
  test('empty chart shows an explicit empty state', () => {
    render(<Doughnut data={[{ name: 'Passed', count: 0 }]} unit="workbenches" />);
    expect(screen.getByText('No workbenches available')).toBeInTheDocument();
  });
  test('updates chart label colors when the theme changes', () => {
    mockTheme = 'light';
    const { container, rerender } = render(<Doughnut data={[{ name: 'Passed', count: 3 }]} />);
    const before = container.querySelector('text')!.getAttribute('fill');
    mockTheme = 'dark';
    rerender(<Doughnut data={[{ name: 'Passed', count: 3 }]} />);
    expect(container.querySelector('text')!.getAttribute('fill')).not.toBe(before);
  });
});
