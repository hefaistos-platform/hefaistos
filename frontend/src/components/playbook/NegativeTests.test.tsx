import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MockedProvider } from '@apollo/client/testing';
import { NEGATIVE_TESTS_QUERY, UPDATE_NEGATIVE_TEST, NegativeTest, NegativeTestsPanel, BlindSpotCoverageNotice, unexpectedlyDetected } from './NegativeTests';

const test = (over: Partial<NegativeTest> = {}): NegativeTest => ({
  id: 't1', source_ref: 'ADE4-01', limitation: 'Ordinal export?', accepted_as: 'accepted', steps: 'Step one', steps_source: 'TEMPLATE',
  expected: 'No alert is raised.', result: 'NOT_RUN', notes: '', tested_at: null, stale: false, ...over,
});

const mockFor = (tests: NegativeTest[]) => ({
  request: { query: NEGATIVE_TESTS_QUERY, variables: { id: 'g1' } },
  result: { data: { playbookGraph: { __typename: 'PlaybookGraphType', id: 'g1', negativeTests: tests } } },
});

const renderWith = (ui: React.ReactElement, tests: NegativeTest[]) =>
  render(<MockedProvider mocks={[mockFor(tests)]} addTypename={false}>{ui}</MockedProvider>);

describe('unexpectedlyDetected', () => {
  it('counts only fresh DETECTED results', () => {
    const rows = [test({ id: 'a', result: 'DETECTED' }), test({ id: 'b', result: 'DETECTED', stale: true }),
      test({ id: 'c', result: 'NOT_DETECTED' }), test({ id: 'd', result: 'NOT_RUN' })];
    expect(unexpectedlyDetected(rows).map((t) => t.id)).toEqual(['a']);
  });
});

describe('NegativeTestsPanel', () => {
  it('renders nothing for a Workbench without negative tests', async () => {
    const { container } = renderWith(<NegativeTestsPanel playbookId="g1" />, []);
    await new Promise((r) => setTimeout(r, 20));
    expect(container.querySelector('[data-testid="negative-tests"]')).toBeNull();
  });

  it('shows the procedure, marks a template and says nothing is run for the user', async () => {
    renderWith(<NegativeTestsPanel playbookId="g1" />, [test()]);
    expect(await screen.findByText('Ordinal export?')).toBeInTheDocument();
    expect(screen.getByText(/Template: edit it/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing is run for you/)).toBeInTheDocument();
    expect(screen.getByText('0 of 1 recorded')).toBeInTheDocument();
    expect((screen.getByLabelText('Steps for ADE4-01') as HTMLTextAreaElement).value).toBe('Step one');
  });

  it('does not mark a test the user wrote as a template', async () => {
    renderWith(<NegativeTestsPanel playbookId="g1" />, [test({ steps_source: 'USER' })]);
    await screen.findByText('Ordinal export?');
    expect(screen.queryByText(/Template: edit it/)).not.toBeInTheDocument();
  });

  it('warns when the rule fired, and when the result is out of date', async () => {
    renderWith(<NegativeTestsPanel playbookId="g1" />, [test({ id: 'a', result: 'DETECTED' }), test({ id: 'b', source_ref: 'ADE4-02', result: 'NOT_DETECTED', stale: true })]);
    expect(await screen.findByText(/raised an alert on something you accepted/)).toBeInTheDocument();
    expect(screen.getByText(/The rule changed after this result was recorded/)).toBeInTheDocument();
    expect(screen.getByText('2 of 2 recorded')).toBeInTheDocument();
  });

  it('only enables Save steps for real changes, and warns that it clears a recorded result', async () => {
    renderWith(<NegativeTestsPanel playbookId="g1" />, [test({ result: 'NOT_DETECTED', tested_at: '2026-11-06T10:00:00Z' })]);
    const save = await screen.findByRole('button', { name: 'Save steps' });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Steps for ADE4-01'), { target: { value: 'Changed' } });
    await waitFor(() => expect(save).toBeEnabled());
    expect(screen.getByText(/clears the recorded result/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Steps for ADE4-01'), { target: { value: '   ' } });
    await waitFor(() => expect(save).toBeDisabled());
  });
});

describe('saving', () => {
  it('sends the steps for the right Workbench and test, then shows the refreshed list', async () => {
    const saved = test({ steps: 'Changed', steps_source: 'USER' });
    const mutation = {
      request: { query: UPDATE_NEGATIVE_TEST, variables: { g: 'g1', t: 't1', steps: 'Changed' } },
      result: jest.fn(() => ({ data: { updateNegativeTest: { negativeTests: [saved] } } })),
    };
    render(
      <MockedProvider mocks={[mockFor([test()]), mutation, mockFor([saved])]} addTypename={false}>
        <NegativeTestsPanel playbookId="g1" />
      </MockedProvider>,
    );
    await screen.findByText('Ordinal export?');
    fireEvent.change(screen.getByLabelText('Steps for ADE4-01'), { target: { value: 'Changed' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save steps' }));
    await waitFor(() => expect(mutation.result).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByText(/Template: edit it/)).not.toBeInTheDocument());
  });

  it('shows the server error instead of failing silently', async () => {
    const mutation = {
      request: { query: UPDATE_NEGATIVE_TEST, variables: { g: 'g1', t: 't1', steps: 'Changed' } },
      error: new Error('Negative test not found.'),
    };
    render(
      <MockedProvider mocks={[mockFor([test()]), mutation]} addTypename={false}>
        <NegativeTestsPanel playbookId="g1" />
      </MockedProvider>,
    );
    await screen.findByText('Ordinal export?');
    fireEvent.change(screen.getByLabelText('Steps for ADE4-01'), { target: { value: 'Changed' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save steps' }));
    expect(await screen.findByText(/Negative test not found/)).toBeInTheDocument();
  });
});

describe('BlindSpotCoverageNotice', () => {
  it('is silent unless a fresh test found the rule covers the point', async () => {
    const { container } = renderWith(<BlindSpotCoverageNotice playbookId="g1" />, [test({ result: 'NOT_DETECTED' }), test({ id: 'x', result: 'DETECTED', stale: true })]);
    await new Promise((r) => setTimeout(r, 20));
    expect(container.querySelector('[data-testid="blind-spot-notice"]')).toBeNull();
  });
  it('names the limitation when the rule fired', async () => {
    renderWith(<BlindSpotCoverageNotice playbookId="g1" />, [test({ result: 'DETECTED' })]);
    expect(await screen.findByTestId('blind-spot-notice')).toHaveTextContent('Ordinal export?');
  });
});
