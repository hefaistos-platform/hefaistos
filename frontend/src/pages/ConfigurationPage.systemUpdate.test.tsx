import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { App } from 'antd';

jest.mock('../utils/authSession', () => ({
  getStoredAccessToken: () => 'fake-token',
}));

jest.mock('../config/env', () => ({
  getApiBaseUrl: () => 'http://localhost:8000',
}));

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

import { SystemUpdateTab } from './ConfigurationPage';

describe('SystemUpdateTab', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseQuery.mockReturnValue({ data: {}, loading: false, error: null, refetch: jest.fn() });
    mockUseMutation.mockReturnValue([jest.fn(), { loading: false }]);
  });

  test('shows superuser-only warning when viewer is not superuser', () => {
    render(
      <App>
        <SystemUpdateTab isSuperuser={false} />
      </App>
    );

    expect(screen.getByText(/restricted to superuser accounts/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /update now/i })).not.toBeInTheDocument();
  });

  test('starts update job with force mode after confirmation', async () => {
    const confirmMock = jest.spyOn(window, 'confirm').mockReturnValue(true);
    const fetchMock = jest.spyOn(global, 'fetch' as any).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/system/config/update/check')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            current_version: '1.0.0',
            build: { commit: 'abc123' },
            update_capability: { can_update: true, reason: 'ok' },
            running_job_id: null,
          }),
        } as Response);
      }
      if (url.endsWith('/api/system/config/update/start')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ job_id: 'job-1', status: 'PENDING', mode: 'force' }),
        } as Response);
      }
      if (url.endsWith('/api/system/config/update/jobs/job-1')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ id: 'job-1', mode: 'force', status: 'RUNNING', summary: { success: false } }),
        } as Response);
      }
      if (url.includes('/api/system/config/update/jobs/job-1/logs')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ logs: [{ ts: '2026-01-01T00:00:00Z', line: 'Pulled' }], total: 1 }),
        } as Response);
      }
      return Promise.reject(new Error(`Unexpected fetch URL: ${url}`));
    });

    render(
      <App>
        <SystemUpdateTab isSuperuser={true} />
      </App>
    );

    await waitFor(() => {
      expect(screen.getByText(/Current Version/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('switch'));
    fireEvent.click(screen.getByRole('button', { name: /update now/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        'http://localhost:8000/api/system/config/update/start',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ force: true }),
        })
      );
    });

    expect(confirmMock).toHaveBeenCalled();
    confirmMock.mockRestore();
    fetchMock.mockRestore();
  });
});
