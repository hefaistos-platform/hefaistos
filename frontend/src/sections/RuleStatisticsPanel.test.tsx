import React from 'react';
import { render, screen } from '@testing-library/react';
import { RuleStatisticsPanel } from './RuleStatisticsPanel';
let mockTheme = 'light';
const mockRefetch = jest.fn();
jest.mock('../context/ThemeContext', () => ({ useTheme: () => ({ resolvedTheme: mockTheme }) }));
jest.mock('react-router-dom', () => ({ useNavigate: () => jest.fn(), Link: ({ children }: { children: React.ReactNode }) => <span>{children}</span> }));
jest.mock('@apollo/client', () => ({ gql: (strings: TemplateStringsArray) => strings[0] }));
jest.mock('@apollo/client/react', () => ({ useQuery: () => ({ loading: false, refetch: mockRefetch, data: { ruleStatistics: {
  generatedAt: '2026-10-21T10:00:00Z', total: 4, createdLast24h: 1, createdLast7d: 2, createdLast30d: 3,
  unchanged90dPlus: 1, activeCount: 2, deprecatedCount: 1, avgTechniquesPerRule: 1,
  withPlaybooksCount: 3, standaloneCount: 1, rulesWithTechniques: 3, linkedWorkbenchCount: 2,
  byStatus: [{ name: 'active', count: 3 }, { name: 'unknown', count: 1 }],
  byFormat: [{ name: 'KQL', count: 4 }], validation: [{ name: 'PASSED', count: 1 }, { name: 'FAILED', count: 1 }],
  deploymentByFormat: [{ name: 'KQL', deployed: 1, testing: 1, development: 1, unlinked: 1 }],
  topTechniques: [{ techniqueId: 'T1059', name: 'Command and Scripting Interpreter', count: 3 }], topSubtechniques: [],
  createdSeries: [{ date: '2026-10-20', count: 1 }, { date: '2026-10-21', count: 2 }],
  updatedSeries: [{ date: '2026-10-20', count: 2 }, { date: '2026-10-21', count: 1 }],
  repositories: [], topTags: [], tagCooccurrence: [], topAuthors: [], inactiveAuthors: [], recentChanges: [],
} } }) }));

test.each(['light', 'dark'])('dashboard renders valid pie, deployment, and trend geometry in %s theme', theme => {
  mockTheme = theme;
  jest.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 600, height: 300 } as DOMRect);
  const { container } = render(<RuleStatisticsPanel />);
  expect(screen.getByText('Validation Results')).toBeInTheDocument();
  expect(container.querySelectorAll('.recharts-pie-sector').length).toBeGreaterThan(0);
  expect(container.querySelectorAll('.recharts-bar-rectangle').length).toBeGreaterThan(0);
  expect(container.querySelectorAll('.recharts-line-curve').length).toBe(2);
  expect(container.innerHTML).not.toContain('NaN');
  jest.restoreAllMocks();
});
