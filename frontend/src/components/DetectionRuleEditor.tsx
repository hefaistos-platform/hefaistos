/**
 * DetectionRuleEditor.tsx
 *
 * Monaco Editor for detection rules with autocomplete and SyntaxTide LSP support.
 * Replaces textarea in DetectionRuleEditorModal.
 */

import React, { useRef, useEffect, useState } from 'react';
import { Editor } from '@monaco-editor/react';
import * as monaco from 'monaco-editor';
import { LSPClient, LspConnectionStatus } from '../utils/lspClient';
import { registerCustomLanguages } from '../utils/monacoLanguages';
import { getApiBaseUrl } from '../config/env';
import { useTheme } from '../context/ThemeContext';

// GraphQL query string for autocomplete
const GET_AUTOCOMPLETE_OPTIONS = `
  mutation GetAutocompleteOptions(
    $format: String!
    $context: String!
    $position: Int!
    $dataSourceId: ID
  ) {
    getAutocompleteOptions(
      format: $format
      context: $context
      position: $position
      dataSourceId: $dataSourceId
    ) {
      result {
        suggestions {
          label
          kind
          insertText
          detail
          documentation
          sortText
          filterText
        }
        isComplete
      }
    }
  }
`;

const VALIDATE_RULE_CONTENT = `
  mutation ValidateRuleContent(
    $format: String!
    $context: String!
    $position: Int!
    $dataSourceId: ID
  ) {
    validateRuleContent(
      format: $format
      context: $context
      position: $position
      dataSourceId: $dataSourceId
    ) {
      result {
        issues {
          line
          column
          message
          severity
        }
      }
    }
  }
`;

interface DetectionRuleEditorProps {
  value: string;
  onChange: (value: string) => void;
  format: 'KQL' | 'EQL' | 'WAZUH' | 'SPL' | 'AQL' | 'OTHER';
  height?: string;
  dataSourceId?: string;
  readOnly?: boolean;
  enableLSP?: boolean;
  enableSemanticValidation?: boolean;
  onBlur?: () => void;
  visualStyle?: 'default' | 'terminal';
}

type LspStatus = 'connecting' | 'connected' | 'error' | 'disabled';

function defineTerminalTheme(monacoApi: typeof monaco) {
  monacoApi.editor.defineTheme('hef-terminal', {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: '', foreground: '8BFF8B' },
      { token: 'comment', foreground: '4EA35B' },
      { token: 'string', foreground: 'A5FFAD' },
      { token: 'keyword', foreground: '6DFE6D' },
      { token: 'number', foreground: '8CF7C8' },
    ],
    colors: {
      'editor.background': '#071108',
      'editor.foreground': '#8BFF8B',
      'editorLineNumber.foreground': '#2C6E3A',
      'editorLineNumber.activeForeground': '#8BFF8B',
      'editorCursor.foreground': '#C9FFBA',
      'editor.selectionBackground': '#123A1B',
      'editor.inactiveSelectionBackground': '#0D2A14',
      'editorGutter.background': '#071108',
    },
  });
}

/** Map a format string to the LSP language identifier used by the proxy. */
const FORMAT_TO_LSP_LANGUAGE: Record<string, string> = {
  KQL: 'kql',
  SPL: 'spl',
  WAZUH: 'wazuh',
  AQL: 'aql',
};

/**
 * Convert Monaco suggestion kind to CompletionItemKind enum
 */
function kindToMonacoKind(kind: string): number {
  const kindMap: { [key: string]: number } = {
    keyword: monaco.languages.CompletionItemKind.Keyword,
    field: monaco.languages.CompletionItemKind.Field,
    value: monaco.languages.CompletionItemKind.Constant,
    operator: monaco.languages.CompletionItemKind.Operator,
    function: monaco.languages.CompletionItemKind.Function,
    snippet: monaco.languages.CompletionItemKind.Snippet,
    text: monaco.languages.CompletionItemKind.Text,
  };
  return kindMap[kind] || monaco.languages.CompletionItemKind.Text;
}

function severityToMarkerSeverity(severity: string): monaco.MarkerSeverity {
  switch ((severity || '').toLowerCase()) {
    case 'warning':
      return monaco.MarkerSeverity.Warning;
    case 'info':
      return monaco.MarkerSeverity.Info;
    case 'hint':
      return monaco.MarkerSeverity.Hint;
    default:
      return monaco.MarkerSeverity.Error;
  }
}

/**
 * Extract prefix (word being typed) at cursor position
 */
function extractPrefix(text: string, position: number): string {
  if (position <= 0) return '';

  let start = position - 1;
  while (start >= 0) {
    const char = text[start];
    if (char.match(/\s/) || char.match(/[:{}[\](),"'=<>!|&-]/)) {
      break;
    }
    start--;
  }
  return text.substring(start + 1, position);
}

/** Get Monaco language ID for a given format. */
function getMonacoLanguage(format: string): string {
  switch (format) {
    case 'KQL': return 'kql';
    case 'EQL': return 'eql';
    case 'WAZUH': return 'xml';
    case 'SPL': return 'spl';
    case 'AQL': return 'aql';
    default: return 'plaintext';
  }
}

/**
 * DetectionRuleEditor: Monaco Editor with KQL/SPL autocomplete and LSP integration
 */
export const DetectionRuleEditor: React.FC<DetectionRuleEditorProps> = ({
  value,
  onChange,
  format,
  height = '100%',
  dataSourceId,
  readOnly = false,
  enableLSP = true,
  enableSemanticValidation = true,
  onBlur,
  visualStyle = 'default',
}) => {
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const blurDisposableRef = useRef<monaco.IDisposable | null>(null);
  const lastRequestRef = useRef<number>(0);
  const validationRequestRef = useRef<number>(0);
  const validationTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lspClientRef = useRef<LSPClient | null>(null);
  const [lspStatus, setLspStatus] = useState<LspStatus>('disabled');
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const themeName = visualStyle === 'terminal' ? 'hef-terminal' : (isDark ? 'vs-dark' : 'vs');
  const supportsSemanticValidation = format !== 'OTHER';
  const hasLspProvider = Boolean(FORMAT_TO_LSP_LANGUAGE[format]);

  // Register custom Monaco language definitions once on mount
  useEffect(() => {
    registerCustomLanguages();
  }, []);

  useEffect(() => {
    return () => {
      blurDisposableRef.current?.dispose();
      blurDisposableRef.current = null;
    };
  }, []);

  useEffect(() => {
    return () => {
      if (validationTimeoutRef.current) {
        clearTimeout(validationTimeoutRef.current);
        validationTimeoutRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (visualStyle !== 'terminal') return;

    defineTerminalTheme(monaco);
  }, [visualStyle]);

  // LSP WebSocket connection via Django Channels proxy
  useEffect(() => {
    if (!enableLSP) {
      setLspStatus('disabled');
      return;
    }

    const lspLanguage = FORMAT_TO_LSP_LANGUAGE[format];
    if (!lspLanguage) {
      setLspStatus('disabled');
      return;
    }

    const client = new LSPClient(
      lspLanguage,
      // Diagnostics callback: update Monaco markers
      (diagnostics) => {
        const model = editorRef.current?.getModel();
        if (model) {
          monaco.editor.setModelMarkers(model, 'lsp', diagnostics);
        }
      },
      // Status change callback
      (status: LspConnectionStatus) => {
        if (status === 'connected') {
          setLspStatus('connected');
          // Notify LSP of the currently open document
          const model = editorRef.current?.getModel();
          if (model) {
            const uri = `inmemory://model/${lspLanguage}`;
            client.didOpen(uri, getMonacoLanguage(format), 1, model.getValue());
          }
        } else if (status === 'error') {
          setLspStatus('error');
        } else if (status === 'connecting') {
          setLspStatus('connecting');
        } else {
          setLspStatus('disabled');
        }
      },
    );

    lspClientRef.current = client;

    client.connect().catch((err) => {
      console.warn(`[LSP] Failed to connect for ${format}:`, err);
    });

    return () => {
      // Clear markers and disconnect when format changes or component unmounts
      const model = editorRef.current?.getModel();
      if (model) {
        monaco.editor.setModelMarkers(model, 'lsp', []);
      }
      client.disconnect();
      lspClientRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [format, enableLSP]);

  // Register autocomplete provider globally (once per format)
  useEffect(() => {
    const languageId = getMonacoLanguage(format);

    // Configure trigger characters based on format:
    // KQL: '|' (pipe operator), '.' (member access), ',' (argument separator)
    // SPL: '|' (pipe operator), '.' (member access), ',' (argument separator)
    // WAZUH: '<' (XML opening tags)
    // AQL/EQL: '.', ',', '(' for SQL/EQL expressions
    // NOTE: Space is intentionally excluded from trigger characters to avoid
    // interfering with normal typing (space key would behave unexpectedly).
    const triggerCharacters =
      format === 'KQL' || format === 'SPL'
        ? ['|', '.', ',']
        : format === 'WAZUH'
        ? ['<']
        : ['.', ',', '(']; // AQL/EQL

    const provider = monaco.languages.registerCompletionItemProvider(
      languageId,
      {
        triggerCharacters,
        provideCompletionItems: async (model, position) => {
          // Debounce autocomplete requests to avoid excessive API calls
          const now = Date.now();
          const timeSinceLastRequest = now - lastRequestRef.current;
          if (timeSinceLastRequest < 200) {
            return { suggestions: [] };
          }
          lastRequestRef.current = now;
          const text = model.getValue();
          const offset = model.getOffsetAt(position);
          const prefix = extractPrefix(text, offset);

          try {
            // Use the same API URL pattern as Apollo Client
            const baseApiUrl = getApiBaseUrl();
            const uri = `${baseApiUrl}/graphql`;

            // Get auth token from localStorage
            const token = localStorage.getItem('accessToken');

            const response = await fetch(uri, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
              },
              body: JSON.stringify({
                query: GET_AUTOCOMPLETE_OPTIONS,
                variables: {
                  format,
                  context: text,
                  position: offset,
                  dataSourceId: dataSourceId || null,
                },
              }),
            });

            const result = await response.json();

            if (result.errors) {
              console.error('[Autocomplete] GraphQL errors:', result.errors);
              return { suggestions: [] };
            }

            const suggestions = result.data?.getAutocompleteOptions?.result?.suggestions || [];

            if (suggestions.length > 0) {
              console.log(`[Autocomplete] Got ${suggestions.length} suggestions for format ${format}`);
            }

            return {
              suggestions: suggestions.map((s: any) => ({
                label: s.label,
                kind: kindToMonacoKind(s.kind),
                insertText: s.insertText,
                detail: s.detail,
                documentation: s.documentation ? { value: s.documentation } : undefined,
                sortText: s.sortText || s.label,
                filterText: s.filterText || s.label,
                range: {
                  startLineNumber: position.lineNumber,
                  startColumn: position.column - prefix.length,
                  endLineNumber: position.lineNumber,
                  endColumn: position.column,
                },
              })),
            };
          } catch (error) {
            console.error('[Autocomplete] Request failed:', error);
            if (error instanceof Error) {
              console.error('[Autocomplete] Error details:', error.message);
            }
            return { suggestions: [] };
          }
        },
      }
    );

    // Cleanup: dispose provider when component unmounts or format changes
    return () => {
      provider.dispose();
    };
  }, [format, dataSourceId]); // Re-register when format or dataSourceId changes

  useEffect(() => {
    if (!enableSemanticValidation || !supportsSemanticValidation) {
      const model = editorRef.current?.getModel();
      if (model) {
        monaco.editor.setModelMarkers(model, 'rule-validation', []);
      }
      return;
    }

    if (validationTimeoutRef.current) {
      clearTimeout(validationTimeoutRef.current);
    }

    validationTimeoutRef.current = setTimeout(async () => {
      const model = editorRef.current?.getModel();
      if (!model) return;

      const text = value || '';
      if (!text.trim()) {
        monaco.editor.setModelMarkers(model, 'rule-validation', []);
        return;
      }

      const requestId = ++validationRequestRef.current;

      try {
        const baseApiUrl = getApiBaseUrl();
        const uri = `${baseApiUrl}/graphql`;
        const token = localStorage.getItem('accessToken');

        const response = await fetch(uri, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            query: VALIDATE_RULE_CONTENT,
            variables: {
              format,
              context: text,
              position: text.length,
              dataSourceId: dataSourceId || null,
            },
          }),
        });

        const result = await response.json();
        if (requestId !== validationRequestRef.current) return;

        if (result.errors) {
          console.error('[Validation] GraphQL errors:', result.errors);
          monaco.editor.setModelMarkers(model, 'rule-validation', []);
          return;
        }

        const issues = result.data?.validateRuleContent?.result?.issues || [];
        const markers = issues.map((issue: any) => {
          const lineNumber = Math.max(1, Math.min(issue.line || 1, model.getLineCount()));
          return {
            startLineNumber: lineNumber,
            startColumn: Math.max(1, issue.column || 1),
            endLineNumber: lineNumber,
            endColumn: model.getLineMaxColumn(lineNumber),
            message: issue.message || 'Validation error',
            severity: severityToMarkerSeverity(issue.severity),
            source: 'HEFAISTOS',
          } satisfies monaco.editor.IMarkerData;
        });

        monaco.editor.setModelMarkers(model, 'rule-validation', markers);
      } catch (error) {
        console.error('[Validation] Request failed:', error);
      }
    }, 500);

    return () => {
      if (validationTimeoutRef.current) {
        clearTimeout(validationTimeoutRef.current);
        validationTimeoutRef.current = null;
      }
    };
  }, [value, format, dataSourceId, enableSemanticValidation, supportsSemanticValidation]);

  return (
    <div className="relative w-full h-full">
      {/* LSP Status Indicator */}
      {enableLSP && lspStatus !== 'disabled' && (
        <div className="absolute top-2 right-2 z-10 pointer-events-none">
          {lspStatus === 'connecting' && (
            <span
              style={{
                fontSize: 12,
                color: isDark ? '#94a3b8' : '#64748b',
                background: isDark ? 'rgba(15, 23, 42, 0.82)' : 'rgba(241, 245, 249, 0.95)',
                padding: '2px 8px',
                borderRadius: 8,
                border: `1px solid ${isDark ? '#334155' : '#dbe4ef'}`,
              }}
            >
              🔄 LSP connecting…
            </span>
          )}
          {lspStatus === 'connected' && (
            <span
              style={{
                fontSize: 12,
                color: isDark ? '#86efac' : '#166534',
                background: isDark ? 'rgba(15, 23, 42, 0.82)' : 'rgba(240, 253, 244, 0.95)',
                padding: '2px 8px',
                borderRadius: 8,
                border: `1px solid ${isDark ? '#14532d' : '#bbf7d0'}`,
              }}
            >
              ✓ LSP active
            </span>
          )}
          {lspStatus === 'error' && (
            <span
              style={{
                fontSize: 12,
                color: isDark ? '#fca5a5' : '#b91c1c',
                background: isDark ? 'rgba(15, 23, 42, 0.82)' : 'rgba(254, 242, 242, 0.95)',
                padding: '2px 8px',
                borderRadius: 8,
                border: `1px solid ${isDark ? '#7f1d1d' : '#fecaca'}`,
              }}
            >
              ✗ LSP unavailable
            </span>
          )}
        </div>
      )}
      {enableLSP && !hasLspProvider && (
        <div className="absolute top-2 right-2 z-10 pointer-events-none">
          <span
            style={{
              fontSize: 12,
              color: isDark ? '#fcd34d' : '#92400e',
              background: isDark ? 'rgba(15, 23, 42, 0.82)' : 'rgba(254, 252, 232, 0.95)',
              padding: '2px 8px',
              borderRadius: 8,
              border: `1px solid ${isDark ? '#854d0e' : '#fde68a'}`,
            }}
          >
            {format === 'EQL'
              ? 'Autocomplete + syntax checks (EQL LSP not yet supported)'
              : 'Autocomplete + syntax checks (no LSP)'}
          </span>
        </div>
      )}

      <Editor
        className={visualStyle === 'terminal' ? 'hef-terminal-editor' : undefined}
        height={height}
        language={getMonacoLanguage(format)}
        value={value}
        beforeMount={(monacoApi) => {
          if (visualStyle === 'terminal') {
            defineTerminalTheme(monacoApi as typeof monaco);
          }
        }}
        onChange={(val) => {
          const newValue = val || '';
          onChange(newValue);
          // Notify LSP of content change for real-time diagnostics
          const lspLanguage = FORMAT_TO_LSP_LANGUAGE[format];
          if (lspClientRef.current && lspLanguage) {
            const uri = `inmemory://model/${lspLanguage}`;
            lspClientRef.current.didChange(uri, Date.now(), newValue);
          }
        }}
        theme={themeName}
        options={{
          minimap: { enabled: true },
          fontSize: 14,
          fontFamily: 'Menlo, Monaco, Courier New, monospace',
          formatOnPaste: true,
          formatOnType: false,
          autoClosingBrackets: 'always',
          autoClosingQuotes: 'always',
          suggest: {
            showSnippets: true,
            showWords: true,
            showIcons: true,
            filterGraceful: true,
            showInlineDetails: true,
          },
          quickSuggestions: {
            other: true,
            comments: false,
            strings: false,
          },
          suggestOnTriggerCharacters: true,
          wordBasedSuggestions: 'off',
          lineNumbers: 'on',
          scrollBeyondLastLine: false,
          readOnly: readOnly,
        }}
        onMount={(editor) => {
          editorRef.current = editor;
          if (visualStyle === 'terminal') {
            monaco.editor.setTheme('hef-terminal');
          }
          if (onBlur) {
            blurDisposableRef.current?.dispose();
            blurDisposableRef.current = editor.onDidBlurEditorText(() => {
              onBlur();
            });
          }
          console.log('Editor mounted, language model:', editor.getModel()?.getLanguageId());
        }}
        loading={
          <div
            style={{
              padding: '16px',
              color: 'var(--hef-text-muted)',
              background: 'var(--hef-bg-surface)',
              border: '1px solid var(--hef-border)',
            }}
          >
            Loading editor...
          </div>
        }
      />
    </div>
  );
};

export default DetectionRuleEditor;
