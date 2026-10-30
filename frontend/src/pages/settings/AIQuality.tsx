import React, { useState } from 'react';
import { gql } from '@apollo/client';
import { useMutation, useQuery } from '@apollo/client/react';
import { Alert, Button, Card, Input, Modal, Select, Space, Table, Tabs, Tag, Typography, message } from 'antd';
import AIFeedbackReview from './AIFeedbackReview';
import AIImprovementProposals from './AIImprovementProposals';
import AIQualityHowTo from '../../components/AIQualityHowTo';

const QUALITY_PROMPTS = gql`
  query AIQualityPrompts($organizationId: UUID, $installation: Boolean!, $language: String!) {
    aiQualityPrompts(organizationId: $organizationId, installation: $installation, language: $language) {
      promptKey title component language configurationId activeVersionId
      defaultVersion defaultInstructions effectiveInstructions effectiveSource effectiveVersion effectiveFingerprint
      inheritedInstructions inheritedSource inheritedFingerprint
      versions {
        id number instructions baseInstructions contentHash changeReason status createdAt
        createdByUsername reviewedByUsername reviewNote diff improvementProposalId
      }
      events { id action reason createdAt actorUsername versionNumber previousVersionNumber }
    }
  }
`;

const ORGANIZATIONS = gql`
  query AIQualityOrganizations { allOrganizations { id name } }
`;

const CREATE_DRAFT = gql`
  mutation CreateQualityPromptDraft($promptKey: String!, $organizationId: UUID, $installation: Boolean!,
    $language: String!, $instructions: String!, $changeReason: String!, $baseFingerprint: String!) {
    createQualityPromptDraft(promptKey: $promptKey, organizationId: $organizationId,
      installation: $installation, language: $language, instructions: $instructions,
      changeReason: $changeReason, baseFingerprint: $baseFingerprint) { version { id } }
  }
`;

const REVIEW_VERSION = gql`
  mutation ReviewQualityPromptVersion($versionId: UUID!, $approve: Boolean!, $reviewNote: String!) {
    reviewQualityPromptVersion(versionId: $versionId, approve: $approve, reviewNote: $reviewNote) {
      version { id status }
    }
  }
`;

const RESTORE_VERSION = gql`
  mutation RestoreQualityPromptVersion($configurationId: UUID!, $versionId: UUID, $reason: String!,
    $expectedFingerprint: String!, $inheritedFingerprint: String) {
    restoreQualityPromptVersion(configurationId: $configurationId, versionId: $versionId, reason: $reason,
      expectedFingerprint: $expectedFingerprint, inheritedFingerprint: $inheritedFingerprint) {
      configurationId
    }
  }
`;

interface PromptVersion {
  id: string;
  number: number;
  instructions: string;
  baseInstructions: string;
  contentHash: string;
  changeReason: string;
  status: 'DRAFT' | 'APPROVED' | 'REJECTED';
  createdAt: string;
  createdByUsername?: string;
  reviewedByUsername?: string;
  reviewNote: string;
  diff: string;
  improvementProposalId?: string;
}

interface AuditEvent {
  id: string;
  action: string;
  reason: string;
  createdAt: string;
  actorUsername?: string;
  versionNumber?: number;
  previousVersionNumber?: number;
}

interface QualityPrompt {
  promptKey: string;
  title: string;
  component: string;
  language: string;
  configurationId?: string;
  activeVersionId?: string;
  defaultVersion: string;
  defaultInstructions: string;
  effectiveInstructions: string;
  effectiveSource: string;
  effectiveVersion: string;
  effectiveFingerprint: string;
  inheritedInstructions: string;
  inheritedSource: string;
  inheritedFingerprint: string;
  versions: PromptVersion[];
  events: AuditEvent[];
}

type Decision = { prompt: QualityPrompt; version?: PromptVersion; action: 'approve' | 'reject' | 'restore' | 'reset' };

const actionLabels: Record<string, string> = {
  DRAFT_CREATED: 'Draft created', APPROVED_ACTIVATED: 'Approved and activated',
  REJECTED: 'Rejected', RESTORED: 'Version restored', RESET_TO_INHERITED: 'Reset to inherited instructions',
};

export default function AIQuality({ isSuperuser }: { isSuperuser: boolean }) {
  const [scope, setScope] = useState(isSuperuser ? 'installation' : 'own');
  const [language, setLanguage] = useState('*');
  const [editor, setEditor] = useState<{ prompt: QualityPrompt; instructions: string; reason: string } | null>(null);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [reviewNote, setReviewNote] = useState('');
  const variables = { installation: scope === 'installation',
    organizationId: scope === 'own' || scope === 'installation' ? null : scope, language };
  const { data, loading, error, refetch } = useQuery<{ aiQualityPrompts: QualityPrompt[] }>(QUALITY_PROMPTS, {
    variables, fetchPolicy: 'network-only',
  });
  const { data: orgs } = useQuery<{ allOrganizations: { id: string; name: string }[] }>(ORGANIZATIONS, {
    skip: !isSuperuser,
  });
  const [createDraft, { loading: creating }] = useMutation(CREATE_DRAFT);
  const [reviewVersion, { loading: reviewing }] = useMutation(REVIEW_VERSION);
  const [restoreVersion, { loading: restoring }] = useMutation(RESTORE_VERSION);
  const busy = creating || reviewing || restoring;

  const openDecision = (value: Decision) => { setReviewNote(''); setDecision(value); };
  const saveDraft = async () => {
    if (!editor) return;
    try {
      await createDraft({ variables: { ...variables, promptKey: editor.prompt.promptKey,
        instructions: editor.instructions, changeReason: editor.reason,
        baseFingerprint: editor.prompt.effectiveFingerprint } });
      setEditor(null);
      message.success('Draft created. Review and approve it to use these instructions.');
      await refetch();
    } catch (err: any) { message.error(err.message || 'Failed to create prompt draft.'); }
  };
  const applyDecision = async () => {
    if (!decision) return;
    try {
      if (decision.action === 'approve' || decision.action === 'reject') {
        await reviewVersion({ variables: { versionId: decision.version!.id,
          approve: decision.action === 'approve', reviewNote } });
      } else {
        await restoreVersion({ variables: { configurationId: decision.prompt.configurationId,
          versionId: decision.version?.id || null, reason: reviewNote,
          expectedFingerprint: decision.prompt.effectiveFingerprint,
          inheritedFingerprint: decision.prompt.inheritedFingerprint } });
      }
      setDecision(null);
      message.success('Prompt configuration updated.');
      await refetch();
    } catch (err: any) { message.error(err.message || 'Failed to update prompt configuration.'); }
  };

  return <div style={{ maxWidth: 1100, margin: '0 auto', padding: 24 }}>
    <Typography.Title level={3}>AI Quality</Typography.Title>
    <Typography.Paragraph>
      Review and improve instructions used by AI rule generation. Drafts take effect after explicit approval.
      Approved local versions survive upgrades and are stored with this installation.
    </Typography.Paragraph>
    <AIQualityHowTo />
    <Space wrap style={{ marginBottom: 16 }}>
      {isSuperuser && <Select className="config-quality-select" classNames={{ popup: { root: 'config-quality-select-dropdown' } }}
        aria-label="Prompt scope" value={scope} onChange={setScope} style={{ minWidth: 240 }}
        options={[{ value: 'own', label: 'My organization' }, { value: 'installation', label: 'Installation default' },
          ...(orgs?.allOrganizations || []).map(org => ({ value: org.id, label: org.name }))]} />}
      <Select className="config-quality-select" classNames={{ popup: { root: 'config-quality-select-dropdown' } }}
        aria-label="Prompt language" value={language} onChange={setLanguage} style={{ minWidth: 170 }}
        options={['*', 'KQL', 'EQL', 'SPL', 'WAZUH', 'AQL', 'OTHER'].map(value => ({
          value, label: value === '*' ? 'All languages' : value,
        }))} />
      <Button onClick={() => refetch()} loading={loading}>Refresh</Button>
    </Space>
    <Alert type="info" showIcon style={{ marginBottom: 16 }} title="Rule generation pilot"
      description="Customize detection guidance here. Review submitted corrections, draft improvements from accepted feedback, and evaluate proposals before activation." />
    {error && <Alert type="error" showIcon title={error.message} style={{ marginBottom: 16 }} />}
    {(data?.aiQualityPrompts || []).map(prompt => <Card key={`${scope}:${language}:${prompt.promptKey}`} title={prompt.title}
      loading={loading} style={{ marginBottom: 16 }} extra={<Space>
        <Tag>{prompt.effectiveSource === 'DEFAULT' ? 'Product default' : prompt.effectiveSource === 'INSTALLATION' ? 'Installation' : 'Organization'}</Tag>
        <Button type="primary" onClick={() => setEditor({ prompt, instructions: prompt.effectiveInstructions, reason: '' })}>New draft</Button>
      </Space>}>
      <Typography.Paragraph><Typography.Text strong>Effective instructions</Typography.Text></Typography.Paragraph>
      <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 300, overflow: 'auto' }}>{prompt.effectiveInstructions}</pre>
      <Space wrap style={{ marginBottom: 16 }}>
        <Typography.Text type="secondary">Product baseline: {prompt.defaultVersion}</Typography.Text>
        {prompt.activeVersionId && <Button onClick={() => openDecision({ prompt, action: 'reset' })}>Use inherited instructions</Button>}
      </Space>
      <Tabs items={[
        { key: 'versions', label: 'Versions and review', children: <Table<PromptVersion> rowKey="id" dataSource={prompt.versions}
          pagination={{ pageSize: 10 }} scroll={{ x: 750 }} columns={[
            { title: 'Version', dataIndex: 'number', render: (number, version) => <Space>v{number}{version.id === prompt.activeVersionId && <Tag color="green">Active</Tag>}</Space> },
            { title: 'Status', dataIndex: 'status', render: status => <Tag color={status === 'APPROVED' ? 'green' : status === 'REJECTED' ? 'red' : 'gold'}>{status}</Tag> },
            { title: 'Reason', dataIndex: 'changeReason' },
            { title: 'Author', dataIndex: 'createdByUsername' },
            { title: 'Actions', render: (_, version) => <Space>
              {version.status === 'DRAFT' && <>
                {version.improvementProposalId ? <Typography.Text type="secondary">Review in Improvement proposals below</Typography.Text>
                  : <Button size="small" onClick={() => openDecision({ prompt, version, action: 'approve' })}>Review</Button>}
                <Button size="small" danger onClick={() => openDecision({ prompt, version, action: 'reject' })}>Reject</Button>
              </>}
              {version.status === 'APPROVED' && version.id !== prompt.activeVersionId && <Button size="small" onClick={() => openDecision({ prompt, version, action: 'restore' })}>Restore</Button>}
            </Space> },
          ]} expandable={{ expandedRowRender: version => <>
            <Typography.Paragraph>{version.reviewNote && `Review: ${version.reviewNote} (${version.reviewedByUsername || 'deleted user'})`}</Typography.Paragraph>
            <pre style={{ whiteSpace: 'pre-wrap' }}>{version.diff || 'No instruction changes.'}</pre>
          </> }} /> },
        { key: 'audit', label: 'Audit history', children: <Table<AuditEvent> rowKey="id" dataSource={prompt.events}
          pagination={{ pageSize: 10 }} columns={[
            { title: 'Time', dataIndex: 'createdAt', render: value => new Date(value).toLocaleString() },
            { title: 'Action', dataIndex: 'action', render: value => actionLabels[value] || value },
            { title: 'User', dataIndex: 'actorUsername' },
            { title: 'Version', dataIndex: 'versionNumber', render: value => value ? `v${value}` : 'Inherited' },
            { title: 'Reason', dataIndex: 'reason' },
          ]} /> },
        { key: 'baseline', label: 'Product baseline', children: <pre style={{ whiteSpace: 'pre-wrap' }}>{prompt.defaultInstructions}</pre> },
      ]} />
    </Card>)}
    {(data?.aiQualityPrompts || []).map(prompt => <Card key={`proposals:${scope}:${language}:${prompt.promptKey}`} title="Improvement proposals" style={{ marginTop: 24 }}>
      <AIImprovementProposals organizationId={variables.organizationId} installation={variables.installation} language={language}
        instructions={prompt.effectiveInstructions} baseFingerprint={prompt.effectiveFingerprint} onChanged={() => { void refetch(); }} />
    </Card>)}
    <Card title="Correction feedback" style={{ marginTop: 24 }}>
      <AIFeedbackReview organizationId={variables.organizationId} allOrganizations={scope === 'installation'} outputFormat={language} />
    </Card>
    <Modal title="Create prompt draft" open={Boolean(editor)} onCancel={() => !busy && setEditor(null)}
      onOk={saveDraft} okText="Create draft" confirmLoading={creating} width={800}
      okButtonProps={{ disabled: !editor?.instructions.trim() || !editor?.reason.trim() }}>
      <Space orientation="vertical" style={{ width: '100%' }}>
        <label htmlFor="quality-instructions">Instructions</label>
        <Input.TextArea id="quality-instructions" value={editor?.instructions || ''} rows={12} maxLength={20000}
          onChange={event => setEditor(current => current && ({ ...current, instructions: event.target.value }))} />
        <label htmlFor="quality-change-reason">Why should these instructions change?</label>
        <Input.TextArea id="quality-change-reason" value={editor?.reason || ''} rows={3} maxLength={4000}
          onChange={event => setEditor(current => current && ({ ...current, reason: event.target.value }))} />
      </Space>
    </Modal>
    <Modal title={decision?.action === 'approve' ? 'Review and approve prompt' : decision?.action === 'reject' ? 'Reject draft' : decision?.action === 'restore' ? 'Restore approved version' : 'Use inherited instructions'}
      open={Boolean(decision)} onCancel={() => !busy && setDecision(null)} onOk={applyDecision} width={800}
      okText={decision?.action === 'approve' ? 'Approve and activate' : decision?.action === 'reject' ? 'Reject draft' : 'Apply'}
      confirmLoading={reviewing || restoring} okButtonProps={{ disabled: !reviewNote.trim(), danger: decision?.action === 'reject' }}>
      {decision?.version && <>
        <Typography.Paragraph><strong>v{decision.version.number}:</strong> {decision.version.changeReason}</Typography.Paragraph>
        <Typography.Paragraph>Proposed instructions</Typography.Paragraph>
        <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto' }}>{decision.version.instructions}</pre>
        {decision.action === 'restore' && <>
          <Typography.Paragraph>Current effective instructions</Typography.Paragraph>
          <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto' }}>{decision.prompt.effectiveInstructions}</pre>
        </>}
        <Typography.Paragraph>Changes from the draft's starting version</Typography.Paragraph>
        <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 240, overflow: 'auto' }}>{decision.version.diff || 'No instruction changes.'}</pre>
      </>}
      {decision?.action === 'reset' && <>
        <Typography.Paragraph>
          This removes the active override for this scope and language. Generation will use these inherited instructions ({decision.prompt.inheritedSource.toLowerCase()}):
        </Typography.Paragraph>
        <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 300, overflow: 'auto' }}>{decision.prompt.inheritedInstructions}</pre>
      </>}
      <label htmlFor="quality-review-note">Review decision and reason</label>
      <Input.TextArea id="quality-review-note" value={reviewNote} onChange={event => setReviewNote(event.target.value)} rows={3} maxLength={4000} />
    </Modal>
  </div>;
}
