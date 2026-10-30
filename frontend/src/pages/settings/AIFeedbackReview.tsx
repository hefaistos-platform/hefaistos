import React, { useState } from 'react';
import { gql } from '@apollo/client';
import { useMutation, useQuery } from '@apollo/client/react';
import { Alert, Button, Input, Modal, Select, Space, Table, Tabs, Tag, Typography, message } from 'antd';

const FEEDBACK = gql`
  query AIQualityFeedback($organizationId: UUID, $allOrganizations: Boolean!, $status: String!, $outputFormat: String) {
    aiQualityFeedback(organizationId: $organizationId, allOrganizations: $allOrganizations, status: $status, outputFormat: $outputFormat) {
      id status ruleTitle outputFormat revisionNumber correctionAuthor variant diff before after issues
      verification verificationEvidence submittedUsername reviewedUsername rootCause reviewNote
      promptProvenance machineReadable events { id action actorUsername reason createdAt }
    }
  }
`;
const REVIEW = gql`
  mutation ReviewRuleCorrectionFeedback($feedbackId: UUID!, $accept: Boolean!, $rootCause: String!, $reviewNote: String!) {
    reviewRuleCorrectionFeedback(feedbackId: $feedbackId, accept: $accept, rootCause: $rootCause, reviewNote: $reviewNote) {
      feedback { id status }
    }
  }
`;
interface Feedback {
  id: string; status: string; ruleTitle: string; outputFormat: string; revisionNumber: number;
  correctionAuthor: string; variant: string; diff: string; before: string; after: string;
  issues: string; verification: string; verificationEvidence: string; submittedUsername: string;
  reviewedUsername: string; rootCause: string; reviewNote: string; promptProvenance: string; machineReadable: string;
  events: Array<{ id: string; action: string; actorUsername: string; reason: string; createdAt: string }>;
}
const pretty = (json: string) => { try { return JSON.stringify(JSON.parse(json), null, 2); } catch { return json; } };

export default function AIFeedbackReview({ organizationId, allOrganizations, outputFormat }: {
  organizationId?: string | null; allOrganizations: boolean; outputFormat: string;
}) {
  const [status, setStatus] = useState('SUBMITTED');
  const { data, loading, error, refetch } = useQuery<{ aiQualityFeedback: Feedback[] }>(FEEDBACK, {
    variables: { organizationId: organizationId || null, allOrganizations, status, outputFormat }, fetchPolicy: 'network-only',
  });
  const [review, { loading: reviewing }] = useMutation(REVIEW);
  const [selected, setSelected] = useState<Feedback | null>(null);
  const [accept, setAccept] = useState(true);
  const [cause, setCause] = useState('UNKNOWN');
  const [note, setNote] = useState('');
  const open = (item: Feedback, accepted: boolean) => { setSelected(item); setAccept(accepted); setCause('UNKNOWN'); setNote(''); };
  const save = async () => {
    if (!selected) return;
    try {
      await review({ variables: { feedbackId: selected.id, accept, rootCause: cause, reviewNote: note } });
      setSelected(null); await refetch(); message.success('Feedback review recorded.');
    } catch (err: any) { message.error(err.message || 'Failed to review feedback.'); }
  };
  const evidence = (item: Feedback) => <Tabs items={[
    { key: 'correction', label: 'Correction and explanation', children: <>
      <Typography.Paragraph>Generated {item.variant} variant → saved revision {item.revisionNumber} by {item.correctionAuthor}</Typography.Paragraph>
      <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 300, overflow: 'auto' }}>{item.diff}</pre>
      <pre style={{ whiteSpace: 'pre-wrap' }}>{pretty(item.issues)}</pre>
      <Typography.Paragraph>User-reported verification: {item.verification}. {item.verificationEvidence}</Typography.Paragraph>
      {item.reviewNote && <Typography.Paragraph>Review by {item.reviewedUsername}: {item.rootCause} — {item.reviewNote}</Typography.Paragraph>}
    </> },
    { key: 'input', label: 'Generation context and prompts', children: <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 400, overflow: 'auto' }}>{pretty(item.promptProvenance)}</pre> },
    { key: 'json', label: 'Machine-readable feedback', children: <Input.TextArea aria-label="Machine-readable feedback" readOnly rows={18} value={pretty(item.machineReadable)} /> },
    { key: 'audit', label: 'Audit history', children: <Table rowKey="id" pagination={false} dataSource={item.events} columns={[
      { title: 'Action', dataIndex: 'action' }, { title: 'User', dataIndex: 'actorUsername' }, { title: 'Reason', dataIndex: 'reason' },
    ]} /> },
  ]} />;
  return <Space orientation="vertical" style={{ width: '100%' }}>
    <Alert type="info" showIcon title="Review correction evidence"
      description="Accept useful feedback and classify its likely cause. Prompt, context, and retrieval changes require their own approval; accepting feedback does not change AI behavior." />
    <Space><Select className="config-quality-select" classNames={{ popup: { root: 'config-quality-select-dropdown' } }}
      aria-label="Feedback status" value={status} onChange={setStatus} style={{ width: 240 }}
      options={['SUBMITTED', 'ACCEPTED', 'REJECTED', 'CANDIDATE', 'DISMISSED', 'SUPERSEDED'].map(value => ({ value, label: value.toLowerCase().replace('_', ' ') }))} />
      <Button loading={loading} onClick={() => refetch()}>Refresh feedback</Button></Space>
    {error && <Alert type="error" title={error.message} />}
    <Table<Feedback> rowKey="id" loading={loading} dataSource={data?.aiQualityFeedback || []} pagination={{ pageSize: 10 }}
      expandable={{ expandedRowRender: evidence }} columns={[
        { title: 'Rule', dataIndex: 'ruleTitle' }, { title: 'Format', dataIndex: 'outputFormat' },
        { title: 'Submitted by', dataIndex: 'submittedUsername' }, { title: 'Status', dataIndex: 'status', render: value => <Tag>{value}</Tag> },
        { title: 'Review', render: (_, item) => item.status === 'SUBMITTED' ? <Space>
          <Button size="small" onClick={() => open(item, true)}>Review and accept</Button>
          <Button size="small" danger onClick={() => open(item, false)}>Reject</Button>
        </Space> : null },
      ]} />
    <Modal open={Boolean(selected)} onCancel={() => !reviewing && setSelected(null)} width={950} onOk={save}
      title={accept ? 'Accept correction feedback for improvement analysis' : 'Reject correction feedback'}
      okText={accept ? 'Accept feedback' : 'Reject feedback'} confirmLoading={reviewing} okButtonProps={{ disabled: !note.trim(), danger: !accept }}>
      {selected && evidence(selected)}
      <Space orientation="vertical" style={{ width: '100%' }}>
        <label htmlFor="feedback-root-cause">Likely root cause</label>
        <Select className="config-quality-select" classNames={{ popup: { root: 'config-quality-select-dropdown' } }}
          id="feedback-root-cause" aria-label="Likely root cause" value={cause} onChange={setCause} style={{ width: '100%' }}
          options={['UNKNOWN', 'PROMPT', 'CONTEXT', 'RETRIEVAL', 'SCHEMA_MAPPING', 'APPLICATION', 'MODEL', 'USER_PREFERENCE'].map(value => ({ value, label: value.toLowerCase().replace('_', ' ') }))} />
        <label htmlFor="feedback-review-note">Review reason</label>
        <Input.TextArea id="feedback-review-note" rows={3} maxLength={4000} value={note} onChange={e => setNote(e.target.value)} />
      </Space>
    </Modal>
  </Space>;
}
