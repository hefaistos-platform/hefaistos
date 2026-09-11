import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { gql, useMutation, useQuery } from '@apollo/client';
import { Button, Card, Form, Input, Select, Tag, Table, Collapse, Typography, Space, Alert, message } from 'antd';
import { SyncOutlined, CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Navigate, useNavigate } from 'react-router-dom';

const { Text, Title } = Typography;
const { Panel } = Collapse;

const DEFAULT_CHOKEPOINT_REPO = 'https://github.com/iimp0ster/detection-chokepoints';
const DEFAULT_CHOKEPOINT_REF = 'main';

// ---------------------------------------------------------------------------
// GraphQL
// ---------------------------------------------------------------------------

const LOADED_ATTACK_VERSIONS_QUERY = gql`
  query LoadedAttackVersions {
    loadedAttackVersions {
      framework
      version
      importedAt
    }
  }
`;

const LATEST_AVAILABLE_ATTACK_VERSION_QUERY = gql`
  query LatestAvailableAttackVersion {
    latestAvailableAttackVersion
  }
`;

const MITRE_IMPORT_JOBS_QUERY = gql`
  query MitreImportJobs($limit: Int) {
    mitreImportJobs(limit: $limit) {
      id
      version
      mode
      status
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

const MITRE_IMPORT_JOB_QUERY = gql`
  query MitreImportJob($id: UUID!) {
    mitreImportJob(id: $id) {
      id
      version
      mode
      status
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

const RUN_MITRE_IMPORT_MUTATION = gql`
  mutation RunMitreImport($version: String!, $mode: String) {
    runMitreImport(version: $version, mode: $mode) {
      job {
        id
        version
        mode
        status
        createdAt
      }
    }
  }
`;

const LATEST_CHOKEPOINT_REVISION_QUERY = gql`
  query LatestAvailableChokepointRevision($sourceRepo: String, $ref: String) {
    latestAvailableChokepointRevision(sourceRepo: $sourceRepo, ref: $ref)
  }
`;

const ACTIVE_CHOKEPOINT_SNAPSHOT_QUERY = gql`
  query ActiveChokepointSnapshot {
    activeChokepointSnapshot {
      id
      status
      sourceRepo
      sourceRef
      sourceSha
      entryCount
      summary
      createdAt
      activatedAt
    }
  }
`;

const CHOKEPOINT_SNAPSHOTS_QUERY = gql`
  query ChokepointSnapshots($limit: Int, $status: String) {
    chokepointSnapshots(limit: $limit, status: $status) {
      id
      status
      sourceRepo
      sourceRef
      sourceSha
      entryCount
      summary
      validationErrors
      createdAt
      activatedAt
      triggeredBy {
        username
      }
    }
  }
`;

const CHOKEPOINT_IMPORT_JOBS_QUERY = gql`
  query ChokepointImportJobs($limit: Int) {
    chokepointImportJobs(limit: $limit) {
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
      snapshot {
        id
        status
        sourceSha
        sourceRef
        entryCount
      }
    }
  }
`;

const CHOKEPOINT_IMPORT_JOB_QUERY = gql`
  query ChokepointImportJob($id: UUID!) {
    chokepointImportJob(id: $id) {
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
      snapshot {
        id
        status
        sourceSha
        sourceRef
        entryCount
      }
    }
  }
`;

const STAGED_CHOKEPOINT_DIFF_QUERY = gql`
  query StagedChokepointDiff($snapshotId: UUID!) {
    stagedChokepointDiff(snapshotId: $snapshotId) {
      snapshotId
      activeSnapshotId
      added
      changed
      removed
      unchanged
      stagedCount
      activeCount
    }
  }
`;

const RUN_CHOKEPOINT_IMPORT_MUTATION = gql`
  mutation RunChokepointImport($sourceRepo: String, $ref: String, $mode: String) {
    runChokepointImport(sourceRepo: $sourceRepo, ref: $ref, mode: $mode) {
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

const PROMOTE_CHOKEPOINT_SNAPSHOT_MUTATION = gql`
  mutation PromoteChokepointSnapshot($snapshotId: UUID!) {
    promoteChokepointSnapshot(snapshotId: $snapshotId) {
      success
      message
      snapshot {
        id
        status
        sourceSha
        sourceRef
        activatedAt
        entryCount
      }
    }
  }
`;

const ROLLBACK_CHOKEPOINT_SNAPSHOT_MUTATION = gql`
  mutation RollbackChokepointSnapshot($snapshotId: UUID!) {
    rollbackChokepointSnapshot(snapshotId: $snapshotId) {
      success
      message
      snapshot {
        id
        status
        sourceSha
        sourceRef
        activatedAt
        entryCount
      }
    }
  }
`;

const ME_QUERY = gql`
  query MeForFramework {
    me {
      id
      role
      isSuperuser
    }
  }
`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function semverGt(a: string, b: string): boolean {
  const pa = a.split('.').map(Number);
  const pb = b.split('.').map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const na = pa[i] ?? 0;
    const nb = pb[i] ?? 0;
    if (na !== nb) return na > nb;
  }
  return false;
}

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

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '–';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function shortSha(sha: string | null | undefined): string {
  if (!sha) return '–';
  return sha.length > 12 ? sha.slice(0, 12) : sha;
}

// ---------------------------------------------------------------------------
// Pollers
// ---------------------------------------------------------------------------

interface JobRecord {
  id: string;
  version: string;
  mode: string;
  status: string;
  log: string;
  error: string;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  durationSeconds: number | null;
  triggeredBy: { username: string } | null;
}

interface ChokepointSnapshotRecord {
  id: string;
  status: string;
  sourceRepo: string;
  sourceRef: string;
  sourceSha: string;
  entryCount: number;
  summary: any;
  validationErrors?: string;
  createdAt: string;
  activatedAt: string | null;
  triggeredBy?: { username: string } | null;
}

interface ChokepointJobRecord {
  id: string;
  sourceRepo: string;
  sourceRef: string;
  mode: string;
  status: string;
  summary: any;
  log: string;
  error: string;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  durationSeconds: number | null;
  triggeredBy: { username: string } | null;
  snapshot: ChokepointSnapshotRecord | null;
}

function RunningJobPoller({ jobId, onComplete }: { jobId: string; onComplete: (job: JobRecord) => void }) {
  const { data, startPolling, stopPolling } = useQuery(MITRE_IMPORT_JOB_QUERY, {
    variables: { id: jobId },
    fetchPolicy: 'network-only',
  });

  useEffect(() => {
    startPolling(3000);
    return () => stopPolling();
  }, [startPolling, stopPolling]);

  const job: JobRecord | null = data?.mitreImportJob ?? null;

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
      message={`Import v${job.version} running…`}
      description="Polling every 3 s. This may take several minutes."
      style={{ marginBottom: 16 }}
    />
  );
}

function RunningChokepointJobPoller({
  jobId,
  onComplete,
}: {
  jobId: string;
  onComplete: (job: ChokepointJobRecord) => void;
}) {
  const { data, startPolling, stopPolling } = useQuery(CHOKEPOINT_IMPORT_JOB_QUERY, {
    variables: { id: jobId },
    fetchPolicy: 'network-only',
  });

  useEffect(() => {
    startPolling(3000);
    return () => stopPolling();
  }, [startPolling, stopPolling]);

  const job: ChokepointJobRecord | null = data?.chokepointImportJob ?? null;

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
      message={`Chokepoint import (${job.sourceRef}) running…`}
      description="Polling every 3 s. This may take several minutes."
      style={{ marginBottom: 16 }}
    />
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export const FrameworkUpdatesPage: React.FC = () => {
  const navigate = useNavigate();
  const [attackForm] = Form.useForm();
  const [chokepointForm] = Form.useForm();
  const [pollingJobId, setPollingJobId] = useState<string | null>(null);
  const [pollingChokepointJobId, setPollingChokepointJobId] = useState<string | null>(null);
  const [selectedStagedSnapshotId, setSelectedStagedSnapshotId] = useState<string | null>(null);
  const [selectedRollbackSnapshotId, setSelectedRollbackSnapshotId] = useState<string | null>(null);
  const [messageApi, contextHolder] = message.useMessage();

  const { data: meData } = useQuery(ME_QUERY);
  const userRole = meData?.me?.role;
  const isSuperuser = Boolean(meData?.me?.isSuperuser);
  const canView = isSuperuser;
  const canManage = isSuperuser;

  // ATT&CK
  const { data: versionsData, refetch: refetchVersions } = useQuery(LOADED_ATTACK_VERSIONS_QUERY);
  const { data: latestData } = useQuery(LATEST_AVAILABLE_ATTACK_VERSION_QUERY, { fetchPolicy: 'cache-and-network' });
  const { data: jobsData, refetch: refetchJobs } = useQuery(MITRE_IMPORT_JOBS_QUERY, {
    variables: { limit: 10 },
    fetchPolicy: 'cache-and-network',
  });
  const [runImport, { loading: importing }] = useMutation(RUN_MITRE_IMPORT_MUTATION);

  // Chokepoints
  const { data: latestChokepointData, refetch: refetchLatestChokepoint } = useQuery(
    LATEST_CHOKEPOINT_REVISION_QUERY,
    {
      variables: { sourceRepo: DEFAULT_CHOKEPOINT_REPO, ref: DEFAULT_CHOKEPOINT_REF },
      fetchPolicy: 'cache-and-network',
    }
  );
  const { data: activeChokepointData, refetch: refetchActiveChokepoint } = useQuery(
    ACTIVE_CHOKEPOINT_SNAPSHOT_QUERY,
    { fetchPolicy: 'cache-and-network' }
  );
  const { data: chokepointSnapshotsData, refetch: refetchChokepointSnapshots } = useQuery(
    CHOKEPOINT_SNAPSHOTS_QUERY,
    {
      variables: { limit: 20 },
      fetchPolicy: 'cache-and-network',
    }
  );
  const { data: chokepointJobsData, refetch: refetchChokepointJobs } = useQuery(CHOKEPOINT_IMPORT_JOBS_QUERY, {
    variables: { limit: 10 },
    fetchPolicy: 'cache-and-network',
  });
  const { data: chokepointDiffData, refetch: refetchChokepointDiff } = useQuery(STAGED_CHOKEPOINT_DIFF_QUERY, {
    variables: { snapshotId: selectedStagedSnapshotId },
    skip: !selectedStagedSnapshotId,
    fetchPolicy: 'network-only',
  });

  const [runChokepointImport, { loading: importingChokepoints }] = useMutation(RUN_CHOKEPOINT_IMPORT_MUTATION);
  const [promoteSnapshot, { loading: promotingSnapshot }] = useMutation(PROMOTE_CHOKEPOINT_SNAPSHOT_MUTATION);
  const [rollbackSnapshot, { loading: rollingBackSnapshot }] = useMutation(ROLLBACK_CHOKEPOINT_SNAPSHOT_MUTATION);

  const latestAvailable: string | null = latestData?.latestAvailableAttackVersion ?? null;
  const loadedVersions: { framework: string; version: string; importedAt: string }[] =
    versionsData?.loadedAttackVersions ?? [];
  const enterpriseVersion = loadedVersions.find(v => v.framework === 'enterprise-attack')?.version ?? null;
  const hasNewerVersion = !!(latestAvailable && enterpriseVersion && semverGt(latestAvailable, enterpriseVersion));

  const activeSnapshot: ChokepointSnapshotRecord | null = activeChokepointData?.activeChokepointSnapshot ?? null;
  const latestChokepointRevision: string | null = latestChokepointData?.latestAvailableChokepointRevision ?? null;
  const hasNewerChokepointRevision = Boolean(
    latestChokepointRevision &&
      activeSnapshot?.sourceSha &&
      latestChokepointRevision !== activeSnapshot.sourceSha
  );

  const chokepointSnapshots: ChokepointSnapshotRecord[] = chokepointSnapshotsData?.chokepointSnapshots ?? [];
  const stagedSnapshots = chokepointSnapshots.filter(s => s.status === 'STAGED');
  const rollbackCandidates = chokepointSnapshots.filter(s => s.status === 'ARCHIVED' || s.status === 'ACTIVE');

  useEffect(() => {
    if (latestAvailable) {
      attackForm.setFieldValue('version', latestAvailable);
    }
  }, [latestAvailable, attackForm]);

  useEffect(() => {
    if (latestChokepointRevision) {
      chokepointForm.setFieldsValue({
        sourceRepo: DEFAULT_CHOKEPOINT_REPO,
        ref: DEFAULT_CHOKEPOINT_REF,
        mode: 'remote',
      });
    }
  }, [latestChokepointRevision, chokepointForm]);

  useEffect(() => {
    if (!selectedStagedSnapshotId && stagedSnapshots.length > 0) {
      setSelectedStagedSnapshotId(stagedSnapshots[0].id);
    }
  }, [selectedStagedSnapshotId, stagedSnapshots]);

  useEffect(() => {
    if (!selectedRollbackSnapshotId && rollbackCandidates.length > 0) {
      const preferred = rollbackCandidates.find(c => c.status === 'ARCHIVED') ?? rollbackCandidates[0];
      setSelectedRollbackSnapshotId(preferred.id);
    }
  }, [rollbackCandidates, selectedRollbackSnapshotId]);

  const handleSubmit = useCallback(async (values: { version: string; mode: string }) => {
    try {
      const result = await runImport({ variables: { version: values.version, mode: values.mode } });
      const job = result.data?.runMitreImport?.job;
      if (job) {
        setPollingJobId(job.id);
        refetchJobs();
      }
    } catch (err: any) {
      messageApi.error(err?.message ?? 'Failed to start import');
    }
  }, [runImport, refetchJobs, messageApi]);

  const handleJobComplete = useCallback((job: JobRecord) => {
    setPollingJobId(null);
    refetchJobs();
    refetchVersions();
    if (job.status === 'SUCCESS') {
      messageApi.success(`ATT&CK v${job.version} import succeeded!`);
    } else {
      messageApi.error(`ATT&CK v${job.version} import failed.`);
    }
  }, [refetchJobs, refetchVersions, messageApi]);

  const handleChokepointSubmit = useCallback(async (values: { sourceRepo: string; ref: string; mode: string }) => {
    try {
      const result = await runChokepointImport({
        variables: {
          sourceRepo: values.sourceRepo,
          ref: values.ref,
          mode: values.mode,
        },
      });
      const job = result.data?.runChokepointImport?.job;
      if (job) {
        setPollingChokepointJobId(job.id);
        refetchChokepointJobs();
      }
    } catch (err: any) {
      messageApi.error(err?.message ?? 'Failed to start chokepoint import');
    }
  }, [runChokepointImport, refetchChokepointJobs, messageApi]);

  const handleChokepointJobComplete = useCallback((job: ChokepointJobRecord) => {
    setPollingChokepointJobId(null);
    refetchChokepointJobs();
    refetchChokepointSnapshots();
    refetchActiveChokepoint();
    refetchVersions();
    if (job.status === 'SUCCESS') {
      if (job.snapshot?.id) {
        setSelectedStagedSnapshotId(job.snapshot.id);
      }
      messageApi.success(`Chokepoint import for ${job.sourceRef} succeeded.`);
    } else {
      messageApi.error(`Chokepoint import for ${job.sourceRef} failed.`);
    }
  }, [
    refetchChokepointJobs,
    refetchChokepointSnapshots,
    refetchActiveChokepoint,
    refetchVersions,
    messageApi,
  ]);

  const handlePromoteSnapshot = useCallback(async () => {
    if (!selectedStagedSnapshotId) {
      messageApi.warning('Select a staged snapshot first.');
      return;
    }
    try {
      const result = await promoteSnapshot({ variables: { snapshotId: selectedStagedSnapshotId } });
      const payload = result.data?.promoteChokepointSnapshot;
      if (payload?.success) {
        messageApi.success(payload.message || 'Snapshot promoted.');
        refetchChokepointJobs();
        refetchChokepointSnapshots();
        refetchActiveChokepoint();
        refetchVersions();
        refetchLatestChokepoint();
      } else {
        messageApi.error(payload?.message || 'Failed to promote snapshot.');
      }
    } catch (err: any) {
      messageApi.error(err?.message || 'Failed to promote snapshot.');
    }
  }, [
    selectedStagedSnapshotId,
    promoteSnapshot,
    refetchChokepointJobs,
    refetchChokepointSnapshots,
    refetchActiveChokepoint,
    refetchVersions,
    refetchLatestChokepoint,
    messageApi,
  ]);

  const handleRollbackSnapshot = useCallback(async () => {
    if (!selectedRollbackSnapshotId) {
      messageApi.warning('Select a rollback snapshot first.');
      return;
    }
    try {
      const result = await rollbackSnapshot({ variables: { snapshotId: selectedRollbackSnapshotId } });
      const payload = result.data?.rollbackChokepointSnapshot;
      if (payload?.success) {
        messageApi.success(payload.message || 'Rollback completed.');
        refetchChokepointSnapshots();
        refetchActiveChokepoint();
        refetchVersions();
      } else {
        messageApi.error(payload?.message || 'Rollback failed.');
      }
    } catch (err: any) {
      messageApi.error(err?.message || 'Rollback failed.');
    }
  }, [
    selectedRollbackSnapshotId,
    rollbackSnapshot,
    refetchChokepointSnapshots,
    refetchActiveChokepoint,
    refetchVersions,
    messageApi,
  ]);

  if (userRole && !canView) {
    return <Navigate to="/" replace />;
  }

  const jobs: JobRecord[] = jobsData?.mitreImportJobs ?? [];
  const chokepointJobs: ChokepointJobRecord[] = chokepointJobsData?.chokepointImportJobs ?? [];
  const diff = chokepointDiffData?.stagedChokepointDiff ?? null;

  const attackColumns = [
    { title: 'Version', dataIndex: 'version', key: 'version', render: (v: string) => `v${v}` },
    { title: 'Mode', dataIndex: 'mode', key: 'mode' },
    { title: 'Status', dataIndex: 'status', key: 'status', render: statusTag },
    { title: 'Triggered by', key: 'triggeredBy', render: (_: any, r: JobRecord) => r.triggeredBy?.username ?? '–' },
    {
      title: 'Started',
      dataIndex: 'createdAt',
      key: 'createdAt',
      render: (v: string) => v ? new Date(v).toLocaleString() : '–',
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
      render: (_: any, r: JobRecord) => (
        <div className="framework-updates-cell-content">
          <Collapse ghost>
            <Panel header="Show last 20 lines" key="log">
              <pre className="framework-updates-pre framework-updates-pre--log">
                {r.log ? r.log.split('\n').slice(-20).join('\n') : '(empty)'}
              </pre>
              {r.error && (
                <pre className="framework-updates-pre framework-updates-pre--error">
                  {r.error.split('\n').slice(-10).join('\n')}
                </pre>
              )}
            </Panel>
          </Collapse>
        </div>
      ),
    },
  ];

  const chokepointColumns = [
    {
      title: 'Ref',
      key: 'sourceRef',
      render: (_: any, r: ChokepointJobRecord) => (
        <Space direction="vertical" size={0}>
          <Text>{r.sourceRef}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>{shortSha(r.snapshot?.sourceSha)}</Text>
        </Space>
      ),
    },
    { title: 'Mode', dataIndex: 'mode', key: 'mode' },
    { title: 'Status', dataIndex: 'status', key: 'status', render: statusTag },
    {
      title: 'Snapshot',
      key: 'snapshot',
      render: (_: any, r: ChokepointJobRecord) => (
        r.snapshot ? (
          <Space direction="vertical" size={0}>
            <Text code>{r.snapshot.id.slice(0, 8)}</Text>
            <Text type="secondary" style={{ fontSize: 11 }}>{snapshotTag(r.snapshot.status)}</Text>
          </Space>
        ) : '–'
      ),
    },
    {
      title: 'Entries',
      key: 'entryCount',
      render: (_: any, r: ChokepointJobRecord) => r.snapshot?.entryCount ?? '–',
    },
    {
      title: 'Triggered by',
      key: 'triggeredBy',
      render: (_: any, r: ChokepointJobRecord) => r.triggeredBy?.username ?? '–',
    },
    {
      title: 'Started',
      dataIndex: 'createdAt',
      key: 'createdAt',
      render: (v: string) => v ? new Date(v).toLocaleString() : '–',
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
      render: (_: any, r: ChokepointJobRecord) => (
        <div className="framework-updates-cell-content">
          <Collapse ghost>
            <Panel header="Show last 20 lines" key="log">
              <pre className="framework-updates-pre framework-updates-pre--log">
                {r.log ? r.log.split('\n').slice(-20).join('\n') : '(empty)'}
              </pre>
              {r.error && (
                <pre className="framework-updates-pre framework-updates-pre--error">
                  {r.error.split('\n').slice(-10).join('\n')}
                </pre>
              )}
            </Panel>
          </Collapse>
        </div>
      ),
    },
  ];

  const stagedSnapshotOptions = useMemo(
    () => stagedSnapshots.map(snapshot => ({
      value: snapshot.id,
      label: `${shortSha(snapshot.sourceSha) || snapshot.sourceRef} · ${snapshot.entryCount} entries · ${new Date(snapshot.createdAt).toLocaleString()}`,
    })),
    [stagedSnapshots]
  );

  const rollbackSnapshotOptions = useMemo(
    () => rollbackCandidates.map(snapshot => ({
      value: snapshot.id,
      label: `${snapshot.status} · ${shortSha(snapshot.sourceSha) || snapshot.sourceRef} · ${snapshot.entryCount} entries`,
    })),
    [rollbackCandidates]
  );

  return (
    <div className="framework-updates-page" style={{ maxWidth: 1120, margin: '0 auto' }}>
      {contextHolder}

      <Title level={3} style={{ marginBottom: 24 }}>
        <ThunderboltOutlined style={{ marginRight: 8 }} />
        Framework Updates
      </Title>

      {/* Current version status */}
      <Card title="Currently Loaded Frameworks" style={{ marginBottom: 24 }}>
        {loadedVersions.length === 0 ? (
          <Text type="secondary">No frameworks loaded yet.</Text>
        ) : (
          <Space direction="vertical" size={4}>
            {loadedVersions.map(lv => (
              <div key={lv.framework}>
                <Text strong>{lv.framework}</Text>
                {': '}
                <Text>v{lv.version}</Text>
                {lv.importedAt && (
                  <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                    (imported {new Date(lv.importedAt).toLocaleDateString()})
                  </Text>
                )}
              </div>
            ))}
          </Space>
        )}

        {hasNewerVersion && (
          <Alert
            type="warning"
            showIcon
            style={{ marginTop: 16 }}
            message={`A newer ATT&CK version is available: v${latestAvailable}`}
            description="Use the ATT&CK update form below to stage the import."
          />
        )}
      </Card>

      {/* ATT&CK Trigger form */}
      <Card title="Run ATT&CK Update" style={{ marginBottom: 24 }}>
        {pollingJobId && (
          <RunningJobPoller jobId={pollingJobId} onComplete={handleJobComplete} />
        )}

        <Form
          form={attackForm}
          layout="inline"
          initialValues={{ mode: 'remote' }}
          onFinish={handleSubmit}
          style={{ gap: 8 }}
          disabled={!canManage}
        >
          <Form.Item
            name="version"
            label="Version"
            rules={[{ required: true, pattern: /^\d+\.\d+$/, message: 'Enter a version like 19.1' }]}
          >
            <Input placeholder="19.1" style={{ width: 120 }} />
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
              Run ATT&CK Update
            </Button>
          </Form.Item>
        </Form>

        {jobs.some(j => j.status === 'SUCCESS') && (
          <div style={{ marginTop: 16 }}>
            <Button type="link" onClick={() => navigate('/coverage', { state: { frameworkUpdated: true } })}>
              ↗ Reload Coverage Map
            </Button>
          </div>
        )}
      </Card>

      {/* ATT&CK Job history */}
      <Card title="Recent ATT&CK Import Jobs" style={{ marginBottom: 24 }}>
        <Table
          dataSource={jobs}
          columns={attackColumns}
          rowKey="id"
          size="small"
          pagination={false}
          locale={{ emptyText: 'No ATT&CK import jobs yet.' }}
          className="framework-updates-table"
          tableLayout="fixed"
        />
      </Card>

      {/* Chokepoint status */}
      <Card title="Detection Chokepoints" style={{ marginBottom: 24 }}>
        <Space direction="vertical" size={6}>
          <Text>
            <Text strong>Source repo:</Text> {DEFAULT_CHOKEPOINT_REPO}
          </Text>
          <Text>
            <Text strong>Active snapshot:</Text>{' '}
            {activeSnapshot ? (
              <>
                {shortSha(activeSnapshot.sourceSha)} ({activeSnapshot.sourceRef}) · {activeSnapshot.entryCount} entries
                {activeSnapshot.activatedAt ? ` · activated ${new Date(activeSnapshot.activatedAt).toLocaleString()}` : ''}
              </>
            ) : 'None'}
          </Text>
          <Text>
            <Text strong>Latest upstream revision:</Text> {shortSha(latestChokepointRevision)}
          </Text>
        </Space>

        {hasNewerChokepointRevision && (
          <Alert
            type="warning"
            showIcon
            style={{ marginTop: 16 }}
            message={`A newer chokepoint revision is available: ${shortSha(latestChokepointRevision)}`}
            description="Run import to stage it, review diff, then promote."
          />
        )}
      </Card>

      {/* Chokepoint import */}
      <Card title="Run Detection Chokepoints Update" style={{ marginBottom: 24 }}>
        {pollingChokepointJobId && (
          <RunningChokepointJobPoller jobId={pollingChokepointJobId} onComplete={handleChokepointJobComplete} />
        )}

        <Form
          form={chokepointForm}
          layout="inline"
          initialValues={{
            sourceRepo: DEFAULT_CHOKEPOINT_REPO,
            ref: DEFAULT_CHOKEPOINT_REF,
            mode: 'remote',
          }}
          onFinish={handleChokepointSubmit}
          style={{ gap: 8 }}
          disabled={!canManage}
        >
          <Form.Item
            name="sourceRepo"
            label="Repository"
            rules={[{ required: true, message: 'Repository is required' }]}
          >
            <Input style={{ width: 360 }} />
          </Form.Item>
          <Form.Item
            name="ref"
            label="Ref"
            rules={[{ required: true, message: 'Ref is required' }]}
          >
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
              loading={importingChokepoints || !!pollingChokepointJobId}
              disabled={!canManage || !!pollingChokepointJobId}
            >
              Run Chokepoint Import
            </Button>
          </Form.Item>
        </Form>
      </Card>

      {/* Staged diff + promote/rollback */}
      <Card title="Chokepoint Snapshot Promotion" style={{ marginBottom: 24 }}>
        <Space direction="vertical" size={14} style={{ width: '100%' }}>
          <Space wrap>
            <Text strong>Staged snapshot</Text>
            <Select
              style={{ minWidth: 520 }}
              value={selectedStagedSnapshotId ?? undefined}
              onChange={(value) => {
                setSelectedStagedSnapshotId(value);
                refetchChokepointDiff({ snapshotId: value });
              }}
              options={stagedSnapshotOptions}
              placeholder="Select staged snapshot"
            />
            <Button
              type="primary"
              onClick={handlePromoteSnapshot}
              disabled={!selectedStagedSnapshotId || !canManage}
              loading={promotingSnapshot}
            >
              Promote to Active
            </Button>
          </Space>

          {diff && (
            <Alert
              type="info"
              showIcon
              message={`Diff vs active snapshot (${shortSha(diff.activeSnapshotId || '') || 'none'})`}
              description={
                <Space size={24} wrap>
                  <Text>Staged entries: <Text strong>{diff.stagedCount}</Text></Text>
                  <Text>Active entries: <Text strong>{diff.activeCount}</Text></Text>
                  <Text>Added: <Text strong>{diff.added}</Text></Text>
                  <Text>Changed: <Text strong>{diff.changed}</Text></Text>
                  <Text>Removed: <Text strong>{diff.removed}</Text></Text>
                  <Text>Unchanged: <Text strong>{diff.unchanged}</Text></Text>
                </Space>
              }
            />
          )}

          <Space wrap>
            <Text strong>Rollback target</Text>
            <Select
              style={{ minWidth: 520 }}
              value={selectedRollbackSnapshotId ?? undefined}
              onChange={(value) => setSelectedRollbackSnapshotId(value)}
              options={rollbackSnapshotOptions}
              placeholder="Select rollback snapshot"
            />
            <Button
              danger
              onClick={handleRollbackSnapshot}
              disabled={!selectedRollbackSnapshotId || !canManage}
              loading={rollingBackSnapshot}
            >
              Rollback to Snapshot
            </Button>
          </Space>
        </Space>
      </Card>

      {/* Chokepoint snapshot history */}
      <Card title="Chokepoint Snapshots" style={{ marginBottom: 24 }}>
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={chokepointSnapshots}
          locale={{ emptyText: 'No chokepoint snapshots yet.' }}
          columns={[
            {
              title: 'Snapshot',
              key: 'id',
              render: (_: any, s: ChokepointSnapshotRecord) => (
                <Space direction="vertical" size={0}>
                  <Text code>{s.id.slice(0, 8)}</Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>{new Date(s.createdAt).toLocaleString()}</Text>
                </Space>
              ),
            },
            { title: 'Status', key: 'status', render: (_: any, s: ChokepointSnapshotRecord) => snapshotTag(s.status) },
            {
              title: 'Revision',
              key: 'revision',
              render: (_: any, s: ChokepointSnapshotRecord) => (
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
              render: (_: any, s: ChokepointSnapshotRecord) => (s.activatedAt ? new Date(s.activatedAt).toLocaleString() : '–'),
            },
            {
              title: 'Validation',
              key: 'validation',
              render: (_: any, s: ChokepointSnapshotRecord) => (
                <div className="framework-updates-cell-content">
                  <Collapse ghost>
                    <Panel header="Show summary / validation" key="validation">
                      <pre className="framework-updates-pre framework-updates-pre--summary">
                        {JSON.stringify(s.summary || {}, null, 2)}
                      </pre>
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
          className="framework-updates-table"
          tableLayout="fixed"
        />
      </Card>

      {/* Chokepoint job history */}
      <Card title="Recent Chokepoint Import Jobs">
        <Table
          dataSource={chokepointJobs}
          columns={chokepointColumns}
          rowKey="id"
          size="small"
          pagination={false}
          locale={{ emptyText: 'No chokepoint import jobs yet.' }}
          className="framework-updates-table"
          tableLayout="fixed"
        />
      </Card>
    </div>
  );
};
