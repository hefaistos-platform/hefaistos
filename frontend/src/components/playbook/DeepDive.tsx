import React, { useMemo, useState, useEffect } from 'react';
import { gql } from '@apollo/client';
import { useLazyQuery, useMutation } from '@apollo/client/react';
import { Select, Typography, message } from 'antd';
import SimpleMDE from 'react-simplemde-editor';
import { configureMdeInstance, MARKDOWN_EDITOR_OPTIONS } from '../../config/markdownConfig';
import "easymde/dist/easymde.min.css"; // Import CSS

interface DeepDiveProps {
  playbookId: string;
  data: {
    goal: string;
    technicalContext: string;
    blindSpots: string;
    response: string;
    falsePositives: string;
  };
  onChange: (field: string, value: string) => void;
  onLinkRules?: (ruleIds: string[]) => void;
}

type DeepDiveFormData = DeepDiveProps['data'];

const DEEP_DIVE_FIELDS: Array<keyof DeepDiveFormData> = [
  'goal',
  'technicalContext',
  'blindSpots',
  'response',
  'falsePositives',
];

const isSameDeepDiveData = (left: DeepDiveFormData, right: DeepDiveFormData) =>
  DEEP_DIVE_FIELDS.every((field) => left[field] === right[field]);

const RULES_CONNECTION_QUERY = gql`
  query RulesConnection($text: String, $first: Int!, $after: String, $repositoryId: ID) {
    rulesConnection(text: $text, first: $first, after: $after, repositoryId: $repositoryId) {
      edges { node { id title } cursor }
      pageInfo { hasNextPage endCursor }
      totalCount
    }
  }
`;

const GENERATE_RESPONSE_PLAYBOOK_MUTATION = gql`
  mutation GenerateResponsePlaybook($playbookId: UUID!) {
    generateResponsePlaybookAi(playbookId: $playbookId) {
      responsePlaybook
      providerUsed
    }
  }
`;

const TRANSLATE_RESPONSE_PLAYBOOK_MUTATION = gql`
  mutation TranslateResponsePlaybook($playbookId: UUID!, $targetLanguage: String!) {
    translateResponsePlaybookAi(playbookId: $playbookId, targetLanguage: $targetLanguage) {
      success
      message
      providerUsed
      targetLanguage
      translatedText
      responsePlaybook
    }
  }
`;

type TranslationLanguageCode = 'CZ' | 'DE' | 'SP' | 'FR';

const TRANSLATION_LANGUAGE_OPTIONS: Array<{ value: TranslationLanguageCode; label: string }> = [
  { value: 'CZ', label: 'CZ (Czech)' },
  { value: 'DE', label: 'DE (German)' },
  { value: 'SP', label: 'SP (Spanish)' },
  { value: 'FR', label: 'FR (French)' },
];

interface MiniRule { id: string; title: string }
interface RulesConnData {
  rulesConnection: {
    edges: { node: MiniRule; cursor: string }[];
    pageInfo: { hasNextPage: boolean; endCursor: string | null };
    totalCount: number;
  };
}
interface RulesConnVars { text?: string; first: number; after?: string; repositoryId?: string }

interface TranslateResponsePlaybookResult {
  translateResponsePlaybookAi?: {
    success?: boolean;
    message?: string;
    providerUsed?: string;
    targetLanguage?: string;
    translatedText?: string;
    responsePlaybook?: string;
  };
}

interface TranslateResponsePlaybookVars {
  playbookId: string;
  targetLanguage: string;
}

export const DeepDive = React.memo<DeepDiveProps>(({ playbookId, data, onChange, onLinkRules }) => {
  // Local state to handle user input without triggering immediate mutations
  const [localData, setLocalData] = useState(data);
  const [linkedRuleIds, setLinkedRuleIds] = useState<string[]>([]);
  const [ruleSearch, setRuleSearch] = useState<string>("");
  const [options, setOptions] = useState<{ label: string; value: string }[]>([]);
  const [aiGenerating, setAiGenerating] = useState(false);
  const [showTranslateControls, setShowTranslateControls] = useState(false);
  const [targetLanguage, setTargetLanguage] = useState<TranslationLanguageCode>('CZ');
  const [translating, setTranslating] = useState(false);

  const [searchRules, { data: rulesData }] = useLazyQuery<RulesConnData, RulesConnVars>(RULES_CONNECTION_QUERY);
  const [generateResponsePlaybook] = useMutation(GENERATE_RESPONSE_PLAYBOOK_MUTATION);
  const [translateResponsePlaybook] = useMutation<TranslateResponsePlaybookResult, TranslateResponsePlaybookVars>(
    TRANSLATE_RESPONSE_PLAYBOOK_MUTATION
  );

  const backendSnapshot = useMemo<DeepDiveFormData>(() => ({
    goal: data.goal,
    technicalContext: data.technicalContext,
    blindSpots: data.blindSpots,
    response: data.response,
    falsePositives: data.falsePositives,
  }), [data.goal, data.technicalContext, data.blindSpots, data.response, data.falsePositives]);

  // Sync from backend only when values actually changed. This avoids resetting editor/caret state
  // on parent rerenders where the data object identity changes but content is the same.
  useEffect(() => {
    setLocalData((previous) => (isSameDeepDiveData(previous, backendSnapshot) ? previous : backendSnapshot));
  }, [backendSnapshot]);

  const handleChange = (field: string, value: string) => {
    setLocalData(prev => ({ ...prev, [field]: value }));
  };

  const handleBlur = (field: string) => {
    // Only trigger mutation if value has changed
    if (localData[field as keyof typeof localData] !== data[field as keyof typeof data]) {
      onChange(field, localData[field as keyof typeof localData]);
    }
  };

  const handleAIGenerateResponse = async () => {
    if (!playbookId) return;
    setAiGenerating(true);
    try {
      const res = await generateResponsePlaybook({ variables: { playbookId } });
      const generated = res.data?.generateResponsePlaybookAi?.responsePlaybook;
      const normalized = typeof generated === 'string' ? generated.trim() : '';
      if (normalized) {
        setLocalData(prev => ({ ...prev, response: normalized }));
        onChange('response', normalized);
        message.success(`Response playbook generated using ${res.data?.generateResponsePlaybookAi?.providerUsed}`);
      } else {
        message.error('AI returned no response playbook. The model may be overloaded or still loading — please try again.');
      }
    } catch (e: any) {
      const errMsg = String(e?.message || '');
      if (errMsg.includes('504') || errMsg.toLowerCase().includes('gateway time-out') || errMsg.toLowerCase().includes('gateway timeout')) {
        message.error('AI Assist timed out at gateway. The backend now uses shorter generation; please retry in a few seconds.');
      } else {
        message.error(errMsg || 'AI generation failed');
      }
    } finally {
      setAiGenerating(false);
    }
  };

  const handleTranslateResponse = async () => {
    if (!playbookId) return;
    if (!localData.response?.trim()) {
      message.warning('Response Playbook is empty. Add content before translation.');
      return;
    }

    setTranslating(true);
    try {
      const res = await translateResponsePlaybook({ variables: { playbookId, targetLanguage } });
      const payload = res.data?.translateResponsePlaybookAi;
      const translatedResponse = payload?.responsePlaybook?.trim() || '';

      if (payload?.success && translatedResponse) {
        setLocalData(prev => ({ ...prev, response: translatedResponse }));
        onChange('response', translatedResponse);
        setShowTranslateControls(false);
        message.success(payload.message || `Response Playbook translated to ${targetLanguage}.`);
      } else {
        message.error(payload?.message || 'Translation failed.');
      }
    } catch (e: any) {
      message.error(e?.message || 'Translation failed');
    } finally {
      setTranslating(false);
    }
  };

  const technicalContextOptions = useMemo(() => ({
    ...MARKDOWN_EDITOR_OPTIONS.standard,
    placeholder: "Explain how the attack works...",
    status: false,
  }), []);

  const responseOptions = useMemo(() => ({
    ...MARKDOWN_EDITOR_OPTIONS.standard,
    placeholder: "1. Isolate Host\n2. Dump RAM...",
    status: false,
  }), []);

  const falsePositivesOptions = useMemo(() => ({
    ...MARKDOWN_EDITOR_OPTIONS.minimal,
    placeholder: "- Antivirus Scanners\n- System Admin Scripts",
    status: false,
  }), []);

  const blindSpotsOptions = useMemo(() => ({
    ...MARKDOWN_EDITOR_OPTIONS.minimal,
    placeholder: "- Data quality limitations\n- Coverage gaps in specific environments\n- Known evasion techniques",
    status: false,
  }), []);

  useEffect(() => {
    const handler = setTimeout(() => {
      searchRules({ variables: { text: ruleSearch || undefined, first: 20 } });
    }, 300);
    return () => clearTimeout(handler);
  }, [ruleSearch, searchRules]);

  useEffect(() => {
    if (rulesData?.rulesConnection?.edges) {
      const opts = rulesData.rulesConnection.edges.map((e) => ({ label: e.node.title, value: e.node.id }));
      setOptions(opts);
    }
  }, [rulesData]);

  return (
    <div className="deep-dive-section p-6 bg-white border-2 border-hefaistos-border rounded-lg shadow-sm mt-6">
      <h2 className="text-xl font-bold mb-4 text-hefaistos-primary">Part 2: Deep Dive (Operational Context)</h2>

      {/* 1. Goal */}
      <div className="mb-6">
        <label className="block text-sm font-bold mb-2">Strategic Goal</label>
        <input 
            type="text" 
            className="w-full p-2 border border-gray-300 rounded"
            value={localData.goal}
            onChange={(e) => handleChange('goal', e.target.value)}
            onBlur={() => handleBlur('goal')}
            placeholder="e.g. Detect LSASS access to prevent credential dumping."
        />
      </div>

      {/* 2. Technical Context (Rich Text) */}
      <div className="mb-6">
        <label className="block text-sm font-bold mb-2">Technical Context</label>
        <SimpleMDE 
            value={localData.technicalContext} 
            onChange={(val) => handleChange('technicalContext', val)} 
            onBlur={() => handleBlur('technicalContext')}
            options={technicalContextOptions}
            getMdeInstance={configureMdeInstance}
        />
      </div>

      {/* 3. Response Playbook (Rich Text) */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <label className="block text-sm font-bold">Response Playbook</label>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            <button
              type="button"
              onClick={handleAIGenerateResponse}
              disabled={aiGenerating || translating}
              className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title="AI: Generate response steps based on goal, technical context, false positives, and blind spots"
            >
              {aiGenerating ? (
                <>
                  <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                  </svg>
                  Generating...
                </>
              ) : (
                <>✨ AI Assist</>
              )}
            </button>

            <button
              type="button"
              onClick={() => setShowTranslateControls((prev) => !prev)}
              disabled={aiGenerating || translating}
              className="inline-flex items-center gap-1.5 min-w-[92px] justify-center px-3 py-1 text-xs font-semibold rounded border border-blue-700 bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title="AI: Translate response playbook while preserving cyber security and IT terms"
            >
              {translating ? 'Translating...' : 'Translate'}
            </button>

            {showTranslateControls && (
              <>
                <Select
                  size="small"
                  style={{ minWidth: 150 }}
                  value={targetLanguage}
                  options={TRANSLATION_LANGUAGE_OPTIONS}
                  onChange={(value) => setTargetLanguage(value as TranslationLanguageCode)}
                  disabled={translating}
                />
                <button
                  type="button"
                  onClick={handleTranslateResponse}
                  disabled={translating}
                  className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded bg-hefaistos-primary text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Apply
                </button>
                <button
                  type="button"
                  onClick={() => setShowTranslateControls(false)}
                  disabled={translating}
                  className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded bg-gray-200 text-gray-700 hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Cancel
                </button>
              </>
            )}
          </div>
        </div>
        <SimpleMDE 
            value={localData.response} 
            onChange={(val) => handleChange('response', val)} 
            onBlur={() => handleBlur('response')}
            options={responseOptions}
            getMdeInstance={configureMdeInstance}
        />
      </div>

       {/* 4. False Positives */}
       <div className="mb-6">
        <label className="block text-sm font-bold mb-2">Known False Positives</label>
        <SimpleMDE
            value={localData.falsePositives}
            onChange={(val) => handleChange('falsePositives', val)}
            onBlur={() => handleBlur('falsePositives')}
            options={falsePositivesOptions}
            getMdeInstance={configureMdeInstance}
        />
      </div>

      {/* 5. Blind Spots & Coverage Gaps */}
      <div className="mb-6">
        <label className="block text-sm font-bold mb-2">Blind Spots & Coverage Gaps</label>
        <SimpleMDE
            value={localData.blindSpots}
            onChange={(val) => handleChange('blindSpots', val)}
            onBlur={() => handleBlur('blindSpots')}
            options={blindSpotsOptions}
            getMdeInstance={configureMdeInstance}
        />
      </div>

      {/* 6. Link Existing Rules */}
      <div className="mb-6">
          <div>
            <Typography.Text type="secondary" className="block mb-1">Link Existing Rules (multi-select)</Typography.Text>
            <Select
              mode="multiple"
              style={{ width: '100%' }}
              placeholder="Search and select rules to associate"
              options={options}
              value={linkedRuleIds}
              onSearch={setRuleSearch}
              onChange={(vals) => {
                setLinkedRuleIds(vals as string[]);
                onLinkRules && onLinkRules(vals as string[]);
              }}
              onDropdownVisibleChange={(open) => {
                if (open) {
                  // Trigger initial load with current query or no text
                  searchRules({ variables: { text: ruleSearch || undefined, first: 20 } });
                }
              }}
              filterOption={false}
              showSearch
            />
          </div>
      </div>
    </div>
  );
});

DeepDive.displayName = 'DeepDive';
