import React, { useState } from 'react';
import { gql } from '@apollo/client';
import { useQuery } from '@apollo/client/react';
import { Modal, Spin, Empty, Collapse, Tag, message } from 'antd';
import { MarkdownRenderer } from './MarkdownRenderer';

// TypeScript interfaces
interface ArchivedPainPoint {
  id: string;
  subject: string;
  description: string;
  priority: string;
  status: string;
  authorName: string;
  author: {
    id: string;
    username: string;
  };
  createdAt: string;
  resolvedAt: string;
  resolvedByName: string;
  resolutionNotes: string | null;
}

interface GetArchivedPainPointsData {
  allPainPoints: ArchivedPainPoint[];
}

// GraphQL Query
const GET_ARCHIVED_PAIN_POINTS = gql`
  query GetArchivedPainPoints($limit: Int, $offset: Int) {
    allPainPoints(
      limit: $limit
      offset: $offset
      includeArchived: true
      status: "ARCHIVED"
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
      resolvedAt
      resolvedByName
      resolutionNotes
    }
  }
`;

interface PainArchiveModalProps {
  visible: boolean;
  onClose: () => void;
}

export const PainArchiveModal: React.FC<PainArchiveModalProps> = ({
  visible,
  onClose,
}) => {
  const { data, loading, error } = useQuery<GetArchivedPainPointsData>(GET_ARCHIVED_PAIN_POINTS, {
    variables: {
      limit: 100,
      offset: 0,
    },
    skip: !visible, // Only fetch when modal is open
  });

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

  const archivedPains = data?.allPainPoints || [];

  const items = archivedPains.map((pain) => ({
    key: pain.id,
    label: (
      <div className="archive-item-label">
        <span className="archive-subject">{pain.subject}</span>
        <Tag color={getPriorityColor(pain.priority)}>{pain.priority}</Tag>
      </div>
    ),
    children: (
      <div className="archive-item-detail">
        <p><strong>Description:</strong></p>
        <MarkdownRenderer content={pain.description} variant="small" skipEmpty={false} />
        <p>
          <strong>Author:</strong> {pain.authorName}
        </p>
        <p>
          <strong>Created:</strong> {new Date(pain.createdAt).toLocaleDateString()}
        </p>
        <p>
          <strong>Resolved:</strong> {new Date(pain.resolvedAt).toLocaleDateString()}
        </p>
        <p>
          <strong>Resolved by:</strong> {pain.resolvedByName}
        </p>
        {pain.resolutionNotes && (
          <div>
            <strong>Resolution Notes:</strong>
            <MarkdownRenderer content={pain.resolutionNotes} variant="small" skipEmpty={false} />
          </div>
        )}
      </div>
    ),
  }));

  return (
    <Modal
      title="📦 Pain Points Archive"
      open={visible}
      onCancel={onClose}
      width={800}
      footer={null}
      className="pain-archive-modal pain-theme-modal"
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: '50px' }}>
          <Spin size="large" tip="Loading archive..." />
        </div>
      ) : error ? (
        <div style={{ color: 'red', padding: '20px' }}>
          <p>Error loading archive: {error.message}</p>
        </div>
      ) : archivedPains.length === 0 ? (
        <Empty description="No archived pain points yet" />
      ) : (
        <div className="archive-container">
          <p className="archive-info">
            Total Archived: <strong>{archivedPains.length}</strong>
          </p>
          <Collapse items={items} accordion />
        </div>
      )}
    </Modal>
  );
};

export default PainArchiveModal;
