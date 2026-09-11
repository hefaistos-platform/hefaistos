/**
 * ImportFromHefModal
 * ==================
 * Multi-step wizard that imports one or many Workbenches from OpenTIDE HEF
 * bundles stored in a GitHub repository (previously published by the HEF
 * Publish flow).
 *
 * Steps:
 *   1 — Source: pick a HEF Publish Profile (or enter repo details manually)
 *   2 — Browse & select bundles
 *   3 — Naming & conflict handling
 *   4 — Confirm & queue
 *   5 — Progress (poll job status)
 */

import React, { useState, useCallback, useEffect } from 'react';
import { useQuery, useMutation, useLazyQuery } from '@apollo/client/react';
import {
  Modal,
  Steps,
  Button,
  Select,
  Input,
  Table,
  Checkbox,
  Space,
  Typography,
  Alert,
  Tag,
  Spin,
  Radio,
  Tooltip,
  Badge,
} from 'antd';
import {
  GithubOutlined,
  SearchOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  LinkOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { GET_HEF_PUBLISH_PROFILES } from '../../graphql/hefPublishProfiles';
import {
  LIST_HEF_BUNDLES,
  QUEUE_OPENTIDE_HEF_IMPORT,
  GET_MY_OPENTIDE_HEF_IMPORT_JOBS,
  HefBundleDescriptor,
  OpentideHefImportJob,
} from '../../graphql/hefImport';

const { Text, Paragraph } = Typography;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SelectedBundle {
  path: string;
  workbenchName: string;
  mdrTitle: string;
  mdrUuid: string;
  status: string;
  techniques: string[];
  valid: boolean;
  validationErrors: string[];
}

interface Props {
  visible: boolean;
  onClose: () => void;
  onImportSuccess?: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CONFLICT_MODES = [
  { value: 'NEW_COPY', label: 'Create new copy (default)' },
  { value: 'OVERWRITE', label: 'Overwrite existing by MDR UUID' },
  { value: 'SKIP', label: 'Skip if MDR UUID already exists' },
];

const POLL_INTERVAL_MS = 3000;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const ImportFromHefModal: React.FC<Props> = ({ visible, onClose, onImportSuccess }) => {
  const navigate = useNavigate();

  // Wizard state
  const [currentStep, setCurrentStep] = useState(0);

  // Step 1 — Source
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);
  const [manualRepoOwner, setManualRepoOwner] = useState('');
  const [manualRepoName, setManualRepoName] = useState('');
  const [manualBranch, setManualBranch] = useState('main');
  const [manualTargetFolder, setManualTargetFolder] = useState('');
  const [commitSha, setCommitSha] = useState('');
  const [useManualMode, setUseManualMode] = useState(false);

  // Step 2 — Bundle browser
  const [bundleSearch, setBundleSearch] = useState('');
  const [techniqueFilter, setTechniqueFilter] = useState<string[]>([]);
  const [statusFilter, setStatusFilter] = useState<string[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);

  // Step 3 — Names and conflict
  const [selectedBundles, setSelectedBundles] = useState<SelectedBundle[]>([]);
  const [conflictMode, setConflictMode] = useState<'NEW_COPY' | 'OVERWRITE' | 'SKIP'>('NEW_COPY');
  const [importPlatformRules, setImportPlatformRules] = useState(true);
  const [dryRun, setDryRun] = useState(false);

  // Step 5 — Progress
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [pollActive, setPollActive] = useState(false);

  // ---------------------------------------------------------------------------
  // GraphQL
  // ---------------------------------------------------------------------------

  const { data: profilesData, loading: profilesLoading } = useQuery(GET_HEF_PUBLISH_PROFILES, {
    skip: !visible,
    fetchPolicy: 'cache-and-network',
  });

  const [fetchBundles, { data: bundlesData, loading: bundlesLoading, error: bundlesError }] =
    useLazyQuery(LIST_HEF_BUNDLES, { fetchPolicy: 'network-only' });

  const [queueImport, { loading: queuingImport }] = useMutation(QUEUE_OPENTIDE_HEF_IMPORT);

  const { data: jobsData, startPolling, stopPolling } = useQuery(GET_MY_OPENTIDE_HEF_IMPORT_JOBS, {
    variables: { limit: 5 },
    skip: !pollActive,
    fetchPolicy: 'network-only',
    pollInterval: pollActive ? POLL_INTERVAL_MS : 0,
  });

  // Derive active job from polling data
  const activeJob: OpentideHefImportJob | null =
    activeJobId && jobsData?.myOpentideHefImportJobs
      ? (jobsData.myOpentideHefImportJobs.find((j: OpentideHefImportJob) => j.taskId === activeJobId) ?? null)
      : null;

  // Stop polling once job is terminal
  useEffect(() => {
    if (activeJob && (activeJob.status === 'COMPLETED' || activeJob.status === 'FAILED')) {
      stopPolling();
      setPollActive(false);
      if (activeJob.status === 'COMPLETED' && onImportSuccess) {
        onImportSuccess();
      }
    }
  }, [activeJob, stopPolling, onImportSuccess]);

  // ---------------------------------------------------------------------------
  // Derived data
  // ---------------------------------------------------------------------------

  const profiles = profilesData?.opentideHefPublishProfiles ?? [];
  const rawBundles: HefBundleDescriptor[] = bundlesData?.listHefBundles ?? [];

  const selectedProfile = profiles.find((p: { id: string }) => p.id === selectedProfileId);

  // Collect all unique techniques and statuses for filter options
  const allTechniques = Array.from(new Set(rawBundles.flatMap((b: HefBundleDescriptor) => b.techniques)));
  const allStatuses = Array.from(new Set(rawBundles.map((b: HefBundleDescriptor) => b.status).filter(Boolean)));

  const filteredBundles = rawBundles.filter((b: HefBundleDescriptor) => {
    const search = bundleSearch.toLowerCase();
    const matchesSearch =
      !search ||
      b.path.toLowerCase().includes(search) ||
      (b.mdrTitle || '').toLowerCase().includes(search);
    const matchesTechnique =
      techniqueFilter.length === 0 || b.techniques.some(t => techniqueFilter.includes(t));
    const matchesStatus = statusFilter.length === 0 || statusFilter.includes(b.status);
    return matchesSearch && matchesTechnique && matchesStatus;
  });

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const handleReset = useCallback(() => {
    setCurrentStep(0);
    setSelectedProfileId(null);
    setManualRepoOwner('');
    setManualRepoName('');
    setManualBranch('main');
    setManualTargetFolder('');
    setCommitSha('');
    setUseManualMode(false);
    setBundleSearch('');
    setTechniqueFilter([]);
    setStatusFilter([]);
    setSelectedRowKeys([]);
    setSelectedBundles([]);
    setConflictMode('NEW_COPY');
    setImportPlatformRules(true);
    setDryRun(false);
    setActiveJobId(null);
    setPollActive(false);
  }, []);

  const handleClose = useCallback(() => {
    handleReset();
    onClose();
  }, [handleReset, onClose]);

  // Step 1 → 2: fetch bundles
  const handleLoadBundles = useCallback(() => {
    const vars: Record<string, unknown> = {
      commitSha: commitSha || undefined,
    };
    if (!useManualMode && selectedProfileId) {
      vars.profileId = selectedProfileId;
    } else {
      vars.repoOwner = manualRepoOwner;
      vars.repoName = manualRepoName;
      vars.branch = manualBranch || 'main';
      vars.targetFolder = manualTargetFolder || undefined;
    }
    fetchBundles({ variables: vars });
    setCurrentStep(1);
  }, [
    useManualMode, selectedProfileId, manualRepoOwner, manualRepoName,
    manualBranch, manualTargetFolder, commitSha, fetchBundles,
  ]);

  // Step 2 → 3: populate selectedBundles from selection
  const handleProceedToNaming = useCallback(() => {
    const bundles = rawBundles
      .filter((b: HefBundleDescriptor) => selectedRowKeys.includes(b.path))
      .map((b: HefBundleDescriptor) => ({
        path: b.path,
        workbenchName: b.mdrTitle || b.path.split('/').pop() || b.path,
        mdrTitle: b.mdrTitle,
        mdrUuid: b.mdrUuid,
        status: b.status,
        techniques: b.techniques,
        valid: b.valid,
        validationErrors: b.validationErrors,
      }));
    setSelectedBundles(bundles);
    setCurrentStep(2);
  }, [rawBundles, selectedRowKeys]);

  // Step 4: submit the import job
  const handleQueueImport = useCallback(async () => {
    try {
      const vars: Record<string, unknown> = {
        selectedBundles: selectedBundles.map(b => b.path),
        conflictMode,
        importPlatformRules,
        dryRun,
        commitSha: commitSha || undefined,
      };
      if (!useManualMode && selectedProfileId) {
        vars.profileId = selectedProfileId;
      } else {
        vars.repoOwner = manualRepoOwner;
        vars.repoName = manualRepoName;
        vars.branch = manualBranch || 'main';
        vars.targetFolder = manualTargetFolder || undefined;
      }
      const result = await queueImport({ variables: vars });
      const taskId = result?.data?.queueOpentideHefImport?.taskId;
      if (taskId) {
        setActiveJobId(taskId);
        setPollActive(true);
        setCurrentStep(4);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      console.error('HEF import queue error:', message);
    }
  }, [
    selectedBundles, conflictMode, importPlatformRules, dryRun, commitSha,
    useManualMode, selectedProfileId, manualRepoOwner, manualRepoName,
    manualBranch, manualTargetFolder, queueImport,
  ]);

  // ---------------------------------------------------------------------------
  // Step 1 — Source
  // ---------------------------------------------------------------------------

  const renderStep1 = () => (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Radio.Group
        value={useManualMode ? 'manual' : 'profile'}
        onChange={e => setUseManualMode(e.target.value === 'manual')}
      >
        <Space direction="vertical">
          <Radio value="profile">Use an existing HEF Publish Profile</Radio>
          <Radio value="manual">Specify repository manually</Radio>
        </Space>
      </Radio.Group>

      {!useManualMode ? (
        profilesLoading ? (
          <Spin />
        ) : profiles.length === 0 ? (
          <Alert
            type="warning"
            message="No HEF Publish Profiles found"
            description="Create a HEF Publish Profile in Settings, or switch to manual mode."
          />
        ) : (
          <Select
            style={{ width: '100%' }}
            placeholder="Select a HEF Publish Profile..."
            value={selectedProfileId}
            onChange={setSelectedProfileId}
            options={profiles.map((p: { id: string; name: string; repositoryName: string; branch: string; targetFolder: string }) => ({
              value: p.id,
              label: `${p.name} (${p.repositoryName || 'unknown repo'} @ ${p.branch})`,
            }))}
          />
        )
      ) : (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space style={{ width: '100%' }}>
            <Input
              placeholder="Owner (e.g. my-org)"
              value={manualRepoOwner}
              onChange={e => setManualRepoOwner(e.target.value)}
              prefix={<GithubOutlined />}
              style={{ flex: 1 }}
            />
            <Input
              placeholder="Repository (e.g. detection-rules)"
              value={manualRepoName}
              onChange={e => setManualRepoName(e.target.value)}
              style={{ flex: 1 }}
            />
          </Space>
          <Space style={{ width: '100%' }}>
            <Input
              placeholder="Branch (default: main)"
              value={manualBranch}
              onChange={e => setManualBranch(e.target.value)}
              style={{ flex: 1 }}
            />
            <Input
              placeholder="Target folder (optional)"
              value={manualTargetFolder}
              onChange={e => setManualTargetFolder(e.target.value)}
              style={{ flex: 1 }}
            />
          </Space>
        </Space>
      )}

      <div>
        <Text type="secondary">
          Pin to a specific commit SHA for point-in-time restore (leave blank for latest):
        </Text>
        <Input
          placeholder="Commit SHA (optional, e.g. a1b2c3d4...)"
          value={commitSha}
          onChange={e => setCommitSha(e.target.value)}
          style={{ marginTop: 4, fontFamily: 'monospace' }}
          maxLength={40}
        />
      </div>

      {!useManualMode && selectedProfile && (
        <Alert
          type="info"
          message={
            <span>
              Repository:{' '}
              <a href={selectedProfile.repositoryUrl} target="_blank" rel="noopener noreferrer">
                {selectedProfile.repositoryName}
              </a>
              {' '}&bull; Branch: <code>{selectedProfile.branch}</code>
              {selectedProfile.targetFolder && (
                <span> &bull; Folder: <code>{selectedProfile.targetFolder}</code></span>
              )}
            </span>
          }
        />
      )}
    </Space>
  );

  // ---------------------------------------------------------------------------
  // Step 2 — Browse & select bundles
  // ---------------------------------------------------------------------------

  const bundleColumns = [
    {
      title: 'Bundle path',
      dataIndex: 'path',
      key: 'path',
      ellipsis: true,
      render: (path: string) => <code style={{ fontSize: 11 }}>{path}</code>,
    },
    {
      title: 'MDR title',
      dataIndex: 'mdrTitle',
      key: 'mdrTitle',
      ellipsis: true,
      render: (title: string) => title || <Text type="secondary">—</Text>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (status: string) =>
        status ? (
          <Tag
            color={
              status === 'production' ? 'green'
              : status === 'experimental' ? 'orange'
              : 'default'
            }
          >
            {status}
          </Tag>
        ) : null,
    },
    {
      title: 'Techniques',
      dataIndex: 'techniques',
      key: 'techniques',
      width: 160,
      render: (techniques: string[]) =>
        techniques?.length
          ? techniques.slice(0, 3).map((t: string) => (
              <Tag key={t} style={{ fontSize: 10 }}>{t}</Tag>
            )).concat(techniques.length > 3 ? [<Tag key="more">+{techniques.length - 3}</Tag>] : [])
          : null,
    },
    {
      title: 'Validation',
      dataIndex: 'valid',
      key: 'valid',
      width: 90,
      render: (valid: boolean, record: HefBundleDescriptor) =>
        valid ? (
          <Tooltip title="Validation passed">
            <CheckCircleOutlined style={{ color: '#52c41a' }} />
          </Tooltip>
        ) : (
          <Tooltip title={record.validationErrors?.join('\n') || 'Validation failed'}>
            <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
          </Tooltip>
        ),
    },
  ];

  const renderStep2 = () => (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      {bundlesLoading && (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <Spin indicator={<LoadingOutlined spin />} />
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">Scanning repository for OpenTIDE HEF bundles…</Text>
          </div>
        </div>
      )}

      {bundlesError && (
        <Alert
          type="error"
          message="Bundle discovery failed"
          description={bundlesError.message}
        />
      )}

      {!bundlesLoading && !bundlesError && rawBundles.length === 0 && (
        <Alert
          type="warning"
          message="No HEF bundles found"
          description="No folders containing mdr.yaml were found in the target location. Check the repository, branch, and target folder settings."
        />
      )}

      {!bundlesLoading && rawBundles.length > 0 && (
        <>
          <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
            <Space>
              <Input
                prefix={<SearchOutlined />}
                placeholder="Search by path or title…"
                value={bundleSearch}
                onChange={e => setBundleSearch(e.target.value)}
                style={{ width: 220 }}
              />
              <Select
                mode="multiple"
                placeholder="Filter by technique"
                value={techniqueFilter}
                onChange={setTechniqueFilter}
                style={{ minWidth: 160 }}
                maxTagCount={2}
                options={allTechniques.map((t: string) => ({ value: t, label: t }))}
              />
              <Select
                mode="multiple"
                placeholder="Filter by status"
                value={statusFilter}
                onChange={setStatusFilter}
                style={{ minWidth: 140 }}
                options={allStatuses.map((s: string) => ({ value: s, label: s }))}
              />
            </Space>
            <Text type="secondary">
              {selectedRowKeys.length} of {rawBundles.length} selected
            </Text>
          </Space>

          <Table
            rowKey="path"
            dataSource={filteredBundles}
            columns={bundleColumns}
            rowSelection={{
              type: 'checkbox',
              selectedRowKeys,
              onChange: keys => setSelectedRowKeys(keys as string[]),
            }}
            size="small"
            scroll={{ y: 340 }}
            pagination={false}
          />
        </>
      )}
    </Space>
  );

  // ---------------------------------------------------------------------------
  // Step 3 — Naming & conflict handling
  // ---------------------------------------------------------------------------

  const renderStep3 = () => (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Table
        rowKey="path"
        dataSource={selectedBundles}
        size="small"
        pagination={false}
        scroll={{ y: 220 }}
        columns={[
          {
            title: 'Bundle',
            dataIndex: 'path',
            key: 'path',
            ellipsis: true,
            render: (p: string) => <code style={{ fontSize: 11 }}>{p}</code>,
          },
          {
            title: 'Workbench name',
            dataIndex: 'workbenchName',
            key: 'workbenchName',
            render: (name: string, _record: SelectedBundle, index: number) => (
              <Input
                value={name}
                onChange={e => {
                  const updated = [...selectedBundles];
                  updated[index] = { ...updated[index], workbenchName: e.target.value };
                  setSelectedBundles(updated);
                }}
                size="small"
              />
            ),
          },
          {
            title: 'Valid',
            dataIndex: 'valid',
            key: 'valid',
            width: 60,
            render: (valid: boolean) =>
              valid
                ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
                : <CloseCircleOutlined style={{ color: '#ff4d4f' }} />,
          },
        ]}
      />

      <Space direction="vertical" style={{ width: '100%' }}>
        <div>
          <Text strong>On conflict (MDR UUID already exists):</Text>
          <Select
            style={{ width: '100%', marginTop: 4 }}
            value={conflictMode}
            onChange={v => setConflictMode(v as 'NEW_COPY' | 'OVERWRITE' | 'SKIP')}
            options={CONFLICT_MODES}
          />
        </div>

        <Space>
          <Checkbox
            checked={importPlatformRules}
            onChange={e => setImportPlatformRules(e.target.checked)}
          >
            Also import per-platform rule files (kql, splunk, sigma, wazuh, qradar)
          </Checkbox>
        </Space>

        <Space>
          <Checkbox
            checked={dryRun}
            onChange={e => setDryRun(e.target.checked)}
          >
            Dry-run (validate only, do not create Workbenches)
          </Checkbox>
        </Space>
      </Space>
    </Space>
  );

  // ---------------------------------------------------------------------------
  // Step 4 — Confirm
  // ---------------------------------------------------------------------------

  const renderStep4 = () => {
    const invalidCount = selectedBundles.filter(b => !b.valid).length;
    return (
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Alert
          type={dryRun ? 'info' : 'warning'}
          message={dryRun ? 'Dry-run mode — no Workbenches will be created' : 'Ready to import'}
          description={
            dryRun
              ? `HEFAISTOS will validate ${selectedBundles.length} bundle(s) and report what would happen, but no Workbenches will be created.`
              : `${selectedBundles.length} Workbench(es) will be created from the selected HEF bundles.`
          }
        />

        {invalidCount > 0 && (
          <Alert
            type="warning"
            message={`${invalidCount} bundle(s) failed validation`}
            description="Invalid bundles will be skipped during import regardless of conflict mode."
          />
        )}

        <Space direction="vertical" style={{ width: '100%' }}>
          <Text><Text strong>Source:</Text>{' '}
            {!useManualMode && selectedProfile
              ? `${selectedProfile.repositoryName} @ ${selectedProfile.branch}`
              : `${manualRepoOwner}/${manualRepoName} @ ${manualBranch || 'main'}`}
          </Text>
          {commitSha && (
            <Text><Text strong>Commit SHA:</Text> <code>{commitSha}</code></Text>
          )}
          <Text><Text strong>Bundles:</Text> {selectedBundles.length}</Text>
          <Text><Text strong>Conflict mode:</Text> {CONFLICT_MODES.find(m => m.value === conflictMode)?.label}</Text>
          <Text><Text strong>Import platform rules:</Text> {importPlatformRules ? 'Yes' : 'No'}</Text>
          <Text><Text strong>Dry-run:</Text> {dryRun ? 'Yes' : 'No'}</Text>
        </Space>

        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
          Clicking <Text strong>Start Import</Text> will enqueue a background job. You can close this
          dialog and the import will continue running — check progress in the hub.
        </Paragraph>
      </Space>
    );
  };

  // ---------------------------------------------------------------------------
  // Step 5 — Progress
  // ---------------------------------------------------------------------------

  const renderStep5 = () => {
    if (!activeJob) {
      return (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <Spin indicator={<LoadingOutlined spin />} />
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">Loading job status…</Text>
          </div>
        </div>
      );
    }

    const statusColor: Record<string, string> = {
      QUEUED: 'default',
      PROCESSING: 'processing',
      COMPLETED: 'success',
      FAILED: 'error',
    };

    return (
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Space>
          <Badge status={statusColor[activeJob.status] as 'default' | 'processing' | 'success' | 'error'} />
          <Text strong>{activeJob.status}</Text>
          {activeJob.progress && <Text type="secondary">— {activeJob.progress}</Text>}
          {(activeJob.status === 'QUEUED' || activeJob.status === 'PROCESSING') && (
            <Spin size="small" />
          )}
        </Space>

        {activeJob.errorMessage && (
          <Alert type="error" message="Job error" description={activeJob.errorMessage} />
        )}

        {activeJob.results && activeJob.results.length > 0 && (
          <Table
            rowKey="bundlePath"
            dataSource={activeJob.results}
            size="small"
            pagination={false}
            scroll={{ y: 280 }}
            columns={[
              {
                title: 'Bundle',
                dataIndex: 'bundlePath',
                key: 'bundlePath',
                ellipsis: true,
                render: (p: string) => <code style={{ fontSize: 11 }}>{p}</code>,
              },
              {
                title: 'Status',
                dataIndex: 'status',
                key: 'status',
                width: 110,
                render: (s: string) => (
                  <Tag
                    color={
                      s === 'CREATED' || s === 'UPDATED' ? 'green'
                      : s === 'SKIPPED' ? 'default'
                      : s === 'FAILED' ? 'red'
                      : s === 'DRY_RUN_OK' ? 'blue'
                      : 'default'
                    }
                  >
                    {s}
                  </Tag>
                ),
              },
              {
                title: 'Workbench',
                dataIndex: 'workbenchId',
                key: 'workbenchId',
                width: 100,
                render: (id: string | null) =>
                  id ? (
                    <Tooltip title="Open Workbench">
                      <Button
                        type="link"
                        size="small"
                        icon={<LinkOutlined />}
                        onClick={() => navigate(`/playbooks/${id}`)}
                      />
                    </Tooltip>
                  ) : null,
              },
              {
                title: 'Errors',
                dataIndex: 'errors',
                key: 'errors',
                ellipsis: true,
                render: (errors: string[]) =>
                  errors?.length ? (
                    <Tooltip title={errors.join('\n')}>
                      <Text type="danger" style={{ fontSize: 12 }}>{errors[0]}{errors.length > 1 ? ` (+${errors.length - 1})` : ''}</Text>
                    </Tooltip>
                  ) : null,
              },
            ]}
          />
        )}

        {activeJob.status === 'COMPLETED' && (
          <Alert
            type="success"
            message={dryRun ? 'Dry-run completed — no Workbenches were created.' : 'Import completed successfully.'}
          />
        )}
      </Space>
    );
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const step1Valid =
    !useManualMode
      ? !!selectedProfileId
      : !!(manualRepoOwner.trim() && manualRepoName.trim());

  const step2Valid = selectedRowKeys.length > 0;

  const steps = [
    { title: 'Source', description: 'Repository & options' },
    { title: 'Select', description: 'Browse bundles' },
    { title: 'Configure', description: 'Names & conflict' },
    { title: 'Confirm', description: 'Review & queue' },
    { title: 'Progress', description: 'Import status' },
  ];

  const footerButtons = () => {
    if (currentStep === 4) {
      return [
        <Button key="close" onClick={handleClose}>
          Close
        </Button>,
      ];
    }
    if (currentStep === 3) {
      return [
        <Button key="back" onClick={() => setCurrentStep(2)}>
          Back
        </Button>,
        <Button
          key="submit"
          type="primary"
          loading={queuingImport}
          onClick={handleQueueImport}
          icon={<GithubOutlined />}
        >
          {dryRun ? 'Start Dry-run' : 'Start Import'}
        </Button>,
      ];
    }
    if (currentStep === 2) {
      return [
        <Button key="back" onClick={() => setCurrentStep(1)}>
          Back
        </Button>,
        <Button key="next" type="primary" onClick={() => setCurrentStep(3)}>
          Next
        </Button>,
      ];
    }
    if (currentStep === 1) {
      return [
        <Button key="back" onClick={() => setCurrentStep(0)}>
          Back
        </Button>,
        <Button
          key="next"
          type="primary"
          disabled={!step2Valid}
          onClick={handleProceedToNaming}
        >
          Next ({selectedRowKeys.length} selected)
        </Button>,
      ];
    }
    // Step 0
    return [
      <Button key="cancel" onClick={handleClose}>
        Cancel
      </Button>,
      <Button
        key="load"
        type="primary"
        disabled={!step1Valid}
        onClick={handleLoadBundles}
        icon={<GithubOutlined />}
      >
        Load Bundles
      </Button>,
    ];
  };

  return (
    <Modal
      title={
        <Space>
          <GithubOutlined />
          Import Workbenches from OpenTIDE HEF (GitHub)
        </Space>
      }
      open={visible}
      onCancel={currentStep === 4 ? handleClose : undefined}
      closable={currentStep === 4 || currentStep === 0}
      maskClosable={false}
      width={860}
      footer={footerButtons()}
      destroyOnClose
      afterClose={handleReset}
    >
      <Steps
        current={currentStep}
        items={steps}
        size="small"
        style={{ marginBottom: 24 }}
      />

      {currentStep === 0 && renderStep1()}
      {currentStep === 1 && renderStep2()}
      {currentStep === 2 && renderStep3()}
      {currentStep === 3 && renderStep4()}
      {currentStep === 4 && renderStep5()}
    </Modal>
  );
};

export default ImportFromHefModal;
