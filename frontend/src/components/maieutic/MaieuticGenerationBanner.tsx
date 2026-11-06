import React, { useEffect, useRef, useState } from 'react';
import { gql, useQuery } from '@apollo/client';
import { Alert } from 'antd';
import MaieuticTraceabilityPanel from './MaieuticTraceabilityPanel';

const STATUS_QUERY = gql`
  query MaieuticGenerationStatus($id: UUID!) {
    maieuticGenerationStatus(workbenchId: $id) { taskId outputFormat status validationStatus hasRule error traceability traceabilityRuleRepaired }
  }
`;

const ACTIVE = new Set(['PENDING', 'RUNNING']);
const POLL_MS = 5000;

/**
 * Shows the progress of rule generation queued by a Maieutic session. Renders nothing for a Workbench
 * that was not created from a session. The backend stores finished rules in the Workbench itself;
 * this banner only reports, and asks the page to reload once something new has been stored.
 */
export const MaieuticGenerationBanner: React.FC<{ playbookId: string; onStored?: () => void }> = ({ playbookId, onStored }) => {
  const { data, startPolling, stopPolling } = useQuery(STATUS_QUERY, {
    variables: { id: playbookId }, skip: !playbookId, fetchPolicy: 'network-only',
  });
  const [hidden, setHidden] = useState(false);
  const stored = useRef<Set<string>>(new Set());
  const rows: any[] = data?.maieuticGenerationStatus ?? [];
  const active = rows.filter((r) => ACTIVE.has(r.status));

  useEffect(() => {
    if (active.length) startPolling(POLL_MS); else stopPolling();
    return () => stopPolling();
  }, [active.length]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const fresh = rows.filter((r) => r.status === 'COMPLETED' && r.hasRule && !stored.current.has(r.taskId));
    if (fresh.length) {
      fresh.forEach((r) => stored.current.add(r.taskId));
      onStored?.();
    }
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!rows.length || hidden) return null;

  const failed = rows.filter((r) => r.status === 'FAILED');
  const noRule = rows.filter((r) => r.status === 'COMPLETED' && !r.hasRule);
  const done = rows.filter((r) => r.status === 'COMPLETED' && r.hasRule);

  if (active.length) {
    return (
      <Alert
        type="info" showIcon banner
        message={`Generating from your Maieutic design: ${active.map((r) => r.outputFormat).join(', ')}. Finished rules appear here by themselves.`}
      />
    );
  }
  const traced = done.find((r) => Array.isArray(r.traceability) && r.traceability.length);
  return (
    <>
    <Alert
      type={failed.length || noRule.length ? 'warning' : 'success'} showIcon banner closable onClose={() => setHidden(true)}
      message={
        <>
          {done.length > 0 && <div>Added from your Maieutic design: {done.map((r) => r.outputFormat).join(', ')}.</div>}
          {noRule.length > 0 && (
            <div>
              Generated but not stored ({noRule.map((r) => r.outputFormat).join(', ')}): the draft did not pass the rule checks.
              Generate it again from the rule editor and review the validation notes.
            </div>
          )}
          {failed.length > 0 && <div>Generation failed for {failed.map((r) => r.outputFormat).join(', ')}. {failed[0].error}</div>}
        </>
      }
    />
    {traced && <MaieuticTraceabilityPanel rows={traced.traceability} outputFormat={traced.outputFormat} ruleRepaired={!!traced.traceabilityRuleRepaired} />}
    </>
  );
};

export default MaieuticGenerationBanner;
