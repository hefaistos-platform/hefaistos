import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

let mockRows: any[] = [];
const mockStored = jest.fn();

jest.mock('@apollo/client', () => ({
  ...jest.requireActual('@apollo/client'),
  useQuery: () => ({ data: { maieuticGenerationStatus: mockRows }, startPolling: jest.fn(), stopPolling: jest.fn() }),
}));

// eslint-disable-next-line import/first
import { MaieuticGenerationBanner } from './MaieuticGenerationBanner';

const row = (over: any) => ({ taskId: 't1', outputFormat: 'KQL', status: 'PENDING', validationStatus: null, hasRule: false, error: '', ...over });

beforeEach(() => mockStored.mockReset());

describe('MaieuticGenerationBanner', () => {
  it('renders nothing for a workbench without Maieutic tasks', () => {
    mockRows = [];
    const { container } = render(<MaieuticGenerationBanner playbookId="w" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('says what is being generated while tasks are active', () => {
    mockRows = [row({ status: 'RUNNING' }), row({ taskId: 't2', outputFormat: 'SPL' })];
    render(<MaieuticGenerationBanner playbookId="w" />);
    expect(screen.getByText(/Generating from your Maieutic design: KQL, SPL/)).toBeInTheDocument();
  });

  it('reports stored rules once and asks the page to reload', async () => {
    mockRows = [row({ status: 'COMPLETED', hasRule: true })];
    const { rerender } = render(<MaieuticGenerationBanner playbookId="w" onStored={mockStored} />);
    expect(screen.getByText(/Added from your Maieutic design: KQL/)).toBeInTheDocument();
    await waitFor(() => expect(mockStored).toHaveBeenCalledTimes(1));
    rerender(<MaieuticGenerationBanner playbookId="w" onStored={mockStored} />);
    expect(mockStored).toHaveBeenCalledTimes(1);
  });

  it('is honest when a draft was not stored or generation failed', () => {
    mockRows = [row({ status: 'COMPLETED', hasRule: false, outputFormat: 'SPL' }), row({ taskId: 't3', status: 'FAILED', error: 'provider down', outputFormat: 'EQL' })];
    render(<MaieuticGenerationBanner playbookId="w" />);
    expect(screen.getByText(/Generated but not stored \(SPL\)/)).toBeInTheDocument();
    expect(screen.getByText(/Generation failed for EQL. provider down/)).toBeInTheDocument();
  });
});
