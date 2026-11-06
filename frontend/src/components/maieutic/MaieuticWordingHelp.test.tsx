import React, { useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const mockSuggest = jest.fn();
const mockAccept = jest.fn();
const mockRestore = jest.fn();

jest.mock('@apollo/client', () => {
  const actual = jest.requireActual('@apollo/client');
  return {
    ...actual,
    useMutation: (doc: any) => {
      const n = doc.definitions[0].name?.value;
      if (n === 'SuggestMaieuticWording') return [mockSuggest, { loading: false }];
      if (n === 'AcceptMaieuticWording') return [mockAccept, {}];
      return [mockRestore, {}];
    },
  };
});

// eslint-disable-next-line import/first
import { MaieuticWordingHelp, originLabel, TextOrigin } from './MaieuticWordingHelp';

const MINE = 'detect lsass dump via comsvcs minidump through rundll32 on servers';
const AI = 'Detect an LSASS dump made through rundll32 with the comsvcs MiniDump call, on servers.';

const flush = jest.fn();
const onApply = jest.fn();

const Harness: React.FC<{ available?: boolean; locked?: boolean; start?: string; origins?: TextOrigin }> = ({
  available = true, locked = false, start = MINE, origins = {},
}) => {
  const [text, setText] = useState(start);
  return (
    <div>
      <textarea aria-label="goal" value={text} onChange={(e) => setText(e.target.value)} />
      <MaieuticWordingHelp draftId="d1" field="hypothesis.goal" text={text} origins={origins} available={available}
        locked={locked} flush={flush} onApply={(f, v, o) => { onApply(f, v, o); setText(v); }} />
    </div>
  );
};

beforeEach(() => {
  flush.mockReset().mockResolvedValue(true);
  onApply.mockReset();
  mockSuggest.mockReset().mockResolvedValue({ data: { suggestMaieuticWording: { suggestion: AI, message: null, remaining: 4 } } });
  mockAccept.mockReset().mockResolvedValue({ data: { acceptMaieuticWording: { value: AI, textOrigin: { 'hypothesis.goal': { origin: 'AI_REWORDED', accepted_text: AI } } } } });
  mockRestore.mockReset().mockResolvedValue({ data: { restoreMaieuticWording: { value: MINE, textOrigin: {} } } });
});

const ask = () => fireEvent.click(screen.getByRole('button', { name: /Help me word this/ }));

describe('MaieuticWordingHelp', () => {
  it('shows nothing when the user has no AI provider or the session is locked', () => {
    const a = render(<Harness available={false} />);
    expect(screen.queryByRole('button', { name: /Help me word this/ })).toBeNull();
    a.unmount();
    render(<Harness locked />);
    expect(screen.queryByRole('button', { name: /Help me word this/ })).toBeNull();
  });

  it('is disabled until the user has written enough, and says why', () => {
    render(<Harness start="too short" />);
    const btn = screen.getByRole('button', { name: /Help me word this/ });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('title', expect.stringContaining('at least 25'));
    fireEvent.click(btn);
    expect(mockSuggest).not.toHaveBeenCalled();
  });

  it('saves the text first, then shows the suggestion without changing anything', async () => {
    render(<Harness />);
    ask();
    expect(await screen.findByTestId('wording-suggestion')).toHaveTextContent(AI);
    expect(flush).toHaveBeenCalledTimes(1);
    expect(flush.mock.invocationCallOrder[0]).toBeLessThan(mockSuggest.mock.invocationCallOrder[0]);
    expect(screen.getByLabelText('goal')).toHaveValue(MINE);
    expect(onApply).not.toHaveBeenCalled();
    expect(mockAccept).not.toHaveBeenCalled();
  });

  it('does not ask the AI when the text could not be saved', async () => {
    flush.mockResolvedValue(false);
    render(<Harness />);
    ask();
    expect(await screen.findByTestId('wording-note')).toHaveTextContent('could not be saved');
    expect(mockSuggest).not.toHaveBeenCalled();
  });

  it('Use this applies the wording and the server-given origin, once', async () => {
    render(<Harness />);
    ask();
    fireEvent.click(await screen.findByRole('button', { name: 'Use this' }));
    await waitFor(() => expect(onApply).toHaveBeenCalledTimes(1));
    expect(onApply.mock.calls[0][0]).toBe('hypothesis.goal');
    expect(onApply.mock.calls[0][1]).toBe(AI);
    expect(onApply.mock.calls[0][2]['hypothesis.goal'].origin).toBe('AI_REWORDED');
    expect(screen.getByLabelText('goal')).toHaveValue(AI);
    expect(screen.queryByTestId('wording-suggestion')).toBeNull();
  });

  it('Discard throws the suggestion away and touches nothing', async () => {
    render(<Harness />);
    ask();
    fireEvent.click(await screen.findByRole('button', { name: 'Discard' }));
    expect(screen.queryByTestId('wording-suggestion')).toBeNull();
    expect(mockAccept).not.toHaveBeenCalled();
    expect(screen.getByLabelText('goal')).toHaveValue(MINE);
  });

  it('typing after a suggestion arrives makes it disappear, so old wording cannot replace new text', async () => {
    render(<Harness />);
    ask();
    await screen.findByTestId('wording-suggestion');
    fireEvent.change(screen.getByLabelText('goal'), { target: { value: MINE + ' and workstations' } });
    expect(screen.queryByTestId('wording-suggestion')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Use this' })).toBeNull();
  });

  it('explains when the AI had nothing safe to offer, without showing a suggestion', async () => {
    mockSuggest.mockResolvedValue({ data: { suggestMaieuticWording: { suggestion: null, message: 'I could not reword this without adding something you did not write', remaining: 4 } } });
    render(<Harness />);
    ask();
    expect(await screen.findByTestId('wording-note')).toHaveTextContent('without adding something you did not write');
    expect(screen.queryByTestId('wording-suggestion')).toBeNull();
  });

  it('shows server errors such as the per-field limit', async () => {
    mockSuggest.mockRejectedValue(new Error('You have used all wording suggestions for this field in this session.'));
    render(<Harness />);
    ask();
    expect(await screen.findByTestId('wording-note')).toHaveTextContent('used all wording suggestions');
  });

  it('warns when few suggestions are left and disables the button at zero', async () => {
    mockSuggest.mockResolvedValue({ data: { suggestMaieuticWording: { suggestion: null, message: 'x', remaining: 0 } } });
    render(<Harness />);
    ask();
    expect(await screen.findByText('0 suggestions left for this field')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Help me word this/ })).toBeDisabled();
  });

  it('a failed Use this keeps the user text and reports the reason', async () => {
    mockAccept.mockRejectedValue(new Error('Your text changed after this wording was made. Ask for a new one.'));
    render(<Harness />);
    ask();
    fireEvent.click(await screen.findByRole('button', { name: 'Use this' }));
    expect(await screen.findByTestId('wording-note')).toHaveTextContent('Your text changed');
    expect(onApply).not.toHaveBeenCalled();
    expect(screen.getByLabelText('goal')).toHaveValue(MINE);
  });

  it('marks AI wording, offers to put the user text back, and marks edits as edited', async () => {
    const origins = { 'hypothesis.goal': { origin: 'AI_REWORDED', accepted_text: AI } };
    const a = render(<Harness start={AI} origins={origins} />);
    expect(screen.getByText('AI reworded')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Put my text back' }));
    await waitFor(() => expect(onApply).toHaveBeenCalledWith('hypothesis.goal', MINE, {}));
    a.unmount();
    render(<Harness start={AI + ' Also workstations.'} origins={origins} />);
    expect(screen.getByText('AI reworded, then edited by you')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Put my text back' })).toBeNull();   // the server refuses it after edits
  });

  it('plain user text carries no mark at all', () => {
    render(<Harness />);
    expect(screen.queryByText(/AI reworded/)).toBeNull();
    expect(originLabel({}, 'hypothesis.goal', MINE)).toBeNull();
    expect(originLabel({ 'hypothesis.goal': { accepted_text: AI } }, 'hypothesis.goal', '  ')).toBeNull();
    expect(originLabel(undefined, 'hypothesis.goal', MINE)).toBeNull();
    // shared copies keep only the mark
    expect(originLabel({ 'hypothesis.goal': { origin: 'AI_REWORDED' } }, 'hypothesis.goal', AI)).toBe('AI reworded');
    expect(originLabel({ 'hypothesis.goal': { origin: 'AI_REWORDED_EDITED' } }, 'hypothesis.goal', AI)).toBe('AI reworded, then edited by you');
  });
});
