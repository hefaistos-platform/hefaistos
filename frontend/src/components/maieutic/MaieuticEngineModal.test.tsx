import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MaieuticEngineModal } from './MaieuticEngineModal';

const mockAskAI = jest.fn();

jest.mock('@apollo/client/react', () => ({
  useMutation: () => [mockAskAI, { loading: false, error: null }],
}));

const aiResponsePayload = {
  socratic_question: 'What is the most specific behavior you can name?',
  teaching_note: 'Specificity improves detection quality.',
  reasoning: 'Narrowing scope reduces ambiguity.',
  answer_template: 'Intent: ... | Mechanism: ...',
  completion_check: {
    step_ready: true,
    quality_score: 90,
    missing_items: [],
    next_best_action: 'Proceed to the next step.',
  },
  field_suggestions: {},
  autofill_candidates: {
    target_fields: [],
    proposed_text: {},
  },
};

const makeMutationResult = () => ({
  data: {
    maieuticQuestion: {
      aiResponse: aiResponsePayload,
      providerUsed: 'GPT-5.5',
      fieldSuggestions: JSON.stringify({}),
      autofillCandidates: JSON.stringify({ target_fields: [], proposed_text: {} }),
    },
  },
});

describe('MaieuticEngineModal 2.0', () => {
  const mockOnClose = jest.fn();
  const mockOnSubmit = jest.fn();

  beforeEach(() => {
    mockOnClose.mockClear();
    mockOnSubmit.mockClear();
    mockAskAI.mockReset();
    mockAskAI.mockResolvedValue(makeMutationResult());
  });

  test('renders when open and shows 2.0 title', async () => {
    render(<MaieuticEngineModal isOpen={true} onClose={mockOnClose} onSubmit={mockOnSubmit} />);
    expect(screen.getByText('Maieutic Engine 2.0')).toBeInTheDocument();

    await waitFor(() => {
      expect(mockAskAI).toHaveBeenCalled(); // auto kickoff
    });
  });

  test('does not render when closed', () => {
    render(<MaieuticEngineModal isOpen={false} onClose={mockOnClose} onSubmit={mockOnSubmit} />);
    expect(screen.queryByText('Maieutic Engine 2.0')).not.toBeInTheDocument();
  });

  test('keeps Next disabled until required hypothesis fields are filled', async () => {
    render(<MaieuticEngineModal isOpen={true} onClose={mockOnClose} onSubmit={mockOnSubmit} />);

    const nextButton = screen.getByRole('button', { name: /Next/i });
    expect(nextButton).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText(/What adversary behavior/i), {
      target: { value: 'Detect credential access behavior' },
    });
    fireEvent.change(screen.getByPlaceholderText(/What technical capability/i), {
      target: { value: 'LSASS handle and memory read sequence' },
    });

    await waitFor(() => {
      expect(nextButton).not.toBeDisabled();
    });
  });

  test('can progress through all stages and submit', async () => {
    render(<MaieuticEngineModal isOpen={true} onClose={mockOnClose} onSubmit={mockOnSubmit} />);

    fireEvent.change(screen.getByPlaceholderText(/What adversary behavior/i), {
      target: { value: 'Detect credential dumping behavior' },
    });
    fireEvent.change(screen.getByPlaceholderText(/What technical capability/i), {
      target: { value: 'LSASS memory access and dump artifacts' },
    });

    const next = () => screen.getByRole('button', { name: /Next/i });

    await waitFor(() => expect(next()).not.toBeDisabled());
    fireEvent.click(next());

    fireEvent.change(screen.getByPlaceholderText(/Enter a question about the hypothesis/i), {
      target: { value: 'What data source captures this?' },
    });
    fireEvent.change(screen.getByPlaceholderText(/Enter the answer/i), {
      target: { value: 'Sysmon event telemetry and EDR process traces' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Add Q&A Entry/i }));

    await waitFor(() => expect(next()).not.toBeDisabled());
    fireEvent.click(next());

    fireEvent.change(screen.getByPlaceholderText(/Assess reliability and completeness/i), {
      target: { value: 'High-quality telemetry from Sysmon and EDR.' },
    });
    fireEvent.change(screen.getByPlaceholderText(/Expected false positive rate/i), {
      target: { value: 'Low with baseline tuning for admin tools.' },
    });
    fireEvent.change(screen.getByPlaceholderText(/Coverage gaps and known blind spots/i), {
      target: { value: 'Gap: unmanaged endpoints without logging.' },
    });
    fireEvent.change(screen.getByPlaceholderText(/Overall robustness reasoning/i), {
      target: { value: 'Behavior-based logic with clear fallback conditions.' },
    });

    await waitFor(() => expect(next()).not.toBeDisabled());
    fireEvent.click(next());

    fireEvent.change(screen.getByPlaceholderText(/Manual investigation and response steps/i), {
      target: { value: 'Validate lineage, isolate host, reset impacted credentials.' },
    });

    await waitFor(() => expect(next()).not.toBeDisabled());
    fireEvent.click(next());

    const submitButton = screen.getByRole('button', { name: /Submit to Workbench/i });
    await waitFor(() => expect(submitButton).not.toBeDisabled());
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledTimes(1);
    });

    const [, selections] = mockOnSubmit.mock.calls[0];
    expect(selections.importSynthesis).toBe(true);
  });

  test('does not offer Sigma as a detection rule format', async () => {
    render(<MaieuticEngineModal isOpen={true} onClose={mockOnClose} onSubmit={mockOnSubmit} />);

    fireEvent.change(screen.getByPlaceholderText(/What adversary behavior/i), {
      target: { value: 'Detect suspicious credential access behavior' },
    });
    fireEvent.change(screen.getByPlaceholderText(/What technical capability/i), {
      target: { value: 'LSASS read and credential extraction sequence' },
    });

    const next = () => screen.getByRole('button', { name: /Next/i });
    await waitFor(() => expect(next()).not.toBeDisabled());
    fireEvent.click(next());

    fireEvent.change(screen.getByPlaceholderText(/Enter a question about the hypothesis/i), {
      target: { value: 'Which data source exposes process access intent?' },
    });
    fireEvent.change(screen.getByPlaceholderText(/Enter the answer/i), {
      target: { value: 'Sysmon process access and EDR telemetry.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Add Q&A Entry/i }));

    await waitFor(() => expect(next()).not.toBeDisabled());
    fireEvent.click(next());

    fireEvent.change(screen.getByPlaceholderText(/Assess reliability and completeness/i), {
      target: { value: 'High confidence in endpoint telemetry quality.' },
    });
    fireEvent.change(screen.getByPlaceholderText(/Expected false positive rate/i), {
      target: { value: 'Low after baseline tuning.' },
    });
    fireEvent.change(screen.getByPlaceholderText(/Coverage gaps and known blind spots/i), {
      target: { value: 'Blind spot on unmanaged hosts.' },
    });
    fireEvent.change(screen.getByPlaceholderText(/Overall robustness reasoning/i), {
      target: { value: 'Strong behavior anchoring with evasion awareness.' },
    });

    await waitFor(() => expect(next()).not.toBeDisabled());
    fireEvent.click(next());

    expect(screen.queryByRole('option', { name: 'Sigma' })).not.toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'KQL' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'SPL' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Pseudocode' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Other' })).toBeInTheDocument();
  });

  test('allows progression when required fields are complete even if AI readiness is advisory', async () => {
    mockAskAI.mockResolvedValue({
      data: {
        maieuticQuestion: {
          aiResponse: {
            ...aiResponsePayload,
            completion_check: {
              step_ready: false,
              quality_score: 74,
              missing_items: ['capability'],
              next_best_action: 'Add more detail about capability.',
            },
          },
          providerUsed: 'GPT-5.5',
          fieldSuggestions: JSON.stringify({}),
          autofillCandidates: JSON.stringify({ target_fields: [], proposed_text: {} }),
        },
      },
    });

    render(<MaieuticEngineModal isOpen={true} onClose={mockOnClose} onSubmit={mockOnSubmit} />);

    fireEvent.change(screen.getByPlaceholderText(/What adversary behavior/i), {
      target: { value: 'Detect suspicious script proxy execution behavior' },
    });
    fireEvent.change(screen.getByPlaceholderText(/What technical capability/i), {
      target: { value: 'ATT&CK T1218.005 mshta execution chain' },
    });

    const nextButton = screen.getByRole('button', { name: /Next/i });
    await waitFor(() => expect(nextButton).not.toBeDisabled());
    expect(screen.getByText(/You can continue now\. AI suggests refining/i)).toBeInTheDocument();
  });

  test('explains challenge levels clearly', async () => {
    render(<MaieuticEngineModal isOpen={true} onClose={mockOnClose} onSubmit={mockOnSubmit} />);

    expect(screen.getByText(/Standard: balanced depth/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Challenge/i), { target: { value: 'expert' } });
    expect(screen.getByText(/Expert: assumes advanced detection knowledge/i)).toBeInTheDocument();
  });

  test('seeds hypothesis context from selected ATT&CK technique', async () => {
    render(
      <MaieuticEngineModal
        isOpen={true}
        onClose={mockOnClose}
        onSubmit={mockOnSubmit}
        workbenchContext={{
          techniqueId: 'T1218.005',
          techniqueName: 'Mshta',
          detectionFocusLayer: 'Execution',
          goal: 'Detect suspicious mshta script execution chain',
        }}
      />,
    );

    const intentField = screen.getByPlaceholderText(/What adversary behavior/i) as HTMLTextAreaElement;
    const capabilityField = screen.getByPlaceholderText(/What technical capability/i) as HTMLTextAreaElement;

    await waitFor(() => {
      expect(intentField.value).toContain('Detect suspicious mshta script execution chain');
      expect(capabilityField.value).toContain('T1218.005');
    });

    expect(screen.getByText(/Loaded Workbench context:/i)).toBeInTheDocument();
  });

  test('auto-fills detection rule hint in selected format even when AI responds with a question', async () => {
    mockAskAI.mockImplementation(({ variables }: any) => {
      const userInput = String(variables?.userInput || '');
      if (userInput.includes('Draft a starter detection rule in')) {
        return Promise.resolve({
          data: {
            maieuticQuestion: {
              aiResponse: {
                ...aiResponsePayload,
                socratic_question:
                  'For this behavior, what exact escalation threshold should move this to analyst containment?',
                answer_template: '',
                field_suggestions: {},
                autofill_candidates: {
                  target_fields: [],
                  proposed_text: {},
                },
              },
              providerUsed: 'GPT-5.5',
              fieldSuggestions: JSON.stringify({}),
              autofillCandidates: JSON.stringify({ target_fields: [], proposed_text: {} }),
            },
          },
        });
      }
      return Promise.resolve(makeMutationResult());
    });

    render(<MaieuticEngineModal isOpen={true} onClose={mockOnClose} onSubmit={mockOnSubmit} />);

    fireEvent.change(screen.getByPlaceholderText(/What adversary behavior/i), {
      target: { value: 'Detect suspicious credential dumping behavior' },
    });
    fireEvent.change(screen.getByPlaceholderText(/What technical capability/i), {
      target: { value: 'ATT&CK T1003.001 LSASS memory access and dump behavior' },
    });

    const next = () => screen.getByRole('button', { name: /Next/i });
    await waitFor(() => expect(next()).not.toBeDisabled());
    fireEvent.click(next());

    fireEvent.change(screen.getByPlaceholderText(/Enter a question about the hypothesis/i), {
      target: { value: 'Which telemetry confirms this behavior?' },
    });
    fireEvent.change(screen.getByPlaceholderText(/Enter the answer/i), {
      target: { value: 'Sysmon process creation and EDR process telemetry.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Add Q&A Entry/i }));

    await waitFor(() => expect(next()).not.toBeDisabled());
    fireEvent.click(next());

    fireEvent.change(screen.getByPlaceholderText(/Assess reliability and completeness/i), {
      target: { value: 'High quality endpoint telemetry with known blind spots on unmanaged hosts.' },
    });
    fireEvent.change(screen.getByPlaceholderText(/Expected false positive rate/i), {
      target: { value: 'Low after allow-listing approved admin diagnostics tooling.' },
    });
    fireEvent.change(screen.getByPlaceholderText(/Coverage gaps and known blind spots/i), {
      target: { value: 'Unmanaged endpoints and legacy hosts without Sysmon.' },
    });
    fireEvent.change(screen.getByPlaceholderText(/Overall robustness reasoning/i), {
      target: { value: 'Behavior-level signal remains stable across tool changes.' },
    });

    await waitFor(() => expect(next()).not.toBeDisabled());
    fireEvent.click(next());

    const detectionRuleTextarea = screen.getByPlaceholderText(/Enter your detection rule here/i) as HTMLTextAreaElement;
    expect(detectionRuleTextarea.value).toBe('');

    const detectionRuleLabel = screen.getByText(/^Detection Rule$/i);
    const detectionLabelRow = detectionRuleLabel.closest('label');
    expect(detectionLabelRow).toBeTruthy();
    fireEvent.click(within(detectionLabelRow as HTMLElement).getByRole('button', { name: /Get AI hint/i }));

    await waitFor(() => {
      expect(detectionRuleTextarea.value.length).toBeGreaterThan(0);
      expect(detectionRuleTextarea.value).toContain('DeviceProcessEvents');
      expect(detectionRuleTextarea.value).toContain('T1003.001');
    });
  });
});
