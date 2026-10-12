import React from 'react';
import { act, render, waitFor } from '@testing-library/react';
import DetectionRuleEditor from './DetectionRuleEditor';
import * as bundledMonaco from 'monaco-editor';
import { Editor } from '@monaco-editor/react';
import { registerCustomLanguages } from '../utils/monacoLanguages';

jest.mock('monaco-editor', () => ({
  languages: { registerCompletionItemProvider: jest.fn(), CompletionItemKind: { Keyword: 17, Field: 4, Value: 12, Operator: 11, Function: 1, Snippet: 27, Text: 18 } },
  MarkerSeverity: { Error: 8, Warning: 4, Info: 2, Hint: 1 },
}), { virtual: true });
jest.mock('@monaco-editor/react', () => ({ Editor: jest.fn(() => <div />) }));
jest.mock('../utils/monacoLanguages', () => ({ registerCustomLanguages: jest.fn() }));
jest.mock('../utils/lspClient', () => ({ LSPClient: jest.fn() }));
jest.mock('../context/ThemeContext', () => ({ useTheme: () => ({ resolvedTheme: 'light' }) }));
jest.mock('../config/env', () => ({ getApiBaseUrl: () => 'https://api.example.test' }));

const cancellation = { isCancellationRequested: false };
const position = { lineNumber: 1, column: 3 };

function mountEditor(format: 'KQL' | 'EQL' | 'SPL' | 'WAZUH' | 'AQL' | 'FREE', text = 'wh') {
  const providers: any[] = [];
  const dispose = jest.fn();
  const runtime = {
    languages: { registerCompletionItemProvider: jest.fn((_language, provider) => { providers.push(provider); return { dispose }; }) },
    editor: { setModelMarkers: jest.fn() },
  };
  const model = { getValue: () => text, getOffsetAt: () => text.length, getLanguageId: () => format.toLowerCase() };
  const view = render(<DetectionRuleEditor value={text} onChange={jest.fn()} format={format} enableLSP={false} enableSemanticValidation={false} />);
  const props = (Editor as unknown as jest.Mock).mock.calls.slice(-1)[0][0];
  act(() => { props.beforeMount(runtime); props.onMount({ getModel: () => model }, runtime); });
  return { ...view, runtime, model, providers, dispose };
}

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.setItem('accessToken', 'test-token');
  globalThis.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ data: { getAutocompleteOptions: { result: { suggestions: [{ label: 'where', kind: 'keyword', insertText: 'where ' }], isComplete: true } } } }) });
});

test.each(['KQL', 'EQL', 'SPL', 'WAZUH', 'AQL'] as const)('%s registers and returns suggestions on the editor runtime', async (format) => {
  const { runtime, model, providers, dispose, unmount } = mountEditor(format);
  await waitFor(() => expect(runtime.languages.registerCompletionItemProvider).toHaveBeenCalled());
  expect(registerCustomLanguages).toHaveBeenCalledWith(runtime);
  expect(bundledMonaco.languages.registerCompletionItemProvider).not.toHaveBeenCalled();
  const result = await providers[0].provideCompletionItems(model, position, {}, cancellation);
  expect(result.suggestions[0]).toMatchObject({ label: 'where', insertText: 'where ', range: { startColumn: 1, endColumn: 3 } });
  expect(result.incomplete).toBe(true);
  const request = (globalThis.fetch as jest.Mock).mock.calls[0];
  expect(request[0]).toBe('https://api.example.test/graphql');
  expect(request[1].headers.Authorization).toBe('Bearer test-token');
  expect(JSON.parse(request[1].body).variables).toMatchObject({ format, context: 'wh', position: 2 });
  unmount();
  expect(dispose).toHaveBeenCalled();
});

test('rapid typing and repeated manual triggers do not return empty throttle results', async () => {
  const { model, providers } = mountEditor('KQL');
  const results = await Promise.all([
    providers[0].provideCompletionItems(model, position, {}, cancellation),
    providers[0].provideCompletionItems(model, position, {}, cancellation),
  ]);
  expect(results.every(result => result.suggestions.length > 0)).toBe(true);
  expect(globalThis.fetch).toHaveBeenCalledTimes(2);
});

test('global providers do not use another editor model or cancelled requests', async () => {
  const { model, providers } = mountEditor('KQL');
  expect(await providers[0].provideCompletionItems({}, position, {}, cancellation)).toEqual({ suggestions: [] });
  expect(await providers[0].provideCompletionItems(model, position, {}, { isCancellationRequested: true })).toEqual({ suggestions: [] });
  expect(globalThis.fetch).not.toHaveBeenCalled();
});

test('FREE highlighting registers no backend autocomplete provider', () => {
  const { runtime } = mountEditor('FREE');
  expect(runtime.languages.registerCompletionItemProvider).not.toHaveBeenCalled();
  expect(globalThis.fetch).not.toHaveBeenCalled();
});

 test('Wazuh tag suggestions preserve the opening angle bracket', async () => {
   const { model, providers } = mountEditor('WAZUH', '<ru');
   const result = await providers[0].provideCompletionItems(model, { lineNumber: 1, column: 4 }, {}, cancellation);
   expect(result.suggestions[0].range).toMatchObject({ startColumn: 2, endColumn: 4 });
   expect(providers[0].triggerCharacters).toContain('<');
 });
