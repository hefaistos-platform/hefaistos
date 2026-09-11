import React, { useState, useEffect } from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { Button } from '../components/ui/Button';
import { PixelIcon } from '../components/ui/PixelIcon';
import { Modal, Input, Select, Tag, Empty, Spin, message, Tooltip } from 'antd';
import { NewPainPointModal } from '../components/NewPainPointModal';
import { PainPointCard } from '../components/PainPointCard';
import { PainArchiveModal } from '../components/PainArchiveModal';
import { MarkdownRenderer } from '../components/MarkdownRenderer';
import '../styles/PainPointsPage.css';

const { TextArea } = Input;

// TypeScript interfaces
interface PainPointComment {
  id: string;
  content: string;
  author: {
    username: string;
  };
  authorName: string;
  parentComment: PainPointComment | null;
  replies: PainPointComment[];
  isResponseToQuestion: boolean;
  isRootComment: boolean;
  replyCount: number;
  createdAt: string;
  updatedAt: string;
}

interface PainPointAuthor {
  id: string;
  username: string;
}

interface PainPoint {
  id: string;
  subject: string;
  description: string;
  priority: string;
  status: string;
  authorName: string;
  author: PainPointAuthor;
  createdAt: string;
  updatedAt: string;
  resolvedAt: string | null;
  resolvedByName: string | null;
  resolutionNotes: string | null;
  isSolved: boolean;
  comments: PainPointComment[];
}

interface GetAllPainPointsData {
  allPainPoints: PainPoint[];
}

interface GetOpenPainPointsCountData {
  openPainPointsCount: number;
}

interface ResolvePainPointData {
  resolvePainPoint: {
    painPoint: PainPoint | null;
    success: boolean;
    message: string;
  };
}

interface ArchivePainPointData {
  archivePainPoint: {
    painPoint: { id: string; status: string } | null;
    success: boolean;
    message: string;
  };
}

// GraphQL Queries
const GET_ALL_PAIN_POINTS = gql`
  query GetAllPainPoints($limit: Int, $offset: Int, $status: String, $priority: String, $includeArchived: Boolean) {
    allPainPoints(
      limit: $limit
      offset: $offset
      status: $status
      priority: $priority
      includeArchived: $includeArchived
    ) {
      id
      subject
      description
      priority
      status
      authorName
      author {
        id
        username
      }
      createdAt
      updatedAt
      resolvedAt
      resolvedByName
      resolutionNotes
      isSolved
      comments {
        id
        content
        authorName
        author {
          username
        }
        parentComment {
          id
        }
        replies {
          id
          content
          authorName
          author {
            username
          }
          isResponseToQuestion
          createdAt
          updatedAt
        }
        isResponseToQuestion
        isRootComment
        replyCount
        createdAt
        updatedAt
      }
    }
  }
`;

const GET_OPEN_PAIN_POINTS_COUNT = gql`
  query GetOpenPainPointsCount {
    openPainPointsCount
  }
`;

const GET_ME_QUERY = gql`
  query GetMe {
    me {
      role
      isSuperuser
      isStaff
    }
  }
`;

// GraphQL Mutations
const RESOLVE_PAIN_POINT_MUTATION = gql`
  mutation ResolvePainPoint($painPointId: UUID!, $status: String!, $resolutionNotes: String) {
    resolvePainPoint(painPointId: $painPointId, status: $status, resolutionNotes: $resolutionNotes) {
      painPoint {
        id
        subject
        status
        resolvedAt
        resolvedByName
        resolutionNotes
      }
      success
      message
    }
  }
`;

const ARCHIVE_PAIN_POINT_MUTATION = gql`
  mutation ArchivePainPoint($painPointId: UUID!) {
    archivePainPoint(painPointId: $painPointId) {
      painPoint {
        id
        status
      }
      success
      message
    }
  }
`;

const ADD_PAIN_POINT_COMMENT_MUTATION = gql`
  mutation AddPainPointComment($painPointId: UUID!, $content: String!, $parentCommentId: UUID, $isResponseToQuestion: Boolean) {
    addPainPointComment(
      painPointId: $painPointId
      content: $content
      parentCommentId: $parentCommentId
      isResponseToQuestion: $isResponseToQuestion
    ) {
      comment {
        id
        content
        authorName
        author {
          username
        }
        parentComment {
          id
        }
        isResponseToQuestion
        isRootComment
        replyCount
        createdAt
        updatedAt
      }
      success
      message
    }
  }
`;

const PainPointsPage = () => {
  const [showNewModal, setShowNewModal] = useState(false);
  const [showArchiveModal, setShowArchiveModal] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string | null>(null);
  const [filterPriority, setFilterPriority] = useState<string | null>(null);
  const [selectedPain, setSelectedPain] = useState<PainPoint | null>(null);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [resolutionNotes, setResolutionNotes] = useState('');
  const [newComment, setNewComment] = useState('');
  const [replyingTo, setReplyingTo] = useState<string | null>(null);
  const [isResponseToQuestion, setIsResponseToQuestion] = useState(false);

  const { data, loading, error, refetch } = useQuery<GetAllPainPointsData>(GET_ALL_PAIN_POINTS, {
    variables: {
      limit: 50,
      offset: 0,
      status: filterStatus,
      priority: filterPriority,
      includeArchived: false,
    },
  });

  const { data: countData } = useQuery<GetOpenPainPointsCountData>(GET_OPEN_PAIN_POINTS_COUNT);
  const { data: meData } = useQuery<{ me: { role: string; isSuperuser: boolean; isStaff: boolean } }>(GET_ME_QUERY, { fetchPolicy: 'cache-first' });
  const userRole = (meData?.me?.role || '').toUpperCase();
  const isElOne = userRole === 'ELONE';
  const canResolve = meData?.me?.isSuperuser || meData?.me?.isStaff || false;

  const [resolvePainPoint] = useMutation<ResolvePainPointData>(RESOLVE_PAIN_POINT_MUTATION, {
    onCompleted: (data) => {
      if (data.resolvePainPoint.success) {
        message.success(data.resolvePainPoint.message);
        refetch();
        setShowDetailsModal(false);
      } else {
        message.error(data.resolvePainPoint.message);
      }
    },
    onError: (err) => {
      message.error('Error resolving pain point');
    },
  });

  const [archivePainPoint] = useMutation<ArchivePainPointData>(ARCHIVE_PAIN_POINT_MUTATION, {
    onCompleted: (data) => {
      if (data.archivePainPoint.success) {
        message.success('Pain point archived');
        refetch();
      } else {
        message.error(data.archivePainPoint.message);
      }
    },
    onError: () => {
      message.error('Error archiving pain point');
    },
  });

  const [addComment] = useMutation(ADD_PAIN_POINT_COMMENT_MUTATION, {
    onCompleted: (data) => {
      if (data.addPainPointComment.success) {
        message.success(data.addPainPointComment.message);
        setNewComment('');
        setReplyingTo(null);
        setIsResponseToQuestion(false);
        refetch();
      } else {
        message.error(data.addPainPointComment.message);
      }
    },
    onError: () => {
      message.error('Error adding comment');
    },
  });

  const handleResolvePain = (status: string) => {
    if (!selectedPain) return;

    resolvePainPoint({
      variables: {
        painPointId: selectedPain.id,
        status: status,
        resolutionNotes: resolutionNotes,
      },
    });
  };

  const handleArchivePain = (painId: string) => {
    archivePainPoint({
      variables: {
        painPointId: painId,
      },
    });
  };

  const handleAddComment = () => {
    if (!selectedPain || !newComment.trim()) {
      message.warning('Please enter a comment');
      return;
    }

    addComment({
      variables: {
        painPointId: selectedPain.id,
        content: newComment.trim(),
        parentCommentId: replyingTo || undefined,
        isResponseToQuestion: isResponseToQuestion || undefined,
      },
    });
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'HIGH':
        return '#ff4d4f';
      case 'MEDIUM':
        return '#faad14';
      case 'LOW':
        return '#52c41a';
      default:
        return '#1890ff';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'OPEN':
        return '#1890ff';
      case 'IN_PROGRESS':
        return '#faad14';
      case 'SOLVED':
        return '#52c41a';
      case 'CLOSED':
        return '#ff7875';
      default:
        return '#666';
    }
  };

  if (error) {
    return (
      <div className="pain-points-page error-container">
        <h2>Error loading pain points</h2>
        <p>{error.message}</p>
        <Button onClick={() => refetch()}>Retry</Button>
      </div>
    );
  }

  const painPoints = data?.allPainPoints || [];

  return (
    <div className="pain-points-page">
      <div className="pain-points-header">
        <div className="header-content">
          <div className="header-title">
            <h1>Pain Points Board 📋</h1>
            <Tooltip title="Share your PAIN: Problems, ideas, And Issues you've Noted! Admins will carefully examine and resolve them.">
              <PixelIcon name="help-circle" className="help-icon" />
            </Tooltip>
          </div>
          <p className="header-subtitle">
            Share your problems, ideas, and complaints. Help us improve the platform!
          </p>
        </div>
        <div className="open-count-badge">
          <span className="count">{countData?.openPainPointsCount || 0}</span>
          <span className="label">Open Issues</span>
        </div>
      </div>

      <div className="pain-points-controls">
        {!isElOne && (
          <Button
            className="btn-new-pain"
            onClick={() => setShowNewModal(true)}
          >
            <span>+ NEW PAIN</span>
          </Button>
        )}
        
        <div className="filters">
          <Select
            placeholder="Filter by Status"
            allowClear
            style={{ width: 150 }}
            onChange={setFilterStatus}
            options={[
              { label: 'Open', value: 'OPEN' },
              { label: 'In Progress', value: 'IN_PROGRESS' },
              { label: 'Solved', value: 'SOLVED' },
              { label: 'Closed', value: 'CLOSED' },
            ]}
          />
          
          <Select
            placeholder="Filter by Priority"
            allowClear
            style={{ width: 150 }}
            onChange={setFilterPriority}
            options={[
              { label: 'Low', value: 'LOW' },
              { label: 'Medium', value: 'MEDIUM' },
              { label: 'High', value: 'HIGH' },
            ]}
          />

          <Button onClick={() => setShowArchiveModal(true)}>
            📦 Show Archive
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="loading-container">
          <Spin size="large" tip="Loading pain points..." />
        </div>
      ) : painPoints.length === 0 ? (
        <Empty
          description="No pain points yet"
          style={{ marginTop: '50px' }}
        />
      ) : (
        <div className="pain-points-board">
          {painPoints.map((pain) => (
            <PainPointCard
              key={pain.id}
              pain={pain}
              onDetails={() => {
                setSelectedPain(pain);
                setShowDetailsModal(true);
              }}
              priorityColor={getPriorityColor(pain.priority)}
            />
          ))}
        </div>
      )}

      {/* New Pain Modal */}
      {!isElOne && (
        <NewPainPointModal
          visible={showNewModal}
          onClose={() => setShowNewModal(false)}
          onSuccess={() => {
            setShowNewModal(false);
            refetch();
          }}
        />
      )}

      {/* Details/Resolution Modal */}
      {selectedPain && (
        <Modal
          title={`Pain Point Details: ${selectedPain.subject}`}
          open={showDetailsModal}
          onCancel={() => setShowDetailsModal(false)}
          width={700}
          footer={null}
          className="pain-details-modal pain-theme-modal"
        >
          <div className="pain-details-content">
            <div className="details-section">
              <h4>Description</h4>
              <MarkdownRenderer content={selectedPain.description} variant="small" skipEmpty={false} />
            </div>

            <div className="details-section meta-info">
              <div className="meta-item">
                <strong>Author:</strong> {selectedPain.authorName}
              </div>
              <div className="meta-item">
                <strong>Priority:</strong>
                <Tag color={getPriorityColor(selectedPain.priority)}>
                  {selectedPain.priority}
                </Tag>
              </div>
              <div className="meta-item">
                <strong>Status:</strong>
                <Tag color={getStatusColor(selectedPain.status)}>
                  {selectedPain.status}
                </Tag>
              </div>
              <div className="meta-item">
                <strong>Created:</strong> {new Date(selectedPain.createdAt).toLocaleDateString()}
              </div>
            </div>

            {selectedPain.comments && selectedPain.comments.length > 0 && (
              <div className="details-section">
                <h4>Discussion Thread</h4>
                <div className="comments-list threaded-comments">
                  {selectedPain.comments && selectedPain.comments
                    .filter(comment => comment.isRootComment)
                    .map((comment) => (
                      <div key={comment.id} className="comment-thread">
                        <div className="comment root-comment">
                          <div className="comment-header">
                            <strong>{comment.authorName}</strong>
                            <span className="comment-date">
                              {new Date(comment.createdAt).toLocaleDateString()}
                            </span>
                            {comment.author.username === 'admin' || comment.author.username === 'superuser' ? (
                              <Tag color="blue">Admin</Tag>
                            ) : null}
                          </div>
                          <MarkdownRenderer content={comment.content} variant="small" skipEmpty={false} />
                          <div className="comment-actions">
                            {!isElOne && (
                              <Button
                                onClick={() => setReplyingTo(comment.id)}
                                style={{ color: 'var(--hef-text-link)', padding: '0', fontSize: '13px', background: 'none', border: 'none', cursor: 'pointer' }}
                              >
                                💬 Reply
                              </Button>
                            )}
                            {comment.replyCount > 0 && (
                              <span className="reply-count">{comment.replyCount} {comment.replyCount === 1 ? 'reply' : 'replies'}</span>
                            )}
                          </div>
                        </div>

                        {/* Nested replies */}
                        {comment.replies && comment.replies.length > 0 && (
                          <div className="replies">
                            {comment.replies.map((reply) => (
                              <div key={reply.id} className="comment reply-comment">
                                <div className="comment-header">
                                  <strong>{reply.authorName}</strong>
                                  <span className="comment-date">
                                    {new Date(reply.createdAt).toLocaleDateString()}
                                  </span>
                                  {reply.isResponseToQuestion ? (
                                    <Tag color="green">Response</Tag>
                                  ) : null}
                                </div>
                                <MarkdownRenderer content={reply.content} variant="small" skipEmpty={false} />
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  {!selectedPain.comments || selectedPain.comments.filter(c => c.isRootComment).length === 0 && (
                    <p className="no-comments">No discussion yet. Be the first to comment!</p>
                  )}
                </div>
              </div>
            )}

            {!selectedPain.isSolved && !isElOne && (
              <div className="new-comment-section">
                <h4>Add Comment</h4>
                {replyingTo && (
                  <div className="reply-info">
                    <span>Replying to a comment</span>
                    <Button onClick={() => setReplyingTo(null)} style={{ color: 'var(--hef-text-link)', padding: '0', fontSize: '12px', background: 'none', border: 'none', cursor: 'pointer' }}>Clear</Button>
                  </div>
                )}
                <TextArea
                  placeholder="Share your thoughts, ask for clarification, or provide an update..."
                  value={newComment}
                  onChange={(e) => setNewComment(e.target.value)}
                  rows={3}
                  maxLength={1000}
                />
                <div className="comment-options">
                  {replyingTo && (
                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <input
                        type="checkbox"
                        checked={isResponseToQuestion}
                        onChange={(e) => setIsResponseToQuestion(e.target.checked)}
                      />
                      <span>This is a response to an admin question</span>
                    </label>
                  )}
                </div>
                <Button
                  variant="primary"
                  onClick={handleAddComment}
                  disabled={!newComment.trim()}
                >
                  {replyingTo ? '↩️ Send Reply' : '💬 Add Comment'}
                </Button>
              </div>
            )}

            {!selectedPain.isSolved && canResolve && (
              <div className="resolution-section">
                <h4>Admin Resolution</h4>
                <TextArea
                  placeholder="Add resolution notes..."
                  value={resolutionNotes}
                  onChange={(e) => setResolutionNotes(e.target.value)}
                  rows={3}
                />
                <div className="resolution-buttons">
                  <Button
                    variant="primary"
                    onClick={() => handleResolvePain('SOLVED')}
                  >
                    ✅ Mark as Solved
                  </Button>
                  <Button
                    onClick={() => handleResolvePain('CLOSED')}
                  >
                    ❌ Mark as Closed
                  </Button>
                </div>
              </div>
            )}

            {selectedPain.isSolved && (
              <div className="resolved-info">
                <h4>Resolution Info</h4>
                <p><strong>Resolved by:</strong> {selectedPain.resolvedByName}</p>
                <p><strong>Resolved at:</strong> {selectedPain.resolvedAt ? new Date(selectedPain.resolvedAt).toLocaleDateString() : 'N/A'}</p>
                {selectedPain.resolutionNotes && (
                  <div>
                    <strong>Notes:</strong>
                    <MarkdownRenderer content={selectedPain.resolutionNotes} variant="small" skipEmpty={false} />
                  </div>
                )}
                {canResolve && (
                <Button
                  onClick={() => handleArchivePain(selectedPain.id)}
                  className="archive-btn"
                >
                  📦 Archive This Pain
                </Button>
                )}
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* Archive Modal */}
      <PainArchiveModal
        visible={showArchiveModal}
        onClose={() => setShowArchiveModal(false)}
      />
    </div>
  );
};

export default PainPointsPage;
