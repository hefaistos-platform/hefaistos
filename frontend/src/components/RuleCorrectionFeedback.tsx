import React, { useState } from 'react';
import { gql } from '@apollo/client';
import { useMutation, useQuery } from '@apollo/client/react';
import { Alert, Button, Input, Modal, Select, Space, Tag, Typography, message } from 'antd';

const CANDIDATES = gql`
  query RuleCorrectionCandidates($playbookId: UUID, $ruleId: ID) {
    aiRuleCorrectionCandidates(playbookId: $playbookId, ruleId: $ruleId) {
      id ruleTitle outputFormat revisionNumber variant before after diff
    }
  }
`;
const SUBMIT = gql`
  mutation SubmitRuleCorrectionFeedback($feedbackId: UUID!, $issues: [AICorrectionIssueInput!]!,
    $verification: String!, $verificationEvidence: String) {
    submitRuleCorrectionFeedback(feedbackId: $feedbackId, issues: $issues,
      verification: $verification, verificationEvidence: $verificationEvidence) { feedback { id status } }
  }
`;
const DISMISS = gql`
  mutation DismissRuleCorrectionFeedback($feedbackId: UUID!, $reason: String!) {
    dismissRuleCorrectionFeedback(feedbackId: $feedbackId, reason: $reason) { feedback { id status } }
  }
`;

export interface CorrectionCandidate {
  id: string; ruleTitle: string; outputFormat: string; revisionNumber: number;
  variant: string; before: string; after: string; diff: string;
}

export const CORRECTION_CATEGORIES = [
  ['incorrect_table', 'Incorrect table'], ['incorrect_field', 'Incorrect field'],
  ['incorrect_logic', 'Detection logic'], ['syntax', 'Syntax'], ['missing_context', 'Missing context'],
  ['false_positives', 'False positives'], ['output_structure', 'Output structure'],
  ['formatting', 'Formatting'], ['changed_requirements', 'Changed requirements'], ['other', 'Other'],
].map(([value, label]) => ({ value, label }));

export default function RuleCorrectionFeedback({ playbookId, ruleId, refreshKey = 0 }: {
  playbookId?: string; ruleId?: string; refreshKey?: number;
}) {
  const { data, error, refetch } = useQuery<{ aiRuleCorrectionCandidates: CorrectionCandidate[] }>(CANDIDATES, {
    variables: { playbookId: playbookId || null, ruleId: ruleId || null },
    skip: !playbookId && !ruleId, fetchPolicy: 'network-only',
  });
  React.useEffect(() => { if (refreshKey && (playbookId || ruleId)) void refetch().catch(() => {}); }, [refreshKey, playbookId, ruleId, refetch]);
  const [submit, { loading: submitting }] = useMutation(SUBMIT);
  const [dismiss, { loading: dismissing }] = useMutation(DISMISS);
  const [candidate, setCandidate] = useState<CorrectionCandidate | null>(null);
  const [dismissMode, setDismissMode] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);
  const [explanation, setExplanation] = useState('');
  const [resolution, setResolution] = useState('');
  const [verification, setVerification] = useState('NOT_TESTED');
  const [evidence, setEvidence] = useState('');
  const open = (item: CorrectionCandidate, dismissOnly = false) => {
    setCandidate(item); setDismissMode(dismissOnly); setCategories([]); setExplanation('');
    setResolution(''); setVerification('NOT_TESTED'); setEvidence('');
  };
  const save = async () => {
    if (!candidate) return;
    try {
      if (dismissMode) await dismiss({ variables: { feedbackId: candidate.id, reason: explanation } });
      else await submit({ variables: { feedbackId: candidate.id,
        issues: categories.map(category => ({ category, explanation, resolution })), verification, verificationEvidence: evidence } });
      setCandidate(null);
      message.success(dismissMode ? 'Correction candidate dismissed.' : 'Feedback submitted for admin review.');
      await refetch();
    } catch (err: any) { message.error(err.message || 'Failed to save correction feedback.'); }
  };
  const candidates = data?.aiRuleCorrectionCandidates || [];
  return <>
    {error && <Alert type="error" title="Could not load AI correction feedback" description={error.message} />}
    {candidates.length > 0 && <Alert type="info" showIcon title="Saved rules differ from their AI-generated versions"
      description={<Space orientation="vertical">
        <Typography.Text>Explain a correction for admin review, or dismiss it if the edit was intentional.</Typography.Text>
        {candidates.map(item => <Space key={item.id} wrap><Tag>{item.outputFormat} · revision {item.revisionNumber}</Tag>
          <Button size="small" onClick={() => open(item)}>Explain correction</Button>
          <Button size="small" onClick={() => open(item, true)}>Intentional edit / dismiss</Button>
        </Space>)}
      </Space>} />}
    <Modal open={Boolean(candidate)} width={850} title={dismissMode ? 'Dismiss correction candidate' : 'Explain AI rule correction'}
      onCancel={() => !submitting && !dismissing && setCandidate(null)} onOk={save}
      okText={dismissMode ? 'Dismiss candidate' : 'Submit feedback'} confirmLoading={submitting || dismissing}
      okButtonProps={{ disabled: !explanation.trim() || (!dismissMode && (!categories.length || !resolution.trim() || (verification !== 'NOT_TESTED' && !evidence.trim()))) }}>
      {candidate && <>
        <Typography.Paragraph>{candidate.ruleTitle} · {candidate.outputFormat} · {candidate.variant} variant · saved revision {candidate.revisionNumber}</Typography.Paragraph>
        <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 260, overflow: 'auto' }}>{candidate.diff}</pre>
      </>}
      <Space orientation="vertical" style={{ width: '100%' }}>
        {!dismissMode && <><label htmlFor="correction-categories">What changed?</label>
          <Select id="correction-categories" aria-label="What changed?" mode="multiple" style={{ width: '100%' }} value={categories} options={CORRECTION_CATEGORIES} onChange={setCategories} />
        </>}
        <label htmlFor="correction-explanation">{dismissMode ? 'Why is this an intentional edit?' : 'What was wrong?'}</label>
        <Input.TextArea id="correction-explanation" value={explanation} onChange={e => setExplanation(e.target.value)} rows={3} maxLength={4000} />
        {!dismissMode && <>
          <label htmlFor="correction-resolution">How was it resolved?</label>
          <Input.TextArea id="correction-resolution" value={resolution} onChange={e => setResolution(e.target.value)} rows={3} maxLength={4000} />
          <label htmlFor="correction-verification">How was the correction checked?</label>
          <Select id="correction-verification" aria-label="How was the correction checked?" value={verification} style={{ width: '100%' }} onChange={setVerification}
            options={[{ value: 'NOT_TESTED', label: 'Not tested' }, { value: 'SYNTAX_CHECKED', label: 'Syntax checked' },
              { value: 'SAMPLE_DATA_TESTED', label: 'Tested against sample data' }, { value: 'REVIEWER_APPROVED', label: 'Approved by a reviewer' }]} />
          <label htmlFor="correction-evidence">Verification evidence {verification === 'NOT_TESTED' ? '(optional)' : '(required)'}</label>
          <Input.TextArea id="correction-evidence" value={evidence} onChange={e => setEvidence(e.target.value)} rows={2} maxLength={4000} />
          <Typography.Text type="secondary">Feedback is reviewed separately from prompt changes. Submission does not activate new instructions.</Typography.Text>
        </>}
      </Space>
    </Modal>
  </>;
}
