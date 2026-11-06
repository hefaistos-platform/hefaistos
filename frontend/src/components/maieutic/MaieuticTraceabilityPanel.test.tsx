import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import MaieuticTraceabilityPanel, { TraceRow, traceVerdict } from './MaieuticTraceabilityPanel';

const row = (o: Partial<TraceRow>): TraceRow => ({
  ref: 'M1', group: 'MUST_IMPLEMENT', text: 'Match on: rundll32', implemented: 'yes', where: 'line 3', note: 'ok', status: 'REPORTED', ...o,
});

describe('traceVerdict', () => {
  it('never shows a missing report as a pass', () => {
    expect(traceVerdict(row({ status: 'NOT_REPORTED', implemented: null })).label).toBe('Not reported');
    expect(traceVerdict(row({ implemented: null })).label).toBe('Not reported');
  });
  it('flags a rule that claims to cover an accepted limitation', () => {
    const v = traceVerdict(row({ group: 'ACCEPTED_LIMITATION', implemented: 'yes', status: 'CONTRADICTS_LIMITATION' }));
    expect(v.color).toBe('red');
  });
  it('treats an uncovered accepted limitation as expected', () => {
    expect(traceVerdict(row({ group: 'ACCEPTED_LIMITATION', implemented: 'no' })).label).toBe('Not covered, as accepted');
  });
  it('separates implemented, partial and not implemented', () => {
    expect(traceVerdict(row({ implemented: 'yes' })).color).toBe('green');
    expect(traceVerdict(row({ implemented: 'partial' })).color).toBe('orange');
    expect(traceVerdict(row({ implemented: 'no' })).color).toBe('red');
  });
});

describe('MaieuticTraceabilityPanel', () => {
  it('renders nothing without rows', () => {
    const { container } = render(<MaieuticTraceabilityPanel rows={[]} />);
    expect(container.firstChild).toBeNull();
    expect(render(<MaieuticTraceabilityPanel rows={null} />).container.firstChild).toBeNull();
  });

  it('summarises how many decisions need review and says it is not proof', () => {
    render(<MaieuticTraceabilityPanel outputFormat="KQL" rows={[row({}), row({ ref: 'M2', implemented: 'partial' })]} />);
    expect(screen.getByText(/2 decisions, 1 to review/)).toBeTruthy();
    fireEvent.click(screen.getByText(/Where your decisions went/));
    expect(screen.getByText(/not proof/)).toBeTruthy();
    expect(screen.getByTestId('trace-M2')).toBeTruthy();
    expect(screen.queryByText(/automatically repaired/)).toBeNull();
  });

  it('warns that locations may be stale when the rule was repaired after the report', () => {
    render(<MaieuticTraceabilityPanel ruleRepaired rows={[row({})]} />);
    fireEvent.click(screen.getByText(/Where your decisions went/));
    expect(screen.getByText(/automatically repaired/)).toBeTruthy();
  });
});
