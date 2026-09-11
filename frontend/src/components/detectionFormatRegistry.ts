import { OpenTideRule } from '../types/opentide';

export type PlatformTab = 'kql' | 'eql' | 'spl' | 'wazuh' | 'qradar';
export type RuleFormat = 'KQL' | 'EQL' | 'SPL' | 'WAZUH' | 'AQL';

export interface DetectionFormatDefinition {
  id: PlatformTab;
  format: RuleFormat;
  displayName: string;
  fileExtension: string;
  commentSyntax: 'line' | 'xml';
  commentPrefix?: string;
  tabLabel: string;
  tabColor: string;
  tabActiveColor: string;
  getContent: (rule: OpenTideRule) => string;
  setContent: (rule: OpenTideRule, content: string) => OpenTideRule;
}

export const DETECTION_FORMAT_REGISTRY: DetectionFormatDefinition[] = [
  {
    id: 'kql',
    format: 'KQL',
    displayName: 'KQL',
    fileExtension: 'kql',
    commentSyntax: 'line',
    commentPrefix: '//',
    tabLabel: '🔷 KQL',
    tabColor: 'bg-blue-50 text-blue-700 border border-blue-200',
    tabActiveColor: 'bg-blue-600 text-white',
    getContent: (rule) => rule.platforms.kql?.query ?? '',
    setContent: (rule, content) => {
      const hasContent = Boolean(content.trim());
      return {
        ...rule,
        platforms: {
          ...rule.platforms,
          kql: hasContent ? { query: content, data_source: rule.platforms.kql?.data_source } : undefined,
        },
      };
    },
  },
  {
    id: 'eql',
    format: 'EQL',
    displayName: 'Elastic EQL',
    fileExtension: 'eql',
    commentSyntax: 'line',
    commentPrefix: '//',
    tabLabel: '🟡 Elastic EQL',
    tabColor: 'bg-yellow-900/40 text-yellow-200 border border-yellow-700',
    tabActiveColor: 'bg-yellow-700 text-white',
    getContent: (rule) => rule.platforms.elastic?.query ?? '',
    setContent: (rule, content) => {
      const hasContent = Boolean(content.trim());
      return {
        ...rule,
        platforms: {
          ...rule.platforms,
          elastic: hasContent ? { query: content } : undefined,
        },
      };
    },
  },
  {
    id: 'spl',
    format: 'SPL',
    displayName: 'SPL',
    fileExtension: 'spl',
    commentSyntax: 'line',
    commentPrefix: '#',
    tabLabel: '🟠 SPL',
    tabColor: 'bg-orange-900/40 text-orange-200 border border-orange-700',
    tabActiveColor: 'bg-orange-700 text-white',
    getContent: (rule) => rule.platforms.spl?.query ?? '',
    setContent: (rule, content) => {
      const hasContent = Boolean(content.trim());
      return {
        ...rule,
        platforms: {
          ...rule.platforms,
          spl: hasContent ? { query: content, index: rule.platforms.spl?.index } : undefined,
        },
      };
    },
  },
  {
    id: 'wazuh',
    format: 'WAZUH',
    displayName: 'WAZUH',
    fileExtension: 'xml',
    commentSyntax: 'xml',
    tabLabel: '🟢 WAZUH',
    tabColor: 'bg-green-900/40 text-green-200 border border-green-700',
    tabActiveColor: 'bg-green-700 text-white',
    getContent: (rule) => rule.platforms.wazuh?.rule ?? '',
    setContent: (rule, content) => {
      const hasContent = Boolean(content.trim());
      return {
        ...rule,
        platforms: {
          ...rule.platforms,
          wazuh: hasContent ? { rule: content } : undefined,
        },
      };
    },
  },
  {
    id: 'qradar',
    format: 'AQL',
    displayName: 'QRadar',
    fileExtension: 'aql',
    commentSyntax: 'line',
    commentPrefix: '--',
    tabLabel: '🟣 QRadar',
    tabColor: 'bg-purple-900/40 text-purple-200 border border-purple-700',
    tabActiveColor: 'bg-purple-700 text-white',
    getContent: (rule) => rule.platforms.qradar?.query ?? '',
    setContent: (rule, content) => {
      const hasContent = Boolean(content.trim());
      return {
        ...rule,
        platforms: {
          ...rule.platforms,
          qradar: hasContent ? { query: content, scope: rule.platforms.qradar?.scope } : undefined,
        },
      };
    },
  },
];

export const FORMAT_BY_TAB = Object.fromEntries(
  DETECTION_FORMAT_REGISTRY.map((f) => [f.id, f])
) as Record<PlatformTab, DetectionFormatDefinition>;

export function getFormatByTab(tab: PlatformTab): DetectionFormatDefinition {
  return FORMAT_BY_TAB[tab];
}

export function getFormatByName(format: string): DetectionFormatDefinition | undefined {
  return DETECTION_FORMAT_REGISTRY.find((f) => f.format === format);
}

export function buildSaveButtonLabel(format: Pick<DetectionFormatDefinition, 'displayName'>): string {
  return `SAVE ${format.displayName.toUpperCase()}`;
}
