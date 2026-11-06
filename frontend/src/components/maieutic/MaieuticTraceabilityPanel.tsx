import React from 'react';
import { Collapse, Tag, Typography } from 'antd';

export interface TraceRow {
  ref: string;
  group: 'MUST_IMPLEMENT' | 'MUST_HANDLE' | 'ACCEPTED_LIMITATION';
  text: string;
  implemented: 'yes' | 'no' | 'partial' | null;
  where: string;
  note: string;
  status: 'REPORTED' | 'NOT_REPORTED' | 'CONTRADICTS_LIMITATION';
}

const GROUP_LABEL: Record<string, string> = {
  MUST_IMPLEMENT: 'Must implement',
  MUST_HANDLE: 'Must handle',
  ACCEPTED_LIMITATION: 'Accepted limitation',
};

/** What to show next to a decision. A missing report is never rendered as a pass. */
export const traceVerdict = (r: TraceRow): { label: string; color: string } => {
  if (r.status === 'CONTRADICTS_LIMITATION') return { label: 'Rule claims to cover an accepted limitation', color: 'red' };
  if (r.status === 'NOT_REPORTED' || !r.implemented) return { label: 'Not reported', color: 'default' };
  if (r.group === 'ACCEPTED_LIMITATION') return { label: 'Not covered, as accepted', color: 'blue' };
  if (r.implemented === 'yes') return { label: 'Reported as implemented', color: 'green' };
  if (r.implemented === 'partial') return { label: 'Reported as partly implemented', color: 'orange' };
  return { label: 'Reported as not implemented', color: 'red' };
};

/**
 * Which design decision ended up where in the generated rule. The answer comes from the model that wrote
 * the rule, so this is an AI-assisted check to review, not a proof that the rule does what it reports.
 */
export const MaieuticTraceabilityPanel: React.FC<{ rows?: TraceRow[] | null; outputFormat?: string; ruleRepaired?: boolean }> = ({ rows, outputFormat, ruleRepaired }) => {
  if (!rows || !rows.length) return null;
  const attention = rows.filter((r) => {
    const v = traceVerdict(r);
    return v.color === 'red' || v.color === 'orange' || v.label === 'Not reported';
  }).length;
  return (
    <Collapse
      size="small"
      items={[{
        key: 'trace',
        label: `Where your decisions went in the ${outputFormat || ''} rule: ${rows.length} decisions${attention ? `, ${attention} to review` : ''}`.replace('  ', ' '),
        children: (
          <>
            <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
              The model that wrote the rule reports this. It is an AI-assisted check to review against the rule, not proof.
            </Typography.Paragraph>
            {ruleRepaired && (
              <Typography.Paragraph type="warning" style={{ fontSize: 12 }}>
                The rule was automatically repaired after this report was written, so the locations may no longer match.
              </Typography.Paragraph>
            )}
            {rows.map((r) => {
              const v = traceVerdict(r);
              return (
                <div key={r.ref} data-testid={`trace-${r.ref}`} style={{ marginBottom: 8 }}>
                  <Tag>{r.ref}</Tag><Tag color={v.color}>{v.label}</Tag>
                  <span style={{ opacity: 0.7 }}>{GROUP_LABEL[r.group] || r.group}</span>
                  <div>{r.text}</div>
                  {r.where && <div style={{ fontSize: 12 }}>In the rule: <code>{r.where}</code></div>}
                  {r.note && <div style={{ fontSize: 12, opacity: 0.8 }}>{r.note}</div>}
                </div>
              );
            })}
          </>
        ),
      }]}
    />
  );
};

export default MaieuticTraceabilityPanel;
