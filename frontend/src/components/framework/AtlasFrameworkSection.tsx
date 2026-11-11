import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { gql, useMutation, useQuery } from '@apollo/client';
import { Alert, Button, Card, Collapse, Form, Input, Select, Space, Table, Tag, Typography, message } from 'antd';
import { CheckCircleOutlined, ClockCircleOutlined, CloseCircleOutlined, SyncOutlined } from '@ant-design/icons';

const { Text } = Typography;
const { Panel } = Collapse;

export const DEFAULT_ATLAS_REPO = 'https://github.com/mitre-atlas/atlas-data';
export const DEFAULT_ATLAS_REF = 'main';

const LATEST_ATLAS_REVISION_QUERY = gql`
  query LatestAvailableAtlasRevision($sourceRepo: String, $ref: String) {
    latestAvailableAtlasRevision(sourceRepo: $sourceRepo, ref: $ref)
  }
`;

const ATLAS_COVERAGE_SUMMARY_QUERY = gql`
  query AtlasCoverageSummary {
    atlasCoverageSummary {
      totalTactics
      totalTechniques
      totalMitigations
      totalCaseStudies
      totalRelationships
    }
  }
`;

const ATLAS_IMPORT_JOBS_QUERY = gql`
  query AtlasImportJobs($limit: Int) {
    atlasImportJobs(limit: $limit) {
      id
      sourceRepo
      sourceRef
      mode
      status
      summary
      log
      error
      createdAt
      startedAt
      finishedAt
      durationSeconds
      triggeredBy {
        username
      }
    }
  }
`;

const ATLAS_IMPORT_JOB_QUERY = gql`
  query AtlasImportJob($id: UUID!) {
    atlasImportJob(id: $id) {
      id
      sourceRepo
      sourceRef
      mode
      status
      summary
      log
      error
      createdAt
      startedAt
      finishedAt
      durationSeconds
      triggeredBy {
        username
      }
    }
  }
`;

const RUN_ATLAS_IMPORT_MUTATION = gql`
  mutation RunAtlasImport($sourceRepo: String, $ref: String, $mode: String) {
    runAtlasImport(sourceRepo: $sourceRepo, ref: $ref, mode: $mode) {
      job {
        id
        sourceRepo
        sourceRef
        mode
        status
        createdAt
      }
    }
  }
`;

function statusTag(status: string) {
  switch (status) {
    case 'RUNNING':
      return <Tag icon={<SyncOutlined spin />} color="processing">RUNNING</Tag>;
    case 'SUCCESS':
      return <Tag icon={<CheckCircleOutlined />} color="success">SUCCESS</Tag>;
    case 'FAILED':
      return <Tag icon={<CloseCircleOutlined />} color="error">FAILED</Tag>;
    default:
      return <Tag icon={<ClockCircleOutlined />} color="default">PENDING</Tag>;
  }
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '–';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function shortSha(sha: string | null | undefined): string {
  if (!sha) return '–';
  return sha.length > 12 ? sha.slice(0, 12) : sha;
}

interface AtlasJobRecord {
  id: string;
  sourceRepo: string;
  sourceRef: string;
  mode: string;
  status: string;
  summary: Record<string, unknown> | null;
  log: string;
  error: string;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  durationSeconds: number | null;
  triggeredBy: { username: string } | null;
}

function RunningAtlasJobPoller({
  jobId,
  onComplete,
}: {
  jobId: string;
  onComplete: (job: { id: string; sourceRef: string; status: string; error: string }) => void;
}) {
  const { data, startPolling, stopPolling } = useQuery(ATLAS_IMPORT_JOB_QUERY, {
    variables: { id: jobId },
    fetchPolicy: 'network-only',
  });

  useEffect(() => {
    startPolling(3000);
    return () => stopPolling();
  }, [startPolling, stopPolling]);

  const job: AtlasJobRecord | null = data?.atlasImportJob ?? null;

  useEffect(() => {
    if (job && job.status !== 'PENDING' && job.status !== 'RUNNING') {
      stopPolling();
      onComplete(job);
    }
  }, [job, stopPolling, onComplete]);

  if (!job) return null;

  return (
    <Alert
      type="info"
      icon={<SyncOutlined spin />}
      showIcon
      message={`ATLAS import (${job.sourceRef}) running…`}
      description="Polling every 3 s. This usually finishes quickly."
      style={{ marginBottom: 16 }}
    />
  );
}

export const AtlasFrameworkSection: React.FC<{ canManage: boolean }> = ({ canManage }) => {
  const [messageApi, contextHolder] = message.useMessage();
  const [form] = Form.useForm();
  const [pollingJobId, setPollingJobId] = useState<string | null>(null);

  const { data: latestData, refetch: refetchLatest } = useQuery(LATEST_ATLAS_REVISION_QUERY, {
    variables: { sourceRepo: DEFAULT_ATLAS_REPO, ref: DEFAULT_ATLAS_REF },
    fetchPolicy: 'network-only',
  });

  const { data: coverageData, refetch: refetchCoverage } = useQuery(ATLAS_COVERAGE_SUMMARY_QUERY, {
    fetchPolicy: 'network-only',
  });

  const { data: jobsData, refetch: refetchJobs } = useQuery(ATLAS_IMPORT_JOBS_QUERY, {
    variables: { limit: 10 },
    fetchPolicy: 'network-only',
  });

  const [runImport, { loading: importing }] = useMutation(RUN_ATLAS_IMPORT_MUTATION);

  const handleSubmit = useCallback(async (values: { sourceRepo?: string; ref?: string; mode?: string }) => {
    try {
      const result = await runImport({
        variables: {
          sourceRepo: values.sourceRepo || DEFAULT_ATLAS_REPO,
          ref: values.ref || DEFAULT_ATLAS_REF,
          mode: values.mode || 'REMOTE',
        },
      });

      const job = result.data?.runAtlasImport?.job;
      if (job?.id) {
        setPollingJobId(job.id);
        messageApi.success(`ATLAS import queued for ${job.sourceRef || DEFAULT_ATLAS_REF}.`);
      }
    } catch (err: any) {
      messageApi.error(err?.message || 'Failed to queue ATLAS import.');
    }
  }, [messageApi, runImport]);

  const handleJobComplete = useCallback((job: { id: string; sourceRef: string; status: string; error: string }) => {
    setPollingJobId(null);
    refetchJobs();
    refetchCoverage();
    refetchLatest();

    if (job.status === 'SUCCESS') {
      messageApi.success(`ATLAS import for ${job.sourceRef} succeeded.`);
    } else {
      messageApi.error(job.error || `ATLAS import for ${job.sourceRef} failed.`);
    }
  }, [messageApi, refetchCoverage, refetchJobs, refetchLatest]);

  const latestRevision = latestData?.latestAvailableAtlasRevision ?? null;
  const summary = coverageData?.atlasCoverageSummary ?? null;
  const jobs: AtlasJobRecord[] = jobsData?.atlasImportJobs ?? [];

  const summaryItems = useMemo(() => [
    { label: 'Tactics', value: summary?.totalTactics ?? 0 },
    { label: 'Techniques', value: summary?.totalTechniques ?? 0 },
    { label: 'Mitigations', value: summary?.totalMitigations ?? 0 },
    { label: 'Case studies', value: summary?.totalCaseStudies ?? 0 },
    { label: 'Relationships', value: summary?.totalRelationships ?? 0 },
  ], [summary]);

  const columns = [
    {
      title: 'Ref',
      key: 'sourceRef',
      render: (_: any, record: AtlasJobRecord) => (
        <Space direction="vertical" size={0}>
          <Text>{record.sourceRef}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>{record.mode}</Text>
        </Space>
      ),
    },
    { title: 'Status', dataIndex: 'status', key: 'status', render: statusTag },
    {
      title: 'Triggered by',
      key: 'triggeredBy',
      render: (_: any, record: AtlasJobRecord) => record.triggeredBy?.username ?? '–',
    },
    {
      title: 'Started',
      dataIndex: 'createdAt',
      key: 'createdAt',
      render: (value: string) => (value ? new Date(value).toLocaleString() : '–'),
    },
    {
      title: 'Duration',
      dataIndex: 'durationSeconds',
      key: 'duration',
      render: formatDuration,
    },
    {
      title: 'Log',
      key: 'log',
      render: (_: any, record: AtlasJobRecord) => (
        <div className="framework-updates-cell-content">
          <Collapse ghost>
            <Panel header="Show last 20 lines" key="log">
              <pre className="framework-updates-pre framework-updates-pre--log">
                {record.log ? record.log.split('\n').slice(-20).join('\n') : '(empty)'}
              </pre>
              {record.error && (
                <pre className="framework-updates-pre framework-updates-pre--error">
                  {record.error.split('\n').slice(-10).join('\n')}
                </pre>
              )}
            </Panel>
          </Collapse>
        </div>
      ),
    },
  ];

  return (
    <Card title="MITRE ATLAS" style={{ marginBottom: 24 }}>
      {contextHolder}

      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Space direction="vertical" size={2}>
          <Text>
            <Text strong>Source repo:</Text> {DEFAULT_ATLAS_REPO}
          </Text>
          <Text>
            <Text strong>Latest upstream revision:</Text> {shortSha(latestRevision)}
          </Text>
        </Space>

        {summary && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 12 }}>
            {summaryItems.map((item) => (
              <Card key={item.label} size="small" style={{ textAlign: 'center' }}>
                <Text type="secondary" style={{ display: 'block', fontSize: 12 }}>{item.label}</Text>
                <Text strong style={{ fontSize: 24 }}>{item.value}</Text>
              </Card>
            ))}
          </div>
        )}

        {pollingJobId && (
          <RunningAtlasJobPoller jobId={pollingJobId} onComplete={handleJobComplete} />
        )}

        <Form
          form={form}
          layout="inline"
          initialValues={{ mode: 'REMOTE', sourceRepo: DEFAULT_ATLAS_REPO, ref: DEFAULT_ATLAS_REF }}
          onFinish={handleSubmit}
          style={{ gap: 8 }}
          disabled={!canManage}
        >
          <Form.Item name="sourceRepo" label="Repo" style={{ minWidth: 320 }}>
            <Input />
          </Form.Item>
          <Form.Item name="ref" label="Ref" style={{ minWidth: 120 }}>
            <Input />
          </Form.Item>
          <Form.Item name="mode" label="Mode">
            <Select style={{ width: 120 }}>
              <Select.Option value="REMOTE">Remote</Select.Option>
              <Select.Option value="LOCAL">Local</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              icon={<SyncOutlined />}
              loading={importing || !!pollingJobId}
              disabled={!canManage || !!pollingJobId}
            >
              Run ATLAS Update
            </Button>
          </Form.Item>
        </Form>

        <Table
          dataSource={jobs}
          columns={columns}
          rowKey="id"
          size="small"
          pagination={false}
          locale={{ emptyText: 'No ATLAS import jobs yet.' }}
          className="framework-updates-table"
          tableLayout="fixed"
        />
      </Space>
    </Card>
  );
};
