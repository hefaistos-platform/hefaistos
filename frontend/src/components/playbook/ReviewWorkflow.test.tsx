import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ReviewWorkflow } from './ReviewWorkflow';

const mockFinalize = jest.fn();
jest.mock('@apollo/client/react', () => ({
  useMutation: () => [mockFinalize, { loading: false }],
}));
jest.mock('react-router-dom', () => ({ useNavigate: () => jest.fn() }));
jest.mock('antd', () => ({
  message: { success: jest.fn(), warning: jest.fn(), error: jest.fn() },
  notification: { open: jest.fn() },
  Button: () => null,
}));
jest.mock('../ui/PixelIcon', () => ({ PixelIcon: () => null }));

const pendingReview = {
  id: 'review-1', status: 'OPEN', createdAt: '2026-10-21T08:00:00Z',
  comments: [{ id: 'comment-1', text: 'Please review this detection.', createdAt: '2026-10-21T08:00:00Z', user: { username: 'author' } }],
};
const props = { playbookId: 'graph-1', userRole: 'REVIEWER', isAuthor: false, refetch: jest.fn() };

beforeEach(() => jest.clearAllMocks());

test.each([
  ['Approve', 'APPROVE', 'APPROVED', 'APPROVED', 'Approved'],
  ['Reject', 'REJECT', 'CHANGES_REQUESTED', 'RESEARCH', 'Changes requested (Rejected)'],
])('keeps the conversation after %s and a page reload', async (button, decision, reviewStatus, graphStatus, label) => {
  mockFinalize.mockResolvedValue({ data: { finalizeReview: { success: true } } });
  const view = render(<ReviewWorkflow {...props} status="REVIEW" activeReview={pendingReview} reviewHistory={[pendingReview]} />);
  fireEvent.change(screen.getByPlaceholderText('Formal feedback (Required for decision)...'), { target: { value: 'Check the threshold.\nExplain the coverage.' } });
  fireEvent.click(screen.getByRole('button', { name: button }));
  await waitFor(() => expect(props.refetch).toHaveBeenCalled());
  expect(mockFinalize).toHaveBeenCalledWith({ variables: { reqId: 'review-1', decision, feedback: 'Check the threshold.\nExplain the coverage.' } });

  const completedReview = { ...pendingReview, status: reviewStatus, comments: [...pendingReview.comments,
    { id: 'comment-2', text: 'Check the threshold.\nExplain the coverage.', createdAt: '2026-10-21T09:00:00Z', user: { username: 'reviewer' } },
  ] };
  view.rerender(<ReviewWorkflow {...props} status={graphStatus} activeReview={null} reviewHistory={[completedReview]} />);
  expect(screen.getByText(label)).toBeInTheDocument();
  expect(screen.getByText('Please review this detection.')).toBeInTheDocument();
  expect(screen.getByText('Check the threshold. Explain the coverage.')).toBeInTheDocument();
  expect(screen.getByText('author')).toBeInTheDocument();
  expect(screen.getByText('reviewer')).toBeInTheDocument();
  expect(view.container.querySelectorAll('time')).toHaveLength(2);

  view.unmount();
  render(<ReviewWorkflow {...props} status={graphStatus} activeReview={null} reviewHistory={[completedReview]} />);
  expect(screen.getByText('Check the threshold. Explain the coverage.')).toBeInTheDocument();
});

test('keeps previous feedback when resubmitted and after deployment', () => {
  const rejected = { ...pendingReview, status: 'CHANGES_REQUESTED' };
  const reopened = { ...pendingReview, id: 'review-2', comments: [{ ...pendingReview.comments[0], id: 'comment-2', text: 'Threshold updated.' }] };
  const view = render(<ReviewWorkflow {...props} status="REVIEW" activeReview={reopened} reviewHistory={[rejected, reopened]} />);
  expect(screen.getByText('Review 1')).toBeInTheDocument();
  expect(screen.getByText('Review 2')).toBeInTheDocument();
  expect(screen.getByText('Please review this detection.')).toBeInTheDocument();
  expect(screen.getByText('Threshold updated.')).toBeInTheDocument();
  view.rerender(<ReviewWorkflow {...props} status="DEPLOYED" activeReview={null} reviewHistory={[rejected, { ...reopened, status: 'APPROVED' }]} />);
  expect(screen.getByText('Please review this detection.')).toBeInTheDocument();
  expect(screen.getByText('Threshold updated.')).toBeInTheDocument();
});
