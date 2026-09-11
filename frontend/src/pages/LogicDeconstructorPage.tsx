import React, { useState } from 'react';
import { gql } from '@apollo/client';
import { useMutation, useQuery } from '@apollo/client/react';

type DeconstructRuleResult = {
  deconstructRule: {
    report: string;
    providerUsed: string;
    warning?: string | null;
  };
};

type AiProvider = 'openai' | 'gemini' | 'claude' | 'ollama' | 'unknown';

const inferProviderFromModel = (value: string): AiProvider => {
  const normalized = value.trim().toUpperCase();
  if (!normalized) return 'unknown';
  if (normalized.startsWith('GEMINI')) return 'gemini';
  if (normalized.startsWith('CLAUDE')) return 'claude';
  if (normalized.startsWith('OLLAMA') || normalized.startsWith('LLAMA') || normalized.startsWith('MISTRAL')) return 'ollama';
  if (normalized.startsWith('GPT')) return 'openai';
  return 'unknown';
};

const DECONSTRUCT_RULE_MUTATION = gql`
  mutation DeconstructRule($ruleText: String, $ruleUrl: String) {
    deconstructRule(ruleText: $ruleText, ruleUrl: $ruleUrl) {
      report
      providerUsed
      warning
    }
  }
`;

export const LogicDeconstructorPage: React.FC = () => {
  const [ruleText, setRuleText] = useState<string>("");
  const [ruleUrl, setRuleUrl] = useState<string>("");
  const [runDeconstruct, { data, loading, error }] = useMutation<DeconstructRuleResult>(DECONSTRUCT_RULE_MUTATION);
  const [modelSel, setModelSel] = useState<string>("");
  const [updateError, setUpdateError] = useState<string>("");

  type GetAiSettingsResult = {
    myAiSettings: {
      preferredModel: string | null;
      decrypted_openai: boolean;
      decrypted_gemini: boolean;
      decrypted_claude: boolean;
      hasOllama: boolean;
      useOrgAi: boolean;
      effectivePreferredModel: string | null;
    };
  };

  const GET_AI_SETTINGS = gql`
    query GetMyAISettings {
      myAiSettings {
        preferredModel
        decrypted_openai
        decrypted_gemini
        decrypted_claude
        hasOllama
        useOrgAi
        effectivePreferredModel
      }
    }
  `;
  const { data: aiData } = useQuery<GetAiSettingsResult>(GET_AI_SETTINGS, { fetchPolicy: 'cache-and-network' });
  const UPDATE_AI_SETTINGS = gql`
    mutation UpdateAISettings($preferredModel: String) {
      updateAiSettings(preferredModel: $preferredModel) {
        settings { preferredModel }
        warning
      }
    }
  `;
  const [updateAiSettings, { loading: updatingModel }] = useMutation(UPDATE_AI_SETTINGS, {
    refetchQueries: [{ query: GET_AI_SETTINGS }],
  });

  // Sync local selector with server once settings load
  React.useEffect(() => {
    const pm = aiData?.myAiSettings?.effectivePreferredModel || aiData?.myAiSettings?.preferredModel || '';
    setModelSel(pm);
  }, [aiData?.myAiSettings?.effectivePreferredModel, aiData?.myAiSettings?.preferredModel]);

  const handleRun = async () => {
    await runDeconstruct({ variables: { ruleText: ruleText || null, ruleUrl: ruleUrl || null } });
  };

  const themedFieldStyle: React.CSSProperties = {
    background: 'var(--hef-bg-subtle)',
    borderColor: 'var(--hef-border)',
    color: 'var(--hef-text-primary)',
  };

  const themedPanelStyle: React.CSSProperties = {
    background: 'var(--hef-bg-surface)',
    borderColor: 'var(--hef-border)',
    color: 'var(--hef-text-primary)',
  };

  return (
    <div className="p-6 space-y-4" style={{ color: 'var(--hef-text-primary)' }}>
      <h1 className="text-2xl font-semibold">Detection Logic Deconstructor</h1>
      <p className="text-sm" style={{ color: 'var(--hef-text-secondary)' }}>
        Paste a detection rule or provide a URL. Uses your preferred AI provider.
        <span className="ml-1 text-xs" style={{ color: 'var(--hef-text-muted)' }}>(AI prompts may be subject to charge)</span>
      </p>

      {/* URL + Model selector row */}
      <div className="flex gap-4 items-end">
        <div className="flex-1 space-y-2">
          <label className="block text-sm font-medium">Rule URL (optional)</label>
          <input
            type="text"
            value={ruleUrl}
            onChange={(e) => setRuleUrl(e.target.value)}
            placeholder="https://..."
            className="w-full border rounded p-2"
            style={themedFieldStyle}
          />
        </div>
        <div className="w-full md:w-1/3 space-y-2">
          <label className="block text-sm font-medium">AI Model</label>
          <div className="text-xs text-gray-600 mb-1">
            Your selected model is {modelSel || 'Not set'}.{aiData?.myAiSettings?.useOrgAi && aiData?.myAiSettings?.hasOllama ? ' (Organizational AI)' : ''} Enter any provider model name below.
          </div>
          <div className="flex items-center gap-2">
            <input
              type="text"
              className="border rounded p-2 text-sm w-full"
              value={modelSel}
              placeholder="e.g. GPT-5.5, GEMINI-3.5-FLASH, CLAUDE-SONNET-4.6, llama3.1"
              style={themedFieldStyle}
              onChange={(e) => {
                setUpdateError('');
                setModelSel(e.target.value);
              }}
              onKeyDown={async (e) => {
                if (e.key !== 'Enter') return;
                e.preventDefault();
                const model = modelSel.trim();
                try {
                  setUpdateError('');
                  await updateAiSettings({ variables: { preferredModel: model || undefined } });
                  setModelSel(model);
                } catch (err: any) {
                  setUpdateError(err?.message || 'Failed to update preferred model');
                }
              }}
            />
            <button
              type="button"
              className="px-3 py-2 text-xs font-semibold rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
              disabled={updatingModel}
              onClick={async () => {
                const model = modelSel.trim();
                try {
                  setUpdateError('');
                  await updateAiSettings({ variables: { preferredModel: model || undefined } });
                  setModelSel(model);
                } catch (err: any) {
                  setUpdateError(err?.message || 'Failed to update preferred model');
                }
              }}
            >
              Save
            </button>
            {updatingModel && <span className="text-xs" style={{ color: 'var(--hef-text-muted)' }}>Updating...</span>}
          </div>
          {updateError && <div className="text-xs text-red-600 mt-1">{updateError}</div>}
          {aiData?.myAiSettings && (
            <div className="mt-1 text-[11px]" style={{ color: 'var(--hef-text-muted)' }}>
              Available: [
              {aiData.myAiSettings.decrypted_openai ? 'OpenAI ' : ''}
              {aiData.myAiSettings.decrypted_gemini ? 'Gemini ' : ''}
              {aiData.myAiSettings.decrypted_claude ? 'Claude ' : ''}
              {aiData.myAiSettings.hasOllama ? 'Ollama (Org) ' : ''}
              ]
              {(() => {
                const m = modelSel.trim();
                const provider = inferProviderFromModel(m);
                // When org AI (Ollama) is active and the model is the org model, no warning needed
                if (aiData.myAiSettings.hasOllama && aiData.myAiSettings.useOrgAi) {
                  return null;
                }
                const providerAvailable = {
                  openai: aiData.myAiSettings.decrypted_openai,
                  gemini: aiData.myAiSettings.decrypted_gemini,
                  claude: aiData.myAiSettings.decrypted_claude,
                  ollama: aiData.myAiSettings.hasOllama,
                } as Record<Exclude<AiProvider, 'unknown'>, boolean>;
                if (provider !== 'unknown' && m && providerAvailable[provider] === false) {
                  return <span className="ml-1 text-yellow-700">(Selected provider has no key)</span>;
                }
                if (provider === 'unknown' && m) {
                  return <span className="ml-1" style={{ color: 'var(--hef-text-muted)' }}>(Provider could not be inferred from model name)</span>;
                }
                return null;
              })()}
            </div>
          )}
        </div>
      </div>

      {/* URL moved above alongside model selector */}

      <div className="space-y-2">
        <label className="block text-sm font-medium">Rule Text</label>
        <textarea
          value={ruleText}
          onChange={(e) => setRuleText(e.target.value)}
          rows={12}
          className="w-full border rounded p-2 font-mono"
          placeholder="# Paste detection rule content here (KQL, SPL, WAZUH...)"
          style={themedFieldStyle}
        />
      </div>

      <button
        onClick={handleRun}
        disabled={loading}
        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
      >
        {loading ? "Running..." : "Run Deconstruction"}
      </button>

      {error && <div className="text-red-600 text-sm">Error: {error.message}</div>}

      {data?.deconstructRule?.warning && (
        <div className="text-yellow-700 text-sm">Warning: {data.deconstructRule.warning}</div>
      )}

      {data?.deconstructRule?.providerUsed && (
        <div className="text-sm" style={{ color: 'var(--hef-text-secondary)' }}>Provider used: {data.deconstructRule.providerUsed}</div>
      )}

      {data?.deconstructRule?.report && (
        <pre className="whitespace-pre-wrap border rounded p-3" style={themedPanelStyle}>{data.deconstructRule.report}</pre>
      )}
    </div>
  );
};
