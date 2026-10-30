import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const mockQuery = jest.fn();
const mockCreate = jest.fn();
const mockSuggest = jest.fn();
const mockEvaluate = jest.fn();
const mockAssess = jest.fn();
const mockReview = jest.fn();
const mockRefetch = jest.fn();
const mockStartPolling = jest.fn();
const mockStopPolling = jest.fn();
jest.mock('@apollo/client', () => ({ gql: (parts: TemplateStringsArray) => parts.join('') }));
jest.mock('@apollo/client/react', () => ({
  useQuery: (...args: unknown[]) => mockQuery(...args),
  useMutation: (document: string) => [document.includes('mutation CreateAI') ? mockCreate
    : document.includes('mutation StartAIImprovementDraft') ? mockSuggest
    : document.includes('mutation StartAIImprovementEvaluation') ? mockEvaluate
    : document.includes('mutation AssessAI') ? mockAssess : mockReview, { loading: false }],
}));
import AIImprovementProposals from './AIImprovementProposals';

const caseId = 'feedback-1';
const baseline = { content: 'DeviceProcessEvents | take 1', passed: false, checks: [{ kind: 'required_text', text: 'TimeGenerated', passed: false }] };
const candidate = { content: 'DeviceProcessEvents | where TimeGenerated > ago(1h)', passed: true, checks: [{ kind: 'required_text', text: 'TimeGenerated', passed: true }] };
const evaluation = { id: 'run-1', status: 'COMPLETED', resultData: JSON.stringify({ provider: 'TEST', model: 'test-model', candidate_passed: true,
  cases: [{ id: caseId, baseline, candidate, review_criteria: 'Verify bounded time.' }] }), assessment: null };
const proposal = { id: 'proposal-1', evaluationReady: false, evidence: '[]', cases: JSON.stringify([{ id: caseId, purpose: 'CORRECTION', required_text: ['TimeGenerated'], forbidden_text: [], review_criteria: 'Verify bounded time.' }]),
  version: { id: 'version-1', number: 2, status: 'DRAFT', instructions: 'Require a time restriction.', baseInstructions: 'Current guidance.', changeReason: 'Reviewed omission.', diff: '-Current guidance.\n+Require a time restriction.' }, evaluations: [evaluation] };
const feedback = { id: caseId, rootCause: 'PROMPT', ruleTitle: 'Reviewed rule', outputFormat: 'KQL', diff: '-take 1\n+where TimeGenerated > ago(1h)' };
let mockProposals = [proposal];
let mockFeedback = [feedback];
const props = { organizationId: 'org-1', installation: false, language: 'KQL', instructions: 'Current guidance.', baseFingerprint: 'baseline-hash', onChanged: jest.fn() };

beforeEach(() => {
  jest.clearAllMocks(); mockProposals = [proposal]; mockFeedback = [feedback];
  for (const fn of [mockCreate, mockSuggest, mockEvaluate, mockAssess, mockReview, mockRefetch]) fn.mockResolvedValue({});
  mockQuery.mockImplementation((document: string) => ({ data: document.includes('query ImprovementFeedback') ? { aiQualityFeedback: mockFeedback }
    : document.includes('query AIImprovementDraftTask') ? {} : { aiImprovementProposals: mockProposals },
    loading: false, refetch: mockRefetch, startPolling: mockStartPolling, stopPolling: mockStopPolling }));
});

test('a passing model result alone does not enable activation', () => {
  render(<AIImprovementProposals {...props} />);
  expect(screen.getByRole('button', { name: 'Review and activate' })).toBeDisabled();
  expect(mockReview).not.toHaveBeenCalled();
});

test('creating a proposal preserves its reviewed baseline and literal checks without evaluating or approving', async () => {
  render(<AIImprovementProposals {...props} />);
  fireEvent.click(screen.getByRole('button', { name: 'New improvement proposal' }));
  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Accepted feedback' }));
  fireEvent.click(screen.getByText('Reviewed rule · KQL · PROMPT'));
  fireEvent.change(screen.getByLabelText('What must the reviewer verify?'), { target: { value: 'Keep the intended time window.' } });
  fireEvent.change(screen.getByLabelText('Required literal text (one phrase per line, optional)'), { target: { value: 'TimeGenerated\nago(1h)' } });
  fireEvent.change(screen.getByLabelText('Proposed instructions'), { target: { value: 'Use a bounded time window.' } });
  fireEvent.change(screen.getByLabelText('Reason for the improvement'), { target: { value: 'Fix the reviewed omission.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save proposal' }));
  await waitFor(() => expect(mockCreate).toHaveBeenCalledWith({ variables: {
    organizationId: 'org-1', installation: false, language: 'KQL', baseFingerprint: 'baseline-hash',
    instructions: 'Use a bounded time window.', changeReason: 'Fix the reviewed omission.',
    cases: [{ feedbackId: caseId, purpose: 'CORRECTION', requiredText: ['TimeGenerated', 'ago(1h)'], forbiddenText: [], reviewCriteria: 'Keep the intended time window.' }],
  } }));
  expect(mockEvaluate).not.toHaveBeenCalled(); expect(mockReview).not.toHaveBeenCalled();
});

test('assessment shows both outputs and records an explicit per-case decision and evidence', async () => {
  render(<AIImprovementProposals {...props} />);
  fireEvent.click(screen.getByRole('button', { name: 'Assess outputs' }));
  expect(screen.getByText(baseline.content)).toBeInTheDocument();
  expect(screen.getByText(candidate.content)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Record assessment' })).toBeDisabled();
  fireEvent.mouseDown(screen.getByRole('combobox', { name: `Assessment ${caseId}` }));
  fireEvent.click(screen.getByText('Pass after review'));
  fireEvent.change(screen.getByLabelText('Assessment reason and evidence'), { target: { value: 'Verified the time window on sample events.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Record assessment' }));
  await waitFor(() => expect(mockAssess).toHaveBeenCalledWith({ variables: { evaluationId: 'run-1', cases: [
    { caseId, passed: true, note: 'Verified the time window on sample events.' },
  ] } }));
  expect(mockReview).not.toHaveBeenCalled();
});

test('activation requires review of exact instructions and a separate approval reason', async () => {
  mockProposals = [{ ...proposal, evaluationReady: true }];
  render(<AIImprovementProposals {...props} />);
  fireEvent.click(screen.getByRole('button', { name: 'Review and activate' }));
  expect(screen.getByText('Require a time restriction.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Approve and activate' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Approval / rejection reason'), { target: { value: 'Reviewed the exact guidance and comparisons.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Approve and activate' }));
  await waitFor(() => expect(mockReview).toHaveBeenCalledWith({ variables: {
    versionId: 'version-1', approve: true, reviewNote: 'Reviewed the exact guidance and comparisons.',
  } }));
});

test('running evaluations are polled and duplicate evaluation is disabled', () => {
  mockProposals = [{ ...proposal, evaluations: [{ ...evaluation, status: 'RUNNING' }] }];
  render(<AIImprovementProposals {...props} />);
  expect(mockStartPolling).toHaveBeenCalledWith(2000);
  expect(screen.getByRole('button', { name: 'Evaluate' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Assess outputs' })).toBeDisabled();
});

test('AI suggestions populate a reviewable draft without creating or activating a version', async () => {
  mockSuggest.mockResolvedValue({ data: { startAiImprovementDraft: { taskId: 'draft-task-1' } } });
  const originalQuery = mockQuery.getMockImplementation()!;
  mockQuery.mockImplementation((document: string, options: any) => document.includes('query AIImprovementDraftTask')
    ? { data: { aiImprovementDraftTask: { id: 'draft-task-1', status: 'COMPLETED', resultData: JSON.stringify({
      instructions: 'Use time windows derived from the context.', rationale: 'Correct the reviewed omission.', base_fingerprint: 'baseline-hash',
    }) } } } : originalQuery(document, options));
  render(<AIImprovementProposals {...props} />);
  fireEvent.click(screen.getByRole('button', { name: 'New improvement proposal' }));
  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Accepted feedback' }));
  fireEvent.click(screen.getByText('Reviewed rule · KQL · PROMPT'));
  fireEvent.click(screen.getByRole('button', { name: 'Suggest instructions from selected feedback' }));
  await waitFor(() => expect(screen.getByLabelText('Proposed instructions')).toHaveValue('Use time windows derived from the context.'));
  expect(mockSuggest).toHaveBeenCalledWith({ variables: {
    organizationId: 'org-1', installation: false, language: 'KQL', feedbackIds: [caseId], baseFingerprint: 'baseline-hash',
  } });
  expect(mockCreate).not.toHaveBeenCalled(); expect(mockReview).not.toHaveBeenCalled();
});

test('suggestions from another baseline cannot replace the current draft', async () => {
  mockSuggest.mockResolvedValue({ data: { startAiImprovementDraft: { taskId: 'stale-task' } } });
  const originalQuery = mockQuery.getMockImplementation()!;
  mockQuery.mockImplementation((document: string, options: any) => document.includes('query AIImprovementDraftTask')
    ? { data: { aiImprovementDraftTask: { id: 'stale-task', status: 'COMPLETED', resultData: JSON.stringify({
      instructions: 'Stale suggestion.', rationale: 'Old feedback.', base_fingerprint: 'old-hash',
    }) } } } : originalQuery(document, options));
  render(<AIImprovementProposals {...props} />);
  fireEvent.click(screen.getByRole('button', { name: 'New improvement proposal' }));
  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Accepted feedback' }));
  fireEvent.click(screen.getByText('Reviewed rule · KQL · PROMPT'));
  fireEvent.click(screen.getByRole('button', { name: 'Suggest instructions from selected feedback' }));
  await screen.findByText('The baseline changed. Refresh and start a new proposal.');
  expect(screen.getByLabelText('Proposed instructions')).toHaveValue('Current guidance.');
  expect(mockCreate).not.toHaveBeenCalled();
});

test('regression evidence is retained for evaluation and excluded from automatic prompt suggestions', async () => {
  mockFeedback = [feedback, { ...feedback, id: 'regression-1', ruleTitle: 'Schema regression', rootCause: 'SCHEMA_MAPPING' }];
  mockSuggest.mockResolvedValue({ data: { startAiImprovementDraft: { taskId: 'pending-task' } } });
  render(<AIImprovementProposals {...props} />);
  fireEvent.click(screen.getByRole('button', { name: 'New improvement proposal' }));
  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Accepted feedback' }));
  fireEvent.click(screen.getByText('Reviewed rule · KQL · PROMPT'));
  fireEvent.click(screen.getByText('Schema regression · KQL · SCHEMA_MAPPING'));
  expect(screen.getByRole('combobox', { name: 'Case purpose regression-1' }).closest('.ant-select')).toHaveTextContent('Regression check');
  fireEvent.click(screen.getByRole('button', { name: 'Suggest instructions from selected feedback' }));
  await waitFor(() => expect(mockSuggest).toHaveBeenCalledWith({ variables: expect.objectContaining({ feedbackIds: [caseId] }) }));
  expect(mockCreate).not.toHaveBeenCalled();
});
