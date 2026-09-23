import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Modal, Select, Button, Tabs, Tag, Radio, Space, Divider, message, InputNumber, Input, Checkbox, Alert } from 'antd';
import { gql } from '@apollo/client';
import { useMutation, useQuery, useLazyQuery } from '@apollo/client/react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { DeleteOutlined } from '@ant-design/icons';
import DataSourcePicker, { DataSourceOption } from './DataSourcePicker';
import RulePicker, { RuleOption } from './RulePicker';
import { PixelIcon } from './ui/PixelIcon';
import DetectionRuleEditor from './DetectionRuleEditor';
import { MarkdownRenderer } from './MarkdownRenderer';
import { OpenTideRule } from '../types/opentide';
import { compileMetadataFromWorkbench, getConfiguredPlatforms } from '../utils/openTideCompiler';
import { isDirty, normalize } from '../utils/ruleDiff';
import OpenTideMetadataPreview from './OpenTideMetadataPreview';
import { DETECTION_FORMAT_REGISTRY, getFormatByTab, getFormatByName, buildSaveButtonLabel, PlatformTab } from './detectionFormatRegistry';

const { Option } = Select;
const { TextArea } = Input;

// Async AI task polling interval (ms)
const AI_POLL_INTERVAL_MS = 2000;
const RAG_REUSE_SUPPORTED_FORMATS = new Set(['KQL', 'EQL', 'SPL', 'WAZUH']);

function isRagReuseSupportedFormat(format: string): boolean {
  return RAG_REUSE_SUPPORTED_FORMATS.has(String(format || '').toUpperCase());
}

// Async AI Generation Task Mutations (avoid 504 gateway timeouts)
const START_GENERATE_RULE_TASK_MUTATION = gql`
  mutation StartGenerateRuleTask($playbookId: UUID!, $outputFormat: String) {
    startGenerateRuleTask(playbookId: $playbookId, outputFormat: $outputFormat) {
      taskId
      success
      message
    }
  }
`;

const START_SUGGEST_IMPROVEMENTS_TASK_MUTATION = gql`
  mutation StartSuggestImprovementsTask($ruleContent: String!, $ruleFormat: String, $playbookId: UUID) {
    startSuggestImprovementsTask(ruleContent: $ruleContent, ruleFormat: $ruleFormat, playbookId: $playbookId) {
      taskId
      success
      message
    }
  }
`;

const START_GENERATE_SIMILAR_RULES_TASK_MUTATION = gql`
  mutation StartGenerateSimilarRulesTask(
    $ruleContent: String!
    $ruleFormat: String
    $variationType: String
    $numVariations: Int
    $targetFormat: String
    $customInstructions: String
    $playbookId: UUID
  ) {
    startGenerateSimilarRulesTask(
      ruleContent: $ruleContent
      ruleFormat: $ruleFormat
      variationType: $variationType
      numVariations: $numVariations
      targetFormat: $targetFormat
      customInstructions: $customInstructions
      playbookId: $playbookId
    ) {
      taskId
      success
      message
    }
  }
`;

const RECOMMEND_REUSABLE_RULE_FROM_RAG_MUTATION = gql`
  mutation RecommendReusableRuleFromRag($playbookId: UUID!, $outputFormat: String) {
    recommendReusableRuleFromRag(playbookId: $playbookId, outputFormat: $outputFormat) {
      success
      message
      providerUsed
      workbenchSummary
      decision
      rationale
      candidateSource
      adaptedRule
      referenceCount
    }
  }
`;

// Polling query for async AI task status
const AI_GENERATION_TASK_STATUS_QUERY = gql`
  query AiGenerationTaskStatus($taskId: UUID!) {
    aiGenerationTaskStatus(taskId: $taskId) {
      id
      taskType
      status
      resultData
      errorMessage
      createdAt
      startedAt
      completedAt
    }
  }
`;

const DELETE_RULE_MUTATION = gql`
  mutation DeleteDetectionRule($ruleId: UUID!) {
    deleteDetectionRule(ruleId: $ruleId) {
      success
      message
    }
  }
`;

const CURRENT_USER_QUERY = gql`
  query CurrentUser {
    me {
      id
      username
      role
    }
  }
`;

const SAVE_DETECTION_RULE_MUTATION = gql`
  mutation SaveDetectionRuleWithMetadata(
    $playbookId: UUID!
    $rawYaml: String!
    $format: String
    $title: String
    $description: String
    $author: String
    $tags: [String]
    $autoCommit: Boolean
    $commitMessage: String
  ) {
    saveDetectionRule(
      playbookId: $playbookId
      rawYaml: $rawYaml
      format: $format
      title: $title
      description: $description
      author: $author
      tags: $tags
      autoCommit: $autoCommit
      commitMessage: $commitMessage
    ) {
      success
      message
      filename
      commitSha
      errors
    }
  }
`;

const SAVE_ALL_DETECTION_RULES_MUTATION = gql`
  mutation SaveAllDetectionRules(
    $playbookId: UUID!
    $rules: [SaveRuleInput!]!
    $title: String
    $description: String
    $author: String
    $tags: [String]
    $autoCommit: Boolean
    $commitMessage: String
  ) {
    saveAllDetectionRules(
      playbookId: $playbookId
      rules: $rules
      title: $title
      description: $description
      author: $author
      tags: $tags
      autoCommit: $autoCommit
      commitMessage: $commitMessage
    ) {
      success
      results {
        format
        status
        filename
        message
      }
    }
  }
`;

const GENERATE_ALL_DETECTION_RULES_MUTATION = gql`
  mutation GenerateAllDetectionRules(
    $sourceFormat: String!
    $sourceContent: String!
    $targetFormats: [String!]
    $playbookId: UUID
  ) {
    generateAllDetectionRules(
      sourceFormat: $sourceFormat
      sourceContent: $sourceContent
      targetFormats: $targetFormats
      playbookId: $playbookId
    ) {
      success
      results {
        format
        status
        method
        content
        error
      }
    }
  }
`;

// Strip markdown code fences and leading prose from an AI-generated rule block so only
// the bare rule syntax is passed to the editor.
function cleanRuleContent(ruleText: string): string {
  let cleaned = ruleText.trim();

  // 1. If a fenced code block exists, extract only the content inside it.
  const fenceMatch = cleaned.match(/```[a-zA-Z]*\s*\n([\s\S]*?)\n?```/);
  if (fenceMatch) {
    cleaned = fenceMatch[1].trim();
  } else {
    // 2. No fences – remove any stray fence markers left on their own lines.
    cleaned = cleaned.replace(/^```[a-zA-Z]*\s*$/gm, '').trim();
  }

  // 3. Replace tab characters with two spaces. YAML (Sigma) forbids tabs as
  //    indentation; AI models sometimes emit them, causing "while scanning a
  //    simple key" parse errors when the rule is later saved.
  cleaned = cleaned.replace(/\t/g, '  ');

  // 4. Strip leading lines that look like markdown prose/formatting rather than
  //    actual rule syntax.  A "prose" line is one that:
  //      • starts with a markdown heading/bold/italic/numbered-list marker, OR
  //      • consists entirely of plain words (no colon, pipe, equals, angle-bracket,
  //        or leading comment characters like // or #)
  //    We stop stripping as soon as we see the first rule-like line.
  const lines = cleaned.split('\n');
  // Prose pattern: markdown bold/italic (**x**, *x*), headings (## ), blockquotes (> ),
  // numbered lists (1. ), bullet lists starting with a capital, or plain English sentences.
  const prosePattern = /^(?:\*\*.*\*\*|\*.*\*|#{1,6}\s|>\s|\d+\.\s|\s*[-*+]\s+[A-Z]|[A-Za-z][A-Za-z\s,]+[.!?]$)/;
  // Rule-line pattern: KQL/SPL/SIGMA/WAZUH syntax indicators –
  //   // or # (comments), SIGMA YAML keys (title: id: …), KQL let keyword,
  //   SPL index= / search / pipe |, XML opening tag <, or generic key=value/key: assignments.
  const ruleLinePattern = /^(?:\/\/|#|title:|id:|status:|name:|description:|detection:|let\s|index=|\||<[a-zA-Z]|[A-Za-z_]+\s*[:=|])/;

  let start = 0;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    if (ruleLinePattern.test(line)) {
      start = i;
      break;
    }
    if (prosePattern.test(line)) {
      start = i + 1; // skip this prose line
    }
  }

  return lines.slice(start).join('\n').trim();
}

/** Heuristic validation for IBM QRadar AQL output. */
function isLikelyAql(ruleText: string): boolean {
  const text = (ruleText || '').trim();
  if (!text) return false;

  const lower = text.toLowerCase();

  // Strong non-AQL signals (common fallback outputs from other formats)
  const nonAqlMarkers = [
    'title:',
    'logsource:',
    'detection:',
    'condition:',
    'falsepositives:',
    '<group',
    '<rule',
    'deviceprocessevents',
    'signinlogs',
  ];
  if (nonAqlMarkers.some((m) => lower.includes(m))) return false;

  // AQL should look SQL-like for QRadar queries.
  const hasSelect = /\bselect\b/i.test(text);
  const hasFrom = /\bfrom\b/i.test(text);
  return hasSelect && hasFrom;
}

// Variation type options for Generate Similar
const VARIATION_TYPES = [
  { value: 'technique', label: 'Similar Techniques', description: 'Rules for related attack techniques in the same chain', icon: 'target' },
  { value: 'evasion', label: 'Evasion Variants', description: 'Rules to catch attackers evading the original rule', icon: 'shield' },
  { value: 'platform', label: 'Cross-Platform', description: 'Adapt rule for different OS/SIEM platforms', icon: 'layers' },
  { value: 'scope', label: 'Scope Variations', description: 'Broader or narrower detection variations', icon: 'maximize' },
  { value: 'custom', label: 'Custom', description: 'Provide your own instructions', icon: 'edit' },
];

// Rule templates for quick start
const RULE_TEMPLATES: Record<string, Record<string, string>> = {
  SPL: {
    'Process Events': `index=* sourcetype=WinEventLog:Security
| where EventCode=4688
| eval process_name=mvindex(split(Process_Name,"\\\\"),-1)
| where process_name IN ("cmd.exe","powershell.exe","wscript.exe","cscript.exe")
| table _time, host, Account_Name, Process_Name, Process_Command_Line
| sort -_time`,
    'Failed Logins': `index=* sourcetype=WinEventLog:Security EventCode=4625
| stats count by src_ip, Account_Name, host
| where count > 5
| rename count as failed_attempts
| sort -failed_attempts`,
    'Network Connections': `index=* sourcetype=WinEventLog:Security EventCode=5156
| where dest_port IN (4444, 5555, 6666, 8080)
| eval dest_ip_type=if(match(dest_ip,"^(10\\.|172\\.(1[6-9]|2[0-9]|3[01])\\.|192\\.168\\.)"), "Private", "Public")
| where dest_ip_type="Public"
| table _time, host, src_ip, dest_ip, dest_port, Application
| sort -_time`,
  },
  KQL: {
    'Process Events': `// KQL - Process Events Detection
DeviceProcessEvents
| where Timestamp > ago(1h)
| where ProcessCommandLine has_any ("cmd.exe", "powershell.exe")
| where InitiatingProcessFileName != "explorer.exe"
| project Timestamp, DeviceName, AccountName, ProcessCommandLine, InitiatingProcessCommandLine
| order by Timestamp desc`,
    'Network Events': `// KQL - Suspicious Network Connections
DeviceNetworkEvents
| where Timestamp > ago(1h)
| where RemotePort in (4444, 5555, 6666, 8080)
| where RemoteIPType == "Public"
| project Timestamp, DeviceName, RemoteIP, RemotePort, InitiatingProcessFileName
| order by Timestamp desc`,
    'Sign-in Events': `// KQL - Suspicious Sign-in Activity
SigninLogs
| where TimeGenerated > ago(24h)
| where ResultType != 0
| summarize FailedAttempts = count() by UserPrincipalName, IPAddress, Location
| where FailedAttempts > 5
| order by FailedAttempts desc`,
  },
  WAZUH: {
    'File Integrity': `<group name="custom_fim,">
  <rule id="100001" level="10">
    <if_sid>550</if_sid>
    <field name="file">/etc/passwd</field>
    <description>Critical file modification detected: /etc/passwd</description>
    <options>no_full_log</options>
    <group>fim,pci_dss_11.5,gpg13_4.11,</group>
  </rule>
</group>`,
    'Authentication': `<group name="custom_auth,">
  <rule id="100002" level="12">
    <if_sid>5710</if_sid>
    <match>authentication failure</match>
    <description>Multiple authentication failures detected</description>
    <group>authentication_failures,pci_dss_10.2.4,gpg13_7.1,</group>
  </rule>
</group>`,
    'Process Monitoring': `<group name="custom_process,">
  <rule id="100003" level="8">
    <if_sid>533</if_sid>
    <match>powershell.exe|cmd.exe</match>
    <description>Suspicious process execution detected</description>
    <group>process_monitoring,</group>
  </rule>
</group>`,
  },
};

// Mode type for detection rule generation
export type DetectionMode = 'logic' | 'ai' | 'manual';

/** Minimal subset of PlaybookGraph fields needed for metadata compilation. */
export interface PlaybookDataForMetadata {
  title?: string;
  goal?: string;
  author?: { username?: string } | null;
  createdAt?: string;
  updatedAt?: string;
  mitreTechnique?: { techniqueId?: string; name?: string } | null;
  technicalContext?: string;
  blindSpots?: string;
  falsePositives?: string;
  detectionFocusLayer?: string;
  selectedCapabilityAbstractions?: Array<{
    abstractionLayer?: string;
    componentArtifact?: string;
    detectionValue?: string;
    robustnessLevel?: number;
  }>;
  responsePlaybook?: string;
  defaultSeverity?: string;
  alertTrigger?: string;
  robustnessLevel?: number;
  dataSourceMaturity?: string;
}

type MainPlatformTab = 'metadata' | 'insights' | PlatformTab;
type GenerateAllStatus = 'pending' | 'converted' | 'generated' | 'failed' | 'skipped (non-empty)';
interface GenerateAllResult {
  format: string;
  status: GenerateAllStatus;
  method: string;
  content?: string | null;
  error?: string | null;
}

interface RagReuseResult {
  success?: boolean;
  message?: string;
  providerUsed?: string;
  workbenchSummary?: string;
  decision?: string;
  rationale?: string;
  candidateSource?: string;
  adaptedRule?: string;
  referenceCount?: number;
}

export const DEFAULT_OVERWRITE_ALL_CONTENT = false;

/** Options passed to library save callbacks. */
export interface SaveToLibraryOptions {
  autoCommit?: boolean;
  commitMessage?: string;
}

/** Result returned from library save callbacks. */
export interface SaveToLibraryResult {
  success: boolean;
  message?: string;
  commitSha?: string;
  errors?: string[];
}

interface DetectionRuleEditorModalProps {
  visible: boolean;
  onClose: () => void;
  playbookId: string;
  initialRule: string;
  initialFormat: 'KQL' | 'EQL' | 'WAZUH' | 'SPL' | 'AQL' | 'OTHER';
  initialMode: DetectionMode;
  onSave: (rule: string, format: string, mode: DetectionMode, dataSourceId?: string, openTideRule?: OpenTideRule) => void | Promise<void>;
  onGenerateAI?: (format: string) => Promise<string | null>;
  onSaveToLibrary?: (rule: string, format: string, options?: SaveToLibraryOptions) => Promise<SaveToLibraryResult | void>;
  /** Save all configured platform rules to the library at once. */
  onSaveAllToLibrary?: (rules: Array<{ content: string; format: string }>, options?: SaveToLibraryOptions) => Promise<SaveToLibraryResult[] | void>;
  /** Optional pre-populated OpenTide rule for multi-platform editing. */
  initialOpenTideRule?: OpenTideRule;
  /** Playbook data used to compile metadata for the OpenTide YAML header. */
  playbookData?: PlaybookDataForMetadata;
}

function platformToFormat(tab: MainPlatformTab): 'KQL' | 'EQL' | 'WAZUH' | 'SPL' | 'AQL' | 'OTHER' {
  if (tab === 'metadata' || tab === 'insights') return 'OTHER';
  return getFormatByTab(tab).format;
}

function getPlatformContent(rule: OpenTideRule, tab: MainPlatformTab): string {
  if (tab === 'metadata' || tab === 'insights') return '';
  return getFormatByTab(tab).getContent(rule);
}

function setPlatformContent(rule: OpenTideRule, tab: MainPlatformTab, content: string): OpenTideRule {
  if (tab === 'metadata' || tab === 'insights') return rule;
  return getFormatByTab(tab).setContent(rule, content);
}

export function buildGenerateAllPlan(
  snapshot: OpenTideRule,
  source: PlatformTab,
  overwriteAllContent: boolean
): { targetFormats: string[]; statuses: Record<string, GenerateAllStatus> } {
  const targets = DETECTION_FORMAT_REGISTRY.filter((f) => f.id !== source);
  const statuses = targets.reduce<Record<string, GenerateAllStatus>>((acc, entry) => {
    const isNonEmpty = Boolean(entry.getContent(snapshot).trim());
    acc[entry.format] = !overwriteAllContent && isNonEmpty ? 'skipped (non-empty)' : 'pending';
    return acc;
  }, {});
  const targetFormats = targets
    .filter((entry) => statuses[entry.format] === 'pending')
    .map((entry) => entry.format);

  return { targetFormats, statuses };
}

/** Build initial OpenTide state from optional pre-existing rule or legacy single-format rule. */
export function buildOpenTideState(
  initial: OpenTideRule | undefined,
  legacyRule: string,
  legacyFormat: 'KQL' | 'EQL' | 'WAZUH' | 'SPL' | 'AQL' | 'OTHER',
  playbook?: PlaybookDataForMetadata,
): OpenTideRule {
  const metadata = playbook ? compileMetadataFromWorkbench(playbook) : (initial?.metadata ?? {
    title: 'Untitled Detection',
    description: '',
    author: 'Unknown',
    created: new Date().toISOString(),
    modified: new Date().toISOString(),
    mitre: {},
    capability: {},
    response: {},
  });

  // Start with existing platforms (if any), then backfill the legacy rule only
  // when no platform content exists yet. This keeps tab content isolated and
  // prevents format-to-format copying on reopen.
  const platforms: OpenTideRule['platforms'] = initial ? { ...initial.platforms } : {};
  const snapshot: OpenTideRule = { metadata, platforms };
  const hasExistingPlatformContent = DETECTION_FORMAT_REGISTRY.some((entry) =>
    Boolean(entry.getContent(snapshot).trim())
  );

  if (legacyRule.trim() && !hasExistingPlatformContent) {
    if (legacyFormat === 'KQL' && !platforms.kql) platforms.kql = { query: legacyRule };
    else if (legacyFormat === 'EQL' && !platforms.elastic) platforms.elastic = { query: legacyRule };
    else if (legacyFormat === 'SPL' && !platforms.spl) platforms.spl = { query: legacyRule };
    else if (legacyFormat === 'WAZUH' && !platforms.wazuh) platforms.wazuh = { rule: legacyRule };
    else if (legacyFormat === 'AQL' && !platforms.qradar) platforms.qradar = { query: legacyRule };
  }

  return { metadata, platforms };
}

export const DetectionRuleEditorModal: React.FC<DetectionRuleEditorModalProps> = ({
  visible,
  onClose,
  playbookId,
  initialRule,
  initialFormat,
  initialMode,
  onSave,
  onGenerateAI,
  onSaveToLibrary,
  onSaveAllToLibrary,
  initialOpenTideRule,
  playbookData,
}) => {
  // Local state
  const [ruleContent, setRuleContent] = useState(initialRule);
  const [mode, setMode] = useState<DetectionMode>(initialMode);
  const [selectedDataSource, setSelectedDataSource] = useState<DataSourceOption | null>(null);
  const [selectedRule, setSelectedRule] = useState<RuleOption | null>(null);
  const [activeTab, setActiveTab] = useState<'editor' | 'preview' | 'suggestions' | 'similar' | 'reuse'>('editor');
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  // Per-platform suggestions, improved rules, and similar rules state
  const [platformSuggestions, setPlatformSuggestions] = useState<Record<string, string>>({});
  const [platformImprovedRules, setPlatformImprovedRules] = useState<Record<string, string>>({});
  const [platformSimilarRules, setPlatformSimilarRules] = useState<Record<string, string>>({});
  const [platformRagReuse, setPlatformRagReuse] = useState<Record<string, RagReuseResult>>({});
  const [savingAll, setSavingAll] = useState(false);
  const [aiGenerating, setAiGenerating] = useState(false);
  const [platformGenerationInsights, setPlatformGenerationInsights] = useState<Record<string, {
    quickWinRule?: string;
    robustRule?: string;
    generationSummary?: string;
    correlationIdeas?: string;
    expectedBlindSpots?: string;
    testGuidance?: string;
  }>>({});
  const [hasUnseenInsights, setHasUnseenInsights] = useState(false);
  const [lastInsightsPlatform, setLastInsightsPlatform] = useState<PlatformTab | null>(null);
  const [selectedVariant, setSelectedVariant] = useState<'quickWin' | 'robust' | null>(null);
  const prevVisibleRef = useRef(false);

  // Git commit state
  const [autoCommit, setAutoCommit] = useState(false);
  const [commitMessage, setCommitMessage] = useState('');
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [lastCommitSha, setLastCommitSha] = useState<string | null>(null);

  // Multi-platform (OpenTide) state
  const [activePlatformTab, setActivePlatformTab] = useState<MainPlatformTab>(() => {
    if (initialOpenTideRule?.platforms?.kql) return 'kql';
    if (initialOpenTideRule?.platforms?.elastic) return 'eql';
    if (initialOpenTideRule?.platforms?.spl) return 'spl';
    if (initialOpenTideRule?.platforms?.wazuh) return 'wazuh';
    if (initialOpenTideRule?.platforms?.qradar) return 'qradar';
    if (initialFormat === 'KQL') return 'kql';
    if (initialFormat === 'EQL') return 'eql';
    if (initialFormat === 'SPL') return 'spl';
    if (initialFormat === 'WAZUH') return 'wazuh';
    if (initialFormat === 'AQL') return 'qradar';
    return 'kql';
  });
  // Derive format from the active platform tab so it is always in sync with what the user sees
  const format = useMemo<'KQL' | 'EQL' | 'WAZUH' | 'SPL' | 'AQL' | 'OTHER'>(
    () => platformToFormat(activePlatformTab),
    [activePlatformTab]
  );
  const [lastEditedPlatform, setLastEditedPlatform] = useState<PlatformTab>('kql');
  const [generateAllStatuses, setGenerateAllStatuses] = useState<Record<string, GenerateAllStatus>>({});
  const [generateAllErrors, setGenerateAllErrors] = useState<Record<string, string>>({});
  const [overwriteAllContent, setOverwriteAllContent] = useState(DEFAULT_OVERWRITE_ALL_CONTENT);
  const [savingSingle, setSavingSingle] = useState(false);
  const [metadataTitle, setMetadataTitle] = useState('');
  const [metadataDescription, setMetadataDescription] = useState('');
  const [metadataAuthor, setMetadataAuthor] = useState('');
  const [metadataTags, setMetadataTags] = useState('');
  const [savedSnapshots, setSavedSnapshots] = useState<Record<string, string>>({});
  const [savedMetadataSnapshot, setSavedMetadataSnapshot] = useState<string>('');
  const [openTideRule, setOpenTideRule] = useState<OpenTideRule>(() => buildOpenTideState(
    initialOpenTideRule, initialRule, initialFormat, playbookData
  ));
  
  // Generate Similar state
  const [showSimilarOptions, setShowSimilarOptions] = useState(false);
  const [similarVariationType, setSimilarVariationType] = useState<string>('technique');
  const [similarNumVariations, setSimilarNumVariations] = useState<number>(3);
  const [similarTargetFormat, setSimilarTargetFormat] = useState<string>('');
  const [similarCustomInstructions, setSimilarCustomInstructions] = useState<string>('');
  const [deletingRule, setDeletingRule] = useState(false);

  // Derive per-platform suggestions, improved rules, and similar rules for the active tab
  const suggestions = platformSuggestions[activePlatformTab] || '';
  const improvedRule = platformImprovedRules[activePlatformTab] || '';
  const generatedSimilarRules = platformSimilarRules[activePlatformTab] || '';
  const ragReuseResult = platformRagReuse[activePlatformTab] || null;
  const ragReuseSupported = useMemo(() => isRagReuseSupportedFormat(format), [format]);

  // Async AI task state – one active task at a time for each operation
  const [aiTaskId, setAiTaskId] = useState<string | null>(null);
  const [aiTaskType, setAiTaskType] = useState<'generate' | 'suggest' | 'similar' | null>(null);
  const aiPollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Async start-task mutations (return task ID immediately, no 504 risk)
  interface StartTaskResult { taskId: string; success: boolean; message: string }
  const [startGenerateRuleTask, { loading: aiLoading }] = useMutation<
    { startGenerateRuleTask: StartTaskResult },
    { playbookId: string; outputFormat?: string }
  >(START_GENERATE_RULE_TASK_MUTATION);

  const [startSuggestImprovementsTask, { loading: suggestingLoading }] = useMutation<
    { startSuggestImprovementsTask: StartTaskResult },
    { ruleContent: string; ruleFormat?: string; playbookId?: string }
  >(START_SUGGEST_IMPROVEMENTS_TASK_MUTATION);

  const [startGenerateSimilarRulesTask, { loading: generatingSimilarLoading }] = useMutation<
    { startGenerateSimilarRulesTask: StartTaskResult },
    { ruleContent: string; ruleFormat?: string; variationType?: string; numVariations?: number; targetFormat?: string; customInstructions?: string; playbookId?: string }
  >(START_GENERATE_SIMILAR_RULES_TASK_MUTATION);
  const [recommendReusableRuleFromRag, { loading: recommendingReuse }] = useMutation<
    { recommendReusableRuleFromRag: RagReuseResult },
    { playbookId: string; outputFormat?: string }
  >(RECOMMEND_REUSABLE_RULE_FROM_RAG_MUTATION);
  const [saveDetectionRuleMutation] = useMutation(SAVE_DETECTION_RULE_MUTATION);
  const [saveAllDetectionRulesMutation] = useMutation(SAVE_ALL_DETECTION_RULES_MUTATION);
  const [generateAllDetectionRulesMutation, { loading: generatingAll }] = useMutation(GENERATE_ALL_DETECTION_RULES_MUTATION);

  // Lazy polling query for AI task status
  interface AITaskStatusResult {
    aiGenerationTaskStatus: {
      id: string;
      taskType: string;
      status: string;
      resultData: string | null;
      errorMessage: string | null;
      createdAt: string;
      startedAt: string | null;
      completedAt: string | null;
    };
  }
  const [fetchAiTaskStatus] = useLazyQuery<AITaskStatusResult>(
    AI_GENERATION_TASK_STATUS_QUERY,
    { fetchPolicy: 'network-only' }
  );

  // Helper: stop AI task polling
  const stopAiPolling = useCallback(() => {
    if (aiPollIntervalRef.current) {
      clearInterval(aiPollIntervalRef.current);
      aiPollIntervalRef.current = null;
    }
  }, []);

  // Poll for AI task status and handle results
  useEffect(() => {
    if (!aiTaskId || !aiTaskType) return;

    const poll = async () => {
      try {
        const res = await fetchAiTaskStatus({ variables: { taskId: aiTaskId } });
        const task = res.data?.aiGenerationTaskStatus;
        if (!task) return;

        if (task.status === 'COMPLETED' || task.status === 'FAILED') {
          stopAiPolling();
          setAiTaskId(null);
          setAiTaskType(null);
          // Dismiss any active loading toast
          message.destroy('ai-generate');
          message.destroy('ai-suggest');
          message.destroy('ai-similar');

          if (task.status === 'FAILED') {
            message.error(task.errorMessage || 'AI generation failed. Please try again.');
            return;
          }

          const result = task.resultData ? JSON.parse(task.resultData) : null;
          if (!result) {
            message.error('AI returned no result. Please try again.');
            return;
          }

          if (aiTaskType === 'generate') {
            let generated: string | null = result.rule || null;
            if (format === 'AQL' && generated && !isLikelyAql(generated)) {
              message.warning('AI returned non-AQL content for QRadar. Please retry.');
              generated = null;
            }
            if (generated && (format !== 'AQL' || isLikelyAql(generated))) {
              const generatedRule = cleanRuleContent(generated);
              setRuleContent(generatedRule);
              setOpenTideRule(prev => setPlatformContent(prev, activePlatformTab, generatedRule));
              setPlatformGenerationInsights(prev => ({
                ...prev,
                [activePlatformTab]: {
                  quickWinRule: result.quick_win_rule || '',
                  robustRule: result.robust_rule || '',
                  generationSummary: result.generation_summary || '',
                  correlationIdeas: result.correlation_ideas || '',
                  expectedBlindSpots: result.expected_blind_spots || '',
                  testGuidance: result.test_guidance || '',
                },
              }));
              setHasUnseenInsights(true);
              if (activePlatformTab !== 'metadata' && activePlatformTab !== 'insights') {
                setLastInsightsPlatform(activePlatformTab);
              }
              setMode('ai');
              message.success(`AI-generated rule loaded (${result.provider_used})`);
            } else if (format === 'AQL') {
              message.error('AI did not return valid AQL for QRadar. Please retry or adjust model settings.');
            } else {
              message.warning('No rule was generated');
            }
          } else if (aiTaskType === 'suggest') {
            const newSuggestions = result.suggestions || '';
            const newImprovedRule = result.improved_rule || '';
            if (newSuggestions) {
              setPlatformSuggestions(prev => ({ ...prev, [activePlatformTab]: newSuggestions }));
              setPlatformImprovedRules(prev => ({ ...prev, [activePlatformTab]: newImprovedRule }));
              setActiveTab('suggestions');
              message.success(`Suggestions generated using ${result.provider_used}`);
            } else {
              message.error('AI returned no suggestions. The model may be overloaded — please try again.');
            }
          } else if (aiTaskType === 'similar') {
            const generatedRules = result.generated_rules || '';
            if (generatedRules) {
              setPlatformSimilarRules(prev => ({ ...prev, [activePlatformTab]: generatedRules }));
              setActiveTab('similar');
              setShowSimilarOptions(false);
              message.success(
                `Generated ${result.num_generated} ${result.variation_type} variations using ${result.provider_used}`
              );
            } else {
              message.error('AI returned no rules. The model may be overloaded — please try again.');
            }
          }
        }
      } catch {
        // Network error during poll – keep polling
      }
    };

    aiPollIntervalRef.current = setInterval(poll, AI_POLL_INTERVAL_MS);
    return stopAiPolling;
  }, [aiTaskId, aiTaskType, fetchAiTaskStatus, stopAiPolling, format, activePlatformTab]);

  // Clean up polling when modal closes
  useEffect(() => {
    if (!visible) {
      stopAiPolling();
      setAiTaskId(null);
      setAiTaskType(null);
    }
  }, [visible, stopAiPolling]);

  // Clear the unseen-insights badge when user visits the Insights tab
  useEffect(() => {
    if (activePlatformTab === 'insights') {
      setHasUnseenInsights(false);
    }
  }, [activePlatformTab]);

  const { data: currentUserData } = useQuery<{ me: { id: string; username: string; role: string } }>(CURRENT_USER_QUERY);
  const [deleteRule] = useMutation(DELETE_RULE_MUTATION);

  // Sync with props when modal opens
  useEffect(() => {
    if (visible && !prevVisibleRef.current) {
      setRuleContent(initialRule);
      setMode(initialMode);
      setSelectedDataSource(null);
      setSelectedRule(null);
      setSelectedTemplate('');
      setActiveTab('editor');
      setShowSimilarOptions(false);
      setSimilarVariationType('technique');
      setSimilarNumVariations(3);
      setSimilarTargetFormat('');
      setSimilarCustomInstructions('');
      setPlatformGenerationInsights({});
      setPlatformRagReuse({});
      setHasUnseenInsights(false);
      setLastInsightsPlatform(null);
      setSelectedVariant(null);
      setGenerateAllStatuses({});
      setGenerateAllErrors({});
      setOverwriteAllContent(DEFAULT_OVERWRITE_ALL_CONTENT);

      // Reset OpenTide state
      const freshOt = buildOpenTideState(initialOpenTideRule, initialRule, initialFormat, playbookData);
      setOpenTideRule(freshOt);
      setMetadataTitle(freshOt.metadata?.title || playbookData?.title || '');
      setMetadataDescription(freshOt.metadata?.description || '');
      setMetadataAuthor(freshOt.metadata?.author || playbookData?.author?.username || '');
      setMetadataTags('');
      // Derive active platform
      let tab: PlatformTab = 'kql';
      if (initialOpenTideRule?.platforms?.kql) tab = 'kql';
      else if (initialOpenTideRule?.platforms?.elastic) tab = 'eql';
      else if (initialOpenTideRule?.platforms?.spl) tab = 'spl';
      else if (initialOpenTideRule?.platforms?.wazuh) tab = 'wazuh';
      else if (initialOpenTideRule?.platforms?.qradar) tab = 'qradar';
      else if (initialFormat === 'KQL') tab = 'kql';
      else if (initialFormat === 'EQL') tab = 'eql';
      else if (initialFormat === 'SPL') tab = 'spl';
      else if (initialFormat === 'WAZUH') tab = 'wazuh';
      else if (initialFormat === 'AQL') tab = 'qradar';
      setActivePlatformTab(tab);
      setRuleContent(getPlatformContent(freshOt, tab));
    }
    prevVisibleRef.current = visible;
  }, [visible, initialRule, initialFormat, initialMode, initialOpenTideRule, playbookData]);

  useEffect(() => {
    if (!visible) return;
    const freshOt = buildOpenTideState(initialOpenTideRule, initialRule, initialFormat, playbookData);
    const initialSnapshots: Record<string, string> = {};
    for (const entry of DETECTION_FORMAT_REGISTRY) {
      initialSnapshots[entry.format] = normalize(entry.getContent(freshOt));
    }
    setSavedSnapshots(initialSnapshots);
    setSavedMetadataSnapshot(normalize(JSON.stringify(freshOt.metadata ?? {})));
  }, [visible, initialRule, initialFormat, initialOpenTideRule, playbookData]);

  // Handle template selection
  const handleTemplateSelect = useCallback((templateName: string) => {
    if (!templateName) return;
    
    const templates = RULE_TEMPLATES[format] || {};
    const templateContent = templates[templateName];
    
    if (templateContent) {
      setRuleContent(templateContent);
      setSelectedTemplate(templateName);
      setMode('manual');
      message.success(`Template "${templateName}" loaded`);
    }
  }, [format]);

  // Handle existing rule selection
  const handleRuleSelect = useCallback((rule: RuleOption | null) => {
    setSelectedRule(rule);
    if (rule) {
      // Load the rule's content into the editor
      if (rule.rawContent) {
        setRuleContent(rule.rawContent);
        setMode('manual');
        // Do NOT change format here – the active platform tab dictates the format.
        message.success(`Rule "${rule.title}" loaded into editor`);
      } else {
        message.warning(`Rule "${rule.title}" has no content to load`);
      }
    }
  }, []);

  // Clear content handler
  const handleClearContent = useCallback(() => {
    setRuleContent('');
    setSelectedRule(null);
    setSelectedTemplate('');
    setMode('manual');
    // Also clear the current platform from openTideRule
    setOpenTideRule(prev => setPlatformContent(prev, activePlatformTab, ''));
    message.info('Editor content cleared');
  }, [activePlatformTab]);

  /** Switch the active platform tab, saving current content first. */
  const handlePlatformTabChange = useCallback((tab: MainPlatformTab) => {
    if (tab === 'insights') {
      // Save current editor content before switching to Insights (no content to load)
      if (activePlatformTab !== 'metadata' && activePlatformTab !== 'insights') {
        setOpenTideRule(prev => setPlatformContent(prev, activePlatformTab, ruleContent));
      }
      setActivePlatformTab('insights');
      return;
    }
    if (activePlatformTab === 'insights') {
      // Switching away from Insights – just load the new platform's content
      const newContent = getPlatformContent(openTideRule, tab);
      setRuleContent(newContent);
      setActivePlatformTab(tab);
      if (tab !== 'metadata') setLastEditedPlatform(tab);
      setActiveTab('editor');
      setSelectedTemplate('');
      return;
    }
    // Persist current editor content to the openTide rule, then load the new platform's content
    const updated = setPlatformContent(openTideRule, activePlatformTab, ruleContent);
    const newContent = getPlatformContent(updated, tab);
    setOpenTideRule(updated);
    setRuleContent(newContent);
    setActivePlatformTab(tab);
    if (tab !== 'metadata') setLastEditedPlatform(tab as PlatformTab);
    setActiveTab('editor');
    setSelectedTemplate('');
  }, [openTideRule, activePlatformTab, ruleContent]);

  const canDeleteSelectedRule = useCallback(() => {
    const currentUser = currentUserData?.me;
    if (!currentUser || !selectedRule) return false;
    const isOwner = selectedRule.author && selectedRule.author === currentUser.username;
    const isAdmin = currentUser.role === 'ADMIN' || currentUser.role === 'SUPERADMIN';
    return !!(isOwner || isAdmin);
  }, [currentUserData, selectedRule]);

  const handleDeleteSelectedRule = useCallback(() => {
    if (!selectedRule) return;
    Modal.confirm({
      title: 'Delete Detection Rule',
      content: `Are you sure you want to delete the rule "${selectedRule.title}"? This action cannot be undone.`,
      okText: 'Delete',
      okType: 'danger',
      onOk: async () => {
        try {
          setDeletingRule(true);
          const { data: result } = await deleteRule({ variables: { ruleId: selectedRule.id } });
          if (result?.deleteDetectionRule?.success) {
            message.success(result.deleteDetectionRule.message || 'Rule deleted successfully');
            setSelectedRule(null);
            setRuleContent('');
            setSelectedTemplate('');
            setMode('manual');
          } else {
            message.error(result?.deleteDetectionRule?.message || 'Failed to delete rule');
          }
        } catch (err: any) {
          message.error(err.message || 'Error deleting rule');
        } finally {
          setDeletingRule(false);
        }
      },
    });
  }, [deleteRule, selectedRule]);

  // Handle data source selection
  const handleDataSourceSelect = useCallback((ds: DataSourceOption | null) => {
    setSelectedDataSource(ds);
    if (ds) {
      // Add data source context to the rule as a comment
      const dsComment = format === 'KQL'
        ? `// Data Source: ${ds.name} (${ds.platform})\n`
        : format === 'AQL'
        ? `-- Data Source: ${ds.name} (${ds.platform})\n`
        : format === 'SPL'
        ? `\`comment("Data Source: ${ds.name} (${ds.platform})")\`\n`
        : `<!-- Data Source: ${ds.name} (${ds.platform}) -->\n`;
      
      if (!ruleContent.includes(`Data Source: ${ds.name}`)) {
        setRuleContent(prev => dsComment + prev);
      }
    }
  }, [format, ruleContent]);

  // AI Generation handler – starts an async task and polls for result
  const handleAIGenerate = useCallback(async () => {
    if (onGenerateAI) {
      // Legacy synchronous path for callers that supply their own generator
      setAiGenerating(true);
      try {
        let generated = await onGenerateAI(format);
        if (format === 'AQL' && generated && !isLikelyAql(generated)) {
          message.warning('AI returned non-AQL content for QRadar. Regenerating as AQL...');
          generated = await onGenerateAI('AQL');
        }
        if (generated && (format !== 'AQL' || isLikelyAql(generated))) {
          const generatedRule = generated;
          setRuleContent(generatedRule);
          setOpenTideRule(prev => setPlatformContent(prev, activePlatformTab, generatedRule));
          setMode('ai');
          message.success('AI-generated rule loaded');
        } else if (format === 'AQL') {
          message.error('AI did not return valid AQL for QRadar. Please retry or adjust model/deployment settings.');
        } else {
          message.warning('No rule was generated');
        }
      } catch (err: any) {
        message.error(`AI generation failed: ${err.message}`);
      } finally {
        setAiGenerating(false);
      }
      return;
    }

    // Async path: start a background task so the request returns immediately
    stopAiPolling();
    setAiTaskId(null);
    setPlatformGenerationInsights(prev => ({ ...prev, [activePlatformTab]: {} }));
    setSelectedVariant(null);
    try {
      const res = await startGenerateRuleTask({
        variables: { playbookId, outputFormat: format },
      });
      const r = res.data?.startGenerateRuleTask;
      if (r?.success && r?.taskId) {
        setAiTaskId(r.taskId);
        setAiTaskType('generate');
        message.loading({ content: 'Generating rule with AI…', key: 'ai-generate', duration: 0 });
      } else {
        message.error(r?.message || 'Failed to start AI generation task.');
      }
    } catch (err: any) {
      message.error(`AI generation failed: ${err.message}`);
    }
  }, [onGenerateAI, startGenerateRuleTask, playbookId, format, activePlatformTab, stopAiPolling]);

  // AI Suggest Improvements handler
  const handleSuggestImprovements = useCallback(async () => {
    if (!ruleContent || !ruleContent.trim()) {
      message.warning('Please add rule content before requesting suggestions');
      return;
    }

    stopAiPolling();
    setAiTaskId(null);
    try {
      const res = await startSuggestImprovementsTask({
        variables: { ruleContent, ruleFormat: format, playbookId },
      });
      const r = res.data?.startSuggestImprovementsTask;
      if (r?.success && r?.taskId) {
        setAiTaskId(r.taskId);
        setAiTaskType('suggest');
        message.loading({ content: 'Analyzing rule with AI…', key: 'ai-suggest', duration: 0 });
      } else {
        message.error(r?.message || 'Failed to start AI suggestions task.');
      }
    } catch (err: any) {
      message.error(`Failed to get suggestions: ${err.message}`);
    }
  }, [ruleContent, format, playbookId, startSuggestImprovementsTask, stopAiPolling]);

  // AI Generate Similar Rules handler
  const handleGenerateSimilar = useCallback(async () => {
    if (!ruleContent || !ruleContent.trim()) {
      message.warning('Please add rule content before generating similar rules');
      return;
    }

    stopAiPolling();
    setAiTaskId(null);
    try {
      const res = await startGenerateSimilarRulesTask({
        variables: {
          ruleContent,
          ruleFormat: format,
          variationType: similarVariationType,
          numVariations: similarNumVariations,
          targetFormat: similarTargetFormat || format,
          customInstructions: similarVariationType === 'custom' ? similarCustomInstructions : undefined,
          playbookId,
        },
      });
      const r = res.data?.startGenerateSimilarRulesTask;
      if (r?.success && r?.taskId) {
        setAiTaskId(r.taskId);
        setAiTaskType('similar');
        message.loading({ content: 'Generating similar rules with AI…', key: 'ai-similar', duration: 0 });
      } else {
        message.error(r?.message || 'Failed to start similar-rules generation task.');
      }
    } catch (err: any) {
      message.error(`Failed to generate similar rules: ${err.message}`);
    }
  }, [ruleContent, format, playbookId, similarVariationType, similarNumVariations, similarTargetFormat, similarCustomInstructions, startGenerateSimilarRulesTask, stopAiPolling]);

  const handleRecommendReuse = useCallback(async () => {
    if (!isRagReuseSupportedFormat(format)) {
      message.info('RAG reuse check currently supports KQL, EQL, SPL, and WAZUH. Switch to one of these editors and retry.');
      return;
    }

    stopAiPolling();
    setAiTaskId(null);
    setAiTaskType(null);

    try {
      const res = await recommendReusableRuleFromRag({
        variables: { playbookId, outputFormat: format },
      });
      const payload = res.data?.recommendReusableRuleFromRag;
      if (!payload) {
        message.error('AI returned no reuse recommendation. Please try again.');
        return;
      }

      setPlatformRagReuse((prev) => ({ ...prev, [activePlatformTab]: payload }));
      if (!payload.success) {
        message.error(payload.message || 'RAG reuse assessment failed.');
        return;
      }

      const decision = String(payload.decision || 'CREATE_NEW').toUpperCase();
      setActiveTab('reuse');
      if (decision === 'CREATE_NEW') {
        message.info(payload.message || 'No close reusable template found; creating a new rule is recommended.');
      } else {
        message.success(`RAG reuse assessment complete (${decision}).`);
      }
    } catch (err: any) {
      message.error(`RAG reuse assessment failed: ${err.message}`);
    }
  }, [format, playbookId, activePlatformTab, recommendReusableRuleFromRag, stopAiPolling]);

  const getReuseDecisionColor = useCallback((decision?: string): 'green' | 'orange' | 'blue' | 'default' => {
    const normalized = String(decision || '').toUpperCase();
    if (normalized === 'REUSE') return 'green';
    if (normalized === 'ADAPT') return 'orange';
    if (normalized === 'CREATE_NEW') return 'blue';
    return 'default';
  }, []);

  // Copy a single generated rule to editor
  const handleCopyRuleToEditor = useCallback((ruleText: string) => {
    setRuleContent(cleanRuleContent(ruleText));
    setMode('ai');
    setActiveTab('editor');
    message.success('Rule copied to editor');
  }, []);

  const currentSnapshot = useMemo(
    () => setPlatformContent(openTideRule, activePlatformTab, ruleContent),
    [openTideRule, activePlatformTab, ruleContent]
  );
  const dirtyByFormat = useMemo(() => {
    const next: Record<string, boolean> = {};
    for (const entry of DETECTION_FORMAT_REGISTRY) {
      next[entry.format] = isDirty(entry.getContent(currentSnapshot), savedSnapshots[entry.format] ?? '');
    }
    return next;
  }, [currentSnapshot, savedSnapshots]);
  const metadataChanged = useMemo(
    () => isDirty(JSON.stringify(currentSnapshot.metadata ?? {}), savedMetadataSnapshot),
    [currentSnapshot, savedMetadataSnapshot]
  );
  const anyDirty = useMemo(
    () => Object.values(dirtyByFormat).some(Boolean) || metadataChanged,
    [dirtyByFormat, metadataChanged]
  );

  const sourcePlatform = useMemo<PlatformTab | null>(() => {
    const filled = DETECTION_FORMAT_REGISTRY.filter((f) => f.getContent(currentSnapshot).trim());
    if (filled.length === 0) return null;
    if (filled.length === 1) return filled[0].id;
    if (activePlatformTab !== 'metadata' && activePlatformTab !== 'insights' && filled.some((f) => f.id === activePlatformTab)) {
      return activePlatformTab;
    }
    if (filled.some((f) => f.id === lastEditedPlatform)) return lastEditedPlatform;
    return filled[0].id;
  }, [currentSnapshot, activePlatformTab, lastEditedPlatform]);

  const sourceFormatName = sourcePlatform ? getFormatByTab(sourcePlatform).displayName : null;

  const ensureMetadata = useCallback(async () => {
    const current = {
      title: metadataTitle.trim(),
      description: metadataDescription.trim(),
      author: metadataAuthor.trim(),
      tags: metadataTags.split(',').map((t) => t.trim()).filter(Boolean),
    };
    const normalized = {
      title: current.title || playbookData?.title || 'rule',
      description: current.description,
      author: current.author,
      tags: current.tags,
      skipped: false,
    };
    const missing: string[] = [];
    if (!normalized.description) missing.push('description');
    if (!normalized.author) missing.push('author');
    if (normalized.tags.length === 0) missing.push('tags');
    if (missing.length > 0) {
      message.warning(`Missing metadata (${missing.join(', ')}). Saving with available metadata only.`);
      return { ...normalized, skipped: true };
    }
    return normalized;
  }, [metadataTitle, metadataDescription, metadataAuthor, metadataTags, playbookData?.title]);

  const persistWorkbench = useCallback(async (finalRule: OpenTideRule) => {
    const activeFormat = platformToFormat(activePlatformTab);
    await onSave(ruleContent, activeFormat, mode, selectedDataSource?.id, finalRule);
  }, [onSave, ruleContent, activePlatformTab, mode, selectedDataSource]);

  const handleSaveFormat = useCallback(async (tab: PlatformTab) => {
    const finalOpenTideRule = setPlatformContent(openTideRule, activePlatformTab, ruleContent);
    const entry = getFormatByTab(tab);
    const content = entry.getContent(finalOpenTideRule).trim();
    if (!content) {
      message.warning(`${entry.displayName} editor is empty.`);
      return;
    }
    if (!isDirty(content, savedSnapshots[entry.format] ?? '')) {
      message.info('No changes, nothing to save');
      return;
    }
    const metadata = await ensureMetadata();

    setSavingSingle(true);
    try {
      await persistWorkbench(finalOpenTideRule);
      const res = await saveDetectionRuleMutation({
        variables: {
          playbookId,
          rawYaml: content,
          format: entry.format,
          title: metadata.title || playbookData?.title || 'rule',
          description: metadata.skipped ? '' : metadata.description,
          author: metadata.skipped ? '' : metadata.author,
          tags: metadata.skipped ? [] : metadata.tags,
          autoCommit,
          commitMessage: commitMessage || undefined,
        },
      });
      const payload = res.data?.saveDetectionRule;
      if (payload?.success) {
        setSavedSnapshots((prev) => ({ ...prev, [entry.format]: normalize(content) }));
        message.success(payload.filename ? `Saved ${payload.filename}` : `Saved ${entry.displayName}`);
      } else {
        message.error(payload?.message || `Failed to save ${entry.displayName}`);
      }
    } catch (err: any) {
      message.error(`Failed to save ${entry.displayName}: ${err.message}`);
    } finally {
      setSavingSingle(false);
    }
  }, [openTideRule, activePlatformTab, ruleContent, savedSnapshots, ensureMetadata, persistWorkbench, saveDetectionRuleMutation, playbookId, autoCommit, commitMessage, playbookData?.title]);

  const handleGenerateAll = useCallback(async () => {
    const finalOpenTideRule = setPlatformContent(openTideRule, activePlatformTab, ruleContent);
    if (!sourcePlatform) return;

    const sourceEntry = getFormatByTab(sourcePlatform);
    const sourceContent = sourceEntry.getContent(finalOpenTideRule).trim();
    const { targetFormats, statuses } = buildGenerateAllPlan(finalOpenTideRule, sourcePlatform, overwriteAllContent);
    setGenerateAllStatuses(statuses);
    setGenerateAllErrors({});
    if (targetFormats.length === 0) {
      message.info('No eligible target editors to generate.');
      return;
    }

    try {
      const res = await generateAllDetectionRulesMutation({
        variables: {
          sourceFormat: sourceEntry.format,
          sourceContent,
          targetFormats,
          playbookId,
        },
      });
      const results: GenerateAllResult[] = res.data?.generateAllDetectionRules?.results || [];
      let updatedRule = finalOpenTideRule;
      const nextStatuses: Record<string, GenerateAllStatus> = { ...statuses };
      const nextErrors: Record<string, string> = {};
      for (const result of results) {
        nextStatuses[result.format] = result.status;
        if (result.status === 'failed' && result.error) {
          nextErrors[result.format] = result.error;
          // Keep a console breadcrumb for quick browser-side debugging.
          console.error(`[GenerateAll] ${result.format} failed: ${result.error}`);
        }
        const targetEntry = getFormatByName(result.format);
        if (result.content && targetEntry) {
          updatedRule = targetEntry.setContent(updatedRule, cleanRuleContent(result.content));
        }
      }
      setOpenTideRule(updatedRule);
      if (activePlatformTab !== 'metadata' && activePlatformTab !== 'insights') {
        setRuleContent(getPlatformContent(updatedRule, activePlatformTab));
      }
      setGenerateAllStatuses(nextStatuses);
      setGenerateAllErrors(nextErrors);
      const failedResults = results.filter((r) => r.status === 'failed');
      if (failedResults.length > 0) {
        message.warning(`Generate all finished with ${failedResults.length} failure(s). See details below.`);
      } else {
        message.success('Generate all completed.');
      }
    } catch (err: any) {
      message.error(`Generate all failed: ${err.message}`);
    }
  }, [openTideRule, activePlatformTab, ruleContent, sourcePlatform, overwriteAllContent, generateAllDetectionRulesMutation, playbookId]);

  const handleSaveAll = useCallback(async () => {
    const finalOpenTideRule = setPlatformContent(openTideRule, activePlatformTab, ruleContent);
    if (playbookData) {
      finalOpenTideRule.metadata = compileMetadataFromWorkbench(playbookData);
    }
    const entries = DETECTION_FORMAT_REGISTRY
      .map((entry) => ({ entry, content: entry.getContent(finalOpenTideRule).trim() }))
      .filter((item) => item.content)
      .filter((item) => isDirty(item.content, savedSnapshots[item.entry.format] ?? ''));
    const clearedEntries = DETECTION_FORMAT_REGISTRY.filter((entry) => {
      const current = normalize(entry.getContent(finalOpenTideRule));
      const previous = savedSnapshots[entry.format] ?? '';
      return current.length === 0 && previous.length > 0;
    });
    const hasMetadataChanges = isDirty(
      JSON.stringify(finalOpenTideRule.metadata ?? {}),
      savedMetadataSnapshot,
    );
    if (entries.length === 0 && clearedEntries.length === 0 && !hasMetadataChanges) {
      message.info('No changes, nothing to save');
      return;
    }
    const metadata = await ensureMetadata();

    setSavingAll(true);
    setValidationErrors([]);
    setLastCommitSha(null);
    try {
      await persistWorkbench(finalOpenTideRule);
      if (entries.length === 0) {
        setSavedSnapshots((prev) => {
          const next = { ...prev };
          for (const entry of clearedEntries) {
            next[entry.format] = '';
          }
          return next;
        });
        setSavedMetadataSnapshot(normalize(JSON.stringify(finalOpenTideRule.metadata ?? {})));
        message.success('Saved workbench changes.');
        return;
      }
      const result = await saveAllDetectionRulesMutation({
        variables: {
          playbookId,
          rules: entries.map((item) => ({ format: item.entry.format, content: item.content })),
          title: metadata.title || playbookData?.title || 'rule',
          description: metadata.skipped ? '' : metadata.description,
          author: metadata.skipped ? '' : metadata.author,
          tags: metadata.skipped ? [] : metadata.tags,
          autoCommit,
          commitMessage: commitMessage || undefined,
        },
      });
      const results = result.data?.saveAllDetectionRules?.results || [];
      const failures = results.filter((r: any) => r.status === 'failed');
      const savedFormats = new Set(
        results
          .filter((r: any) => r.status === 'saved')
          .map((r: any) => r.format)
      );
      setSavedSnapshots((prev) => {
        const next = { ...prev };
        for (const { entry, content } of entries) {
          if (savedFormats.has(entry.format)) {
            next[entry.format] = normalize(content);
          }
        }
        for (const entry of clearedEntries) {
          next[entry.format] = '';
        }
        return next;
      });
      setSavedMetadataSnapshot(normalize(JSON.stringify(finalOpenTideRule.metadata ?? {})));
      if (failures.length > 0) {
        message.error(`Saved with failures: ${failures.map((f: any) => f.format).join(', ')}`);
      } else {
        message.success(`Saved ${results.filter((r: any) => r.status === 'saved').length} rule(s).`);
      }
    } catch (err: any) {
      message.error(`Failed to save: ${err.message}`);
    } finally {
      setSavingAll(false);
    }
  }, [openTideRule, activePlatformTab, ruleContent, playbookData, savedSnapshots, savedMetadataSnapshot, ensureMetadata, persistWorkbench, saveAllDetectionRulesMutation, playbookId, autoCommit, commitMessage, playbookData?.title]);

  // Get syntax language for highlighter
  const getSyntaxLanguage = (): string => {
    switch (format) {
      case 'KQL':
        return 'sql'; // KQL is similar to SQL
      case 'WAZUH':
        return 'xml';
      case 'SPL':
        return 'bash'; // SPL is closest to shell/bash for highlighting purposes
      case 'AQL':
        return 'sql';
      default:
        return 'text';
    }
  };

  // Get available templates for current format
  const getTemplateOptions = () => {
    const templates = RULE_TEMPLATES[format] || {};
    return Object.keys(templates);
  };

  // Mode badge component
  const ModeBadge = () => {
    const badges: Record<DetectionMode, { color: string; label: string; icon: string }> = {
      logic: { color: 'blue', label: 'Generated by Logic', icon: 'cpu' },
      ai: { color: 'purple', label: 'Generated by AI', icon: 'zap' },
      manual: { color: 'green', label: 'Manual Edit', icon: 'edit' },
    };
    const badge = badges[mode];
    return (
      <Tag color={badge.color} className="flex items-center gap-1">
        <PixelIcon name={badge.icon} className="w-3 h-3" />
        {badge.label}
      </Tag>
    );
  };

  return (
    <Modal
      open={visible}
      onCancel={onClose}
      centered
      destroyOnClose
      title={
        <div className="flex items-center justify-between pr-8">
          <span className="text-lg font-semibold">Detection Rule Editor</span>
          <ModeBadge />
        </div>
      }
      width="95vw"
      style={{ paddingBottom: 0, maxWidth: '95vw' }}
      className="fullscreen-modal detection-editor-modal"
      styles={{
        content: {
          height: 'calc(100dvh - 24px)',
          maxHeight: 'calc(100dvh - 24px)',
          display: 'flex',
          flexDirection: 'column',
          padding: 0,
        },
        header: {
          marginBottom: 0,
          padding: '16px 24px',
          borderBottom: '1px solid var(--hef-border)',
          background: 'var(--hef-bg-surface)',
        },
        body: { 
          flex: 1,
          overflow: 'hidden',
          padding: 0,
          minHeight: 0,
          background: 'var(--hef-bg-page)',
        },
        footer: {
          marginTop: 0,
          padding: '12px 24px',
          borderTop: '1px solid var(--hef-border)',
          background: 'var(--hef-bg-surface)',
        },
      }}
      footer={
        <div className="flex flex-col gap-2">
          {/* Validation errors */}
          {validationErrors.length > 0 && (
            <Alert
              type="error"
              message="Validation Errors"
              description={
                <ul className="list-disc pl-4 mt-1">
                  {validationErrors.map((err, idx) => (
                    <li key={idx} className="text-xs">{err}</li>
                  ))}
                </ul>
              }
              closable
              onClose={() => setValidationErrors([])}
            />
          )}
          {/* Commit success */}
          {lastCommitSha && (
            <Alert
              type="success"
              message={`Committed to Git: ${lastCommitSha}`}
              closable
              onClose={() => setLastCommitSha(null)}
            />
          )}
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-gray-500 text-sm font-medium">Configured:</span>
              {getConfiguredPlatforms(setPlatformContent(openTideRule, activePlatformTab, ruleContent)).length === 0 ? (
                <span className="text-gray-400 text-sm">No platforms configured</span>
              ) : (
                getConfiguredPlatforms(setPlatformContent(openTideRule, activePlatformTab, ruleContent)).map(p => (
                  <Tag key={p} color={p === 'kql' ? 'blue' : p === 'spl' ? 'orange' : 'green'} className="text-xs">
                    {p.toUpperCase()}
                  </Tag>
                ))
              )}
            </div>
            <div className="flex items-center gap-2 flex-wrap justify-end">
              {/* Git commit option */}
              <Checkbox
                checked={autoCommit}
                onChange={(e) => setAutoCommit(e.target.checked)}
                className="text-sm"
              >
                Commit to Repository
              </Checkbox>
              {autoCommit && (
                <Input
                  placeholder="Commit message (optional)"
                  value={commitMessage}
                  onChange={(e) => setCommitMessage(e.target.value)}
                  style={{ width: 220 }}
                  size="small"
                />
              )}
              <Button onClick={onClose}>Cancel</Button>
              {selectedRule && canDeleteSelectedRule() && (
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  loading={deletingRule}
                  onClick={handleDeleteSelectedRule}
                >
                  Delete Rule
                </Button>
              )}
              {activePlatformTab !== 'metadata' && activePlatformTab !== 'insights' && (
                <Button
                  type="primary"
                  ghost
                  onClick={() => handleSaveFormat(activePlatformTab)}
                  loading={savingSingle}
                  disabled={!ruleContent.trim() || !dirtyByFormat[getFormatByTab(activePlatformTab).format]}
                >
                  {buildSaveButtonLabel(getFormatByTab(activePlatformTab))}
                </Button>
              )}
              <Button type="primary" onClick={handleSaveAll} loading={savingAll} disabled={!anyDirty}>
                {savingAll ? 'SAVING ALL...' : 'SAVE ALL'}
              </Button>
            </div>
          </div>
        </div>
      }
    >
      <div className="flex h-full">
        {/* Left Panel - Configuration */}
        <div className="w-80 border-r border-gray-200 p-4 overflow-y-auto bg-gray-50">
          {activePlatformTab === 'metadata' ? (
            <div className="flex flex-col items-center justify-center h-full text-center text-gray-400 gap-3 py-12">
              <PixelIcon name="file-text" className="w-10 h-10 opacity-40" />
              <p className="text-sm font-medium text-gray-500">Metadata is read-only</p>
              <p className="text-xs text-gray-400">Select a platform tab (KQL, SPL, WAZUH, QRadar) to access editor tools.</p>
            </div>
          ) : activePlatformTab === 'insights' ? (
            <div className="flex flex-col items-center justify-center h-full text-center text-gray-400 gap-3 py-12">
              <PixelIcon name="zap" className="w-10 h-10 opacity-40" />
              <p className="text-sm font-medium text-gray-500">AI Insights</p>
              <p className="text-xs text-gray-400">View AI-generated correlation ideas, blind spots, and test guidance on the right.</p>
            </div>
          ) : (
          <div className="space-y-6">
            {/* Data Source Section */}
            <div>
              <h4 className="font-medium text-gray-700 mb-2 flex items-center gap-2">
                <PixelIcon name="database" className="w-4 h-4" />
                Data Source
              </h4>
              <DataSourcePicker
                value={selectedDataSource}
                onChange={handleDataSourceSelect}
                placeholder="Search data sources..."
              />
              {selectedDataSource && (
                <div className="mt-2 p-2 bg-white rounded border text-sm">
                  <div className="font-medium">{selectedDataSource.name}</div>
                  <div className="text-gray-500 text-xs">{selectedDataSource.platform}</div>
                </div>
              )}
            </div>

            <Divider className="my-4" />

            {/* Existing Rule Section */}
            <div>
              <h4 className="font-medium text-gray-700 mb-2 flex items-center gap-2">
                <PixelIcon name="file-text" className="w-4 h-4" />
                Load Existing Rule
              </h4>
              <RulePicker
                value={selectedRule}
                onChange={handleRuleSelect}
                formatFilter={format !== 'OTHER' ? format : undefined}
                placeholder="Search rules..."
              />
            </div>

            <Divider className="my-4" />

            {/* Templates Section */}
            <div>
              <h4 className="font-medium text-gray-700 mb-2 flex items-center gap-2">
                <PixelIcon name="layers" className="w-4 h-4" />
                Quick Templates
              </h4>
              <Select
                value={selectedTemplate || undefined}
                onChange={handleTemplateSelect}
                placeholder="Select a template..."
                style={{ width: '100%' }}
                allowClear
              >
                {getTemplateOptions().map((name) => (
                  <Option key={name} value={name}>{name}</Option>
                ))}
              </Select>
            </div>

            <Divider className="my-4" />

            {/* AI Assist Section */}
            <div>
              <h4 className="font-medium text-gray-700 mb-2 flex items-center gap-2">
                <PixelIcon name="zap" className="w-4 h-4" />
                AI Assist
              </h4>
              <div className="space-y-2">
                <Button
                  block
                  type="primary"
                  className="bg-purple-600 hover:bg-purple-700"
                  onClick={handleAIGenerate}
                  loading={aiLoading || aiGenerating || (aiTaskType === 'generate' && !!aiTaskId)}
                  icon={<PixelIcon name="zap" className="w-4 h-4" />}
                >
                  {(aiLoading || aiGenerating || (aiTaskType === 'generate' && !!aiTaskId)) ? `Generating ${format}...` : 'Generate with AI'}
                </Button>
                <div className="flex items-center gap-2">
                  <Button
                    block
                    onClick={handleGenerateAll}
                    loading={generatingAll}
                    disabled={!sourcePlatform}
                    icon={<PixelIcon name="layers" className="w-4 h-4" />}
                    className="border-indigo-500 text-indigo-600 hover:bg-indigo-50 hover:border-indigo-600"
                  >
                    GENERATE ALL
                  </Button>
                  <Checkbox
                    checked={overwriteAllContent}
                    onChange={(e) => setOverwriteAllContent(e.target.checked)}
                  >
                    Overwrite all content
                  </Checkbox>
                </div>
                <p className="text-xs text-gray-500">
                  When enabled, GENERATE ALL overwrites non-source editors. When disabled, non-empty targets are skipped.
                </p>
                {sourceFormatName && (
                  <p className="text-xs text-gray-500 mt-1">Using {sourceFormatName} as source</p>
                )}
                {Object.keys(generateAllStatuses).length > 0 && (
                  <div className="text-xs bg-gray-50 border border-gray-200 rounded p-2 space-y-1">
                    <div className="font-medium text-gray-700">Overwrite mode: {overwriteAllContent ? 'ON' : 'OFF'}</div>
                    {Object.entries(generateAllStatuses).map(([fmt, status]) => (
                      <div key={fmt} className="space-y-0.5">
                        <div className="flex justify-between">
                          <span>{fmt}</span>
                          <span className="font-medium">{status}</span>
                        </div>
                        {generateAllErrors[fmt] && (
                          <div className="text-[11px] text-red-600 break-words">
                            {generateAllErrors[fmt]}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                <Button
                  block
                  onClick={handleSuggestImprovements}
                  loading={suggestingLoading || (aiTaskType === 'suggest' && !!aiTaskId)}
                  disabled={!ruleContent || !ruleContent.trim()}
                  icon={<PixelIcon name="lightbulb" className="w-4 h-4" />}
                  className="border-amber-500 text-amber-600 hover:bg-amber-50 hover:border-amber-600"
                >
                  {(suggestingLoading || (aiTaskType === 'suggest' && !!aiTaskId)) ? 'Analyzing Rule...' : 'Suggest Improvements'}
                </Button>
                <Button
                  block
                  onClick={handleRecommendReuse}
                  loading={recommendingReuse}
                  disabled={!ragReuseSupported}
                  icon={<PixelIcon name="target" className="w-4 h-4" />}
                  className="border-emerald-500 text-emerald-600 hover:bg-emerald-50 hover:border-emerald-600"
                >
                  {recommendingReuse ? 'Checking RAG Reuse...' : 'RAG Reuse Check'}
                </Button>
                <Button
                  block
                  onClick={() => setShowSimilarOptions(!showSimilarOptions)}
                  disabled={!ruleContent || !ruleContent.trim()}
                  icon={<PixelIcon name="copy" className="w-4 h-4" />}
                  className="border-blue-500 text-blue-600 hover:bg-blue-50 hover:border-blue-600"
                >
                  Generate Similar {showSimilarOptions ? '▲' : '▼'}
                </Button>
                
                {!ragReuseSupported && (
                  <p className="text-xs text-gray-400">RAG reuse check is available for KQL, EQL, SPL, and WAZUH.</p>
                )}

                {/* Generate Similar Options Panel */}
                {showSimilarOptions && (
                  <div className="mt-2 p-3 bg-blue-50 rounded-lg border border-blue-200 space-y-3">
                    <div>
                      <label className="text-xs font-medium text-gray-600 block mb-1">Variation Type</label>
                      <Select
                        value={similarVariationType}
                        onChange={setSimilarVariationType}
                        style={{ width: '100%' }}
                        size="small"
                      >
                        {VARIATION_TYPES.map((vt) => (
                          <Option key={vt.value} value={vt.value}>
                            <div className="flex items-center gap-2">
                              <PixelIcon name={vt.icon} className="w-3 h-3" />
                              <span>{vt.label}</span>
                            </div>
                          </Option>
                        ))}
                      </Select>
                      <p className="text-xs text-gray-500 mt-1">
                        {VARIATION_TYPES.find(v => v.value === similarVariationType)?.description}
                      </p>
                    </div>
                    
                    <div className="flex gap-2">
                      <div className="flex-1">
                        <label className="text-xs font-medium text-gray-600 block mb-1">Count</label>
                        <InputNumber
                          min={1}
                          max={5}
                          value={similarNumVariations}
                          onChange={(v) => setSimilarNumVariations(v || 3)}
                          size="small"
                          style={{ width: '100%' }}
                        />
                      </div>
                      <div className="flex-1">
                        <label className="text-xs font-medium text-gray-600 block mb-1">Output Format</label>
                        <Select
                          value={similarTargetFormat || format}
                          onChange={setSimilarTargetFormat}
                          size="small"
                          style={{ width: '100%' }}
                        >
                          {DETECTION_FORMAT_REGISTRY.map((entry) => (
                            <Option key={entry.format} value={entry.format}>{entry.displayName.toUpperCase()}</Option>
                          ))}
                        </Select>
                      </div>
                    </div>
                    
                    {similarVariationType === 'custom' && (
                      <div>
                        <label className="text-xs font-medium text-gray-600 block mb-1">Custom Instructions</label>
                        <TextArea
                          value={similarCustomInstructions}
                          onChange={(e) => setSimilarCustomInstructions(e.target.value)}
                          placeholder="Describe what kind of variations you want..."
                          rows={2}
                          size="small"
                        />
                      </div>
                    )}
                    
                    <Button
                      block
                      type="primary"
                      onClick={handleGenerateSimilar}
                      loading={generatingSimilarLoading || (aiTaskType === 'similar' && !!aiTaskId)}
                      icon={<PixelIcon name="copy" className="w-4 h-4" />}
                      className="bg-blue-600 hover:bg-blue-700"
                    >
                      {(generatingSimilarLoading || (aiTaskType === 'similar' && !!aiTaskId)) ? 'Generating Variations...' : `Generate ${similarNumVariations} Variation${similarNumVariations > 1 ? 's' : ''}`}
                    </Button>
                  </div>
                )}

              </div>
            </div>

            <Divider className="my-4" />

            {/* Clear Content Section */}
            <div>
              <h4 className="font-medium text-gray-700 mb-2 flex items-center gap-2">
                <PixelIcon name="trash" className="w-4 h-4" />
                Editor Actions
              </h4>
              <Button
                block
                danger
                onClick={handleClearContent}
                icon={<PixelIcon name="trash" className="w-4 h-4" />}
                disabled={!ruleContent}
              >
                Clear Content
              </Button>
            </div>

            <Divider className="my-4" />

            {/* Mode Selection */}
            <div>
              <h4 className="font-medium text-gray-700 mb-2 flex items-center gap-2">
                <PixelIcon name="settings" className="w-4 h-4" />
                Edit Mode
              </h4>
              <Radio.Group
                value={mode}
                onChange={(e) => setMode(e.target.value)}
                className="w-full"
              >
                <Space direction="vertical" className="w-full">
                  <Radio value="manual" className="w-full">
                    <span className="flex items-center gap-2">
                      <Tag color="green">Manual</Tag>
                      <span className="text-xs text-gray-500">Free editing</span>
                    </span>
                  </Radio>
                  <Radio value="logic" className="w-full">
                    <span className="flex items-center gap-2">
                      <Tag color="blue">Logic</Tag>
                      <span className="text-xs text-gray-500">From strategy</span>
                    </span>
                  </Radio>
                  <Radio value="ai" className="w-full">
                    <span className="flex items-center gap-2">
                      <Tag color="purple">AI</Tag>
                      <span className="text-xs text-gray-500">AI-generated</span>
                    </span>
                  </Radio>
                </Space>
              </Radio.Group>
            </div>
          </div>
          )}
        </div>

        {/* Right Panel - Editor */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Platform Tabs (Primary Navigation) */}
          <div className="border-b border-gray-300 bg-gray-100 px-4 pt-2">
            <div className="flex items-center gap-1 flex-wrap">
              {(
                [
                  { key: 'metadata' as MainPlatformTab, label: '📋 Metadata' as React.ReactNode, color: 'bg-gray-200 text-gray-700', activeColor: 'bg-gray-600 text-white' },
                  {
                    key: 'insights' as MainPlatformTab,
                    label: (
                      <span className="inline-flex items-center gap-1">
                        💡 Insights
                        {hasUnseenInsights && (
                          <span
                            className="inline-block w-2 h-2 rounded-full bg-red-500"
                            aria-label="New AI insights available"
                            title="New AI insights available"
                          />
                        )}
                      </span>
                    ) as React.ReactNode,
                    color: 'bg-amber-50 text-amber-700 border border-amber-200',
                    activeColor: 'bg-amber-500 text-white',
                  },
                  ...DETECTION_FORMAT_REGISTRY.map((entry) => ({
                    key: entry.id as MainPlatformTab,
                    label: (
                      <span className="inline-flex items-center gap-1">
                        {entry.tabLabel}
                        {dirtyByFormat[entry.format] && <span title="Unsaved changes">●</span>}
                      </span>
                    ) as React.ReactNode,
                    color: entry.tabColor,
                    activeColor: entry.tabActiveColor,
                  })),
                ]
              ).map(({ key, label, color, activeColor }) => {
                const isActive = activePlatformTab === key;
                const configured = key !== 'metadata' && key !== 'insights' && (() => {
                  const snapshot = setPlatformContent(openTideRule, activePlatformTab, ruleContent);
                  return getConfiguredPlatforms(snapshot).includes(key as PlatformTab);
                })();
                return (
                  <button
                    key={key}
                    onClick={() => handlePlatformTabChange(key as MainPlatformTab)}
                    className={`px-3 py-1.5 rounded-t text-xs font-medium transition-all relative ${isActive ? activeColor : color} hover:opacity-90`}
                  >
                    {label}
                    {configured && !isActive && (
                      <span className="ml-1 inline-block w-1.5 h-1.5 rounded-full bg-green-500 align-middle" title="Configured" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Metadata Panel (read-only) */}
          {activePlatformTab === 'metadata' ? (
            <div className="flex-1 overflow-auto bg-white p-6">
              <OpenTideMetadataPreview openTideRule={openTideRule} />
            </div>
          ) : activePlatformTab === 'insights' ? (() => {
              const tabInsights = lastInsightsPlatform ? platformGenerationInsights[lastInsightsPlatform] : null;
              return (
                <div className="flex-1 overflow-auto bg-white p-6">
                  {tabInsights ? (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between pb-3 border-b">
                        <div className="flex items-center gap-2">
                          <PixelIcon name="zap" className="w-5 h-5 text-amber-500" />
                          <h3 className="text-base font-semibold m-0 text-gray-800">
                            {tabInsights.generationSummary || 'Capability-aware generation insights'}
                          </h3>
                        </div>
                        <Button
                          size="small"
                          onClick={() => {
                            setPlatformGenerationInsights({});
                            setLastInsightsPlatform(null);
                            setHasUnseenInsights(false);
                            setSelectedVariant(null);
                          }}
                        >
                          Clear insights
                        </Button>
                      </div>
                      {tabInsights.correlationIdeas && (
                        <div>
                          <strong className="text-sm text-gray-700">Correlation ideas:</strong>
                          <pre className="whitespace-pre-wrap font-sans text-xs mt-1 bg-gray-50 p-3 rounded border">{tabInsights.correlationIdeas}</pre>
                        </div>
                      )}
                      {tabInsights.expectedBlindSpots && (
                        <div>
                          <strong className="text-sm text-gray-700">Expected blind spots:</strong>
                          <pre className="whitespace-pre-wrap font-sans text-xs mt-1 bg-gray-50 p-3 rounded border">{tabInsights.expectedBlindSpots}</pre>
                        </div>
                      )}
                      {tabInsights.testGuidance && (
                        <div>
                          <strong className="text-sm text-gray-700">Suggested test guidance:</strong>
                          <pre className="whitespace-pre-wrap font-sans text-xs mt-1 bg-gray-50 p-3 rounded border">{tabInsights.testGuidance}</pre>
                        </div>
                      )}
                      <Space wrap className="pt-2">
                        {tabInsights.quickWinRule && lastInsightsPlatform && (
                          <Button
                            type={selectedVariant === 'quickWin' ? 'primary' : 'default'}
                            onClick={() => {
                              const quickWinRule = tabInsights.quickWinRule || '';
                              setRuleContent(quickWinRule);
                              setOpenTideRule(prev => setPlatformContent(prev, lastInsightsPlatform, quickWinRule));
                              setMode('ai');
                              setActivePlatformTab(lastInsightsPlatform);
                              setActiveTab('editor');
                              setSelectedVariant('quickWin');
                              message.success('Quick-win variant loaded into editor');
                            }}
                          >
                            Load quick-win variant
                          </Button>
                        )}
                        {tabInsights.robustRule && lastInsightsPlatform && (
                          <Button
                            type={selectedVariant === 'robust' ? 'primary' : 'default'}
                            onClick={() => {
                              const robustRule = tabInsights.robustRule || '';
                              setRuleContent(robustRule);
                              setOpenTideRule(prev => setPlatformContent(prev, lastInsightsPlatform, robustRule));
                              setMode('ai');
                              setActivePlatformTab(lastInsightsPlatform);
                              setActiveTab('editor');
                              setSelectedVariant('robust');
                              message.success('Robust variant loaded into editor');
                            }}
                          >
                            Load robust variant
                          </Button>
                        )}
                      </Space>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center h-full text-center text-gray-400 gap-3 py-12">
                      <PixelIcon name="zap" className="w-10 h-10 opacity-40" />
                      <p className="text-sm font-medium text-gray-500">No AI insights yet.</p>
                      <p className="text-xs text-gray-400">Click <strong>Generate with AI</strong> to populate Correlation Ideas, Expected Blind Spots, and Suggested Test Guidance here.</p>
                    </div>
                  )}
                </div>
              );
            })() : (
            <>
          {/* Tab Header (secondary) */}
          <div className="border-b border-gray-200 bg-white">
              <Tabs
                activeKey={activeTab}
              onChange={(key) => setActiveTab(key as 'editor' | 'preview' | 'suggestions' | 'similar' | 'reuse')}
                items={[
                  { key: 'editor', label: 'Editor' },
                  { key: 'preview', label: 'Preview' },
                { 
                  key: 'suggestions', 
                  label: (
                    <span className="flex items-center gap-1">
                      <PixelIcon name="lightbulb" className="w-3 h-3" />
                      Suggestions
                      {suggestions && <span className="ml-1 px-1.5 py-0.5 text-xs bg-amber-100 text-amber-700 rounded">New</span>}
                    </span>
                  ) 
                },
                { 
                  key: 'similar', 
                  label: (
                    <span className="flex items-center gap-1">
                      <PixelIcon name="copy" className="w-3 h-3" />
                      Similar Rules
                      {generatedSimilarRules && <span className="ml-1 px-1.5 py-0.5 text-xs bg-blue-100 text-blue-700 rounded">New</span>}
                    </span>
                  ) 
                },
                {
                  key: 'reuse',
                  label: (
                    <span className="flex items-center gap-1">
                      <PixelIcon name="target" className="w-3 h-3" />
                      RAG Reuse
                      {ragReuseResult?.decision && (
                        <span className="ml-1 px-1.5 py-0.5 text-xs bg-emerald-100 text-emerald-700 rounded">
                          {String(ragReuseResult.decision).replace('_', ' ')}
                        </span>
                      )}
                    </span>
                  )
                },
              ]}
              className="px-4"
            />
          </div>

          {/* Content Area */}
          <div className="flex-1 overflow-hidden">
            {activeTab === 'editor' ? (
              <DetectionRuleEditor
                value={ruleContent}
                onChange={(val) => {
                  setRuleContent(val);
                  setLastEditedPlatform(activePlatformTab as PlatformTab);
                  if (mode !== 'manual') setMode('manual');
                }}
                format={format as 'KQL' | 'EQL' | 'WAZUH' | 'SPL' | 'AQL' | 'OTHER'}
                height="100%"
                dataSourceId={selectedDataSource?.id}
              />
            ) : activeTab === 'preview' ? (
              <div className="h-full overflow-auto bg-gray-900">
                <SyntaxHighlighter
                  language={getSyntaxLanguage()}
                  style={vscDarkPlus}
                  customStyle={{
                    margin: 0,
                    padding: '1rem',
                    minHeight: '100%',
                    fontSize: '0.875rem',
                  }}
                  showLineNumbers
                >
                  {ruleContent || '// No content to preview'}
                </SyntaxHighlighter>
              </div>
            ) : activeTab === 'reuse' ? (
              <div className="h-full overflow-auto bg-white p-6">
                {ragReuseResult && (ragReuseResult.decision || ragReuseResult.message || ragReuseResult.rationale || ragReuseResult.workbenchSummary) ? (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 mb-2 pb-3 border-b">
                      <PixelIcon name="target" className="w-5 h-5 text-emerald-500" />
                      <h3 className="text-lg font-semibold m-0">RAG Template Reuse Assessment</h3>
                    </div>

                    <Space wrap>
                      <Tag color={getReuseDecisionColor(ragReuseResult.decision)}>
                        Decision: {String(ragReuseResult.decision || 'CREATE_NEW').replace('_', ' ')}
                      </Tag>
                      {typeof ragReuseResult.referenceCount === 'number' && (
                        <Tag color="default">References: {ragReuseResult.referenceCount}</Tag>
                      )}
                      {ragReuseResult.providerUsed && (
                        <Tag color="purple">Provider: {ragReuseResult.providerUsed}</Tag>
                      )}
                    </Space>

                    {ragReuseResult.candidateSource && ragReuseResult.candidateSource !== 'NONE' && (
                      <div>
                        <strong className="text-sm text-gray-700">Best candidate source:</strong>
                        <pre className="whitespace-pre-wrap font-sans text-xs mt-1 bg-gray-50 p-3 rounded border">{ragReuseResult.candidateSource}</pre>
                      </div>
                    )}

                    {ragReuseResult.workbenchSummary && (
                      <div>
                        <strong className="text-sm text-gray-700">Workbench summary:</strong>
                        <pre className="whitespace-pre-wrap font-sans text-xs mt-1 bg-gray-50 p-3 rounded border">{ragReuseResult.workbenchSummary}</pre>
                      </div>
                    )}

                    {ragReuseResult.rationale && (
                      <div>
                        <strong className="text-sm text-gray-700">Rationale:</strong>
                        <div className="mt-1 p-3 rounded border bg-gray-50">
                          <MarkdownRenderer content={ragReuseResult.rationale} variant="compact" />
                        </div>
                      </div>
                    )}

                    {ragReuseResult.adaptedRule && ragReuseResult.adaptedRule.trim() && (
                      <div>
                        <div className="flex items-center justify-between">
                          <strong className="text-sm text-gray-700">Adapted rule candidate:</strong>
                          <Button
                            size="small"
                            type="primary"
                            onClick={() => {
                              const adaptedRule = cleanRuleContent(ragReuseResult.adaptedRule || '');
                              if (!adaptedRule) {
                                message.warning('No adapted rule content to apply.');
                                return;
                              }
                              setRuleContent(adaptedRule);
                              setOpenTideRule(prev => setPlatformContent(prev, activePlatformTab, adaptedRule));
                              setMode('ai');
                              setActiveTab('editor');
                              message.success('Adapted rule applied to editor');
                            }}
                            icon={<PixelIcon name="download" className="w-3 h-3" />}
                          >
                            Use Adapted Rule
                          </Button>
                        </div>
                        <SyntaxHighlighter
                          language={getSyntaxLanguage()}
                          style={vscDarkPlus}
                          customStyle={{
                            margin: 0,
                            padding: '1rem',
                            fontSize: '0.75rem',
                            maxHeight: '360px',
                            marginTop: '0.5rem',
                          }}
                          showLineNumbers
                        >
                          {cleanRuleContent(ragReuseResult.adaptedRule)}
                        </SyntaxHighlighter>
                      </div>
                    )}

                    <div className="mt-4 pt-4 border-t flex gap-2">
                      <Button
                        size="small"
                        onClick={() => setActiveTab('editor')}
                        icon={<PixelIcon name="edit" className="w-3 h-3" />}
                      >
                        Back to Editor
                      </Button>
                      <Button
                        size="small"
                        onClick={handleRecommendReuse}
                        loading={recommendingReuse}
                        icon={<PixelIcon name="refresh-cw" className="w-3 h-3" />}
                      >
                        Re-run Assessment
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full text-gray-400">
                    <PixelIcon name="target" className="w-12 h-12 mb-4 opacity-50" />
                    <p className="text-lg font-medium mb-2">No RAG Reuse Assessment Yet</p>
                    <p className="text-sm text-center max-w-md mb-4">
                      Click "RAG Reuse Check" in the AI Assist section to evaluate whether an existing template should be reused or adapted.
                    </p>
                    <Button
                      onClick={handleRecommendReuse}
                      loading={recommendingReuse}
                      disabled={!ragReuseSupported}
                      icon={<PixelIcon name="target" className="w-4 h-4" />}
                    >
                      Run RAG Reuse Check
                    </Button>
                  </div>
                )}
              </div>
            ) : activeTab === 'suggestions' ? (
              <div className="h-full overflow-auto bg-white p-6">
                {suggestions ? (
                  <div className="prose prose-sm max-w-none">
                    <div className="flex items-center gap-2 mb-4 pb-4 border-b">
                      <PixelIcon name="lightbulb" className="w-5 h-5 text-amber-500" />
                      <h3 className="text-lg font-semibold m-0">AI Improvement Suggestions</h3>
                    </div>
                    <MarkdownRenderer content={suggestions} variant="compact" />
                    <div className="mt-6 pt-4 border-t flex gap-2">
                      <Button 
                        size="small" 
                        onClick={() => setActiveTab('editor')}
                        icon={<PixelIcon name="edit" className="w-3 h-3" />}
                      >
                        Back to Editor
                      </Button>
                      <Button 
                        size="small" 
                        type="primary"
                        disabled={!improvedRule}
                        onClick={() => {
                          // Apply only the improved rule (section 7) to the editor, replacing
                          // the existing content so users get a clean, better rule.
                          setRuleContent(cleanRuleContent(improvedRule));
                          setActiveTab('editor');
                          message.success('Improved rule applied to editor');
                        }}
                        icon={<PixelIcon name="download" className="w-3 h-3" />}
                      >
                        Apply to Editor
                      </Button>
                      <Button 
                        size="small" 
                        onClick={handleSuggestImprovements}
                        loading={suggestingLoading || (aiTaskType === 'suggest' && !!aiTaskId)}
                        icon={<PixelIcon name="refresh-cw" className="w-3 h-3" />}
                      >
                        Regenerate
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full text-gray-400">
                    <PixelIcon name="lightbulb" className="w-12 h-12 mb-4 opacity-50" />
                    <p className="text-lg font-medium mb-2">No Suggestions Yet</p>
                    <p className="text-sm text-center max-w-md mb-4">
                      Click "Suggest Improvements" in the AI Assist section to get AI-powered recommendations for improving your detection rule.
                    </p>
                    <Button 
                      onClick={handleSuggestImprovements}
                      loading={suggestingLoading || (aiTaskType === 'suggest' && !!aiTaskId)}
                      disabled={!ruleContent || !ruleContent.trim()}
                      icon={<PixelIcon name="lightbulb" className="w-4 h-4" />}
                    >
                      Get Suggestions
                    </Button>
                  </div>
                )}
              </div>
            ) : activeTab === 'similar' ? (
              <div className="h-full overflow-auto bg-white p-6">
                {generatedSimilarRules ? (
                  <div>
                    <div className="flex items-center gap-2 mb-4 pb-4 border-b">
                      <PixelIcon name="copy" className="w-5 h-5 text-blue-500" />
                      <h3 className="text-lg font-semibold m-0">Generated Similar Rules</h3>
                    </div>
                    
                    {/* Parse and display each rule */}
                    {generatedSimilarRules.split('---RULE---').map((ruleText, index) => {
                      const trimmedRule = ruleText.trim();
                      if (!trimmedRule) return null;

                      // Clean for both display and editor use
                      const cleanedRule = cleanRuleContent(trimmedRule);
                      
                      // Try to extract title from the rule
                      const titleMatch = trimmedRule.match(/title:\s*(.+)/i) || 
                                        trimmedRule.match(/\/\/\s*(.+)/);
                      const ruleTitle = titleMatch ? titleMatch[1].trim() : `Rule ${index + 1}`;
                      
                      return (
                        <div key={index} className="mb-6 border rounded-lg overflow-hidden">
                          <div className="flex items-center justify-between px-4 py-2 bg-gray-100 border-b">
                            <span className="font-medium text-sm text-gray-700">
                              {index + 1}. {ruleTitle}
                            </span>
                            <Button
                              size="small"
                              type="primary"
                              onClick={() => handleCopyRuleToEditor(cleanedRule)}
                              icon={<PixelIcon name="download" className="w-3 h-3" />}
                            >
                              Use This Rule
                            </Button>
                          </div>
                          <SyntaxHighlighter
                            language={getSyntaxLanguage()}
                            style={vscDarkPlus}
                            customStyle={{
                              margin: 0,
                              padding: '1rem',
                              fontSize: '0.75rem',
                              maxHeight: '300px',
                            }}
                            showLineNumbers
                          >
                            {cleanedRule}
                          </SyntaxHighlighter>
                        </div>
                      );
                    })}
                    
                    <div className="mt-6 pt-4 border-t flex gap-2">
                      <Button 
                        size="small" 
                        onClick={() => setActiveTab('editor')}
                        icon={<PixelIcon name="edit" className="w-3 h-3" />}
                      >
                        Back to Editor
                      </Button>
                      <Button 
                        size="small" 
                        onClick={() => setShowSimilarOptions(true)}
                        icon={<PixelIcon name="settings" className="w-3 h-3" />}
                      >
                        Change Options
                      </Button>
                      <Button 
                        size="small" 
                        onClick={handleGenerateSimilar}
                        loading={generatingSimilarLoading || (aiTaskType === 'similar' && !!aiTaskId)}
                        icon={<PixelIcon name="refresh-cw" className="w-3 h-3" />}
                      >
                        Regenerate
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full text-gray-400">
                    <PixelIcon name="copy" className="w-12 h-12 mb-4 opacity-50" />
                    <p className="text-lg font-medium mb-2">No Similar Rules Generated</p>
                    <p className="text-sm text-center max-w-md mb-4">
                      Click "Generate Similar" in the AI Assist section to create variations of your detection rule.
                    </p>
                    <Button 
                      onClick={() => setShowSimilarOptions(true)}
                      disabled={!ruleContent || !ruleContent.trim()}
                      icon={<PixelIcon name="copy" className="w-4 h-4" />}
                    >
                      Generate Similar Rules
                    </Button>
                  </div>
                )}
              </div>
            ) : null}
          </div>

          {/* Status Bar */}
          <div className="border-t border-gray-200 bg-gray-100 px-4 py-2 flex items-center justify-between text-xs text-gray-600">
            <div className="flex items-center gap-4">
              <span>Lines: {ruleContent.split('\n').length}</span>
              <span>Characters: {ruleContent.length}</span>
            </div>
            <div className="flex items-center gap-4">
              <span>Platform: {activePlatformTab.toUpperCase()}</span>
              <span>Language: {getSyntaxLanguage()}</span>
            </div>
          </div>
          </>
          )}
        </div>
      </div>
    </Modal>
  );
};

export default DetectionRuleEditorModal;
