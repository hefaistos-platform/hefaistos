import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

const mockNavigate = jest.fn();
const mockUseQuery = jest.fn();

jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}), { virtual: true });

jest.mock('@apollo/client', () => ({
  gql: (strings: TemplateStringsArray) => strings[0],
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
}));

jest.mock('../components/PromptLibrary', () => ({
  PromptLibrary: () => <div data-testid="prompt-library" />,
}));

jest.mock('../components/mgmt/ReportingTab', () => ({
  ReportingTab: () => <div data-testid="reporting-tab">Reporting Tab</div>,
}));

import { MGMTCavePage } from './MGMTCavePage';

const ACCESS_DATA = {
  data: {
    me: {
      id: '1',
      username: 'admin',
      role: 'ADMIN',
      isSuperuser: false,
      organization: { id: 'org-1' },
    },
  },
  loading: false,
};

describe('MGMTCavePage', () => {
  beforeEach(() => {
    mockNavigate.mockReset();
    mockUseQuery.mockReset();
  });

  test('renders MGMT Cave content for admin users', () => {
    mockUseQuery.mockReturnValue(ACCESS_DATA);

    render(<MGMTCavePage />);

    expect(screen.getByRole('heading', { name: /mgmt cave/i })).toBeInTheDocument();
    expect(screen.getByText(/ai assistant/i)).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  test('loads reporting tab lazily', async () => {
    mockUseQuery.mockReturnValue(ACCESS_DATA);

    render(<MGMTCavePage />);

    expect(await screen.findByTestId('reporting-tab')).toBeInTheDocument();
  });

  test('redirects unauthorized users to the homepage', async () => {
    mockUseQuery.mockReturnValue({
      data: {
        me: {
          id: '2',
          username: 'analyst',
          role: 'ANALYST',
          isSuperuser: false,
          organization: { id: 'org-1' },
        },
      },
      loading: false,
    });

    render(<MGMTCavePage />);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
    });
  });
});
