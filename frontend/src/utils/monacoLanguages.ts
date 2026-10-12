/**
 * monacoLanguages.ts
 *
 * Register custom Monaco Editor language definitions for the detection query
 * languages used by HEFAISTOS that are not natively supported by Monaco:
 *   - KQL  (Kusto Query Language)
 *   - EQL  (Elastic Event Query Language)
 *   - SPL  (Splunk Processing Language)
 *   - AQL  (QRadar Ariel Query Language)
 *
 * SIGMA rules (YAML) and Wazuh rules (XML) reuse Monaco's built-in language
 * support and do not need custom registration. Note: SIGMA is no longer supported.
 *
 * Call `registerCustomLanguages()` once during application initialisation.
 */

import * as monaco from 'monaco-editor';

const registeredInstances = new WeakSet<typeof monaco>();

export function registerCustomLanguages(monacoApi: typeof monaco = monaco): void {
  if (registeredInstances.has(monacoApi)) return;
  registeredInstances.add(monacoApi);

  // ---------------------------------------------------------------------------
  // KQL – Kusto Query Language
  // ---------------------------------------------------------------------------
  monacoApi.languages.register({ id: 'kql' });
  monacoApi.languages.setMonarchTokensProvider('kql', {
    keywords: [
      'let', 'summarize', 'where', 'project', 'extend', 'join', 'union',
      'render', 'sort', 'top', 'count', 'distinct', 'take', 'limit',
      'by', 'on', 'as', 'asc', 'desc', 'kind', 'ago', 'bin', 'range',
    ],
    operators: [
      '==', '!=', '>', '<', '>=', '<=', 'and', 'or', 'not', 'contains',
      'startswith', 'endswith', 'matches', 'has', 'in', 'between',
    ],
    tokenizer: {
      root: [
        { include: '@whitespace' },
        [/\/\/.*$/, 'comment'],
        [/[a-zA-Z_]\w*/, {
          cases: {
            '@keywords': 'keyword',
            '@default': 'identifier',
          },
        }],
        [/"([^"\\]|\\.)*"/, 'string'],
        [/'([^'\\]|\\.)*'/, 'string'],
        [/\d+(\.\d+)?([eE][+-]?\d+)?/, 'number'],
        [/[|,;.()\[\]{}]/, 'delimiter'],
      ],
      whitespace: [
        [/[ \t\r\n]+/, ''],
      ],
    },
  });

  // ---------------------------------------------------------------------------
  // EQL – Elastic Event Query Language
  // ---------------------------------------------------------------------------
  monacoApi.languages.register({ id: 'eql' });
  monacoApi.languages.setMonarchTokensProvider('eql', {
    keywords: [
      'sequence', 'where', 'by', 'with', 'maxspan', 'any', 'until',
      'and', 'or', 'not', 'in', 'true', 'false',
    ],
    tokenizer: {
      root: [
        { include: '@whitespace' },
        [/\/\/.*$/, 'comment'],
        [/[a-zA-Z_]\w*/, {
          cases: {
            '@keywords': 'keyword',
            '@default': 'identifier',
          },
        }],
        [/"([^"\\]|\\.)*"/, 'string'],
        [/'([^'\\]|\\.)*'/, 'string'],
        [/\d+(\.\d+)?([smhdw])?/, 'number'],
        [/[|,;.()\[\]{}]/, 'delimiter'],
      ],
      whitespace: [
        [/[ \t\r\n]+/, ''],
      ],
    },
  });

  // ---------------------------------------------------------------------------
  // SPL – Splunk Processing Language
  // ---------------------------------------------------------------------------
  monacoApi.languages.register({ id: 'spl' });
  monacoApi.languages.setMonarchTokensProvider('spl', {
    keywords: [
      'search', 'stats', 'eval', 'where', 'table', 'rename', 'dedup',
      'sort', 'head', 'tail', 'rex', 'fields', 'streamstats', 'transaction',
      'index', 'sourcetype', 'source', 'host', 'by', 'as', 'over',
      'count', 'sum', 'avg', 'min', 'max', 'values', 'list',
    ],
    tokenizer: {
      root: [
        { include: '@whitespace' },
        [/`[^`]*`/, 'string.backtick'],
        [/[a-zA-Z_]\w*/, {
          cases: {
            '@keywords': 'keyword',
            '@default': 'identifier',
          },
        }],
        [/"([^"\\]|\\.)*"/, 'string'],
        [/'([^'\\]|\\.)*'/, 'string'],
        [/\d+(\.\d+)?/, 'number'],
        [/[|,;.()\[\]{}*]/, 'delimiter'],
      ],
      whitespace: [
        [/[ \t\r\n]+/, ''],
      ],
    },
  });

  // ---------------------------------------------------------------------------
  // AQL – QRadar Ariel Query Language
  // ---------------------------------------------------------------------------
  monacoApi.languages.register({ id: 'aql' });
  monacoApi.languages.setMonarchTokensProvider('aql', {
    keywords: [
      'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'LIKE', 'IN',
      'BETWEEN', 'ORDER', 'BY', 'LIMIT', 'GROUP', 'HAVING', 'AS',
      'DISTINCT', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'NULL',
      'IS', 'JOIN', 'ON', 'INNER', 'LEFT', 'RIGHT', 'OUTER',
    ],
    tokenizer: {
      root: [
        { include: '@whitespace' },
        [/--.*$/, 'comment'],
        [/[a-zA-Z_]\w*/, {
          cases: {
            '@keywords': 'keyword',
            '@default': 'identifier',
          },
        }],
        [/'([^'\\]|\\.)*'/, 'string'],
        [/\d+(\.\d+)?/, 'number'],
        [/[,;.()\[\]{}*]/, 'delimiter'],
      ],
      whitespace: [
        [/[ \t\r\n]+/, ''],
      ],
    },
  });
}
