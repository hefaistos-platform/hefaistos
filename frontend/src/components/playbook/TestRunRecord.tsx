import React, { useState } from 'react';
import { gql, useMutation, useQuery } from '@apollo/client';
import { Button, Tag, Typography } from 'antd';

const { Text } = Typography;

export const TEST_RUNS_QUERY = gql`
  query TestRuns($id: UUID!) {
    playbookGraph(id: $id) { id testRuns }
  }
`;

export const RECORD_TEST_RUN = gql`
  mutation RecordTestRun($g: UUID!, $executed: Boolean!, $fired: Boolean!, $notes: String) {
    recordTestRun(graphId: $g, executed: $executed, fired: $fired, notes: $notes) { testRuns }
  }
`;

export interface TestRun {
  id: string;
  executed: boolean;
  fired: boolean;
  notes: string;
  recorded_at: string | null;
  recorded_by: string;
  stale: boolean;
}

const when = (iso: string | null): string => {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
};

/**
 * What the person who ran the test reports: executed, and did the rule fire. HEFAISTOS does not run the test.
 * A record is added, never edited, and does not change the Workbench status or version.
 */
export const TestRunRecord: React.FC<{ playbookId?: string }> = ({ playbookId }) => {
  const { data, error } = useQuery(TEST_RUNS_QUERY, { variables: { id: playbookId }, skip: !playbookId });
  const [record, { loading }] = useMutation(RECORD_TEST_RUN, { refetchQueries: ['TestRuns'], awaitRefetchQueries: true });
  const [executed, setExecuted] = useState(false);
  const [fired, setFired] = useState(false);
  const [notes, setNotes] = useState('');
  const [problem, setProblem] = useState('');
  const runs: TestRun[] = Array.isArray(data?.playbookGraph?.testRuns) ? data.playbookGraph.testRuns : [];

  if (!playbookId) {
    return <p className="text-[11px] text-gray-500 mt-3">Save the Workbench first, then you can record a test run here.</p>;
  }

  const submit = async () => {
    setProblem('');
    try {
      await record({ variables: { g: playbookId, executed, fired: executed && fired, notes } });
      setExecuted(false); setFired(false); setNotes('');
    } catch (e: any) {
      setProblem(e?.message ?? 'Could not record the run.');
    }
  };

  return (
    <div data-testid="test-run-record" className="mt-3">
      <div className="grid grid-cols-2 gap-2 text-sm text-gray-700">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={executed} onChange={(e) => { setExecuted(e.target.checked); if (!e.target.checked) setFired(false); }} />
          Test executed
        </label>
        <label className={`flex items-center gap-2 ${executed ? '' : 'opacity-50'}`}>
          <input type="checkbox" checked={fired} disabled={!executed} onChange={(e) => setFired(e.target.checked)} />
          Rule fired
        </label>
      </div>
      <textarea
        className="w-full h-20 mt-3 p-3 border border-gray-300 rounded text-sm"
        placeholder="Notes (artifacts observed, rule ID, correlation IDs)"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      <div className="mt-2 flex items-center gap-3">
        <Button size="small" type="primary" disabled={!executed} loading={loading} onClick={submit}>Record test run</Button>
        {!executed && <Text type="secondary" style={{ fontSize: 11 }}>Tick &quot;Test executed&quot; to record a run.</Text>}
      </div>
      {problem && <div><Text type="danger" data-testid="test-run-problem">{problem}</Text></div>}
      <p className="text-[10px] text-gray-500 mt-1">
        This is your own report, added to the list below with your name and the time. HEFAISTOS does not run the test,
        and a record does not change the Workbench status or version.
      </p>
      {error && <Text type="danger">Could not load earlier runs.</Text>}
      {runs.length > 0 && (
        <ul data-testid="test-run-list" className="mt-2 pl-0 list-none">
          {runs.map((run) => (
            <li key={run.id} data-testid="test-run-item" className="border-t border-gray-200 py-2 text-sm">
              <Tag color={run.fired ? 'green' : 'default'}>{run.fired ? 'Rule fired' : 'Rule did not fire'}</Tag>
              <Text type="secondary">{[run.recorded_by, when(run.recorded_at)].filter(Boolean).join(' · ')}</Text>
              {run.stale && <Tag color="orange" style={{ marginLeft: 8 }}>The rule changed after this run</Tag>}
              {run.notes && <div style={{ whiteSpace: 'pre-wrap' }}>{run.notes}</div>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
