import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ExportImportModal } from './ExportImportModal';

const mockUseQuery = jest.fn();
const mockUseMutation = jest.fn();
const mockPublishMutation = jest.fn();

jest.mock('@apollo/client', () => ({
  gql: (literals: TemplateStringsArray, ...placeholders: string[]) =>
    literals.reduce((acc, lit, i) => acc + lit + (placeholders[i] ?? ''), ''),
}));

jest.mock('@apollo/client/react', () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
  useMutation: (...args: unknown[]) => mockUseMutation(...args),
}));

describe('ExportImportModal HEF publish options', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    mockUseQuery.mockReturnValue({
      data: {
        allRuleRepositories: [{ id: 'repo-1', name: 'Repo', url: 'https://github.com/acme/repo' }],
        opentideHefPublishProfiles: [{ id: 'profile-1', name: 'Primary', repositoryId: 'repo-1', repositoryName: 'Repo', pushPlatformRules: false, enabledPlatforms: [], kqlTargetPolicy: 'defender' }],
        platformCredentials: [],
        opentideHefPublishJobStatus: null,
      },
      loading: false,
      error: null,
    });

    mockUseMutation.mockImplementation((query: string) => {
      if (query.includes('mutation PublishWorkbenchOpenTide')) {
        return [
          mockPublishMutation.mockResolvedValue({
            data: { publishWorkbenchOpenTide: { success: true, message: 'ok', taskId: null } },
          }),
          { loading: false },
        ];
      }
      return [jest.fn(), { loading: false }];
    });
  });

  test('renders platform rules checkbox unchecked by default and sends variable when checked', async () => {
    render(
      <ExportImportModal
        visible
        onClose={jest.fn()}
        playbookId="playbook-1"
        playbookTitle="Playbook"
      />,
    );

    fireEvent.click(screen.getByRole('tab', { name: /GitHub/i }));

    const rulesCheckbox = screen.getByRole('checkbox', { name: /Also save individual rules by format/i });
    expect(rulesCheckbox).not.toBeChecked();

    fireEvent.mouseDown(screen.getByText(/Select a HEF publish profile/i));
    fireEvent.click(await screen.findByText(/Primary \(Repo\)/i));

    fireEvent.click(rulesCheckbox);
    expect(rulesCheckbox).toBeChecked();

    const publishBtn = screen.getByText(/^Publish$/i).closest('button');
    expect(publishBtn).toBeTruthy();
    fireEvent.click(publishBtn!);

    await waitFor(() => expect(mockPublishMutation).toHaveBeenCalled());
    expect(mockPublishMutation.mock.calls[0][0].variables.pushPlatformRules).toBe(true);
    expect(mockPublishMutation.mock.calls[0][0].variables.platforms).toEqual([]);
    expect(mockPublishMutation.mock.calls[0][0].variables.kqlTargetPolicy).toBe('defender');
  });
});
