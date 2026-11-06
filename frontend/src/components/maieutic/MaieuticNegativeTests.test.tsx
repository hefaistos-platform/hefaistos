import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import MaieuticNegativeTests, { acceptedLimitations } from './MaieuticNegativeTests';

const item = (adeId: string, disposition: string, answer = '') => ({
  adeId, questionText: `Question ${adeId}?`, ledgerEntry: disposition ? { disposition, answer_text: answer } : null,
});

describe('acceptedLimitations', () => {
  it('keeps only accepted limitations, never unknown, covered elsewhere, handled or unanswered', () => {
    const rows = acceptedLimitations([
      item('A1', 'ACCEPTED_LIMITATION', 'ok'), item('A2', 'UNKNOWN'), item('A3', 'COVERED_BY_OTHER_RULE'),
      item('A4', 'HANDLED_IN_DESIGN'), item('A5', 'NOT_APPLICABLE'), item('A6', ''),
    ]);
    expect(rows.map((r) => r.adeId)).toEqual(['A1']);
    expect(rows[0].answer).toBe('ok');
  });
  it('tolerates a missing plan', () => {
    expect(acceptedLimitations(undefined)).toEqual([]);
    expect(acceptedLimitations(null)).toEqual([]);
  });
});

describe('MaieuticNegativeTests', () => {
  const lim = [{ adeId: 'A1', question: 'Ordinal export?', answer: 'accepted' }];

  it('does not say there are none while loading, and says so when loading failed', () => {
    const { rerender } = render(<MaieuticNegativeTests limitations={[]} value={[]} onChange={jest.fn()} loading />);
    expect(screen.getByText(/Loading/)).toBeInTheDocument();
    expect(screen.queryByText(/You have none yet/)).not.toBeInTheDocument();
    rerender(<MaieuticNegativeTests limitations={[]} value={[]} onChange={jest.fn()} failed />);
    expect(screen.getByText(/Could not load/)).toBeInTheDocument();
    expect(screen.queryByText(/You have none yet/)).not.toBeInTheDocument();
  });

  it('explains there is nothing to test without accepted limitations', () => {
    render(<MaieuticNegativeTests limitations={[]} value={[]} onChange={jest.fn()} />);
    expect(screen.getByText(/You have none yet/)).toBeInTheDocument();
  });

  it('stores the steps against the limitation and removes the entry when they are cleared', () => {
    const onChange = jest.fn();
    const { rerender } = render(<MaieuticNegativeTests limitations={lim} value={[]} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('Steps to check A1'), { target: { value: '1. run it' } });
    expect(onChange).toHaveBeenLastCalledWith([{ from_ade_id: 'A1', steps: '1. run it' }]);
    rerender(<MaieuticNegativeTests limitations={lim} value={[{ from_ade_id: 'A1', steps: 'x' }]} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('Steps to check A1'), { target: { value: '' } });
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it('keeps the steps of other limitations when one is edited', () => {
    const onChange = jest.fn();
    const two = [...lim, { adeId: 'A2', question: 'Q2?', answer: '' }];
    render(<MaieuticNegativeTests limitations={two} value={[{ from_ade_id: 'A2', steps: 'keep' }]} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('Steps to check A1'), { target: { value: 'new' } });
    expect(onChange).toHaveBeenLastCalledWith([{ from_ade_id: 'A2', steps: 'keep' }, { from_ade_id: 'A1', steps: 'new' }]);
  });

  it('says nothing is run here', () => {
    render(<MaieuticNegativeTests limitations={lim} value={[]} onChange={jest.fn()} />);
    expect(screen.getByText(/Nothing is run for you/)).toBeInTheDocument();
  });
});
