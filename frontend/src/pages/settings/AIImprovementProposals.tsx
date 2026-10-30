import React, { useEffect, useState } from 'react';
import { gql } from '@apollo/client';
import { useMutation, useQuery } from '@apollo/client/react';
import { Alert, Button, Card, Col, Input, Modal, Row, Select, Space, Table, Tag, Typography, message } from 'antd';

const SELECT_THEME = { className: 'config-quality-select', classNames: { popup: { root: 'config-quality-select-dropdown' } } };
const ACCEPTED = gql`query ImprovementFeedback($organizationId: UUID, $allOrganizations: Boolean!, $outputFormat: String) {
  aiQualityFeedback(organizationId: $organizationId, allOrganizations: $allOrganizations, status: "ACCEPTED", outputFormat: $outputFormat) {
    id ruleTitle outputFormat rootCause diff machineReadable
  }
}`;
const PROPOSALS = gql`query AIImprovementProposals($organizationId: UUID, $installation: Boolean!, $language: String!) {
  aiImprovementProposals(organizationId: $organizationId, installation: $installation, language: $language) {
    id evidence cases evaluationReady createdAt
    version { id number status instructions baseInstructions baseFingerprint changeReason diff reviewNote }
    evaluations { id status resultData preparedEvidence errorMessage createdAt assessment { id cases reviewerUsername } }
  }
}`;
const SUGGEST = gql`mutation StartAIImprovementDraft($organizationId: UUID, $installation: Boolean!, $language: String!, $feedbackIds: [UUID!]!, $baseFingerprint: String!) {
  startAiImprovementDraft(organizationId: $organizationId, installation: $installation, language: $language,
    feedbackIds: $feedbackIds, baseFingerprint: $baseFingerprint) { taskId }
}`;
const TASK = gql`query AIImprovementDraftTask($taskId: UUID!) {
  aiImprovementDraftTask(taskId: $taskId) { id status resultData errorMessage }
}`;
const CREATE = gql`mutation CreateAIImprovementProposal($organizationId: UUID, $installation: Boolean!, $language: String!,
  $instructions: String!, $changeReason: String!, $baseFingerprint: String!, $cases: [ImprovementCaseInput!]!) {
  createAiImprovementProposal(organizationId: $organizationId, installation: $installation, language: $language,
    instructions: $instructions, changeReason: $changeReason, baseFingerprint: $baseFingerprint, cases: $cases) { proposal { id } }
}`;
const EVALUATE = gql`mutation StartAIImprovementEvaluation($proposalId: UUID!) {
  startAiImprovementEvaluation(proposalId: $proposalId) { evaluation { id status } }
}`;
const ASSESS = gql`mutation AssessAIImprovementEvaluation($evaluationId: UUID!, $cases: [ImprovementAssessmentInput!]!) {
  assessAiImprovementEvaluation(evaluationId: $evaluationId, cases: $cases) { evaluation { id } }
}`;
const REVIEW = gql`mutation ReviewImprovementVersion($versionId: UUID!, $approve: Boolean!, $reviewNote: String!) {
  reviewQualityPromptVersion(versionId: $versionId, approve: $approve, reviewNote: $reviewNote) { version { id status } }
}`;

interface Feedback { id: string; ruleTitle: string; outputFormat: string; rootCause: string; diff: string; machineReadable: string }
interface Case { id: string; purpose: string; required_text: string[]; forbidden_text: string[]; review_criteria: string; output_format?: string }
interface Output { content: string; passed: boolean; checks: Array<{ kind: string; text?: string; passed: boolean }> }
interface Result { cases: Array<{ id: string; baseline: Output; candidate: Output; review_criteria: string }>; candidate_passed: boolean; provider: string; model: string }
interface Evaluation { id: string; status: string; resultData?: string; preparedEvidence?: string; errorMessage?: string; assessment?: { cases: string; reviewerUsername: string } }
interface Proposal { id: string; evidence: string; cases: string; evaluationReady: boolean;
  version: { id: string; number: number; status: string; instructions: string; baseInstructions: string; changeReason: string; diff: string; reviewNote?: string };
  evaluations: Evaluation[] }
interface EditableCase { purpose: string; required: string; forbidden: string; criteria: string }
const parse = <T,>(value: string | null | undefined, fallback: T): T => { try { return value ? JSON.parse(value) : fallback; } catch { return fallback; } };
const phrases = (value: string) => value.split('\n').map(item => item.trim()).filter(Boolean);
const pretty = (value: string | undefined) => JSON.stringify(parse(value, {}), null, 2);

export default function AIImprovementProposals({ organizationId, installation, language, instructions, baseFingerprint, onChanged }: {
  organizationId?: string | null; installation: boolean; language: string; instructions: string; baseFingerprint: string; onChanged: () => void;
}) {
  const variables = { organizationId: organizationId || null, installation, language };
  const { data: acceptedData, refetch: refreshFeedback } = useQuery<{ aiQualityFeedback: Feedback[] }>(ACCEPTED, {
    variables: { organizationId: organizationId || null, allOrganizations: installation, outputFormat: language }, fetchPolicy: 'network-only',
  });
  const { data, loading, error, refetch, startPolling, stopPolling } = useQuery<{ aiImprovementProposals: Proposal[] }>(PROPOSALS, { variables, fetchPolicy: 'network-only' });
  const proposals = data?.aiImprovementProposals || [];
  const running = proposals.some(item => item.evaluations.some(run => ['PENDING', 'RUNNING'].includes(run.status)));
  useEffect(() => { if (running) startPolling(2000); else stopPolling(); }, [running, startPolling, stopPolling]);
  const [editor, setEditor] = useState(false);
  const [draftInProgress, setDraftInProgress] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [caseInputs, setCaseInputs] = useState<Record<string, EditableCase>>({});
  const [draft, setDraft] = useState('');
  const [reason, setReason] = useState('');
  const [draftBaseline, setDraftBaseline] = useState('');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [suggestionError, setSuggestionError] = useState('');
  const { data: taskData, error: taskError } = useQuery(TASK, { variables: { taskId }, skip: !taskId, pollInterval: taskId ? 2000 : 0, fetchPolicy: 'network-only' });
  const [suggest, { loading: suggesting }] = useMutation(SUGGEST);
  const [create, { loading: creating }] = useMutation(CREATE);
  const [evaluate, { loading: evaluating }] = useMutation(EVALUATE);
  const [assess, { loading: assessing }] = useMutation(ASSESS);
  const [review, { loading: reviewing }] = useMutation(REVIEW);
  const [selected, setSelected] = useState<{ proposal: Proposal; mode: 'assess' | 'approve' | 'reject' } | null>(null);
  const [verdicts, setVerdicts] = useState<Record<string, { passed: boolean; note: string }>>({});
  const [reviewNote, setReviewNote] = useState('');
  const feedback = acceptedData?.aiQualityFeedback || [];
  const suggestionIds = selectedIds.filter(id => (caseInputs[id]?.purpose || 'CORRECTION') === 'CORRECTION');

  useEffect(() => {
    const task = taskData?.aiImprovementDraftTask;
    if (!taskId || task?.id !== taskId || !['COMPLETED', 'FAILED'].includes(task.status)) return;
    setTaskId(null);
    if (task.status === 'FAILED') { setSuggestionError(task.errorMessage || 'Suggestion failed.'); return; }
    const result = parse<any>(task.resultData, {});
    if (result.base_fingerprint !== baseFingerprint || result.base_fingerprint !== draftBaseline) {
      setSuggestionError('The baseline changed. Refresh and start a new proposal.'); return;
    }
    setDraft(result.instructions || ''); setReason(result.rationale || '');
    message.success('Suggested instructions are ready to review.');
  }, [taskId, taskData, baseFingerprint, draftBaseline]);

  const openEditor = (proposal?: Proposal) => {
    if (!proposal && draftInProgress) { setEditor(true); return; }
    void refreshFeedback(); setSuggestionError(''); setDraft(proposal?.version.instructions || instructions);
    setReason(proposal?.version.changeReason || ''); setDraftBaseline(baseFingerprint);
    const previous = parse<Case[]>(proposal?.cases, []);
    setSelectedIds(previous.map(item => item.id));
    setCaseInputs(Object.fromEntries(previous.map(item => [item.id, { purpose: item.purpose,
      required: item.required_text.join('\n'), forbidden: item.forbidden_text.join('\n'), criteria: item.review_criteria }])));
    setDraftInProgress(true); setEditor(true);
  };
  const setCase = (id: string, update: Partial<EditableCase>) => setCaseInputs(current => ({ ...current,
    [id]: { ...(current[id] || { purpose: 'CORRECTION', required: '', forbidden: '', criteria: '' }), ...update } }));
  const refresh = async () => { await refetch(); onChanged(); };
  const startSuggestion = async () => {
    try {
      setSuggestionError('');
      const result = await suggest({ variables: { ...variables, feedbackIds: suggestionIds, baseFingerprint: draftBaseline } });
      setTaskId(result.data.startAiImprovementDraft.taskId);
    } catch (err: any) { setSuggestionError(err.message); }
  };
  const save = async () => {
    try {
      await create({ variables: { ...variables, instructions: draft, changeReason: reason, baseFingerprint: draftBaseline,
        cases: selectedIds.map(id => ({ feedbackId: id, purpose: caseInputs[id]?.purpose || 'CORRECTION',
          requiredText: phrases(caseInputs[id]?.required || ''), forbiddenText: phrases(caseInputs[id]?.forbidden || ''), reviewCriteria: caseInputs[id]?.criteria || '' })) } });
      setEditor(false); setDraftInProgress(false); await refresh(); message.success('Proposal saved. Evaluate it before approval.');
    } catch (err: any) { message.error(err.message); }
  };
  const startRun = async (proposal: Proposal) => {
    try { await evaluate({ variables: { proposalId: proposal.id } }); await refresh(); }
    catch (err: any) { message.error(err.message); }
  };
  const openReview = (proposal: Proposal, mode: 'assess' | 'approve' | 'reject') => {
    setSelected({ proposal, mode }); setVerdicts({}); setReviewNote('');
  };
  const saveReview = async () => {
    if (!selected) return;
    try {
      if (selected.mode === 'assess') {
        const run = selected.proposal.evaluations[0];
        await assess({ variables: { evaluationId: run.id, cases: parse<Case[]>(selected.proposal.cases, []).map(item => ({
          caseId: item.id, passed: verdicts[item.id]?.passed ?? false, note: verdicts[item.id]?.note || '',
        })) } });
      } else await review({ variables: { versionId: selected.proposal.version.id, approve: selected.mode === 'approve', reviewNote } });
      setSelected(null); await refresh(); message.success('Review recorded.');
    } catch (err: any) { message.error(err.message); }
  };
  const outputs = (run: Evaluation) => {
    const result = parse<Result | null>(run.resultData, null);
    return <>
      {run.errorMessage && <Alert type="error" title={run.errorMessage} />}
      {result && <>
        <Typography.Paragraph>{result.provider} · {result.model}. Literal checks compare saved inputs; assess detection logic and regression risk yourself.</Typography.Paragraph>
        {result.cases.map(item => <Card key={item.id} size="small" title={item.review_criteria} style={{ marginBottom: 12 }}>
          <Row gutter={16}>{(['baseline', 'candidate'] as const).map(arm => <Col key={arm} xs={24} md={12}>
            <Typography.Text strong>{arm === 'baseline' ? 'Baseline output' : 'Proposed output'}</Typography.Text>
            <Tag color={item[arm].passed ? 'green' : 'red'}>{item[arm].passed ? 'Checks passed' : 'Checks failed'}</Tag>
            <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 260, overflow: 'auto' }}>{item[arm].content}</pre>
            {item[arm].checks.map((check, index) => <div key={index}>{check.passed ? '✓' : '✗'} {check.kind}: {check.text || 'non-empty rule'}</div>)}
          </Col>)}</Row>
        </Card>)}
      </>}
      {run.assessment && <Typography.Paragraph>Assessment by {run.assessment.reviewerUsername}: <pre style={{ whiteSpace: 'pre-wrap' }}>{pretty(run.assessment.cases)}</pre></Typography.Paragraph>}
      <details><summary>Exact evaluation inputs and outputs</summary><pre style={{ whiteSpace: 'pre-wrap', maxHeight: 400, overflow: 'auto' }}>{pretty(run.resultData || run.preparedEvidence)}</pre></details>
    </>;
  };
  const proposalEvidence = (proposal: Proposal) => <>
    <Typography.Paragraph>{proposal.version.changeReason}</Typography.Paragraph>
    <pre style={{ whiteSpace: 'pre-wrap' }}>{proposal.version.diff}</pre>
    <details><summary>Reviewed feedback and frozen evaluation cases</summary><pre style={{ whiteSpace: 'pre-wrap', maxHeight: 400, overflow: 'auto' }}>{pretty(proposal.evidence)}{'\n'}{pretty(proposal.cases)}</pre></details>
    {proposal.evaluations.map((run, index) => <Card key={run.id} size="small" title={`${index === 0 ? 'Latest evaluation' : 'Previous evaluation'} · ${run.status}`} style={{ marginTop: 12 }}>{outputs(run)}</Card>)}
  </>;
  const assessmentCases = selected ? parse<Case[]>(selected.proposal.cases, []) : [];
  const suggestionAllowed = suggestionIds.length > 0 && suggestionIds.every(id => feedback.find(item => item.id === id)?.rootCause === 'PROMPT');
  return <Space orientation="vertical" style={{ width: '100%' }}>
    <Alert type="info" title="Evaluate improvements before activation" description="Use accepted prompt-related corrections to draft instructions. Compare baseline and proposed outputs on saved cases, assess every case, then approve the exact version. Include regression cases to check behavior beyond the original correction." />
    <Space><Button type="primary" onClick={() => openEditor()}>{draftInProgress ? 'Continue proposal draft' : 'New improvement proposal'}</Button><Button loading={loading} onClick={() => { void refetch(); void refreshFeedback(); }}>Refresh proposals</Button></Space>
    {error && <Alert type="error" title={error.message} />}
    <Table<Proposal> rowKey="id" loading={loading} dataSource={proposals} expandable={{ expandedRowRender: proposalEvidence }} columns={[
      { title: 'Version', render: (_, item) => `v${item.version.number}` }, { title: 'Status', render: (_, item) => <Tag>{item.version.status}</Tag> },
      { title: 'Reason', render: (_, item) => item.version.changeReason },
      { title: 'Evaluation', render: (_, item) => item.evaluationReady ? 'Ready for approval' : item.evaluations[0]?.status || 'Not evaluated' },
      { title: 'Actions', render: (_, item) => item.version.status === 'DRAFT' && <Space wrap>
        <Button size="small" onClick={() => openEditor(item)}>Revise as new proposal</Button>
        <Button size="small" loading={evaluating} disabled={item.evaluations.some(run => ['PENDING', 'RUNNING'].includes(run.status))} onClick={() => startRun(item)}>Evaluate</Button>
        <Button size="small" disabled={item.evaluations[0]?.status !== 'COMPLETED' || Boolean(item.evaluations[0]?.assessment)} onClick={() => openReview(item, 'assess')}>Assess outputs</Button>
        <Button size="small" type="primary" disabled={!item.evaluationReady} onClick={() => openReview(item, 'approve')}>Review and activate</Button>
        <Button size="small" danger onClick={() => openReview(item, 'reject')}>Reject proposal</Button>
      </Space> },
    ]} />
    <Modal open={editor} width={1000} title="Draft improvement from reviewed feedback" onCancel={() => !creating && setEditor(false)} onOk={save}
      okText="Save proposal" confirmLoading={creating} okButtonProps={{ disabled: Boolean(taskId) || !draft.trim() || !reason.trim() || !selectedIds.length || selectedIds.some(id => !caseInputs[id]?.criteria.trim()) || draftBaseline !== baseFingerprint }}>
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Button disabled={creating} onClick={() => { setEditor(false); setDraftInProgress(false); setTaskId(null); }}>Discard draft</Button>
        <label htmlFor="improvement-feedback">Accepted feedback and regression cases (up to five)</label>
        <Select {...SELECT_THEME} id="improvement-feedback" aria-label="Accepted feedback" mode="multiple" style={{ width: '100%' }} value={selectedIds}
          disabled={Boolean(taskId)} onChange={ids => { if (ids.length <= 5) {
            setSelectedIds(ids);
            ids.forEach(id => { if (!caseInputs[id]) setCase(id, { purpose: feedback.find(item => item.id === id)?.rootCause === 'PROMPT' ? 'CORRECTION' : 'REGRESSION' }); });
          } }} options={feedback.map(item => ({ value: item.id, label: `${item.ruleTitle} · ${item.outputFormat} · ${item.rootCause}` }))} />
        {selectedIds.map(id => <Card size="small" key={id} title={feedback.find(item => item.id === id)?.ruleTitle || id}>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{feedback.find(item => item.id === id)?.diff}</pre>
          <Space orientation="vertical" style={{ width: '100%' }}>
            <Select {...SELECT_THEME} aria-label={`Case purpose ${id}`} value={caseInputs[id]?.purpose || 'CORRECTION'} onChange={purpose => setCase(id, { purpose })}
              options={[{ value: 'CORRECTION', label: 'Prompt correction' }, { value: 'REGRESSION', label: 'Regression check' }]} />
            <label htmlFor={`criteria-${id}`}>What must the reviewer verify?</label><Input.TextArea id={`criteria-${id}`} rows={2} maxLength={4000} value={caseInputs[id]?.criteria || ''} onChange={event => setCase(id, { criteria: event.target.value })} />
            <label htmlFor={`required-${id}`}>Required literal text (one phrase per line, optional)</label><Input.TextArea id={`required-${id}`} rows={2} value={caseInputs[id]?.required || ''} onChange={event => setCase(id, { required: event.target.value })} />
            <label htmlFor={`forbidden-${id}`}>Forbidden literal text (one phrase per line, optional)</label><Input.TextArea id={`forbidden-${id}`} rows={2} value={caseInputs[id]?.forbidden || ''} onChange={event => setCase(id, { forbidden: event.target.value })} />
          </Space>
        </Card>)}
        <Button disabled={!suggestionAllowed || draftBaseline !== baseFingerprint} loading={suggesting || Boolean(taskId)} onClick={startSuggestion}>Suggest instructions from selected feedback</Button>
        {(suggestionError || taskError) && <Alert type="error" title={suggestionError || taskError?.message} />}
        {draftBaseline !== baseFingerprint && <Alert type="warning" title="The baseline changed. Start a new proposal." />}
        <details><summary>Current baseline instructions</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{instructions}</pre></details>
        <label htmlFor="improvement-instructions">Proposed instructions</label><Input.TextArea id="improvement-instructions" rows={10} maxLength={20000} value={draft} disabled={Boolean(taskId)} onChange={event => setDraft(event.target.value)} />
        <label htmlFor="improvement-reason">Reason for the improvement</label><Input.TextArea id="improvement-reason" rows={3} maxLength={4000} value={reason} onChange={event => setReason(event.target.value)} />
      </Space>
    </Modal>
    <Modal open={Boolean(selected)} width={1100} title={selected?.mode === 'assess' ? 'Assess baseline and proposed outputs' : selected?.mode === 'approve' ? 'Review exact proposal and activate' : 'Reject improvement proposal'}
      onCancel={() => !assessing && !reviewing && setSelected(null)} onOk={saveReview} confirmLoading={assessing || reviewing}
      okText={selected?.mode === 'assess' ? 'Record assessment' : selected?.mode === 'approve' ? 'Approve and activate' : 'Reject proposal'}
      okButtonProps={{ disabled: selected?.mode === 'assess' ? assessmentCases.some(item => !verdicts[item.id]?.note.trim()) : !reviewNote.trim(), danger: selected?.mode === 'reject' }}>
      {selected && <>
        <Typography.Paragraph strong>Exact proposed instructions</Typography.Paragraph><pre style={{ whiteSpace: 'pre-wrap', maxHeight: 300, overflow: 'auto' }}>{selected.proposal.version.instructions}</pre>
        {proposalEvidence(selected.proposal)}
        {selected.mode === 'assess' ? assessmentCases.map(item => <Card size="small" key={item.id} title={item.review_criteria}>
          <Select {...SELECT_THEME} aria-label={`Assessment ${item.id}`} value={verdicts[item.id]?.passed ?? false}
            options={[{ value: false, label: 'Fail / not verified' }, { value: true, label: 'Pass after review' }]}
            onChange={passed => setVerdicts(current => ({ ...current, [item.id]: { ...(current[item.id] || { note: '', passed: false }), passed } }))} />
          <label htmlFor={`assessment-${item.id}`}>Assessment reason and evidence</label><Input.TextArea id={`assessment-${item.id}`} rows={3} maxLength={4000} value={verdicts[item.id]?.note || ''}
            onChange={event => setVerdicts(current => ({ ...current, [item.id]: { ...(current[item.id] || { passed: false, note: '' }), note: event.target.value } }))} />
        </Card>) : <><label htmlFor="improvement-review-note">Approval / rejection reason</label><Input.TextArea id="improvement-review-note" rows={3} maxLength={4000} value={reviewNote} onChange={event => setReviewNote(event.target.value)} /></>}
      </>}
    </Modal>
  </Space>;
}
