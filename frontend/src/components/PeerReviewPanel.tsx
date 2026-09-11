import React, { useMemo, useState } from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { Card, Typography, Space, Tag, Button, Input, message, Tabs } from 'antd';
import SimpleMDE from 'react-simplemde-editor';
import { createEditorOptions, MARKDOWN_PLACEHOLDERS, configureMdeInstance } from '../config/markdownConfig';
import { MarkdownRenderer } from './MarkdownRenderer';

// Queries
const GET_ME = gql`
  query Me { me { username } }
`;

const GET_PLAYBOOK_REVIEWS = gql`
  query GetPlaybookReviews($playbookId: UUID!) {
    playbookReviews(playbookId: $playbookId) {
      id
      status
      createdAt
      updatedAt
      author { username }
      comments { id text createdAt author { username } }
    }
  }
`;

// Mutations
const CREATE_REVIEW_REQUEST = gql`
  mutation CreateReviewRequest($playbookId: UUID!, $reviewerIds: [ID!]) {
    createReviewRequest(playbookId: $playbookId, reviewerIds: $reviewerIds) {
      reviewRequest { id status }
    }
  }
`;

const ADD_REVIEW_COMMENT = gql`
  mutation AddReviewComment($reviewRequestId: UUID!, $text: String!) {
    addReviewComment(reviewRequestId: $reviewRequestId, text: $text) {
      comment { id text createdAt author { username } }
    }
  }
`;

const APPROVE_REVIEW = gql`
  mutation ApproveReview($reviewRequestId: UUID!) {
    approveReview(reviewRequestId: $reviewRequestId) { reviewRequest { id status } }
  }
`;

const REQUEST_CHANGES = gql`
  mutation RequestChanges($reviewRequestId: UUID!, $commentText: String!) {
    requestChanges(reviewRequestId: $reviewRequestId, commentText: $commentText) {
      reviewRequest { id status }
    }
  }
`;

const CLOSE_REVIEW = gql`
  mutation CloseReview($reviewRequestId: UUID!) {
    closeReview(reviewRequestId: $reviewRequestId) { playbook { id status } }
  }
`;

const REOPEN_REVIEW = gql`
  mutation ReopenReview($reviewRequestId: UUID!, $commentText: String) {
    reopenReview(reviewRequestId: $reviewRequestId, commentText: $commentText) { reviewRequest { id status } }
  }
`;

interface Props {
  playbookId: string;
  playbookStatus: string;
  authorUsername: string | null;
}

export const PeerReviewPanel: React.FC<Props> = ({ playbookId, playbookStatus, authorUsername }) => {
  const [reviewComment, setReviewComment] = useState('');
  const [commentPreviewTab, setCommentPreviewTab] = useState('editor');

  // Memoized editor options for review comments
  const commentEditorOptions = useMemo(
    () => createEditorOptions('minimal', MARKDOWN_PLACEHOLDERS.notes),
    []
  );

  const { data: meData } = useQuery<{ me: { username: string } }>(GET_ME, { fetchPolicy: 'cache-first' });
  const me = meData?.me;
  const isAuthor = useMemo(() => !!me && !!authorUsername && me.username === authorUsername, [me, authorUsername]);

  const { data: reviewsData } = useQuery<{ playbookReviews: Array<{ id: string; status: string; createdAt: string; updatedAt: string; author: { username: string }; comments: Array<{ id: string; text: string; createdAt: string; author: { username: string } }> }> }, { playbookId: string }>(
    GET_PLAYBOOK_REVIEWS,
    { variables: { playbookId } }
  );

  const activeReview = reviewsData?.playbookReviews?.[0] ?? null;

  const [createReviewRequest, { loading: creatingReview }] = useMutation(CREATE_REVIEW_REQUEST, {
    refetchQueries: [ { query: GET_PLAYBOOK_REVIEWS, variables: { playbookId } } ],
  });
  const [addReviewComment, { loading: addingComment }] = useMutation(ADD_REVIEW_COMMENT, {
    refetchQueries: [ { query: GET_PLAYBOOK_REVIEWS, variables: { playbookId } } ],
  });
  const [approveReview, { loading: approving }] = useMutation(APPROVE_REVIEW, {
    refetchQueries: [ { query: GET_PLAYBOOK_REVIEWS, variables: { playbookId } } ],
  });
  const [requestChanges, { loading: requesting }] = useMutation(REQUEST_CHANGES, {
    refetchQueries: [ { query: GET_PLAYBOOK_REVIEWS, variables: { playbookId } } ],
  });
  const [closeReview, { loading: closing }] = useMutation(CLOSE_REVIEW, {
    refetchQueries: [ { query: GET_PLAYBOOK_REVIEWS, variables: { playbookId } } ],
  });
  const [reopenReview, { loading: reopening }] = useMutation(REOPEN_REVIEW, {
    refetchQueries: [ { query: GET_PLAYBOOK_REVIEWS, variables: { playbookId } } ],
  });

  const handleSubmitForReview = async () => {
    try {
      await createReviewRequest({ variables: { playbookId } });
      message.success('Submitted for peer review');
    } catch (e: any) {
      message.error(e.message || 'Failed to submit review');
    }
  };

  const handleApprove = async () => {
    if (!activeReview) return;
    try {
      await approveReview({ variables: { reviewRequestId: activeReview.id } });
      message.success('Review approved');
    } catch (e: any) {
      message.error(e.message || 'Failed to approve');
    }
  };

  const handleRequestChanges = async () => {
    if (!activeReview) return;
    if (!reviewComment.trim()) {
      message.warning('Please add a comment before requesting changes');
      return;
    }
    try {
      await requestChanges({ variables: { reviewRequestId: activeReview.id, commentText: reviewComment.trim() } });
      setReviewComment('');
      message.success('Changes requested');
    } catch (e: any) {
      message.error(e.message || 'Failed to request changes');
    }
  };

  const handleAddComment = async () => {
    if (!activeReview || !reviewComment.trim()) return;
    try {
      await addReviewComment({ variables: { reviewRequestId: activeReview.id, text: reviewComment.trim() } });
      setReviewComment('');
    } catch (e: any) {
      message.error(e.message || 'Failed to add comment');
    }
  };

  const handleCloseReview = async () => {
    if (!activeReview) return;
    try {
      await closeReview({ variables: { reviewRequestId: activeReview.id } });
      message.success('Review closed');
    } catch (e: any) {
      message.error(e.message || 'Failed to close review');
    }
  };

  const handleReopenReview = async () => {
    if (!activeReview) return;
    try {
      await reopenReview({ variables: { reviewRequestId: activeReview.id, commentText: reviewComment.trim() || null } });
      setReviewComment('');
      message.success('Review reopened');
    } catch (e: any) {
      message.error(e.message || 'Failed to reopen review');
    }
  };

  const showSubmit = isAuthor && playbookStatus === 'DEVELOPMENT' && (!activeReview || activeReview.status === 'CLOSED');
  const showApproveRequest = !isAuthor && activeReview?.status === 'OPEN';
  const showFinalize = isAuthor && activeReview?.status === 'APPROVED';
  const showReopen = isAuthor && activeReview?.status === 'CHANGES_REQUESTED';

  return (
    <Card size="small" title="Peer Review" style={{ marginBottom: 16 }}>
      {!activeReview || activeReview.status === 'CLOSED' ? (
        <div>
          <Typography.Paragraph type="secondary">Submit this playbook for peer review.</Typography.Paragraph>
          <Button type="primary" onClick={handleSubmitForReview} disabled={!showSubmit} loading={creatingReview}>
            Submit for Review
          </Button>
          {!showSubmit && (
            <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>
              Only the author can submit, and the playbook must be in DEVELOPMENT.
            </Typography.Paragraph>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          <Space style={{ display: 'flex', justifyContent: 'space-between' }}>
            <Typography.Text>
              Current Review Status: <Tag color="processing">{activeReview.status}</Tag>
            </Typography.Text>
            <Space>
              {showApproveRequest && (
                <>
                  <Button onClick={handleApprove} loading={approving}>Approve</Button>
                  <Button danger onClick={handleRequestChanges} loading={requesting}>Request Changes</Button>
                </>
              )}
              {showFinalize && (
                <Button type="primary" onClick={handleCloseReview} loading={closing}>Finalize Review</Button>
              )}
              {showReopen && (
                <Button type="primary" onClick={handleReopenReview} loading={reopening}>Reopen</Button>
              )}
            </Space>
          </Space>

          {/* Comments List */}
          <div style={{ marginTop: 8 }}>
            <Typography.Text strong>Comments</Typography.Text>
            <div style={{ marginTop: 8 }}>
              {activeReview.comments?.length ? (
                activeReview.comments.map(c => (
                  <div key={c.id} style={{ padding: 8, border: '1px solid #eee', borderRadius: 6, marginBottom: 8 }}>
                    <div style={{ fontSize: 12, color: '#888' }}>{new Date(c.createdAt).toLocaleString()} — {c.author?.username || 'Unknown'}</div>
                    <MarkdownRenderer content={c.text} variant="small" />
                  </div>
                ))
              ) : (
                <Typography.Paragraph type="secondary" italic>No comments yet.</Typography.Paragraph>
              )}
            </div>
          </div>

          {/* Comment Input */}
          {activeReview.status !== 'CLOSED' && (
            <div style={{ marginTop: 8 }}>
              <Tabs
                activeKey={commentPreviewTab}
                onChange={setCommentPreviewTab}
                tabBarStyle={{ marginBottom: 8 }}
                items={[
                  {
                    key: 'editor',
                    label: '✏️ Editor',
                    children: (
                      <div style={{ border: '1px solid #d9d9d9', borderRadius: '6px', overflow: 'hidden' }}>
                        <SimpleMDE
                          value={reviewComment}
                          onChange={setReviewComment}
                          options={commentEditorOptions}
                          getMdeInstance={configureMdeInstance}
                        />
                      </div>
                    ),
                  },
                  {
                    key: 'preview',
                    label: '👁️ Preview',
                    children: (
                      <Card size="small" style={{ marginBottom: 16, background: '#f5f5f5', minHeight: 100 }}>
                        {reviewComment.trim() ? (
                          <MarkdownRenderer content={reviewComment} variant="small" />
                        ) : (
                          <p style={{ color: '#999', fontStyle: 'italic' }}>
                            No content to preview...
                          </p>
                        )}
                      </Card>
                    ),
                  },
                ]}
              />
              <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                <Button onClick={handleAddComment} loading={addingComment} disabled={!reviewComment.trim()}>
                  Add Comment
                </Button>
                {showApproveRequest && (
                  <Button danger onClick={handleRequestChanges} loading={requesting}>
                    Request Changes
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
};

export default PeerReviewPanel;
