import React, { useEffect, useState } from 'react';
import { gql, useMutation, useQuery } from '@apollo/client';
import { Alert, Button, Input, Select, Tag, Typography } from 'antd';

const { Text } = Typography;

export const NEGATIVE_TESTS_QUERY = gql`
  query NegativeTests($id: UUID!) {
    playbookGraph(id: $id) { id negativeTests }
  }
`;

export const UPDATE_NEGATIVE_TEST = gql`
  mutation UpdateNegativeTest($g: UUID!, $t: UUID!, $steps: String, $result: String, $notes: String) {
    updateNegativeTest(graphId: $g, testId: $t, steps: $steps, result: $result, notes: $notes) { negativeTests }
  }
`;

export interface NegativeTest {
  id: string;
  source_ref: string;
  limitation: string;
  accepted_as: string;
  steps: string;
  steps_source: 'USER' | 'TEMPLATE';
  expected: string;
  result: 'NOT_RUN' | 'NOT_DETECTED' | 'DETECTED';
  notes: string;
  tested_at: string | null;
  stale: boolean;
}

export const RESULT_OPTIONS = [
  { value: 'NOT_RUN', label: 'Not run yet' },
  { value: 'NOT_DETECTED', label: 'No alert, as accepted' },
  { value: 'DETECTED', label: 'Alert raised unexpectedly' },
];

/** Tests whose recorded result says the rule fires on something the engineer accepted as not covered. */
export const unexpectedlyDetected = (tests: NegativeTest[]): NegativeTest[] =>
  tests.filter((t) => t.result === 'DETECTED' && !t.stale);

const useNegativeTests = (playbookId?: string) => {
  const { data, loading, error } = useQuery(NEGATIVE_TESTS_QUERY, { variables: { id: playbookId }, skip: !playbookId });
  const tests: NegativeTest[] = Array.isArray(data?.playbookGraph?.negativeTests) ? data.playbookGraph.negativeTests : [];
  return { tests, loading, error };
};

const Row: React.FC<{ test: NegativeTest; playbookId: string }> = ({ test, playbookId }) => {
  const [steps, setSteps] = useState(test.steps);
  const [notes, setNotes] = useState(test.notes);
  const [error, setError] = useState('');
  const [update, { loading }] = useMutation(UPDATE_NEGATIVE_TEST, { refetchQueries: ['NegativeTests'], awaitRefetchQueries: true });
  useEffect(() => { setSteps(test.steps); }, [test.steps]);
  useEffect(() => { setNotes(test.notes); }, [test.notes]);

  const save = async (vars: Record<string, string>) => {
    setError('');
    try { await update({ variables: { g: playbookId, t: test.id, ...vars } }); } catch (e: any) { setError(e?.message ?? 'Could not save.'); }
  };
  const stepsChanged = steps !== test.steps;

  return (
    <div data-testid={`negtest-row-${test.id}`} className="border border-gray-200 rounded-lg p-3 mb-3 bg-white">
      <div className="mb-2">
        <Tag>{test.source_ref}</Tag><Text strong>{test.limitation}</Text>
        {test.accepted_as && <div><Text type="secondary">You accepted: {test.accepted_as}</Text></div>}
      </div>
      <div className="mb-1 flex items-center gap-2">
        <Text strong style={{ fontSize: 12 }}>Steps</Text>
        {test.steps_source === 'TEMPLATE' && <Tag color="gold">Template: edit it for your environment</Tag>}
      </div>
      <Input.TextArea rows={5} value={steps} aria-label={`Steps for ${test.source_ref}`} onChange={(e) => setSteps(e.target.value)} />
      <div className="mt-1 mb-3 flex items-center gap-2">
        <Button size="small" disabled={!stepsChanged || !steps.trim() || loading} onClick={() => save({ steps })}>Save steps</Button>
        {stepsChanged && test.result !== 'NOT_RUN' && (
          <Text type="warning" style={{ fontSize: 12 }}>Saving new steps clears the recorded result, because it belongs to the old steps.</Text>
        )}
      </div>
      <div className="mb-2"><Text strong style={{ fontSize: 12 }}>Expected</Text> <Text>{test.expected}</Text></div>
      <div className="flex flex-wrap items-center gap-3 mb-2">
        <Text strong style={{ fontSize: 12 }}>What happened</Text>
        <Select
          style={{ width: 240 }} aria-label={`Result for ${test.source_ref}`} value={test.result} options={RESULT_OPTIONS}
          disabled={loading} onChange={(v) => save({ result: v })}
        />
        {test.tested_at && test.result !== 'NOT_RUN' && (
          <Text type="secondary" style={{ fontSize: 12 }}>recorded {new Date(test.tested_at).toLocaleString()}</Text>
        )}
      </div>
      {test.stale && (
        <Alert type="warning" showIcon style={{ marginBottom: 8 }}
          message="The rule changed after this result was recorded. Run the test again to keep it meaningful." />
      )}
      {test.result === 'DETECTED' && !test.stale && (
        <Alert type="warning" showIcon style={{ marginBottom: 8 }}
          message="The rule raised an alert on something you accepted as not covered. Review the rule or the Blind Spots entry for this point." />
      )}
      <Input.TextArea
        rows={2} placeholder="Notes: host, alert id, what you saw (optional)" aria-label={`Notes for ${test.source_ref}`}
        value={notes} onChange={(e) => setNotes(e.target.value)}
        onBlur={() => { if (notes !== test.notes) save({ notes }); }}
      />
      {error && <Alert type="error" showIcon style={{ marginTop: 8 }} message={error} />}
    </div>
  );
};

/**
 * Negative tests of a Workbench: how to check that the rule stays silent on what the engineer accepted.
 * HEFAISTOS does not run them. The person who ran a test records what happened; nothing else in the Workbench
 * (version, test status, Blind Spots) changes because of it.
 */
export const NegativeTestsPanel: React.FC<{ playbookId?: string }> = ({ playbookId }) => {
  const { tests, error } = useNegativeTests(playbookId);
  if (!playbookId || (!tests.length && !error)) return null;
  if (error) return <Alert type="error" showIcon message="Could not load the negative tests." style={{ marginBottom: 16 }} />;
  const done = tests.filter((t) => t.result !== 'NOT_RUN').length;
  return (
    <div data-testid="negative-tests" className="mb-6 border border-gray-200 rounded-lg p-4 bg-gray-50">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-semibold text-gray-700">Negative tests (accepted limitations)</span>
        <span className="text-[11px] text-gray-500">{done} of {tests.length} recorded</span>
      </div>
      <p className="text-xs text-gray-700 mb-3">
        Each test checks that the rule stays silent on something you accepted as a limitation. You run it yourself, in a lab,
        and record the outcome here. Nothing is run for you and this does not change the Workbench test status.
      </p>
      {tests.map((t) => <Row key={t.id} test={t} playbookId={playbookId} />)}
    </div>
  );
};

/** Shown under Blind Spots when a negative test found the rule covers a point listed there. */
export const BlindSpotCoverageNotice: React.FC<{ playbookId?: string }> = ({ playbookId }) => {
  const { tests } = useNegativeTests(playbookId);
  const hits = unexpectedlyDetected(tests);
  if (!hits.length) return null;
  return (
    <Alert
      type="warning" showIcon style={{ marginTop: 8 }} data-testid="blind-spot-notice"
      message="A negative test found the rule fires on a point listed as a blind spot"
      description={<ul style={{ margin: 0, paddingLeft: 18 }}>{hits.map((t) => <li key={t.id}>{t.limitation}</li>)}</ul>}
    />
  );
};

export default NegativeTestsPanel;
