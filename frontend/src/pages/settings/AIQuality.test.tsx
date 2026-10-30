import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const mockQuery = jest.fn();
const mockCreate = jest.fn();
const mockReview = jest.fn();
const mockRestore = jest.fn();
const mockRefetch = jest.fn();

jest.mock('@apollo/client', () => ({
  gql: (parts: TemplateStringsArray) => parts.join(''),
}));
jest.mock('@apollo/client/react', () => ({
  useQuery: (...args: unknown[]) => mockQuery(...args),
  useMutation: (document: string) => [document.includes('mutation CreateQuality') ? mockCreate
    : document.includes('mutation ReviewQuality') ? mockReview : mockRestore, { loading: false }],
}));

import AIQuality from './AIQuality';

const prompt = {
  promptKey: 'rule_generation.generate', title: 'Rule generation', component: 'rule_generation', language: 'KQL',
  configurationId: 'config-1', activeVersionId: 'approved-1', defaultVersion: '2026.10.30.1',
  defaultInstructions: 'Product guidance.', effectiveInstructions: 'Current approved guidance.',
  effectiveSource: 'ORGANIZATION', effectiveVersion: 'approved-1', effectiveFingerprint: 'current-hash',
  inheritedInstructions: 'Installation guidance.', inheritedSource: 'INSTALLATION', inheritedFingerprint: 'inherited-hash',
  versions: [{ id: 'draft-2', number: 2, instructions: 'Prefer approved local tables.', baseInstructions: 'Current approved guidance.',
    contentHash: 'draft-hash', changeReason: 'Correct invalid tables.', status: 'DRAFT', createdAt: '2026-10-30T10:00:00Z',
    createdByUsername: 'admin', reviewNote: '', diff: '-Current approved guidance.\n+Prefer approved local tables.' }],
  events: [],
};

describe('AI Quality review workflow', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCreate.mockResolvedValue({ data: { createQualityPromptDraft: { version: { id: 'new-draft' } } } });
    mockReview.mockResolvedValue({ data: { reviewQualityPromptVersion: { version: { id: 'draft-2', status: 'APPROVED' } } } });
    mockRestore.mockResolvedValue({ data: { restoreQualityPromptVersion: { configurationId: 'config-1' } } });
    mockRefetch.mockResolvedValue({});
    mockQuery.mockReturnValue({ data: { aiQualityPrompts: [prompt] }, loading: false, refetch: mockRefetch });
  });

  test('creating a draft does not approve it and preserves its reviewed baseline', async () => {
    render(<AIQuality isSuperuser={false} />);
    fireEvent.click(screen.getByRole('button', { name: 'New draft' }));
    fireEvent.change(screen.getByLabelText('Instructions'), { target: { value: 'Use the validated schema.' } });
    fireEvent.change(screen.getByLabelText('Why should these instructions change?'), { target: { value: 'Repeated table errors.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create draft' }));
    await waitFor(() => expect(mockCreate).toHaveBeenCalledWith({ variables: expect.objectContaining({
      instructions: 'Use the validated schema.', changeReason: 'Repeated table errors.', baseFingerprint: 'current-hash', installation: false,
    }) }));
    expect(mockReview).not.toHaveBeenCalled();
  });

  test('approval shows the exact proposed instructions and requires a review reason', async () => {
    render(<AIQuality isSuperuser={false} />);
    fireEvent.click(screen.getByRole('button', { name: 'Review' }));
    expect(screen.getByText('Prefer approved local tables.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve and activate' })).toBeDisabled();
    expect(mockReview).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Review decision and reason'), { target: { value: 'Checked the schema and reviewed outputs.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Approve and activate' }));
    await waitFor(() => expect(mockReview).toHaveBeenCalledWith({ variables: {
      versionId: 'draft-2', approve: true, reviewNote: 'Checked the schema and reviewed outputs.',
    } }));
  });

  test('reset previews inherited guidance and sends fingerprints for stale-change checks', async () => {
    render(<AIQuality isSuperuser={false} />);
    fireEvent.click(screen.getByRole('button', { name: 'Use inherited instructions' }));
    expect(screen.getByText('Installation guidance.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Review decision and reason'), { target: { value: 'Use the installation baseline.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    await waitFor(() => expect(mockRestore).toHaveBeenCalledWith({ variables: {
      configurationId: 'config-1', versionId: null, reason: 'Use the installation baseline.',
      expectedFingerprint: 'current-hash', inheritedFingerprint: 'inherited-hash',
    } }));
  });
});
