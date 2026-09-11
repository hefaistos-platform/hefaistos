import React, { useMemo, useState } from 'react';
import { gql } from '@apollo/client';
import { useQuery } from '@apollo/client/react';
import { Button, Card, Input, Modal, Space, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { MarkdownRenderer } from '../components/MarkdownRenderer';

const GET_L1_PORTAL_ENTRIES = gql`
  query GetL1PortalEntries($search: String, $limit: Int, $offset: Int) {
    l1PortalEntries(search: $search, limit: $limit, offset: $offset) {
      id
      title
      urlToken
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

interface L1PortalRow {
  id: string;
  title: string;
  urlToken: string;
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
}

interface L1PortalEntriesData {
  l1PortalEntries: L1PortalRow[];
}

export const L1PortalPage: React.FC = () => {
  const [searchText, setSearchText] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [selectedEntry, setSelectedEntry] = useState<L1PortalRow | null>(null);

  const { data, loading, refetch } = useQuery<L1PortalEntriesData>(GET_L1_PORTAL_ENTRIES, {
    variables: { search: appliedSearch || undefined, limit: 200, offset: 0 },
    fetchPolicy: 'network-only',
    nextFetchPolicy: 'cache-first',
  });

  const rows = data?.l1PortalEntries || [];

  const columns: ColumnsType<L1PortalRow> = useMemo(
    () => [
      {
        title: 'Title',
        dataIndex: 'title',
        key: 'title',
        render: (_: unknown, row: L1PortalRow) => (
          <Space direction="vertical" size={2}>
            <Typography.Link onClick={() => setSelectedEntry(row)}>
              {row.title}
            </Typography.Link>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {(row.responsePlaybook || row.knownFalsePositives || row.blindSpotsCoverageGaps || '').slice(0, 120) || 'No content'}
              {(row.responsePlaybook || row.knownFalsePositives || row.blindSpotsCoverageGaps || '').length > 120 ? '…' : ''}
            </Typography.Text>
          </Space>
        ),
      },
      {
        title: 'Workbench',
        key: 'sourceGraph',
        render: (_: unknown, row: L1PortalRow) => (
          <Space direction="vertical" size={0}>
            <Typography.Text>{row.sourceGraph?.title || 'N/A'}</Typography.Text>
            <Tag color="green">{row.sourceGraph?.status || 'UNKNOWN'}</Tag>
          </Space>
        ),
      },
      {
        title: 'Updated',
        dataIndex: 'updatedAt',
        key: 'updatedAt',
        width: 210,
        render: (dt: string) => new Date(dt).toLocaleString(),
      },
      {
        title: 'Actions',
        key: 'actions',
        width: 210,
        render: (_: unknown, row: L1PortalRow) => (
          <Space>
            <Button size="small" onClick={() => setSelectedEntry(row)}>
              Open
            </Button>
            <Button
              size="small"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(row.shareUrl);
                  message.success('Share URL copied');
                } catch {
                  message.error('Failed to copy share URL');
                }
              }}
            >
              Copy URL
            </Button>
          </Space>
        ),
      },
    ],
    [setSelectedEntry]
  );

  return (
    <div className="l1-portal-theme" style={{ padding: '0 24px' }}>
      <Card
        title={<Typography.Title level={3} style={{ margin: 0 }}>L1 Portal</Typography.Title>}
        extra={
          <Space>
            <Input.Search
              allowClear
              placeholder="Search title, response playbook, false positives, blind spots…"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              onSearch={(value) => setAppliedSearch((value || '').trim())}
              style={{ width: 420 }}
            />
            <Button onClick={() => refetch()}>Refresh</Button>
          </Space>
        }
      >
        <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
          Read-only playbook snapshots generated from deployed Workbenches in your organization only. Search matches title and content fields.
        </Typography.Paragraph>
        <Table<L1PortalRow>
          rowKey="id"
          columns={columns}
          dataSource={rows}
          loading={loading}
          pagination={{ pageSize: 20 }}
        />
      </Card>

      <Modal
        title={selectedEntry?.title || 'L1 Portal Detail'}
        open={!!selectedEntry}
        onCancel={() => setSelectedEntry(null)}
        width={1050}
        className="l1-portal-modal"
        footer={
          <Space>
            <Button onClick={() => setSelectedEntry(null)}>Close</Button>
            <Button
              type="primary"
              onClick={async () => {
                if (!selectedEntry) return;
                try {
                  await navigator.clipboard.writeText(selectedEntry.shareUrl);
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
        {selectedEntry && (
          <>
            <Space direction="vertical" size={4} style={{ marginBottom: 16 }}>
              <Typography.Text type="secondary">
                Source Workbench: {selectedEntry.sourceGraph?.title || 'N/A'}
              </Typography.Text>
              <Typography.Text type="secondary">
                Last Updated: {new Date(selectedEntry.updatedAt).toLocaleString()}
              </Typography.Text>
              <Typography.Text type="secondary">
                Share URL: {selectedEntry.shareUrl}
              </Typography.Text>
            </Space>

            <Card size="small" title="Response Playbook" style={{ marginBottom: 12 }}>
              <MarkdownRenderer content={selectedEntry.responsePlaybook || 'N/A'} variant="small" />
            </Card>

            <Card size="small" title="Known False Positives" style={{ marginBottom: 12 }}>
              <MarkdownRenderer content={selectedEntry.knownFalsePositives || 'N/A'} variant="small" />
            </Card>

            <Card size="small" title="Blind Spots & Coverage Gaps">
              <MarkdownRenderer content={selectedEntry.blindSpotsCoverageGaps || 'N/A'} variant="small" />
            </Card>
          </>
        )}
      </Modal>
    </div>
  );
};

export default L1PortalPage;
