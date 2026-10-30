import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const mockQuery = jest.fn();
const mockSubmit = jest.fn();
const mockDismiss = jest.fn();
const mockReview = jest.fn();
const mockRefetch = jest.fn();
jest.mock('@apollo/client', () => ({ gql: (parts: TemplateStringsArray) => parts.join('') }));
jest.mock('@apollo/client/react', () => ({
  useQuery: (...args: unknown[]) => mockQuery(...args),
  useMutation: (document: string) => [document.includes('mutation Submit') ? mockSubmit
    : document.includes('mutation Dismiss') ? mockDismiss : mockReview, { loading: false }],
}));

import RuleCorrectionFeedback from './RuleCorrectionFeedback';
import AIFeedbackReview from '../pages/settings/AIFeedbackReview';

const candidate = { id: 'feedback-1', ruleTitle: 'Process detection', outputFormat: 'KQL',
  revisionNumber: 2, variant: 'robust', before: 'DeviceProcessEvents', after: 'ProcessEvents_CL',
  diff: '-DeviceProcessEvents\n+ProcessEvents_CL' };
const reviewed = { ...candidate, status: 'SUBMITTED', correctionAuthor: 'analyst',
  issues: JSON.stringify([{ category: 'incorrect_table', explanation: 'Custom telemetry.', resolution: 'Changed table.' }]),
  verification: 'NOT_TESTED', verificationEvidence: '', submittedUsername: 'analyst', reviewedUsername: '',
  rootCause: 'UNKNOWN', reviewNote: '', promptProvenance: '{}', machineReadable: '{}', events: [] };

beforeEach(() => {
  jest.clearAllMocks();
  mockRefetch.mockResolvedValue({});
  mockSubmit.mockResolvedValue({}); mockDismiss.mockResolvedValue({}); mockReview.mockResolvedValue({});
  mockQuery.mockReturnValue({ data: { aiRuleCorrectionCandidates: [candidate], aiQualityFeedback: [reviewed] },
    refetch: mockRefetch, loading: false });
});

test('a correction submits categories and resolution only after user confirmation', async () => {
  render(<RuleCorrectionFeedback ruleId="rule-1" />);
  fireEvent.click(screen.getByRole('button', { name: 'AI feedback' }));
  expect(mockSubmit).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Explain correction' }));
  expect(screen.getByText(/-DeviceProcessEvents\s+\+ProcessEvents_CL/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Submit feedback' })).toBeDisabled();
  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'What changed?' }));
  fireEvent.click(screen.getByText('Incorrect table', { selector: '.ant-select-item-option-content' }));
  fireEvent.change(screen.getByLabelText('What was wrong?'), { target: { value: 'Local telemetry uses another table.' } });
  fireEvent.change(screen.getByLabelText('How was it resolved?'), { target: { value: 'Replaced the table name.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Submit feedback' }));
  await waitFor(() => expect(mockSubmit).toHaveBeenCalledWith({ variables: {
    feedbackId: 'feedback-1', issues: [{ category: 'incorrect_table', explanation: 'Local telemetry uses another table.',
      resolution: 'Replaced the table name.' }], verification: 'NOT_TESTED', verificationEvidence: '',
  } }));
  expect(mockReview).not.toHaveBeenCalled();
});

test('intentional edits require a reason and never submit an error classification', async () => {
  render(<RuleCorrectionFeedback ruleId="rule-1" />);
  fireEvent.click(screen.getByRole('button', { name: 'AI feedback' }));
  fireEvent.click(screen.getByRole('button', { name: 'Intentional edit / dismiss' }));
  expect(screen.getByRole('button', { name: 'Dismiss candidate' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Why is this an intentional edit?'), { target: { value: 'Requirements changed.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Dismiss candidate' }));
  await waitFor(() => expect(mockDismiss).toHaveBeenCalledWith({ variables: { feedbackId: 'feedback-1', reason: 'Requirements changed.' } }));
  expect(mockSubmit).not.toHaveBeenCalled();
});

test('admin accepts exact feedback with a reason without calling prompt activation', async () => {
  render(<AIFeedbackReview organizationId="org-1" allOrganizations={false} outputFormat="KQL" />);
  expect(mockQuery.mock.calls[0][1].variables).toEqual({ organizationId: 'org-1', allOrganizations: false, status: 'SUBMITTED', outputFormat: 'KQL' });
  fireEvent.click(screen.getByRole('button', { name: 'Review and accept' }));
  expect(screen.getByText(/-DeviceProcessEvents\s+\+ProcessEvents_CL/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Accept feedback' })).toBeDisabled();
  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Likely root cause' }));
  fireEvent.click(screen.getByText('schema mapping'));
  fireEvent.change(screen.getByLabelText('Review reason'), { target: { value: 'Confirmed local schema mismatch.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Accept feedback' }));
  await waitFor(() => expect(mockReview).toHaveBeenCalledWith({ variables: {
    feedbackId: 'feedback-1', accept: true, rootCause: 'SCHEMA_MAPPING', reviewNote: 'Confirmed local schema mismatch.',
  } }));
  expect(mockSubmit).not.toHaveBeenCalled(); expect(mockDismiss).not.toHaveBeenCalled();
});


test('feedback entry stays visible before the first save and explains how to create a correction', () => {
  mockQuery.mockReturnValue({ data: { aiRuleCorrectionCandidates: [] }, refetch: mockRefetch, loading: false });
  render(<RuleCorrectionFeedback />);
  expect(screen.getByRole('button', { name: 'AI feedback' })).toBeVisible();
  expect(mockQuery.mock.calls[0][1].skip).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'AI feedback' }));
  expect(screen.getByText('No saved AI corrections awaiting feedback')).toBeInTheDocument();
  expect(screen.getByText(/Correct the rule in the editor, then save it/)).toBeInTheDocument();
  expect(mockSubmit).not.toHaveBeenCalled();
});

test('pending correction count is visible on the feedback button', () => {
  render(<RuleCorrectionFeedback ruleId="rule-1" />);
  expect(screen.getByRole('button', { name: 'AI feedback' })).toHaveTextContent('AI feedback (1)');
  expect(screen.queryByRole('button', { name: 'Explain correction' })).not.toBeInTheDocument();
});
