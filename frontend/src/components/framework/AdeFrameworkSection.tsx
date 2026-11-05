import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { gql, useMutation, useQuery } from '@apollo/client';
import { Alert, Button, Card, Collapse, Form, Input, Popconfirm, Select, Space, Table, Tag, Typography, message } from 'antd';
import { SyncOutlined } from '@ant-design/icons';

const { Text } = Typography;
const { Panel } = Collapse;

export const DEFAULT_ADE_REPO =
  'https://github.com/Adversarial-Detection-Engineering/Adversarial-Detection-Engineering-Framework';
export const DEFAULT_ADE_REF = 'main';

// ---------------------------------------------------------------------------
// GraphQL
// ---------------------------------------------------------------------------

const SNAPSHOT_FIELDS = `
  id status sourceRepo sourceRef sourceSha entryCount summary validationErrors
  createdAt activatedAt
`;

const LATEST_ADE_REVISION_QUERY = gql`
  query LatestAvailableAdeRevision($sourceRepo: String, $ref: String) {
    latestAvailableAdeRevision(sourceRepo: $sourceRepo, ref: $ref)
  }
`;

const ACTIVE_ADE_SNAPSHOT_QUERY = gql`
  query ActiveAdeSnapshot {
    activeAdeSnapshot { ${SNAPSHOT_FIELDS} }
  }
`;

const ADE_SNAPSHOTS_QUERY = gql`
  query AdeSnapshots($limit: Int, $status: String) {
    adeSnapshots(limit: $limit, status: $status) { ${SNAPSHOT_FIELDS} }
  }
`;

const ADE_IMPORT_JOBS_QUERY = gql`
  query AdeImportJobs($limit: Int) {
    adeImportJobs(limit: $limit) {
      id sourceRepo sourceRef mode status error log createdAt finishedAt durationSeconds
      snapshot { id status sourceSha }
      triggeredBy { username }
    }
  }
`;

const ADE_IMPORT_JOB_QUERY = gql`
  query AdeImportJob($id: UUID!) {
    adeImportJob(id: $id) { id sourceRef status error }
  }
`;

const STAGED_ADE_DIFF_QUERY = gql`
  query StagedAdeDiff($snapshotId: UUID!) {
    stagedAdeDiff(snapshotId: $snapshotId) {
      snapshotId activeSnapshotId added changed removed unchanged stagedCount activeCount
      changes { entryKey kind adeId title change }
    }
  }
`;

const RUN_ADE_IMPORT_MUTATION = gql`
  mutation RunAdeImport($sourceRepo: String, $ref: String, $mode: String) {
    runAdeImport(sourceRepo: $sourceRepo, ref: $ref, mode: $mode) {
      job { id status sourceRef }
    }
  }
`;

const PROMOTE_ADE_SNAPSHOT_MUTATION = gql`
  mutation PromoteAdeSnapshot($snapshotId: UUID!) {
    promoteAdeSnapshot(snapshotId: $snapshotId) { success message }
  }
`;

const ROLLBACK_ADE_SNAPSHOT_MUTATION = gql`
  mutation RollbackAdeSnapshot($snapshotId: UUID!) {
    rollbackAdeSnapshot(snapshotId: $snapshotId) { success message }
  }
`;

// ---------------------------------------------------------------------------
// Types and helpers
// ---------------------------------------------------------------------------

interface AdeSnapshotRecord {
  id: string;
  status: string;
  sourceRepo: string;
  sourceRef: string;
  sourceSha: string;
  entryCount: number;
  summary: string | Record<string, unknown> | null;
  validationErrors: string;
  createdAt: string;
  activatedAt: string | null;
}

interface AdeJobRecord {
  id: string;
  sourceRepo: string;
  sourceRef: string;
  mode: string;
  status: string;
  error: string;
  log: string;
  createdAt: string;
  finishedAt: string | null;
  durationSeconds: number | null;
  snapshot: { id: string; status: string; sourceSha: string } | null;
  triggeredBy: { username: string } | null;
}

interface AdeDiffChange {
  entryKey: string;
  kind: string;
  adeId: string;
  title: string;
  change: 'ADDED' | 'CHANGED' | 'RENAMED' | 'REMOVED';
}

export function shortSha(sha: string | null | undefined): string {
  if (!sha) return '–';
  return sha.length > 12 ? sha.slice(0, 12) : sha;
}

function snapshotTag(status: string) {
  switch (status) {
    case 'ACTIVE':
      return <Tag color="success">ACTIVE</Tag>;
    case 'STAGED':
      return <Tag color="processing">STAGED</Tag>;
    case 'ARCHIVED':
      return <Tag color="default">ARCHIVED</Tag>;
    default:
      return <Tag color="error">FAILED</Tag>;
  }
}

function jobTag(status: string) {
  const color = status === 'SUCCESS' ? 'success' : status === 'FAILED' ? 'error' : 'processing';
  return <Tag color={color}>{status}</Tag>;
}

const CHANGE_COLORS: Record<string, string> = {
  ADDED: 'green',
  CHANGED: 'orange',
  RENAMED: 'blue',
  REMOVED: 'red',
};

function prettySummary(summary: AdeSnapshotRecord['summary']): string {
  if (!summary) return '{}';
  if (typeof summary === 'string') {
    try {
      return JSON.stringify(JSON.parse(summary), null, 2);
    } catch {
      return summary;
    }
  }
  return JSON.stringify(summary, null, 2);
}

function countsLine(summary: AdeSnapshotRecord['summary']): string {
  try {
    const parsed = typeof summary === 'string' ? JSON.parse(summary) : summary;
    const counts = (parsed as { counts?: Record<string, number> } | null)?.counts;
    if (!counts) return '';
    const label: Record<string, string> = {
      CATEGORY: 'categories',
      SUBCATEGORY: 'subcategories',
      LIKELIHOOD_CHECK: 'likelihood checks',
      DLE: 'rule bypass examples',
      ITW: 'in-the-wild records',
    };
    return Object.entries(counts)
      .map(([kind, n]) => `${n} ${label[kind] ?? kind.toLowerCase()}`)
      .join(' · ');
  } catch {
    return '';
  }
}

function snapshotLabel(s: AdeSnapshotRecord): string {
  return `${s.id.slice(0, 8)} · ${shortSha(s.sourceSha)} (${s.sourceRef}) · ${s.entryCount} entries · ${new Date(
    s.createdAt,
  ).toLocaleString()}`;
}

// ---------------------------------------------------------------------------
// Job poller
// ---------------------------------------------------------------------------

function RunningAdeJobPoller({
  jobId,
  onComplete,
}: {
  jobId: string;
  onComplete: (job: { id: string; sourceRef: string; status: string; error: string }) => void;
}) {
  const { data, startPolling, stopPolling } = useQuery(ADE_IMPORT_JOB_QUERY, {
    variables: { id: jobId },
    fetchPolicy: 'network-only',
  });

  useEffect(() => {
    startPolling(3000);
    return () => stopPolling();
  }, [startPolling, stopPolling]);

  const job = data?.adeImportJob ?? null;

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
      message={`ADE import (${job.sourceRef}) running…`}
      description="Polling every 3 s. This usually takes under a minute."
      style={{ marginBottom: 16 }}
    />
  );
}

// ---------------------------------------------------------------------------
// Section
// ---------------------------------------------------------------------------

export const AdeFrameworkSection: React.FC<{ canManage: boolean }> = ({ canManage }) => {
  const [messageApi, contextHolder] = message.useMessage();
  const [form] = Form.useForm();
  const [pollingJobId, setPollingJobId] = useState<string | null>(null);
  const [selectedStagedId, setSelectedStagedId] = useState<string | null>(null);
  const [selectedRollbackId, setSelectedRollbackId] = useState<string | null>(null);

  const { data: latestData } = useQuery(LATEST_ADE_REVISION_QUERY, {
    variables: { sourceRepo: DEFAULT_ADE_REPO, ref: DEFAULT_ADE_REF },
    fetchPolicy: 'network-only',
  });
  const { data: activeData, refetch: refetchActive } = useQuery(ACTIVE_ADE_SNAPSHOT_QUERY, {
    fetchPolicy: 'network-only',
  });
  const { data: snapshotsData, refetch: refetchSnapshots } = useQuery(ADE_SNAPSHOTS_QUERY, {
    variables: { limit: 30 },
    fetchPolicy: 'network-only',
  });
  const { data: jobsData, refetch: refetchJobs } = useQuery(ADE_IMPORT_JOBS_QUERY, {
    variables: { limit: 10 },
    fetchPolicy: 'network-only',
  });
  const { data: diffData, refetch: refetchDiff } = useQuery(STAGED_ADE_DIFF_QUERY, {
    variables: { snapshotId: selectedStagedId },
    skip: !selectedStagedId,
    fetchPolicy: 'network-only',
  });

  const [runImport, { loading: importing }] = useMutation(RUN_ADE_IMPORT_MUTATION);
  const [promote, { loading: promoting }] = useMutation(PROMOTE_ADE_SNAPSHOT_MUTATION);
  const [rollback, { loading: rollingBack }] = useMutation(ROLLBACK_ADE_SNAPSHOT_MUTATION);

  const active: AdeSnapshotRecord | null = activeData?.activeAdeSnapshot ?? null;
  const latestRevision: string | null = latestData?.latestAvailableAdeRevision ?? null;
  const hasNewerRevision = Boolean(latestRevision && (!active || latestRevision !== active.sourceSha));
  const snapshots: AdeSnapshotRecord[] = snapshotsData?.adeSnapshots ?? [];
  const jobs: AdeJobRecord[] = jobsData?.adeImportJobs ?? [];
  const staged = snapshots.filter((s) => s.status === 'STAGED');
  const rollbackCandidates = snapshots.filter((s) => s.status === 'ARCHIVED' || s.status === 'ACTIVE');
  const diff = diffData?.stagedAdeDiff ?? null;

  useEffect(() => {
    if (!selectedStagedId && staged.length > 0) setSelectedStagedId(staged[0].id);
    if (selectedStagedId && !staged.some((s) => s.id === selectedStagedId)) {
      setSelectedStagedId(staged[0]?.id ?? null);
    }
  }, [staged, selectedStagedId]);

  const refreshAll = useCallback(() => {
    refetchActive();
    refetchSnapshots();
    refetchJobs();
  }, [refetchActive, refetchSnapshots, refetchJobs]);

  const handleSubmit = useCallback(
    async (values: { sourceRepo: string; ref: string; mode: string }) => {
      try {
        const result = await runImport({ variables: values });
        const job = result.data?.runAdeImport?.job;
        if (job?.id) {
          setPollingJobId(job.id);
          refetchJobs();
        }
      } catch (err: any) {
        messageApi.error(err?.message ?? 'Failed to start ADE import');
      }
    },
    [runImport, refetchJobs, messageApi],
  );

  const handleJobComplete = useCallback(
    (job: { sourceRef: string; status: string; error: string }) => {
      setPollingJobId(null);
      refreshAll();
      if (job.status === 'SUCCESS') {
        messageApi.success(`ADE import for ${job.sourceRef} succeeded. Review the diff, then promote.`);
      } else {
        messageApi.error(`ADE import for ${job.sourceRef} failed.`);
      }
    },
    [refreshAll, messageApi],
  );

  const handlePromote = useCallback(async () => {
    if (!selectedStagedId) return;
    try {
      const res = await promote({ variables: { snapshotId: selectedStagedId } });
      messageApi.success(res.data?.promoteAdeSnapshot?.message ?? 'Snapshot promoted.');
      setSelectedStagedId(null);
      refreshAll();
    } catch (err: any) {
      messageApi.error(err?.message ?? 'Promotion failed');
    }
  }, [promote, selectedStagedId, refreshAll, messageApi]);

  const handleRollback = useCallback(async () => {
    if (!selectedRollbackId) return;
    try {
      const res = await rollback({ variables: { snapshotId: selectedRollbackId } });
      messageApi.success(res.data?.rollbackAdeSnapshot?.message ?? 'Rolled back.');
      setSelectedRollbackId(null);
      refreshAll();
    } catch (err: any) {
      messageApi.error(err?.message ?? 'Rollback failed');
    }
  }, [rollback, selectedRollbackId, refreshAll, messageApi]);

  const stagedOptions = useMemo(
    () => staged.map((s) => ({ value: s.id, label: snapshotLabel(s) })),
    [staged],
  );
  const rollbackOptions = useMemo(
    () =>
      rollbackCandidates.map((s) => ({
        value: s.id,
        label: `${s.status === 'ACTIVE' ? '(active) ' : ''}${snapshotLabel(s)}`,
        disabled: s.status === 'ACTIVE',
      })),
    [rollbackCandidates],
  );

  return (
    <div data-testid="ade-framework-section">
      {contextHolder}

      <Card title="Adversarial Detection Engineering (ADE)" style={{ marginBottom: 24 }}>
        <Space direction="vertical" size={6}>
          <Text type="secondary">
            Taxonomy of detection-logic false-negative bugs, a bug likelihood checklist, and real bypass
            examples. Imports are staged first and only change what HEFAISTOS uses after you promote them.
          </Text>
          <Text>
            <Text strong>Source repo:</Text> {DEFAULT_ADE_REPO}
          </Text>
          <Text>
            <Text strong>Active snapshot:</Text>{' '}
            {active ? (
              <>
                {shortSha(active.sourceSha)} ({active.sourceRef}) · {active.entryCount} entries
                {active.activatedAt ? ` · activated ${new Date(active.activatedAt).toLocaleString()}` : ''}
              </>
            ) : (
              'None'
            )}
          </Text>
          {active && countsLine(active.summary) && <Text type="secondary">{countsLine(active.summary)}</Text>}
          <Text>
            <Text strong>Latest upstream revision:</Text> {shortSha(latestRevision)}
          </Text>
        </Space>
        {hasNewerRevision && (
          <Alert
            type="warning"
            showIcon
            style={{ marginTop: 16 }}
            message={`A newer ADE revision is available: ${shortSha(latestRevision)}`}
            description="Run import to stage it, review the diff, then promote."
          />
        )}
      </Card>

      <Card title="Run ADE Update" style={{ marginBottom: 24 }}>
        {pollingJobId && <RunningAdeJobPoller jobId={pollingJobId} onComplete={handleJobComplete} />}
        <Form
          form={form}
          layout="inline"
          initialValues={{ sourceRepo: DEFAULT_ADE_REPO, ref: DEFAULT_ADE_REF, mode: 'remote' }}
          onFinish={handleSubmit}
          style={{ gap: 8 }}
          disabled={!canManage}
        >
          <Form.Item name="sourceRepo" label="Repository" rules={[{ required: true, message: 'Repository is required' }]}>
            <Input style={{ width: 420 }} />
          </Form.Item>
          <Form.Item name="ref" label="Ref" rules={[{ required: true, message: 'Ref is required' }]}>
            <Input placeholder="main" style={{ width: 140 }} />
          </Form.Item>
          <Form.Item name="mode" label="Mode">
            <Select style={{ width: 120 }}>
              <Select.Option value="remote">Remote</Select.Option>
              <Select.Option value="local">Local</Select.Option>
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
              Run ADE Import
            </Button>
          </Form.Item>
        </Form>
      </Card>

      <Card title="ADE Snapshot Promotion" style={{ marginBottom: 24 }}>
        <Space direction="vertical" size={14} style={{ width: '100%' }}>
          <Space wrap>
            <Text strong>Staged snapshot</Text>
            <Select
              style={{ minWidth: 560 }}
              value={selectedStagedId ?? undefined}
              onChange={(value) => {
                setSelectedStagedId(value);
                refetchDiff({ snapshotId: value });
              }}
              options={stagedOptions}
              placeholder="Select staged snapshot"
            />
            <Popconfirm
              title="Promote this snapshot to active?"
              description="Questions and hints built from ADE will use this content."
              onConfirm={handlePromote}
              disabled={!selectedStagedId || !canManage}
            >
              <Button type="primary" disabled={!selectedStagedId || !canManage} loading={promoting}>
                Promote to Active
              </Button>
            </Popconfirm>
          </Space>

          {diff && (
            <>
              <Alert
                type="info"
                showIcon
                message={`Diff vs active snapshot (${shortSha(diff.activeSnapshotId || '') || 'none'})`}
                description={
                  <Space size={24} wrap>
                    <Text>Staged entries: <Text strong>{diff.stagedCount}</Text></Text>
                    <Text>Active entries: <Text strong>{diff.activeCount}</Text></Text>
                    <Text>Added: <Text strong>{diff.added}</Text></Text>
                    <Text>Changed or renamed: <Text strong>{diff.changed}</Text></Text>
                    <Text>Removed: <Text strong>{diff.removed}</Text></Text>
                    <Text>Unchanged: <Text strong>{diff.unchanged}</Text></Text>
                  </Space>
                }
              />
              {diff.changes.length > 0 && (
                <Table
                  rowKey="entryKey"
                  size="small"
                  pagination={{ pageSize: 10, hideOnSinglePage: true }}
                  dataSource={diff.changes as AdeDiffChange[]}
                  columns={[
                    {
                      title: 'Change',
                      dataIndex: 'change',
                      key: 'change',
                      render: (c: string) => <Tag color={CHANGE_COLORS[c] ?? 'default'}>{c}</Tag>,
                    },
                    { title: 'Kind', dataIndex: 'kind', key: 'kind' },
                    { title: 'ID', dataIndex: 'adeId', key: 'adeId', render: (v: string) => v || '–' },
                    { title: 'Title', dataIndex: 'title', key: 'title' },
                  ]}
                />
              )}
            </>
          )}

          <Space wrap>
            <Text strong>Rollback target</Text>
            <Select
              style={{ minWidth: 560 }}
              value={selectedRollbackId ?? undefined}
              onChange={(value) => setSelectedRollbackId(value)}
              options={rollbackOptions}
              placeholder="Select rollback snapshot"
            />
            <Popconfirm
              title="Roll back to this snapshot?"
              onConfirm={handleRollback}
              disabled={!selectedRollbackId || !canManage}
            >
              <Button danger disabled={!selectedRollbackId || !canManage} loading={rollingBack}>
                Rollback to Snapshot
              </Button>
            </Popconfirm>
          </Space>
        </Space>
      </Card>

      <Card title="ADE Snapshots" style={{ marginBottom: 24 }}>
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={snapshots}
          locale={{ emptyText: 'No ADE snapshots yet.' }}
          className="framework-updates-table"
          tableLayout="fixed"
          columns={[
            {
              title: 'Snapshot',
              key: 'id',
              render: (_: unknown, s: AdeSnapshotRecord) => (
                <Space direction="vertical" size={0}>
                  <Text code>{s.id.slice(0, 8)}</Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>{new Date(s.createdAt).toLocaleString()}</Text>
                </Space>
              ),
            },
            { title: 'Status', key: 'status', render: (_: unknown, s: AdeSnapshotRecord) => snapshotTag(s.status) },
            {
              title: 'Revision',
              key: 'revision',
              render: (_: unknown, s: AdeSnapshotRecord) => (
                <Space direction="vertical" size={0}>
                  <Text>{shortSha(s.sourceSha)}</Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>{s.sourceRef}</Text>
                </Space>
              ),
            },
            { title: 'Entries', dataIndex: 'entryCount', key: 'entryCount' },
            {
              title: 'Activated',
              key: 'activatedAt',
              render: (_: unknown, s: AdeSnapshotRecord) => (s.activatedAt ? new Date(s.activatedAt).toLocaleString() : '–'),
            },
            {
              title: 'Validation',
              key: 'validation',
              render: (_: unknown, s: AdeSnapshotRecord) => (
                <div className="framework-updates-cell-content">
                  <Collapse ghost>
                    <Panel header={s.validationErrors ? 'Summary and warnings' : 'Summary'} key="validation">
                      <pre className="framework-updates-pre framework-updates-pre--summary">{prettySummary(s.summary)}</pre>
                      {s.validationErrors && (
                        <pre className="framework-updates-pre framework-updates-pre--warning">
                          {s.validationErrors.split('\n').slice(0, 20).join('\n')}
                        </pre>
                      )}
                    </Panel>
                  </Collapse>
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Card title="Recent ADE Import Jobs" style={{ marginBottom: 24 }}>
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={jobs}
          locale={{ emptyText: 'No ADE import jobs yet.' }}
          className="framework-updates-table"
          tableLayout="fixed"
          columns={[
            {
              title: 'Started',
              key: 'createdAt',
              render: (_: unknown, j: AdeJobRecord) => (
                <Space direction="vertical" size={0}>
                  <Text>{new Date(j.createdAt).toLocaleString()}</Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>{j.triggeredBy?.username ?? '–'}</Text>
                </Space>
              ),
            },
            { title: 'Status', key: 'status', render: (_: unknown, j: AdeJobRecord) => jobTag(j.status) },
            { title: 'Ref', dataIndex: 'sourceRef', key: 'sourceRef' },
            { title: 'Mode', dataIndex: 'mode', key: 'mode' },
            {
              title: 'Duration',
              key: 'duration',
              render: (_: unknown, j: AdeJobRecord) =>
                j.durationSeconds == null ? '–' : `${j.durationSeconds.toFixed(1)}s`,
            },
            {
              title: 'Snapshot',
              key: 'snapshot',
              render: (_: unknown, j: AdeJobRecord) => (j.snapshot ? shortSha(j.snapshot.sourceSha) : '–'),
            },
            {
              title: 'Error',
              key: 'error',
              render: (_: unknown, j: AdeJobRecord) =>
                j.error ? <Text type="danger" style={{ fontSize: 12 }}>{j.error.slice(0, 160)}</Text> : '–',
            },
          ]}
        />
      </Card>
    </div>
  );
};

export default AdeFrameworkSection;
