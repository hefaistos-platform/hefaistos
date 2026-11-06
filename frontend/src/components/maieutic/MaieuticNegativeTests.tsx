import React from 'react';
import { Input, Tag, Typography } from 'antd';

const { Text, Paragraph } = Typography;

export interface AcceptedLimitation {
  adeId: string;
  question: string;
  answer: string;
}

export interface NegativeTestDraft {
  from_ade_id: string;
  steps: string;
}

/** Accepted limitations of a session, read from the evasion plan. Only ACCEPTED_LIMITATION counts. */
export const acceptedLimitations = (planItems: any[] | undefined | null): AcceptedLimitation[] =>
  (planItems ?? [])
    .filter((i) => i?.ledgerEntry?.disposition === 'ACCEPTED_LIMITATION')
    .map((i) => ({ adeId: i.adeId, question: i.questionText ?? '', answer: i.ledgerEntry?.answer_text ?? '' }));

/**
 * One optional procedure per accepted limitation: how to check that the rule does not fire on it.
 * The session only describes the test. Nobody runs it here; the outcome is recorded in the Workbench.
 */
export const MaieuticNegativeTests: React.FC<{
  limitations: AcceptedLimitation[];
  value: NegativeTestDraft[];
  onChange: (next: NegativeTestDraft[]) => void;
  loading?: boolean;
  failed?: boolean;
}> = ({ limitations, value, onChange, loading, failed }) => {
  const stepsOf = (id: string) => value.find((v) => v.from_ade_id === id)?.steps ?? '';
  const set = (id: string, steps: string) => {
    const rest = value.filter((v) => v.from_ade_id !== id);
    onChange(steps ? [...rest, { from_ade_id: id, steps }] : rest);
  };
  if (failed) return <Text type="danger">Could not load your accepted limitations. Reload the page to try again.</Text>;
  if (loading) return <Text type="secondary">Loading your accepted limitations…</Text>;
  if (!limitations.length) {
    return <Text type="secondary">Negative tests come from evasion points you accepted as limitations. You have none yet.</Text>;
  }
  return (
    <div>
      <Paragraph type="secondary" style={{ fontSize: 12 }}>
        Each test describes how to check that the rule stays silent on something you accepted. Nothing is run for you.
        Leave the steps empty to get a starting template in the Workbench. You record the outcome there, before or after
        you finish this session.
      </Paragraph>
      {limitations.map((l) => (
        <div key={l.adeId} data-testid={`negtest-${l.adeId}`} style={{ border: '1px solid #f0f0f0', borderRadius: 6, padding: 8, marginBottom: 8 }}>
          <Tag>{l.adeId}</Tag><Text strong>{l.question}</Text>
          {l.answer && <div><Text type="secondary">You accepted: {l.answer}</Text></div>}
          <Input.TextArea
            rows={3} style={{ maxWidth: 700, marginTop: 6 }} aria-label={`Steps to check ${l.adeId}`}
            placeholder="Steps to reproduce it, and confirm no alert is raised (optional)"
            value={stepsOf(l.adeId)} onChange={(e) => set(l.adeId, e.target.value)}
          />
        </div>
      ))}
    </div>
  );
};

export default MaieuticNegativeTests;
