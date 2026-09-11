import React from 'react';
import { render, screen } from '@testing-library/react';

const mockUseQuery = jest.fn();
const mockUseMutation = jest.fn();

jest.mock('@apollo/client', () => ({
  gql: (strings: TemplateStringsArray) => strings[0],
}));

jest.mock('@apollo/client/react', () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
  useMutation: (...args: unknown[]) => mockUseMutation(...args),
}));

import { WaitingRoomPage } from './WaitingRoomPage';

describe('WaitingRoomPage', () => {
  beforeEach(() => {
    mockUseQuery.mockReset();
    mockUseMutation.mockReset();
    mockUseMutation.mockReturnValue([jest.fn().mockResolvedValue({ data: {} }), { loading: false }]);
    mockUseQuery.mockImplementation(() => ({ data: {}, loading: false, refetch: jest.fn() }));
  });

  test('shows create/import actions for reviewer and supports happy-path rendering', () => {
    mockUseQuery
      .mockReturnValueOnce({
        data: { me: { id: 'u1', role: 'REVIEWER', isSuperuser: false } },
        loading: false,
      })
      .mockReturnValueOnce({
        data: {
          waitingCases: [
            {
              id: 'wc-1',
              createdBy: { id: 'u1' },
              title: 'Suspicious command line',
              shortDescription: 'Investigate encoded command execution',
              detectionObjective: 'Detect powershell abuse',
              mappedTtps: ['T1059.001'],
              estimatedDetectionComplexity: 'MEDIUM',
              sourceType: 'MANUAL',
              mispEventId: '',
              status: 'READY',
              enrichmentError: '',
              promotedAt: null,
              updatedAt: new Date().toISOString(),
              promotedGraph: null,
            },
          ],
        },
        loading: false,
        refetch: jest.fn(),
      })
      .mockReturnValueOnce({
        data: { mispInstances: [{ id: 'misp-1', name: 'Main MISP' }] },
        loading: false,
      });

    render(<WaitingRoomPage />);

    expect(screen.getByRole('heading', { name: /waiting room/i })).toBeInTheDocument();
    expect(screen.getByText(/suspicious command line/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create case/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /import from misp/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();

  });

  test('hides reviewer/admin actions for viewer role', () => {
    mockUseQuery
      .mockReturnValueOnce({
        data: { me: { id: 'u2', role: 'VIEWER', isSuperuser: false } },
        loading: false,
      })
      .mockReturnValueOnce({
        data: { waitingCases: [] },
        loading: false,
        refetch: jest.fn(),
      })
      .mockReturnValueOnce({
        data: { mispInstances: [] },
        loading: false,
      });

    render(<WaitingRoomPage />);

    expect(screen.queryByRole('button', { name: /create case/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /import from misp/i })).not.toBeInTheDocument();
  });
});
