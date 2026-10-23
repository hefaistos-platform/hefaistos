import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import DetectionRuleEditorModal, {
  buildGenerateAllPlan,
  buildOpenTideState,
  DEFAULT_OVERWRITE_ALL_CONTENT,
  savedFormatSnapshot,
  formatHasChanges,
} from './DetectionRuleEditorModal';
import type { OpenTideRule } from '../types/opentide';
import { useLazyQuery, useMutation, useQuery } from '@apollo/client/react';

jest.mock('./DataSourcePicker', () => () => <div data-testid="data-source-picker" />);
jest.mock('./RulePicker', () => () => <div data-testid="rule-picker" />);
jest.mock('./DetectionRuleEditor', () => () => <div data-testid="detection-rule-editor" />);
jest.mock('./OpenTideMetadataPreview', () => () => <div data-testid="opentide-metadata-preview" />);
jest.mock('./MarkdownRenderer', () => ({ MarkdownRenderer: () => <div data-testid="markdown-renderer" /> }));
jest.mock('./ui/PixelIcon', () => ({ PixelIcon: () => <span data-testid="pixel-icon" /> }));
jest.mock('react-syntax-highlighter', () => ({ Prism: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
jest.mock('react-syntax-highlighter/dist/esm/styles/prism', () => ({ vscDarkPlus: {} }));
jest.mock('@apollo/client/react', () => ({
  useMutation: jest.fn(),
  useQuery: jest.fn(),
  useLazyQuery: jest.fn(),
}));

const BASE_RULE: OpenTideRule = {
  metadata: {
    title: 'Rule',
    description: '',
    author: 'tester',
    created: '2026-01-01T00:00:00.000Z',
    modified: '2026-01-01T00:00:00.000Z',
    mitre: {},
    capability: {},
    response: {},
  },
  platforms: {
    spl: { query: 'index=main' },
    kql: { query: 'SecurityEvent | take 1' },
    wazuh: { rule: '' },
    qradar: { query: '' },
  },
};

describe('DetectionRuleEditorModal generate-all overwrite behavior', () => {
  beforeEach(() => {
    (useMutation as jest.Mock).mockImplementation(() => [jest.fn(), { loading: false }]);
    (useQuery as jest.Mock).mockReturnValue({ data: { me: { id: '1', username: 'tester', role: 'ADMIN' } } });
    (useLazyQuery as jest.Mock).mockReturnValue([jest.fn()]);
  });

  test('buildGenerateAllPlan skips non-empty targets when overwrite is OFF', () => {
    const plan = buildGenerateAllPlan(BASE_RULE, 'spl', false);

    expect(plan.targetFormats).toEqual(expect.arrayContaining(['WAZUH', 'AQL']));
    expect(plan.targetFormats).toContain('EQL');
    expect(plan.targetFormats).not.toContain('KQL');
    expect(plan.statuses).toMatchObject({
      KQL: 'skipped (non-empty)',
      EQL: 'pending',
      WAZUH: 'pending',
      AQL: 'pending',
    });
  });

  test('buildGenerateAllPlan overwrites all non-source targets when overwrite is ON', () => {
    const plan = buildGenerateAllPlan(BASE_RULE, 'spl', true);

    expect(plan.targetFormats).toEqual(expect.arrayContaining(['KQL', 'EQL', 'WAZUH', 'AQL']));
    expect(plan.statuses).toMatchObject({
      KQL: 'pending',
      EQL: 'pending',
      WAZUH: 'pending',
      AQL: 'pending',
    });
  });

  test('overwrite checkbox is unchecked by default on modal open and resets on reopen', () => {
    const { rerender } = render(
      <DetectionRuleEditorModal
        visible
        onClose={jest.fn()}
        playbookId="11111111-1111-1111-1111-111111111111"
        initialRule="index=main"
        initialFormat="SPL"
        initialMode="manual"
        onSave={jest.fn()}
      />
    );

    const checkbox = screen.getByRole('checkbox', { name: /overwrite all content/i });
    expect(DEFAULT_OVERWRITE_ALL_CONTENT).toBe(false);
    expect(checkbox).not.toBeChecked();

    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();

    rerender(
      <DetectionRuleEditorModal
        visible={false}
        onClose={jest.fn()}
        playbookId="11111111-1111-1111-1111-111111111111"
        initialRule="index=main"
        initialFormat="SPL"
        initialMode="manual"
        onSave={jest.fn()}
      />
    );

    rerender(
      <DetectionRuleEditorModal
        visible
        onClose={jest.fn()}
        playbookId="11111111-1111-1111-1111-111111111111"
        initialRule="index=main"
        initialFormat="SPL"
        initialMode="manual"
        onSave={jest.fn()}
      />
    );

    expect(screen.getByRole('checkbox', { name: /overwrite all content/i })).not.toBeChecked();
  });

  test('buildOpenTideState does not backfill legacy content into another format when platform content already exists', () => {
    const initial: OpenTideRule = {
      metadata: BASE_RULE.metadata,
      platforms: {
        qradar: { query: 'SELECT * FROM events' },
      },
    };

    const state = buildOpenTideState(
      initial,
      'SELECT * FROM events',
      'KQL',
      undefined,
    );

    expect(state.platforms.qradar?.query).toBe('SELECT * FROM events');
    expect(state.platforms.kql?.query ?? '').toBe('');
  });

  test('SAVE ALL persists cleared content via onSave even when no non-empty rules remain', async () => {
    const onSave = jest.fn().mockResolvedValue(undefined);
    render(
      <DetectionRuleEditorModal
        visible
        onClose={jest.fn()}
        playbookId="11111111-1111-1111-1111-111111111111"
        initialRule="SecurityEvent | take 1"
        initialFormat="KQL"
        initialMode="logic"
        onSave={onSave}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /clear content/i }));
    fireEvent.click(screen.getByRole('button', { name: /save all/i }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalled();
    });
  });
});

describe('FREE Format manual editing', () => {
  beforeEach(() => {
    (useMutation as jest.Mock).mockImplementation(() => [jest.fn(), { loading: false }]);
    (useQuery as jest.Mock).mockReturnValue({ data: { me: { id: '1', username: 'tester', role: 'ADMIN' } } });
    (useLazyQuery as jest.Mock).mockReturnValue([jest.fn()]);
  });

  test('FREE content is isolated and excluded from generate-all', () => {
    const raw = '\n\trule example { condition: true }  \n';
    const state = buildOpenTideState(BASE_RULE, raw, 'FREE');
    expect(state.freeRule?.content).toBe(raw);
    expect(state.platforms).toEqual(BASE_RULE.platforms);
    expect(buildGenerateAllPlan(state, 'free', true).targetFormats).toEqual([]);
    expect(buildGenerateAllPlan(state, 'kql', true).targetFormats).not.toContain('FREE');
  });

  test('FREE opens with manual controls and hides AI, RAG and templates', () => {
    render(<DetectionRuleEditorModal visible onClose={jest.fn()} playbookId="1"
      initialRule="rule test {}" initialFormat="FREE" initialMode="manual" onSave={jest.fn()} />);
    expect(screen.getByLabelText('Custom format label')).toBeInTheDocument();
    expect(screen.getByLabelText('Syntax highlighting')).toBeInTheDocument();
    expect(screen.getByLabelText('Custom file extension')).toHaveValue('txt');
    expect(screen.queryByText('Generate with AI')).not.toBeInTheDocument();
    expect(screen.queryByText('RAG Reuse')).not.toBeInTheDocument();
    expect(screen.queryByText('Quick Templates')).not.toBeInTheDocument();
    expect(screen.queryByTestId('data-source-picker')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'SAVE FREE FORMAT' })).toBeInTheDocument();
  });

  test('label changes trigger save and preserve raw content on SAVE ALL', async () => {
    const raw = '\n\trule example {}  \n';
    const saveAll = jest.fn().mockResolvedValue({ data: { saveAllDetectionRules: { success: true, results: [{ format: 'FREE', status: 'saved' }] } } });
    (useMutation as jest.Mock).mockImplementation((document) => {
      const name = document.definitions?.[0]?.name?.value;
      return [name === 'SaveAllDetectionRules' ? saveAll : jest.fn(), { loading: false }];
    });
    const onSave = jest.fn().mockResolvedValue(undefined);
    render(<DetectionRuleEditorModal visible onClose={jest.fn()} playbookId="1"
      initialRule={raw} initialFormat="FREE" initialMode="manual" onSave={onSave} />);
    fireEvent.change(screen.getByLabelText('Custom format label'), { target: { value: 'YARA' } });
    fireEvent.change(screen.getByLabelText('Custom file extension'), { target: { value: '.YARA' } });
    fireEvent.click(screen.getByRole('button', { name: 'SAVE ALL' }));
    await waitFor(() => expect(saveAll).toHaveBeenCalled());
    expect(saveAll.mock.calls[0][0].variables.rules).toEqual([{ format: 'FREE', content: raw, customFormatLabel: 'YARA', editorLanguage: 'plaintext', customFileExtension: 'yara' }]);
    expect(onSave.mock.calls[0][4].freeRule).toEqual({ content: raw, label: 'YARA', language: 'plaintext', extension: 'yara' });
  });
});

 test('FREE reopening retains preferences and whitespace-only edits are dirty', () => {
   const freeRule = { content: 'rule example {}\n', label: 'YARA-L', language: 'xml', extension: 'xml' };
   const initial = { ...BASE_RULE, freeRule };
   const reopened = buildOpenTideState(initial, '', 'FREE');
   expect(reopened.freeRule).toEqual(freeRule);
   const saved = savedFormatSnapshot(initial, 'FREE');
   expect(formatHasChanges(reopened, 'FREE', saved)).toBe(false);
   expect(formatHasChanges({ ...reopened, freeRule: { ...freeRule, content: freeRule.content + '  ' } }, 'FREE', saved)).toBe(true);
 });

 test('extension-only edits are unsaved changes', () => {
   const freeRule = { content: 'rule example {}', label: 'YARA', language: 'plaintext', extension: 'txt' };
   const initial = { ...BASE_RULE, freeRule };
   expect(formatHasChanges({ ...initial, freeRule: { ...freeRule, extension: 'yara' } }, 'FREE', savedFormatSnapshot(initial, 'FREE'))).toBe(true);
 });

describe('Standalone Rule Hub editor', () => {
  beforeEach(() => {
    (useMutation as jest.Mock).mockImplementation(() => [jest.fn(), { loading: false }]);
    (useQuery as jest.Mock).mockReturnValue({ data: { me: { id: '1', username: 'tester', role: 'ADMIN' } } });
    (useLazyQuery as jest.Mock).mockReturnValue([jest.fn()]);
  });

  test('saves edited metadata through standalone callback without Workbench mutations', async () => {
    const onSave = jest.fn().mockResolvedValue(undefined);
    render(<DetectionRuleEditorModal visible standalone onClose={jest.fn()} initialRule="" initialFormat="KQL" initialMode="manual" initialOpenTideRule={BASE_RULE} onSave={onSave} />);
    expect(screen.queryByRole('checkbox', { name: /commit to repository/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /metadata/i }));
    fireEvent.change(screen.getByLabelText('Rule title'), { target: { value: 'Standalone alternative' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Draft' }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(onSave.mock.calls[0][4].metadata.title).toBe('Standalone alternative');
    expect(onSave.mock.calls[0][4].platforms.kql.query).toBe(BASE_RULE.platforms.kql?.query);
    for (const result of (useMutation as jest.Mock).mock.results) expect(result.value[0]).not.toHaveBeenCalled();
  });

  test('publish receives latest metadata and all platforms', async () => {
    const onPublish = jest.fn().mockResolvedValue(undefined);
    render(<DetectionRuleEditorModal visible standalone onClose={jest.fn()} initialRule="" initialFormat="KQL" initialMode="manual" initialOpenTideRule={BASE_RULE} onSave={jest.fn()} onPublish={onPublish} />);
    fireEvent.click(screen.getByRole('button', { name: /metadata/i }));
    fireEvent.change(screen.getByLabelText('Detection description'), { target: { value: 'Updated detection objective' } });
    fireEvent.click(screen.getByRole('button', { name: 'Publish to Git' }));
    expect(onPublish.mock.calls[0][0].metadata.description).toBe('Updated detection objective');
    expect(onPublish.mock.calls[0][0].platforms.spl.query).toBe('index=main');
  });
});
