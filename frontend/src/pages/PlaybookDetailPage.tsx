import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { gql, DocumentNode } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { Alert, Card, Descriptions, Tag, Typography, Space, Button, Input, message, Select, Slider, Tooltip } from 'antd';
import { useGraphQLErrorHandling } from '../utils/errorHandling';
import { usePlaybookMeta } from '../context/PlaybookMetaContext';
import { LinkManager } from '../components/LinkManager';
import { TagManager } from '../components/TagManager';
import { PushToGitModal } from '../components/PushToGitModal';
import { MarkdownRenderer } from '../components/MarkdownRenderer';

interface GetPlaybookData {
  playbook: any | null;
}

const GET_PLAYBOOK_QUERY = gql`
  query GetPlaybook($id: UUID!) {
    playbook(id: $id) {
      id
      title
      description
      technicalDetails
      status
      playbookType
      updatedAt
      createdAt
      analyticId
      version
      hypothesis
      robustnessLevel
      dataSourceRobustness
      falsePositiveRate
      knownFalsePositives
      exclusionStrategy
      testingProcedures
      triageGuidance
      soarEnrichment
      soarTriage
      soarContainment
      operationalPath
      functionCallGraphs
      executionModalities
      ownerOrganizationName
      isReadOnly
      author { username }
      tags { name }
      detectionRules { id title }
      requiredDataSources { id name }
      mitreAttackMappings {
        id
        techniqueId
        name
      }
      graphs {
        id
        title
        pngSnapshotUrl
      }
    }
  }
`;

  // Available items queries for Linked Content editors
  const SEARCH_RULES_QUERY: DocumentNode = gql`
    query SearchRules($search: String, $limit: Int, $offset: Int) {
      searchRules(search: $search, limit: $limit, offset: $offset) {
        id
        title
        status
        description
      }
    }
  `;

  const GET_ALL_DATASOURCES_QUERY: DocumentNode = gql`
    query GetAllDataSources {
      allDataSources { id name platform description }
    }
  `;

const UPDATE_PLAYBOOK_MUTATION = gql`
  mutation UpdatePlaybook(
    $id: UUID!
    $analyticId: String
    $version: String
    $description: String
    $technicalDetails: String
    $hypothesis: String
    $robustnessLevel: Int
    $dataSourceRobustness: String
    $falsePositiveRate: Int
    $knownFalsePositives: String
    $exclusionStrategy: String
    $testingProcedures: String
    $triageGuidance: String
    $soarEnrichment: String
    $soarTriage: String
    $soarContainment: String
    $operationalPath: String
    $functionCallGraphs: String
    $executionModalities: String
    $playbookType: String
  ) {
    updatePlaybook(
      id: $id
      analyticId: $analyticId
      version: $version
      description: $description
      technicalDetails: $technicalDetails
      hypothesis: $hypothesis
      playbookType: $playbookType
      robustnessLevel: $robustnessLevel
      dataSourceRobustness: $dataSourceRobustness
      falsePositiveRate: $falsePositiveRate
      knownFalsePositives: $knownFalsePositives
      exclusionStrategy: $exclusionStrategy
      testingProcedures: $testingProcedures
      triageGuidance: $triageGuidance
      soarEnrichment: $soarEnrichment
      soarTriage: $soarTriage
      soarContainment: $soarContainment
      operationalPath: $operationalPath
      functionCallGraphs: $functionCallGraphs
      executionModalities: $executionModalities
    ) {
      playbook {
        id
        updatedAt
        analyticId
        version
        playbookType
        hypothesis
        description
        technicalDetails
        robustnessLevel
        dataSourceRobustness
        falsePositiveRate
        knownFalsePositives
        exclusionStrategy
        testingProcedures
        triageGuidance
        soarEnrichment
        soarTriage
        soarContainment
        operationalPath
        functionCallGraphs
        executionModalities
        status
      }
    }
  }
`;

const UPDATE_PLAYBOOK_STATUS_MUTATION = gql`
  mutation UpdatePlaybookStatus($id: UUID!, $status: String!) {
    updatePlaybookStatus(id: $id, status: $status) {
      playbook { id status updatedAt }
    }
  }
`;

const UPLOAD_SNAPSHOT_MUTATION = gql`
  mutation UploadSnapshot($graphId: UUID!, $file: Upload!) {
    uploadGraphSnapshot(graphId: $graphId, file: $file) {
      success
      imageUrl
    }
  }
`;

export const PlaybookDetailPage: React.FC = () => {
  const { playbookId } = useParams<{ playbookId: string }>();
  const { handleError } = useGraphQLErrorHandling('PlaybookDetailPage');

  const { data, loading, error, refetch } = useQuery<GetPlaybookData>(GET_PLAYBOOK_QUERY, {
    variables: { id: playbookId },
    skip: !playbookId,
    context: { componentName: 'PlaybookDetailPage' },
    fetchPolicy: 'network-only', // Always hit backend so admin edits appear immediately
    nextFetchPolicy: 'cache-first'
  });

  const [updatePlaybook, { loading: saving }] = useMutation(UPDATE_PLAYBOOK_MUTATION);
  const [updatePlaybookStatus] = useMutation(UPDATE_PLAYBOOK_STATUS_MUTATION);

  const [isEditing, setIsEditing] = useState(false);
  const [isPushModalOpen, setIsPushModalOpen] = useState(false);

  const [formState, setFormState] = useState({
    analyticId: '',
    version: '',
    description: '',
    technicalDetails: '',
    hypothesis: '',
    robustnessLevel: undefined as number | undefined,
    dataSourceRobustness: '',
    falsePositiveRate: undefined as number | undefined,
    knownFalsePositives: '',
    exclusionStrategy: '',
    testingProcedures: '',
    triageGuidance: '',
    soarEnrichment: '',
    soarTriage: '',
    soarContainment: '',
    operationalPath: '',
    functionCallGraphs: '',
    executionModalities: '',
    status: '',
    playbookType: '',
  });

  const p = data?.playbook;
  const meta = usePlaybookMeta();

  useEffect(() => {
    if (!p) return;
    // Avoid overwriting user input while actively editing (Apollo may deliver new object references)
    if (isEditing) return;
    setFormState({
      analyticId: p.analyticId || '',
      version: p.version || '',
      description: p.description || '',
      technicalDetails: p.technicalDetails || '',
      hypothesis: p.hypothesis || '',
      robustnessLevel: p.robustnessLevel ?? undefined,
      dataSourceRobustness: p.dataSourceRobustness || '',
      falsePositiveRate: p.falsePositiveRate ?? undefined,
      knownFalsePositives: p.knownFalsePositives || '',
      exclusionStrategy: p.exclusionStrategy || '',
      testingProcedures: p.testingProcedures || '',
      triageGuidance: p.triageGuidance || '',
      soarEnrichment: p.soarEnrichment || '',
      soarTriage: p.soarTriage || '',
      soarContainment: p.soarContainment || '',
      operationalPath: p.operationalPath || '',
      functionCallGraphs: p.functionCallGraphs || '',
      executionModalities: p.executionModalities || '',
      status: p.status || '',
      playbookType: p.playbookType || '',
    });
  }, [p, isEditing]);


  if (loading) return <p>Loading playbook...</p>;
  if (error) return <Alert type="error" message={handleError(error)} />;
  if (!p) return <Alert type="warning" message="Playbook not found" />;

  const handleFieldChange = (field: keyof typeof formState, value: string) => {
    setFormState(prev => ({ ...prev, [field]: value }));
  };

  const renderMarkdownValue = (value?: string | null) => {
    if (!value) {
      return 'N/A';
    }

    return <MarkdownRenderer content={value} variant="small" skipEmpty={false} />;
  };

  // Removed unused handleNumberChange to satisfy lint rule

  const handleSave = async () => {
    if (!playbookId) return;
    try {
      // Determine changed fields for success toast
      const labelMap: Record<string, string> = {
        analyticId: 'Analytic ID',
        version: 'Version',
        hypothesis: 'Hypothesis',
        description: 'Description',
        technicalDetails: 'Technical Details',
        robustnessLevel: 'Robustness Level',
        dataSourceRobustness: 'Data Source Robustness',
        falsePositiveRate: 'False Positive Rate',
        knownFalsePositives: 'Known False Positives',
        exclusionStrategy: 'Exclusion Strategy',
        testingProcedures: 'Testing Procedures',
        triageGuidance: 'Triage Guidance',
        soarEnrichment: 'SOAR Enrichment',
        soarTriage: 'SOAR Triage',
        soarContainment: 'SOAR Containment',
        operationalPath: 'Operational Path',
        functionCallGraphs: 'Function Call Graphs',
        executionModalities: 'Execution Modalities',
        playbookType: 'Playbook Type',
        status: 'Status',
      };
      const changed: string[] = [];
      const compare = (key: keyof typeof formState, condition: boolean = true) => {
        if (!condition) return;
        const before = (p as any)[key];
        const after = (formState as any)[key];
        // Normalize undefined/null/empty string for comparison
        const norm = (v: any) => (v === undefined || v === null ? '' : v);
        if (norm(before) !== norm(after)) changed.push(labelMap[key]);
      };
      compare('analyticId');
      compare('version');
      compare('hypothesis');
      compare('description', formState.playbookType === 'DETECTION');
      compare('technicalDetails', formState.playbookType === 'HUNT');
      compare('robustnessLevel', formState.playbookType === 'DETECTION');
      compare('dataSourceRobustness', formState.playbookType === 'DETECTION');
      compare('falsePositiveRate', formState.playbookType === 'DETECTION');
      compare('knownFalsePositives', formState.playbookType === 'DETECTION');
      compare('exclusionStrategy', formState.playbookType === 'DETECTION');
      compare('testingProcedures', formState.playbookType === 'DETECTION');
      compare('triageGuidance', formState.playbookType === 'DETECTION');
      compare('soarEnrichment');
      compare('soarTriage');
      compare('soarContainment');
      compare('operationalPath');
      compare('functionCallGraphs');
      compare('executionModalities');
      compare('playbookType');
      compare('status');

      // Only convert empty string to null for optional (blank=True/null=True) backend fields.
      const optionalKeys = new Set([
        'analyticId','hypothesis','description','robustnessLevel','dataSourceRobustness','falsePositiveRate',
        'knownFalsePositives','exclusionStrategy','testingProcedures','triageGuidance','soarEnrichment','soarTriage',
        'soarContainment','operationalPath','functionCallGraphs','executionModalities','technicalDetails'
      ]);
      const toOptional = (key: string, value: any) => {
        if (value === '') return null; // treat empty string as null to clear optional field
        return value;
      };

      const vars: any = { id: playbookId };
      // Required-ish fields (model does not allow null): version, playbookType
      vars.version = formState.version === '' ? p.version : formState.version;
      vars.playbookType = formState.playbookType === '' ? p.playbookType : formState.playbookType;

      // Optional simple scalar fields
      Object.entries(formState).forEach(([k,v]) => {
        if (k === 'version' || k === 'playbookType' || k === 'status') return; // handled separately
        if (k === 'description') {
          if (formState.playbookType === 'DETECTION') vars.description = toOptional(k, v);
          return;
        }
        if (k === 'technicalDetails') {
          if (formState.playbookType === 'HUNT') vars.technicalDetails = toOptional(k, v);
          return;
        }
        if (optionalKeys.has(k)) {
          vars[k] = toOptional(k, v);
        } else {
          // Non-optional but we already handled above or skip
        }
      });
      // Numeric optional fields keep null if undefined
      vars.robustnessLevel = formState.robustnessLevel ?? null;
      vars.falsePositiveRate = formState.falsePositiveRate ?? null;

      await updatePlaybook({ variables: vars });
      if (formState.status && formState.status !== p.status) {
        await updatePlaybookStatus({ variables: { id: playbookId, status: formState.status } });
      }
      await refetch();
      message.success(
        changed.length
          ? `Updated: ${changed.join(', ')}`
          : 'No field changes detected'
      );
      setIsEditing(false);
    } catch (e: any) {
      const attempted = Object.keys(formState)
        .filter(k => typeof (formState as any)[k] !== 'undefined')
        .join(', ');
      message.error(`${e?.message || 'Update failed'} (attempted: ${attempted})`);
    }
  };

  const statusColor: Record<string, string> = {
    IDEA: 'default',
    RESEARCH: 'gold',
    DEVELOPMENT: 'blue',
    REVIEW: 'purple',
    TESTING: 'volcano',
    DEPLOYED: 'green',
    TUNING: 'orange',
  };

  const fpColor = (value: number | undefined) => {
    if (value === undefined || value === null) return '#d9d9d9';
    if (value >= 80) return '#389e0d';
    if (value >= 50) return '#faad14';
    return '#cf1322';
  };

  const resolveRobustnessLabel = (val: number | undefined) => {
    if (val === undefined || val === null) return 'N/A';
    return meta.byRobustness?.[val] || meta.data?.robustnessLevels?.find(r => r.value === val)?.label || 'N/A';
  };

  const resolveEventRobustnessLabel = (code: string | undefined) => {
    if (!code) return 'N/A';
    return meta.byEventRobustness?.[code] || meta.data?.eventRobustness?.find(r => String(r.value) === String(code))?.label || 'N/A';
  };

  return (
    <Space className="workbench-detail-theme" direction="vertical" style={{ width: '100%' }} size="large">
      <Space align="baseline" style={{ justifyContent: 'space-between', width: '100%' }}>
        <div>
          <Typography.Title level={3} style={{ marginBottom: 4 }}>{p.title}</Typography.Title>
          <Space size="small">
            <Tag color={statusColor[p.status] || 'default'}>{p.status}</Tag>
            <Tag>{p.playbookType}</Tag>
            {p.isReadOnly ? (
              <Tag color="geekblue">Shared template from {p.ownerOrganizationName}</Tag>
            ) : (
              <Tag color="default">Owned by you</Tag>
            )}
          </Space>
        </div>
        <Space>
          {!p.isReadOnly && (
            isEditing ? (
              <>
                <Button onClick={() => setIsEditing(false)} disabled={saving}>Cancel</Button>
                <Button type="primary" onClick={handleSave} loading={saving}>Save</Button>
              </>
            ) : (
              <>
                <Button onClick={() => setIsEditing(true)}>Edit</Button>
                <Button onClick={() => setIsPushModalOpen(true)}>Push to Git</Button>
              </>
            )
          )}
          <Link to="/playbooks">Back to Playbooks</Link>
        </Space>
      </Space>

      {/* --- Top Section: Capability Abstraction --- */}
      <section style={{
        marginBottom: '2rem',
        padding: '1.5rem',
        backgroundColor: 'var(--hef-bg-subtle)',
        border: '2px dashed var(--hef-border)',
        borderRadius: '8px',
        textAlign: 'center'
      }}>
        {p.graphs && p.graphs.length > 0 && p.graphs[0].pngSnapshotUrl ? (
          <div style={{ position: 'relative' }} className="group">
            <img
              src={p.graphs[0].pngSnapshotUrl}
              alt="Capability Map"
              style={{ maxHeight: '256px', margin: '0 auto', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}
            />
            <div style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              opacity: 0,
              backgroundColor: 'color-mix(in srgb, var(--hef-bg-page) 30%, transparent)',
              transition: 'opacity 0.2s'
            }} className="group-hover:opacity-100">
              <Button onClick={() => {
                if (p.graphs && p.graphs.length > 0) {
                  window.location.href = `/playbooks/${p.graphs[0].id}`;
                }
              }}>Edit Graph</Button>
            </div>
          </div>
        ) : (
          <div>
            <Typography.Title level={4} style={{ color: 'var(--hef-text-muted)', marginBottom: '0.5rem' }}>
              No Capability Map Attached
            </Typography.Title>
            <Button
              type="primary"
              onClick={() => {
                // Navigate to create new graph or open modal
                window.location.href = `/playbooks/new?playbookId=${playbookId}`;
              }}
            >
              + Create Abstraction Graph
            </Button>
          </div>
        )}
      </section>

      <Card title="Overview">
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="Analytic ID">
            {isEditing ? (
              <Input
                value={formState.analyticId}
                onChange={e => handleFieldChange('analyticId', e.target.value)}
              />
            ) : (
              p.analyticId || 'N/A'
            )}
          </Descriptions.Item>
          <Descriptions.Item label="Playbook Type">
            {isEditing ? (
              <Select
                value={formState.playbookType}
                onChange={val => setFormState(prev => ({ ...prev, playbookType: val }))}
                style={{ width: '100%' }}
                options={[
                  { label: 'Hunt', value: 'HUNT' },
                  { label: 'Detection', value: 'DETECTION' },
                ]}
              />
            ) : (
              p.playbookType
            )}
          </Descriptions.Item>
          <Descriptions.Item label="Status">
            {isEditing ? (
              <Select
                value={formState.status}
                onChange={val => setFormState(prev => ({ ...prev, status: val }))}
                style={{ width: '100%' }}
                options={[
                  { label: 'Idea / Hypothesis', value: 'IDEA' },
                  { label: 'In Research', value: 'RESEARCH' },
                  { label: 'In Development', value: 'DEVELOPMENT' },
                  { label: 'Peer Review', value: 'REVIEW' },
                  { label: 'Testing / Validation', value: 'TESTING' },
                  { label: 'Deployed', value: 'DEPLOYED' },
                  { label: 'Tuning / Maintenance', value: 'TUNING' },
                ]}
              />
            ) : (
              <Tag color={statusColor[p.status] || 'default'}>{p.status}</Tag>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="Created At">{new Date(p.createdAt).toLocaleString()}</Descriptions.Item>
          <Descriptions.Item label="Last Updated">{new Date(p.updatedAt).toLocaleString()}</Descriptions.Item>
          <Descriptions.Item label="Hypothesis">
            {isEditing ? (
              <Input.TextArea
                value={formState.hypothesis}
                onChange={e => handleFieldChange('hypothesis', e.target.value)}
                rows={3}
              />
            ) : (
              renderMarkdownValue(p.hypothesis)
            )}
          </Descriptions.Item>
          {formState.playbookType === 'DETECTION' && (
            <Descriptions.Item label="Description">
              {isEditing ? (
                <Input.TextArea
                  value={formState.description}
                  onChange={e => handleFieldChange('description', e.target.value)}
                  autoSize={{ minRows: 4, maxRows: 12 }}
                  placeholder="Enter description"
                />
              ) : (
                renderMarkdownValue(p.description)
              )}
            </Descriptions.Item>
          )}
          {formState.playbookType === 'HUNT' && (
            <Descriptions.Item label="Technical Details">
              {isEditing ? (
                <Input.TextArea
                  value={formState.technicalDetails}
                  onChange={e => handleFieldChange('technicalDetails', e.target.value)}
                  autoSize={{ minRows: 4, maxRows: 12 }}
                  placeholder="Enter technical details"
                />
              ) : (
                renderMarkdownValue(p.technicalDetails)
              )}
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      {/* --- VALUATION Sidebar: False Positive Rate --- */}
      <Card title="VALUATION" style={{ maxWidth: 420 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Text strong>False Positive Rate</Typography.Text>
          {isEditing ? (
            <Space direction="vertical" style={{ width: '100%' }}>
              <Input
                type="number"
                min={0}
                max={100}
                value={formState.falsePositiveRate ?? 0}
                onChange={(e) => {
                  const v = Math.max(0, Math.min(100, Number(e.target.value || 0)));
                  setFormState(prev => ({ ...prev, falsePositiveRate: v }));
                }}
                addonAfter="%"
              />
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ flex: 1, height: 8, borderRadius: 4, background: 'var(--hef-border)', overflow: 'hidden' }}>
                  <div
                    style={{
                      width: `${formState.falsePositiveRate ?? 0}%`,
                      height: '100%',
                      backgroundColor: fpColor(formState.falsePositiveRate),
                      transition: 'width 0.2s ease',
                    }}
                  />
                </div>
                <Tag color={fpColor(formState.falsePositiveRate)}>
                  {formState.falsePositiveRate ?? 0}%
                </Tag>
              </div>
              <Typography.Text type="secondary">
                0% = worst (very noisy), 100% = best (ideal)
              </Typography.Text>
            </Space>
          ) : (
            p.falsePositiveRate !== null && p.falsePositiveRate !== undefined ? (
              <Space direction="vertical" style={{ width: '100%' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ flex: 1, height: 8, borderRadius: 4, background: 'var(--hef-border)', overflow: 'hidden' }}>
                    <div
                      style={{
                        width: `${p.falsePositiveRate}%`,
                        height: '100%',
                        backgroundColor: fpColor(p.falsePositiveRate),
                      }}
                    />
                  </div>
                  <Tag color={fpColor(p.falsePositiveRate)}>
                    {p.falsePositiveRate}%
                  </Tag>
                </div>
                <Typography.Text type="secondary">
                  0% = worst (very noisy), 100% = best (ideal)
                </Typography.Text>
              </Space>
            ) : (
              <Typography.Text type="secondary">Not set</Typography.Text>
            )
          )}
        </Space>
      </Card>

      {formState.playbookType === 'DETECTION' && (
      <Card title="Analytic Details">
        <Descriptions column={2} size="small" bordered>
          <Descriptions.Item label="Robustness Level">
            {isEditing ? (
              <Select
                value={formState.robustnessLevel ?? undefined}
                onChange={(val) => setFormState(prev => ({ ...prev, robustnessLevel: val as number }))}
                options={((meta.data?.robustnessLevels && meta.data.robustnessLevels.length)
                  ? meta.data.robustnessLevels
                  : [
                    { value: 1, label: 'Level 1: Ephemeral (IP, Domain, Hash)' },
                    { value: 2, label: 'Level 2: Core to Adversary-Brought Tool' },
                    { value: 3, label: 'Level 3: Core to Pre-Existing Tool (LOLBin)' },
                    { value: 4, label: 'Level 4: Core to Some Implementations' },
                    { value: 5, label: 'Level 5: Core to Technique (Invariant)' },
                  ]).map(o => ({ label: o.label, value: o.value }))}
                loading={meta.loading}
                allowClear
                placeholder="Select level"
                style={{ width: '100%' }}
                notFoundContent={meta.loading ? 'Loading...' : 'No levels'}
              />
            ) : (
              resolveRobustnessLabel(p.robustnessLevel)
            )}
          </Descriptions.Item>
          <Descriptions.Item label="Data Source Robustness">
            {isEditing ? (
              <Select
                value={formState.dataSourceRobustness || undefined}
                onChange={(val) => setFormState(prev => ({ ...prev, dataSourceRobustness: val as string }))}
                options={((meta.data?.eventRobustness && meta.data.eventRobustness.length)
                  ? meta.data.eventRobustness
                  : [
                    { value: 'A', label: 'Application (A)' },
                    { value: 'U', label: 'User-Mode (U)' },
                    { value: 'K', label: 'Kernel-Mode (K)' },
                    { value: 'P', label: 'Protocol Payload (P)' },
                    { value: 'H', label: 'Protocol Header (H)' },
                    { value: 'N', label: 'N/A' },
                  ]).map(o => ({ label: o.label, value: o.value }))}
                loading={meta.loading}
                allowClear
                placeholder="Event source"
                style={{ width: '100%' }}
                notFoundContent={meta.loading ? 'Loading...' : 'No event source options'}
              />
            ) : (
              resolveEventRobustnessLabel(p.dataSourceRobustness)
            )}
          </Descriptions.Item>
          
          <Descriptions.Item label="Known False Positives">
            {isEditing ? (
              <Input.TextArea
                value={formState.knownFalsePositives}
                onChange={e => handleFieldChange('knownFalsePositives', e.target.value)}
                rows={3}
              />
            ) : (
              renderMarkdownValue(p.knownFalsePositives)
            )}
          </Descriptions.Item>
          <Descriptions.Item label="Exclusion Strategy" span={2}>
            {isEditing ? (
              <Input.TextArea
                value={formState.exclusionStrategy}
                onChange={e => handleFieldChange('exclusionStrategy', e.target.value)}
                rows={3}
              />
            ) : (
              renderMarkdownValue(p.exclusionStrategy)
            )}
          </Descriptions.Item>
        </Descriptions>
      </Card>
      )}

      {formState.playbookType === 'DETECTION' && (
      <Card title="Validation & Response">
        <Descriptions column={2} size="small" bordered>
          <Descriptions.Item label="Testing Procedures" span={2}>
            {isEditing ? (
              <Input.TextArea
                value={formState.testingProcedures}
                onChange={e => handleFieldChange('testingProcedures', e.target.value)}
                rows={3}
              />
            ) : (
              renderMarkdownValue(p.testingProcedures)
            )}
          </Descriptions.Item>
          <Descriptions.Item label="Triage Guidance" span={2}>
            {isEditing ? (
              <Input.TextArea
                value={formState.triageGuidance}
                onChange={e => handleFieldChange('triageGuidance', e.target.value)}
                rows={3}
              />
            ) : (
              renderMarkdownValue(p.triageGuidance)
            )}
          </Descriptions.Item>
        </Descriptions>
      </Card>
      )}

      <Card title="Automation (SOAR)">
        <Descriptions column={2} size="small" bordered>
          <Descriptions.Item label="Enrichment" span={2}>
            {isEditing ? (
              <Input.TextArea
                value={formState.soarEnrichment}
                onChange={e => handleFieldChange('soarEnrichment', e.target.value)}
                rows={2}
              />
            ) : (
              renderMarkdownValue(p.soarEnrichment)
            )}
          </Descriptions.Item>
          <Descriptions.Item label="Triage" span={2}>
            {isEditing ? (
              <Input.TextArea
                value={formState.soarTriage}
                onChange={e => handleFieldChange('soarTriage', e.target.value)}
                rows={2}
              />
            ) : (
              renderMarkdownValue(p.soarTriage)
            )}
          </Descriptions.Item>
          <Descriptions.Item label="Containment" span={2}>
            {isEditing ? (
              <Input.TextArea
                value={formState.soarContainment}
                onChange={e => handleFieldChange('soarContainment', e.target.value)}
                rows={2}
              />
            ) : (
              renderMarkdownValue(p.soarContainment)
            )}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="Linked Content">
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="Tags">
            {isEditing ? (
              <TagManager playbookId={p.id} currentTags={p.tags || []} />
            ) : (
              p.tags && p.tags.length ? p.tags.map((t: any) => <Tag key={t.name}>{t.name}</Tag>) : 'None'
            )}
          </Descriptions.Item>
          <Descriptions.Item label="MITRE ATT&CK Mappings">
            {isEditing ? (
              <LinkManager
                playbookId={p.id}
                linkType="attack"
                availableItemsQuery={gql`query AllAttack($search: String, $limit: Int, $offset: Int) { allAttackTechniques(search: $search, limit: $limit, offset: $offset) { id techniqueId name } }`}
                queryDataKey="allAttackTechniques"
                buildVariables={(search?: string) => ({ search: search || '', limit: 50, offset: 0 })}
                currentItems={p.mitreAttackMappings || []}
              />
            ) : (
              p.mitreAttackMappings && p.mitreAttackMappings.length ? (
                <ul>
                  {p.mitreAttackMappings.map((m: any) => (
                    <li key={m.id}>
                      <Typography.Text code>{m.techniqueId}</Typography.Text> {m.name}
                    </li>
                  ))}
                </ul>
              ) : 'None'
            )}
          </Descriptions.Item>
          <Descriptions.Item label="Detection Rules">
            {isEditing ? (
              <LinkManager
                playbookId={p.id}
                linkType="rules"
                availableItemsQuery={SEARCH_RULES_QUERY}
                queryDataKey="searchRules"
                buildVariables={(search?: string) => ({ search: search || '', limit: 50, offset: 0 })}
                currentItems={p.detectionRules || []}
              />
            ) : (
              p.detectionRules && p.detectionRules.length ? (
                <ul>
                  {p.detectionRules.map((r: any) => (
                    <li key={r.id}>{r.title}</li>
                  ))}
                </ul>
              ) : 'None'
            )}
          </Descriptions.Item>
          <Descriptions.Item label="Required Data Sources">
            {isEditing ? (
              <LinkManager
                playbookId={p.id}
                linkType="dataSources"
                availableItemsQuery={GET_ALL_DATASOURCES_QUERY}
                queryDataKey="allDataSources"
                currentItems={p.requiredDataSources || []}
              />
            ) : (
              p.requiredDataSources && p.requiredDataSources.length ? (
                <ul>
                  {p.requiredDataSources.map((d: any) => (
                    <li key={d.id}>{d.name}</li>
                  ))}
                </ul>
              ) : 'None'
            )}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="Abstraction Capability Graphs">
        {p.graphs && p.graphs.length ? (
          <Space direction="vertical" style={{ width: '100%' }}>
            {p.graphs.map((g: any) => (
              <Card
                key={g.id}
                type="inner"
                title={g.title || 'Graph'}
                extra={<Link to={`/playbooks/${g.id}`}>Edit graph</Link>}
              >
                {g.pngSnapshotUrl ? (
                  <img
                    src={g.pngSnapshotUrl}
                    alt={g.title || 'Graph snapshot'}
                    style={{ maxWidth: '100%', borderRadius: 4, border: '1px solid var(--hef-border)' }}
                  />
                ) : (
                  <Typography.Text type="secondary">
                    No snapshot captured yet. Open the graph and use the snapshot action.
                  </Typography.Text>
                )}
              </Card>
            ))}
          </Space>
        ) : (
          <Typography.Text type="secondary">
            No abstraction capability graphs attached yet.
          </Typography.Text>
        )}
      </Card>

      <PushToGitModal 
        isOpen={isPushModalOpen}
        onClose={() => setIsPushModalOpen(false)}
        graphId={(p.graphs && p.graphs.length > 0) ? p.graphs[0].id : undefined}
      />
    </Space>
  );
};
