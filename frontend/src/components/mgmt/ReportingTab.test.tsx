import React from 'react';
import { render, screen } from '@testing-library/react';

const mockUseQuery = jest.fn();
const mockUseMutation = jest.fn();

jest.mock('@apollo/client', () => ({
  gql: (strings: TemplateStringsArray) => strings[0],
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
  useMutation: (...args: unknown[]) => mockUseMutation(...args),
}));

jest.mock('../../context/ThemeContext', () => ({
  useTheme: () => ({
    mode: 'dark',
    resolvedTheme: 'dark',
    setMode: jest.fn(),
    cycleMode: jest.fn(),
  }),
}));

jest.mock('recharts', () => ({
  BarChart: ({ children }: any) => <div data-testid="bar-chart">{children}</div>,
  LineChart: ({ children }: any) => <div data-testid="line-chart">{children}</div>,
  Bar: () => null,
  Line: () => null,
  Cell: () => null,
  CartesianGrid: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}));

import { ReportingTab } from './ReportingTab';

describe('ReportingTab', () => {
  beforeEach(() => {
    mockUseQuery.mockReset();
    mockUseMutation.mockReturnValue([jest.fn(), { loading: false }]);
  });

  test('renders query error state', () => {
    mockUseQuery.mockReturnValue({
      data: undefined,
      loading: false,
      error: { message: 'backend unavailable' },
    });

    render(<ReportingTab />);

    expect(screen.getByText(/failed to load report data/i)).toBeInTheDocument();
    expect(screen.getByText(/backend unavailable/i)).toBeInTheDocument();
  });
});
