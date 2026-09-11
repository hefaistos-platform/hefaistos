import React from 'react';
import { Tag, Card } from 'antd';
import { MessageOutlined } from '@ant-design/icons';
import { markdownToPlainText } from './MarkdownRenderer';
import '../styles/PainPointCard.css';

interface PainPointCardProps {
  pain: any;
  onDetails: () => void;
  priorityColor: string;
}

export const PainPointCard: React.FC<PainPointCardProps> = ({
  pain,
  onDetails,
  priorityColor,
}) => {
  const descriptionPreview = markdownToPlainText(pain.description || '');

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'OPEN':
        return '🔴';
      case 'IN_PROGRESS':
        return '🟡';
      case 'SOLVED':
        return '✅';
      case 'CLOSED':
        return '❌';
      default:
        return '⚪';
    }
  };

  return (
    <Card
      className="pain-point-card"
      onClick={onDetails}
      style={{
        borderLeft: `4px solid ${priorityColor}`,
        cursor: 'pointer',
        transition: 'all 0.3s ease',
      }}
      hoverable
    >
      <div className="card-header">
        <div className="card-title">
          <span className="status-icon">{getStatusIcon(pain.status)}</span>
          <h3>{pain.subject}</h3>
        </div>
        <Tag color={priorityColor}>{pain.priority}</Tag>
      </div>

      <p className="card-description">{descriptionPreview.length > 100 ? `${descriptionPreview.substring(0, 100)}...` : descriptionPreview}</p>

      <div className="card-footer">
        <span className="author">by {pain.authorName}</span>
        <div className="card-meta">
          {pain.comments && pain.comments.length > 0 && (
            <span className="comments-badge">
              <MessageOutlined /> {pain.comments.length}
            </span>
          )}
          <span className="date">
            {new Date(pain.createdAt).toLocaleDateString()}
          </span>
        </div>
      </div>
    </Card>
  );
};

export default PainPointCard;
