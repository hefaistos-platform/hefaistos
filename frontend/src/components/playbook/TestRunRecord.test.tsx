import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MockedProvider } from '@apollo/client/testing';
import { RECORD_TEST_RUN, TEST_RUNS_QUERY, TestRun, TestRunRecord } from './TestRunRecord';

const run = (over: Partial<TestRun> = {}): TestRun => ({
  id: 'r1', executed: true, fired: true, notes: 'Ran on lab-win-01', recorded_at: '2026-11-06T12:00:00+00:00',
  recorded_by: 'anna_analyst', stale: false, ...over,
});

const listMock = (runs: TestRun[]) => ({
  request: { query: TEST_RUNS_QUERY, variables: { id: 'g1' } },
  result: { data: { playbookGraph: { __typename: 'PlaybookGraphType', id: 'g1', testRuns: runs } } },
});

const recordMock = (vars: any, runs: TestRun[], spy?: jest.Mock) => ({
  request: { query: RECORD_TEST_RUN, variables: { g: 'g1', ...vars } },
  result: () => { spy?.(); return { data: { recordTestRun: { __typename: 'RecordTestRun', testRuns: runs } } }; },
});

const renderWith = (mocks: any[], id: string | undefined = 'g1') =>
  render(<MockedProvider mocks={mocks} addTypename={false}><TestRunRecord playbookId={id} /></MockedProvider>);

describe('TestRunRecord', () => {
  it('asks to save the Workbench first when it has no id yet, and offers no form', () => {
    renderWith([], '');
    expect(screen.getByText(/Save the Workbench first/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Record test run/ })).toBeNull();
  });

  it('cannot record a run that did not happen, and Rule fired needs Test executed', async () => {
    renderWith([listMock([])]);
    const fired = screen.getByLabelText('Rule fired') as HTMLInputElement;
    expect(fired).toBeDisabled();
    expect(screen.getByRole('button', { name: /Record test run/ })).toBeDisabled();
    fireEvent.click(screen.getByLabelText('Test executed'));
    expect(fired).not.toBeDisabled();
    expect(screen.getByRole('button', { name: /Record test run/ })).not.toBeDisabled();
  });

  it('unticking Test executed also clears Rule fired', () => {
    renderWith([listMock([])]);
    fireEvent.click(screen.getByLabelText('Test executed'));
    fireEvent.click(screen.getByLabelText('Rule fired'));
    expect((screen.getByLabelText('Rule fired') as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByLabelText('Test executed'));
    expect((screen.getByLabelText('Rule fired') as HTMLInputElement).checked).toBe(false);
  });

  it('sends exactly what was ticked and typed, then shows the new record and clears the form', async () => {
    const spy = jest.fn();
    const after = [run({ id: 'r2', fired: false, notes: 'Silent' })];
    renderWith([listMock([]), recordMock({ executed: true, fired: false, notes: 'Silent' }, after, spy), listMock(after)]);
    fireEvent.click(screen.getByLabelText('Test executed'));
    fireEvent.change(screen.getByPlaceholderText(/Notes/), { target: { value: 'Silent' } });
    fireEvent.click(screen.getByRole('button', { name: /Record test run/ }));
    expect(await screen.findByText('Rule did not fire')).toBeInTheDocument();
    expect(spy).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Silent')).toBeInTheDocument();
    expect((screen.getByLabelText('Test executed') as HTMLInputElement).checked).toBe(false);
    expect((screen.getByPlaceholderText(/Notes/) as HTMLTextAreaElement).value).toBe('');
  });

  it('records a fired run', async () => {
    const after = [run({ notes: 'Alert 4711' })];
    renderWith([listMock([]), recordMock({ executed: true, fired: true, notes: 'Alert 4711' }, after), listMock(after)]);
    fireEvent.click(screen.getByLabelText('Test executed'));
    fireEvent.click(screen.getByLabelText('Rule fired'));
    fireEvent.change(screen.getByPlaceholderText(/Notes/), { target: { value: 'Alert 4711' } });
    fireEvent.click(screen.getByRole('button', { name: /Record test run/ }));
    expect(await screen.findByText('Rule fired', { selector: '.ant-tag' })).toBeInTheDocument();
  });

  it('shows who recorded it and when, newest first, and marks runs made for an older rule', async () => {
    renderWith([listMock([run({ id: 'a', notes: 'new run' }), run({ id: 'b', notes: 'old run', stale: true, fired: false })])]);
    const items = await screen.findAllByTestId('test-run-item');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('new run');
    expect(items[0]).toHaveTextContent('anna_analyst');
    expect(items[0]).not.toHaveTextContent('The rule changed after this run');
    expect(items[1]).toHaveTextContent('old run');
    expect(items[1]).toHaveTextContent('The rule changed after this run');
  });

  it('shows a server refusal and keeps what the user typed', async () => {
    const failing = {
      request: { query: RECORD_TEST_RUN, variables: { g: 'g1', executed: true, fired: false, notes: 'keep me' } },
      error: new Error('Graph not found or you do not have permission'),
    };
    renderWith([listMock([]), failing]);
    fireEvent.click(screen.getByLabelText('Test executed'));
    fireEvent.change(screen.getByPlaceholderText(/Notes/), { target: { value: 'keep me' } });
    fireEvent.click(screen.getByRole('button', { name: /Record test run/ }));
    expect(await screen.findByTestId('test-run-problem')).toHaveTextContent('do not have permission');
    expect((screen.getByPlaceholderText(/Notes/) as HTMLTextAreaElement).value).toBe('keep me');
    expect((screen.getByLabelText('Test executed') as HTMLInputElement).checked).toBe(true);
  });

  it('says plainly that it is the user\'s own report and not a status change', async () => {
    renderWith([listMock([])]);
    await waitFor(() => expect(screen.getByText(/does not run the test/)).toBeInTheDocument());
    expect(screen.getByText(/does not change the Workbench status or version/)).toBeInTheDocument();
  });

  it('renders no list when nothing was recorded', async () => {
    renderWith([listMock([])]);
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId('test-run-list')).toBeNull();
  });
});
