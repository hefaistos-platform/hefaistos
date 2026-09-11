import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App as AntApp } from 'antd';
import HefPublishTargets from './HefPublishTargets';

const mockUseQuery = jest.fn();
const mockUseMutation = jest.fn();
const mockSetProfile = jest.fn();

jest.mock('@apollo/client', () => ({
  gql: (literals: TemplateStringsArray, ...placeholders: string[]) =>
    literals.reduce((acc, lit, i) => acc + lit + (placeholders[i] ?? ''), ''),
}));

jest.mock('@apollo/client/react', () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
  useMutation: (...args: unknown[]) => mockUseMutation(...args),
}));

describe('HefPublishTargets pushPlatformRules field', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    mockUseQuery.mockImplementation((query: string) => {
      if (query.includes('query GetOpenTideHefPublishProfilesAdmin')) {
        return {
          data: {
            opentideHefPublishProfiles: [{
              id: 'profile-1',
              name: 'Prod',
              repositoryId: 'repo-1',
              repositoryName: 'Repo',
              repositoryUrl: 'https://github.com/acme/repo',
              branch: 'main',
              targetFolder: '',
              pushPlatformRules: true,
              enabledPlatforms: [],
              useGraphConfiguredPlatforms: true,
              kqlTargetPolicy: 'defender',
              enabled: true,
              createdAt: '2026-01-01',
              updatedAt: '2026-01-01',
            }],
          },
          loading: false,
          error: null,
          refetch: jest.fn(),
        };
      }

      return {
        data: {
          allRuleRepositories: [{ id: 'repo-1', name: 'Repo', url: 'https://github.com/acme/repo' }],
        },
        loading: false,
        error: null,
      };
    });

    mockUseMutation.mockImplementation((query: string) => {
      if (query.includes('mutation SetOpenTidePublishProfile')) {
        return [
          mockSetProfile.mockResolvedValue({
            data: { setOpenTidePublishProfile: { success: true } },
          }),
          { loading: false },
        ];
      }
      return [jest.fn(), { loading: false }];
    });
  });

  test('loads and submits pushPlatformRules from profile form', async () => {
    const { container } = render(
      <AntApp>
        <HefPublishTargets />
      </AntApp>,
    );

    const editBtn = Array.from(container.querySelectorAll('button')).find((btn) =>
      btn.querySelector('.anticon-edit'),
    );
    expect(editBtn).toBeTruthy();
    fireEvent.click(editBtn!);
    const label = await screen.findByText(/Push individual platform rule files/i);
    const toggle = label.closest('.ant-form-item')?.querySelector('button[role="switch"]');
    expect(toggle).toBeTruthy();
    expect(toggle!).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));

    await waitFor(() => expect(mockSetProfile).toHaveBeenCalled());
    expect(mockSetProfile.mock.calls[0][0].variables.pushPlatformRules).toBe(true);
  });
});
