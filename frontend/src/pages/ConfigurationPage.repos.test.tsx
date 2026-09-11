import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from 'antd';
import { MemoryRouter } from 'react-router-dom';

const mockUseQuery = jest.fn();
const mockUseMutation = jest.fn();

jest.mock('@apollo/client', () => ({
  gql: (literals: TemplateStringsArray, ...placeholders: string[]) =>
    literals.reduce((acc, lit, i) => acc + lit + (placeholders[i] ?? ''), ''),
}));

jest.mock('@apollo/client/react', () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
  useMutation: (...args: unknown[]) => mockUseMutation(...args),
}));

jest.mock('./settings/PlatformCredentials', () => () => <div data-testid="platform-credentials" />);
jest.mock('./settings/HefPublishTargets', () => () => <div data-testid="hef-publish-targets" />);
jest.mock('./settings/AITasks', () => () => <div data-testid="ai-tasks-tab" />);
jest.mock('./settings/InstanceSharing', () => () => <div data-testid="instance-sharing" />);

import { REPOSITORIES_TAB_LABEL, ReposTab } from './ConfigurationPage';

describe('Configuration Repos tab', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    mockUseQuery
      .mockReturnValueOnce({
        data: {
          me: { username: 'admin', role: 'ADMIN' },
          allRuleRepositories: [
            {
              id: 'repo-1',
              name: 'Repo One',
              url: 'https://github.com/acme/repo-one',
              username: 'svc-user',
              verifySsl: true,
              lastSync: null,
              ruleCount: 3,
              autoPullEnabled: false,
              autoPullSchedule: 'DISABLED',
              nextScheduledPull: null,
              ragSyncEnabled: true,
              ragSyncSchedule: '24H',
              ragDatasetPath: 'rules/templates/**/*.jsonl',
              ragBranch: 'main',
              ragNextScheduledSync: null,
              ragLastSynced: null,
              ragLastSyncStatus: 'PARTIAL',
              ragLastSyncError: '',
              ragLastSyncedTemplates: 0,
              ragFiles: [
                {
                  id: 'file-1',
                  sourcePath: 'rules/templates/base.jsonl',
                  sourceBranch: 'main',
                  language: 'KQL',
                  ingestionStatus: 'INGESTED',
                  templatesCount: 4,
                  lastSyncedAt: null,
                  lastError: '',
                  usedInGeneration: true,
                  usageCount: 2,
                  lastUsedAt: null,
                },
                {
                  id: 'file-2',
                  sourcePath: 'rules/templates/broken.jsonl',
                  sourceBranch: 'main',
                  language: 'KQL',
                  ingestionStatus: 'FAILED',
                  templatesCount: 0,
                  lastSyncedAt: null,
                  lastError: 'No valid templates found',
                  usedInGeneration: false,
                  usageCount: 0,
                  lastUsedAt: null,
                },
              ],
            },
          ],
        },
        loading: false,
        error: null,
        refetch: jest.fn(),
        startPolling: jest.fn(),
        stopPolling: jest.fn(),
      })
      .mockReturnValueOnce({
        data: { allPlaybookGraphs: [] },
        loading: false,
        error: null,
      });
  });

  test('uses Repos tab label constant', () => {
    expect(REPOSITORIES_TAB_LABEL).toBe('Repos');
  });

  test('renders RAG fields and opens edit modal with RAG controls', () => {
    mockUseMutation.mockReturnValue([jest.fn(), { loading: false }]);

    render(
      <MemoryRouter>
        <App>
          <ReposTab />
        </App>
      </MemoryRouter>
    );

    expect(screen.getByText('RAG Dataset')).toBeInTheDocument();
    expect(screen.getByText('RAG Files')).toBeInTheDocument();
    expect(screen.getByText('RAG Sync')).toBeInTheDocument();
    expect(screen.getByText('PARTIAL')).toBeInTheDocument();
    expect(screen.getByText('1/2 ingested')).toBeInTheDocument();
    expect(screen.getByText('1 used in AI')).toBeInTheDocument();
    expect(screen.getByText('Sync Now')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /edit/i }));

    expect(screen.getByText('RAG Template Sync')).toBeInTheDocument();
    expect(screen.getByText('RAG Dataset Path / Pattern')).toBeInTheDocument();
    expect(screen.getByText('RAG Branch')).toBeInTheDocument();
    expect(screen.getByText('RAG Sync Schedule')).toBeInTheDocument();
  });

  test('sync now button shows loading state while request is pending', async () => {
    let resolveSync: ((value: unknown) => void) | null = null;
    const syncPromise = new Promise((resolve) => {
      resolveSync = resolve;
    });
    const syncMock = jest.fn(() => syncPromise);

    mockUseMutation.mockImplementation((query: string) => {
      if (query.includes('syncRuleRepositoryRag')) {
        return [syncMock, { loading: false }];
      }
      return [jest.fn().mockResolvedValue({ data: {} }), { loading: false }];
    });

    render(
      <MemoryRouter>
        <App>
          <ReposTab />
        </App>
      </MemoryRouter>
    );

    const syncButton = screen.getByRole('button', { name: /sync now/i });
    fireEvent.click(syncButton);

    expect(syncMock).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      expect(syncButton).toHaveClass('ant-btn-loading');
    });

    resolveSync?.({
      data: {
        syncRuleRepositoryRag: {
          ok: true,
          message: 'queued',
          repository: { id: 'repo-1' },
        },
      },
    });
  });
});
