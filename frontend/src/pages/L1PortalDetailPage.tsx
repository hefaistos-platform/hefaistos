import React from 'react';
import { gql } from '@apollo/client';
import { useQuery } from '@apollo/client/react';
import { Alert, Button, Card, Space, Typography, message } from 'antd';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { MarkdownRenderer } from '../components/MarkdownRenderer';

const GET_L1_PORTAL_ENTRY = gql`
  query GetL1PortalEntry($token: UUID!) {
    l1PortalEntryByToken(token: $token) {
      id
      title
      shareUrl
      responsePlaybook
      knownFalsePositives
      blindSpotsCoverageGaps
      updatedAt
      sourceGraph {
        id
        title
        status
      }
    }
  }
`;

interface L1PortalEntryData {
  l1PortalEntryByToken: {
    id: string;
    title: string;
    shareUrl: string;
    responsePlaybook: string;
    knownFalsePositives: string;
    blindSpotsCoverageGaps: string;
    updatedAt: string;
    sourceGraph: {
      id: string;
      title: string;
      status: string;
    } | null;
  } | null;
}

export const L1PortalDetailPage: React.FC = () => {
  const navigate = useNavigate();
  const { token } = useParams<{ token: string }>();

  const { data, loading, error } = useQuery<L1PortalEntryData>(GET_L1_PORTAL_ENTRY, {
    variables: { token },
    skip: !token,
    fetchPolicy: 'network-only',
    nextFetchPolicy: 'cache-first',
  });

  const entry = data?.l1PortalEntryByToken;

  if (!token) {
    return (
      <Alert
        type="error"
        showIcon
        message="Invalid URL"
        description="Missing L1 portal token in URL."
      />
    );
  }

  if (loading) return <p>Loading L1 portal entry…</p>;

  if (error) {
    return (
      <Alert
        type="error"
        showIcon
        message="Failed to load L1 portal entry"
        description={error.message}
      />
    );
  }

  if (!entry) {
    return (
      <Alert
        type="warning"
        showIcon
        message="Entry not available"
        description="This entry was not found, is outside your organization, or the related workbench is not currently deployed."
      />
    );
  }

  return (
    <div className="l1-portal-theme" style={{ padding: '0 24px', maxWidth: 1100 }}>
      <Card
        title={<Typography.Title level={3} style={{ margin: 0 }}>{entry.title}</Typography.Title>}
        extra={
          <Space>
            <Button onClick={() => navigate('/l1-portal')}>Back to L1 Portal</Button>
            <Button
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(entry.shareUrl);
                  message.success('Share URL copied');
                } catch {
                  message.error('Failed to copy share URL');
                }
              }}
            >
              Copy URL
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" size={4} style={{ marginBottom: 16 }}>
          <Typography.Text type="secondary">
            Source Workbench:{' '}
            {entry.sourceGraph ? (
              <Link to={`/playbooks/${entry.sourceGraph.id}`}>{entry.sourceGraph.title}</Link>
            ) : (
              'N/A'
            )}
          </Typography.Text>
          <Typography.Text type="secondary">
            Last Updated: {new Date(entry.updatedAt).toLocaleString()}
          </Typography.Text>
          <Typography.Text type="secondary">
            Share URL: {entry.shareUrl}
          </Typography.Text>
        </Space>

        <Card size="small" title="Response Playbook" style={{ marginBottom: 12 }}>
          <MarkdownRenderer content={entry.responsePlaybook || 'N/A'} variant="small" />
        </Card>

        <Card size="small" title="Known False Positives" style={{ marginBottom: 12 }}>
          <MarkdownRenderer content={entry.knownFalsePositives || 'N/A'} variant="small" />
        </Card>

        <Card size="small" title="Blind Spots & Coverage Gaps">
          <MarkdownRenderer content={entry.blindSpotsCoverageGaps || 'N/A'} variant="small" />
        </Card>
      </Card>
    </div>
  );
};

export default L1PortalDetailPage;
