import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import DetectionRuleEditorModal, {
  buildGenerateAllPlan,
  buildOpenTideState,
  DEFAULT_OVERWRITE_ALL_CONTENT,
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
