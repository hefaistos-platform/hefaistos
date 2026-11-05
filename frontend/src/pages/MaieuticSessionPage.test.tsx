import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockUpdate = jest.fn();
const mockAnswer = jest.fn();
const mockHint = jest.fn();
const mockCreate = jest.fn();
const mockNavigate = jest.fn();
let mockDraft: any;

const PLAN = {
  openCount: 1,
  needsQuestion: [],
  items: [{
    adeId: 'ADE2-01', state: 'OPEN', version: 1, triggerReason: 'x', designRefs: ['match_element:m1'],
    questionText: 'You plan to detect rundll32. What other tools could do the same?',
    whyWeAsk: 'Because attackers choose their tools.', weakAnswer: 'Nothing else.', strongAnswer: 'Named alternatives.',
    glossary: [], hintRungsUsed: 0, hintRungsTotal: 3, ledgerEntry: null,
  }],
};

jest.mock('@apollo/client', () => {
  const actual = jest.requireActual('@apollo/client');
  const opName = (doc: any) => doc.definitions[0].name?.value;
  return {
    ...actual,
    useQuery: (doc: any) => {
      switch (opName(doc)) {
        case 'MaieuticSession': return { data: { maieuticDraft: mockDraft }, loading: false, error: undefined };
        case 'MaieuticSources': return { data: { allLogSources: [{ id: 'l1', name: 'Sysmon Process Creation', coverageStatus: 'ACTIVE', siemProduct: 'X' }], allDataSources: [] }, loading: false };
        case 'MaieuticAdePlan': return { data: { maieuticAdePlan: PLAN }, loading: false, error: undefined, refetch: jest.fn() };
        default: return { data: undefined, loading: false };
      }
    },
    useLazyQuery: () => [jest.fn(), { data: undefined, loading: false }],
    useMutation: (doc: any) => {
      const n = opName(doc);
      if (n === 'UpdateMaieuticDraft') return [mockUpdate, {}];
      if (n === 'AnswerMaieuticAdeQuestion') return [mockAnswer, { loading: false }];
      if (n === 'CreateWorkbenchFromMaieuticDraft') return [mockCreate, { loading: false }];
      return [mockHint, {}];
    },
  };
});

jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => mockNavigate,
}));

// eslint-disable-next-line import/first
import MaieuticSessionPage from './MaieuticSessionPage';

const renderPage = () => render(
  <MemoryRouter initialEntries={['/maieutics/d1']}>
    <Routes>
      <Route path="/maieutics/:draftId" element={<MaieuticSessionPage />} />
      <Route path="/playbooks" element={<div>HUB</div>} />
    </Routes>
  </MemoryRouter>,
);

beforeEach(() => {
  mockUpdate.mockReset().mockResolvedValue({ data: {} });
  mockAnswer.mockReset().mockResolvedValue({
    data: { answerMaieuticAdeQuestion: { evaluatorFlag: 'VAGUE', evaluatorSource: 'AI', followUp: 'Which of those would you still see?', openCount: 0 } },
  });
  mockCreate.mockReset().mockResolvedValue({ data: { createWorkbenchFromMaieuticDraft: { workbenchId: 'wb-1', queuedFormats: ['KQL'] } } });
  mockNavigate.mockReset();
  mockHint.mockReset().mockResolvedValue({ data: { revealMaieuticHint: { hint: 'Look at the ATT&CK page.', rung: 1 } } });
  mockDraft = {
    id: 'd1', name: 'My idea', status: 'IN_PROGRESS', currentStage: 1, isLocked: false, tlpClassification: 'UNCLEAR',
    updatedAt: '2026-11-05', spec: { hypothesis: { title: '' } },
  };
});

describe('MaieuticSessionPage', () => {
  it('shows stage 1 and autosaves a typed title as one section patch', async () => {
    renderPage();
    expect(screen.getByText('1. Hypothesis')).toBeInTheDocument();
    const title = screen.getAllByRole('textbox')[1];
    fireEvent.change(title, { target: { value: 'LSASS dump' } });
    await waitFor(() => expect(mockUpdate).toHaveBeenCalled(), { timeout: 3000 });
    const vars = mockUpdate.mock.calls[0][0].variables;
    expect(vars.patch).toEqual({ hypothesis: expect.objectContaining({ title: 'LSASS dump' }) });
    expect(Object.keys(vars.patch)).toEqual(['hypothesis']);
  });

  it('saves pending edits before moving to the next stage and remembers the stage', async () => {
    renderPage();
    fireEvent.change(screen.getAllByRole('textbox')[1], { target: { value: 'T' } });
    fireEvent.click(screen.getByRole('button', { name: /Next/ }));
    expect(await screen.findByText('2. Telemetry')).toBeInTheDocument();
    const calls = mockUpdate.mock.calls.map((c) => c[0].variables);
    expect(calls[0].patch.hypothesis.title).toBe('T');
    expect(calls.some((v) => v.stage === 2)).toBe(true);
  });

  it('refuses to open a finished session for editing', () => {
    mockDraft = { ...mockDraft, status: 'FINISHED', isLocked: true };
    renderPage();
    expect(screen.getByText(/finished and locked/i)).toBeInTheDocument();
    expect(screen.queryByText('1. Hypothesis')).not.toBeInTheDocument();
  });

  it('blocks Create Workbench until the stage 1 minimum is there, and says what is missing', async () => {
    mockDraft = { ...mockDraft, currentStage: 6 };
    renderPage();
    expect(await screen.findByText('6. Review')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Create Workbench and generate rule/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Create Workbench without a rule/ })).toBeDisabled();
    expect(screen.getByText(/you still need a title, a technique or the choice of none, a goal/i)).toBeInTheDocument();
    expect(screen.getByText(/not a quality score/i)).toBeInTheDocument();
  });

  it('creates the Workbench after confirmation, saving first, and opens it', async () => {
    mockDraft = { ...mockDraft, currentStage: 6, spec: { hypothesis: { title: 'T', goal: 'G', technique: { state: 'NONE_CHOSEN' } } } };
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /Create Workbench and generate rule/ }));
    expect(mockCreate).not.toHaveBeenCalled(); // asks first, because it locks the session
    fireEvent.click(await screen.findByRole('button', { name: 'Create' }));
    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    expect(mockCreate.mock.calls[0][0].variables).toEqual({ id: 'd1', exit: 'CREATE_AND_GENERATE' });
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/playbooks/wb-1'));
  });

  it('shows the server error and stays on the page when creation fails', async () => {
    mockCreate.mockRejectedValue(new Error('Rule generation needs an AI provider.'));
    mockDraft = { ...mockDraft, currentStage: 6, spec: { hypothesis: { title: 'T', goal: 'G', technique: { state: 'NONE_CHOSEN' } } } };
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /Create Workbench and generate rule/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Create' }));
    expect(await screen.findByText(/needs an AI provider/)).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('asks the planned ADE question, needs a status before saving, and shows the advisory follow-up', async () => {
    mockDraft = { ...mockDraft, currentStage: 4, spec: { hypothesis: { title: 'T' }, design: {} } };
    renderPage();
    const q = await screen.findByText(/You plan to detect rundll32/, { selector: '.ant-collapse-header-text span, .ant-collapse-header-text' }).catch(() => null);
    const header = q || (await screen.findAllByText(/You plan to detect rundll32/))[0];
    fireEvent.click(header);
    const save = await screen.findByRole('button', { name: 'Save answer' });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByPlaceholderText(/in your own words/i), { target: { value: 'regsvr32 too, not covered' } });
    expect(save).toBeDisabled(); // still no status chosen
    fireEvent.click(screen.getByRole('button', { name: /I do not know yet/ }));
    await waitFor(() => expect(mockAnswer).toHaveBeenCalled());
    expect(mockAnswer.mock.calls[0][0].variables).toEqual(expect.objectContaining({ ade: 'ADE2-01', disp: 'UNKNOWN', text: '' }));
    expect(await screen.findByText(/Which of those would you still see/)).toBeInTheDocument();
    expect(screen.getByText(/did not block saving/)).toBeInTheDocument();
  });
});
