import React, { useEffect, useMemo, useState } from 'react';
import { gql, useMutation, useQuery } from '@apollo/client';
import { Alert, Button, Collapse, Input, Select, Space, Tag, Typography } from 'antd';
import { MaieuticFrameworkDrift } from './MaieuticFrameworkDrift';

const { Text, Paragraph } = Typography;

export const PLAN_QUERY = gql`
  query MaieuticAdePlan($id: UUID!) {
    maieuticAdePlan(draftId: $id) {
      openCount needsQuestion
      frameworkDrift { pinnedLabel activeLabel removed changed }
      items {
        adeId state version triggerReason designRefs questionText whyWeAsk weakAnswer strongAnswer glossary
        hintRungsUsed hintRungsTotal ledgerEntry
      }
    }
  }
`;

const HINT_MUTATION = gql`
  mutation RevealMaieuticHint($id: UUID!, $ade: String!, $rung: Int!) {
    revealMaieuticHint(draftId: $id, adeId: $ade, rung: $rung) { hint rung }
  }
`;

const ANSWER_MUTATION = gql`
  mutation AnswerMaieuticAdeQuestion(
    $id: UUID!, $ade: String!, $text: String, $disp: String!, $ref: String, $dref: String
  ) {
    answerMaieuticAdeQuestion(
      draftId: $id, adeId: $ade, answerText: $text, disposition: $disp, reference: $ref, designRef: $dref
    ) { evaluatorFlag evaluatorSource followUp openCount }
  }
`;

export const DISPOSITIONS = [
  { value: 'HANDLED_IN_DESIGN', label: 'My design already handles this' },
  { value: 'ACCEPTED_LIMITATION', label: 'I accept this as a limitation' },
  { value: 'COVERED_BY_OTHER_RULE', label: 'Another detection covers this' },
  { value: 'NOT_APPLICABLE', label: 'This does not apply to my design' },
];

const HINT_LABELS = ['Where to look', 'How to look', 'A worked example'];

const FLAG_TEXT: Record<string, { color: string; text: string }> = {
  ANSWERED: { color: 'green', text: 'The check found your answer covers the points we ask about.' },
  VAGUE: { color: 'orange', text: 'The check found your answer general or incomplete.' },
  CONTRADICTS_DESIGN: { color: 'red', text: 'The check found your answer in conflict with your own design.' },
};

interface Draft { text: string; disposition?: string; reference: string; designRef?: string }

interface Props {
  draftId: string;
  disabled?: boolean;
  refLabel: (ref: string) => string;
  beforeLoad: () => Promise<void>;
  onOpenCount?: (n: number) => void;
}

export const MaieuticAdeStage: React.FC<Props> = ({ draftId, disabled, refLabel, beforeLoad, onOpenCount }) => {
  const [ready, setReady] = useState(false);
  const { data, loading, error, refetch } = useQuery(PLAN_QUERY, {
    variables: { id: draftId }, skip: !ready, fetchPolicy: 'network-only',
  });
  const [revealHint] = useMutation(HINT_MUTATION);
  const [answer, { loading: saving }] = useMutation(ANSWER_MUTATION);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [hints, setHints] = useState<Record<string, Record<number, string>>>({});
  const [feedback, setFeedback] = useState<Record<string, any>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  // The plan is derived from the saved design, so save first, then ask.
  useEffect(() => { beforeLoad().finally(() => setReady(true)); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const plan = data?.maieuticAdePlan;
  const items: any[] = plan?.items ?? [];

  useEffect(() => {
    if (plan) onOpenCount?.(plan.openCount);
  }, [plan]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setDrafts((prev) => {
      const next = { ...prev };
      items.forEach((it) => {
        if (!next[it.adeId]) {
          const e = it.ledgerEntry || {};
          next[it.adeId] = {
            text: e.answer_text ?? '', disposition: e.disposition && e.disposition !== 'UNKNOWN' ? e.disposition : undefined,
            reference: e.reference ?? '', designRef: e.design_ref ?? undefined,
          };
        }
      });
      return next;
    });
  }, [plan]); // eslint-disable-line react-hooks/exhaustive-deps

  const patch = (ade: string, change: Partial<Draft>) =>
    setDrafts((d) => ({ ...d, [ade]: { ...(d[ade] || { text: '', reference: '' }), ...change } }));

  const submit = async (item: any, unknown = false) => {
    const d = drafts[item.adeId] || { text: '', reference: '' };
    setErrors((e) => ({ ...e, [item.adeId]: '' }));
    try {
      const res = await answer({
        variables: {
          id: draftId, ade: item.adeId, text: unknown ? '' : d.text,
          disp: unknown ? 'UNKNOWN' : d.disposition || '', ref: d.reference || null, dref: d.designRef || null,
        },
      });
      setFeedback((f) => ({ ...f, [item.adeId]: res.data.answerMaieuticAdeQuestion }));
      await refetch();
    } catch (err: any) {
      setErrors((e) => ({ ...e, [item.adeId]: err?.message ?? 'Could not save' }));
    }
  };

  const showHint = async (item: any, rung: number) => {
    try {
      const res = await revealHint({ variables: { id: draftId, ade: item.adeId, rung } });
      setHints((h) => ({ ...h, [item.adeId]: { ...(h[item.adeId] || {}), [rung]: res.data.revealMaieuticHint.hint } }));
      await refetch();
    } catch (err: any) {
      setErrors((e) => ({ ...e, [item.adeId]: err?.message ?? 'Could not open hint' }));
    }
  };

  const stateTag = (s: string) =>
    s === 'ANSWERED' ? <Tag color="green">Answered</Tag>
      : s === 'STALE' ? <Tag color="gold">Question changed, please re-check</Tag>
        : <Tag>To do</Tag>;

  const panels = useMemo(() => items.map((item) => {
    const d = drafts[item.adeId] || { text: '', reference: '' };
    const fb = feedback[item.adeId];
    const flag = fb?.evaluatorFlag ? FLAG_TEXT[fb.evaluatorFlag] : null;
    return {
      key: item.adeId,
      label: (
        <Space>
          {stateTag(item.state)}
          <Text>{item.questionText.length > 110 ? `${item.questionText.slice(0, 110)}…` : item.questionText}</Text>
        </Space>
      ),
      children: (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Paragraph strong style={{ marginBottom: 0 }}>{item.questionText}</Paragraph>
          <Collapse ghost size="small" items={[
            { key: 'why', label: 'Why we ask this', children: <Paragraph>{item.whyWeAsk}</Paragraph> },
            {
              key: 'good', label: 'What a thin and a thorough answer look like',
              children: (
                <>
                  <Paragraph><Text type="secondary">Thin: </Text>{item.weakAnswer}</Paragraph>
                  <Paragraph><Text type="secondary">Thorough: </Text>{item.strongAnswer}</Paragraph>
                </>
              ),
            },
            ...(item.glossary?.length ? [{
              key: 'gl', label: 'Terms used',
              children: item.glossary.map((g: any) => (
                <Paragraph key={g.term} style={{ marginBottom: 4 }}><Text strong>{g.term}: </Text>{g.meaning}</Paragraph>
              )),
            }] : []),
          ]} />

          <Space wrap>
            <Text type="secondary">Stuck? Open hints one at a time:</Text>
            {[1, 2, 3].map((rung) => (
              <Button
                key={rung} size="small"
                disabled={disabled || rung > item.hintRungsUsed + 1}
                onClick={() => showHint(item, rung)}
              >
                {rung}. {HINT_LABELS[rung - 1]}
              </Button>
            ))}
          </Space>
          {Object.entries(hints[item.adeId] || {}).sort().map(([rung, text]) => (
            <Alert key={rung} type="info" showIcon message={HINT_LABELS[Number(rung) - 1]} description={text} />
          ))}

          <Input.TextArea
            rows={4} disabled={disabled} value={d.text}
            placeholder="Answer in your own words. Nothing is filled in for you."
            onChange={(e) => patch(item.adeId, { text: e.target.value })}
          />
          <Space wrap>
            <Select
              style={{ width: 320 }} disabled={disabled} placeholder="What is the status of this point?"
              value={d.disposition} options={DISPOSITIONS}
              onChange={(v) => patch(item.adeId, { disposition: v })}
            />
            {d.disposition === 'COVERED_BY_OTHER_RULE' && (
              <Input
                style={{ width: 260 }} placeholder="Name of the other detection" value={d.reference}
                onChange={(e) => patch(item.adeId, { reference: e.target.value })}
              />
            )}
            {item.designRefs?.length > 0 && (
              <Select
                allowClear style={{ width: 300 }} disabled={disabled} placeholder="Which part of your design? (optional)"
                value={d.designRef}
                options={item.designRefs.map((r: string) => ({ value: r, label: refLabel(r) }))}
                onChange={(v) => patch(item.adeId, { designRef: v })}
              />
            )}
          </Space>
          <Space>
            <Button type="primary" loading={saving} disabled={disabled || !d.disposition} onClick={() => submit(item)}>
              Save answer
            </Button>
            <Button disabled={disabled} onClick={() => submit(item, true)}>I do not know yet</Button>
            {!disabled && !d.disposition && (
              <Text type="secondary">Pick a status first, then write your answer. Or choose "I do not know yet".</Text>
            )}
          </Space>
          {errors[item.adeId] && <Text type="danger">{errors[item.adeId]}</Text>}
          {fb && (
            <Alert
              type="success" showIcon message="Saved."
              description={
                <>
                  {flag && <div><Tag color={flag.color}>{fb.evaluatorFlag}</Tag>{flag.text} This check is advisory and did not block saving.</div>}
                  {!flag && fb.evaluatorSource === 'NOT_EVALUATED' && (
                    <Text type="secondary">Your answer was stored as written. It was not checked.</Text>
                  )}
                  {fb.followUp && <Paragraph style={{ marginTop: 8, marginBottom: 0 }}><Text strong>To think about: </Text>{fb.followUp}</Paragraph>}
                </>
              }
            />
          )}
        </Space>
      ),
    };
  }), [items, drafts, hints, feedback, errors, saving, disabled]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Alert
        type="info" showIcon
        message="Where could an attacker slip past this design?"
        description="These questions come from your own hypothesis and planned design. Only you can answer them. Hints explain where and how to look, they never contain the answer. Every point can be answered with “I do not know yet”."
      />
      {error && <Alert type="error" showIcon message={error.message} />}
      {plan?.needsQuestion?.length > 0 && (
        <Alert type="warning" showIcon message={`The ADE framework now lists topics that have no question yet: ${plan.needsQuestion.join(', ')}. A maintainer needs to add them.`} />
      )}
      <MaieuticFrameworkDrift drift={plan?.frameworkDrift} />
      {!loading && items.length === 0 && ready && <Text type="secondary">No questions apply yet. Fill in stage 3 first.</Text>}
      {plan && <Text>{plan.openCount} of {items.length} points still open.</Text>}
      <Collapse accordion items={panels} />
    </Space>
  );
};

export default MaieuticAdeStage;
