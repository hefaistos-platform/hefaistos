import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Skeleton, Tabs, Card } from 'antd';
import { useMutation, useQuery } from '@apollo/client/react';
import { useAppStore, Dcg420DetectionTemplate } from '../useStore';
// Import our themed UI components
import { Button } from './ui/Button';
import { PixelIcon } from './ui/PixelIcon';
import { Textarea } from './ui/Textarea';
import { Select as NativeSelect } from './ui/Select';
import SimpleMDE from 'react-simplemde-editor';
import Select from 'react-select';
import { GET_ALL_ATTACK_QUERY } from './PushToGitModal';
import { gql } from '@apollo/client';
import { createEditorOptions, MARKDOWN_PLACEHOLDERS, configureMdeInstance } from '../config/markdownConfig';
import { MarkdownRenderer } from './MarkdownRenderer';

type AttackTechnique = { id: string; techniqueId: string; name: string };
type GetAllAttackQueryResult = { allAttackTechniques: AttackTechnique[] };

const UPDATE_NODE_TEMPLATE_MUTATION = gql`
  mutation UpdateNodeTemplate($nodeId: UUID!, $templateData: GenericScalar!) {
    updateNodeTemplate(nodeId: $nodeId, templateData: $templateData) {
      node {
        id
        templateData # Get the updated data back
      }
    }
  }
`;

// Delete node mutation and graph refetch query
const DELETE_PLAYBOOK_NODE_MUTATION = gql`
  mutation DeletePlaybookNode($nodeId: UUID!) {
    deletePlaybookNode(nodeId: $nodeId) {
      ok
    }
  }
`;

const GET_PLAYBOOK_GRAPH_QUERY = gql`
  query GetPlaybookGraph($id: UUID!) {
    playbookGraph(id: $id) {
      id
      nodes { id layerName positionX positionY templateData mitreAttackMappings { id techniqueId name } }
      edges { id source target }
    }
  }
`;

// Update node ATT&CK mappings
const UPDATE_NODE_ATTACK_MAPPINGS_MUTATION = gql`
  mutation UpdateNodeAttackMappings($nodeId: UUID!, $mitreAttackIds: [ID]!) {
    updateNodeAttackMappings(nodeId: $nodeId, mitreAttackIds: $mitreAttackIds) {
      node {
        id
        mitreAttackMappings { id techniqueId name }
      }
    }
  }
`;

// Helper to render the YAML/Sigma rule
const RuleBlock: React.FC<{ rule: { format?: string, rule?: string } | undefined }> = ({ rule }) => {
  if (!rule || !rule.rule) {
    return <p className="text-gray-400 italic">No rule provided.</p>;
  }

  // Use a standard <pre> block. A proper YAML highlighter can be added later.
  return (
    <pre className="p-2 bg-hefaistos-subtle rounded-md text-sm overflow-x-auto">
      <code>
        {rule.rule}
      </code>
    </pre>
  );
};

// Helper for a single data field
const TemplateSection: React.FC<{ title: string, children: React.ReactNode, hasData?: boolean }> = ({ title, children, hasData }) => {
  // Check if data exists. For children like <p> or <ul>, we check if they have content.
  const dataExists = hasData !== undefined ? hasData : children;

  return (
    <div className="mb-4">
      <strong className="text-sm font-semibold text-gray-500 uppercase tracking-wider">{title}</strong>
      {dataExists ? (
        <div className="mt-1 text-gray-700">{children}</div>
      ) : (
        <p className="mt-1 text-gray-400 italic">Not provided.</p>
      )}
    </div>
  );
};


export function Sidebar() {
  const selectedNode = useAppStore((state) => state.selectedNode);
  const setSelectedNode = useAppStore((state) => state.setSelectedNode);
  const lastNodeIdRef = useRef<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [technicalContextTab, setTechnicalContextTab] = useState('editor');
  const [falsePositivesTab, setFalsePositivesTab] = useState('editor');
  const [responseTab, setResponseTab] = useState('editor');

  // Memoized editor options
  const technicalContextOptions = useMemo(() => createEditorOptions('standard', MARKDOWN_PLACEHOLDERS.technicalContext), []);
  const falsePositivesOptions = useMemo(() => createEditorOptions('standard', MARKDOWN_PLACEHOLDERS.falsePositives), []);
  const responseOptions = useMemo(() => createEditorOptions('standard', MARKDOWN_PLACEHOLDERS.response), []);

  // --- Local form state for all simple fields ---
  const [goal, setGoal] = useState('');
  const [strategyAbstract, setStrategyAbstract] = useState('');
  const [technicalContext, setTechnicalContext] = useState('');
  const [falsePositives, setFalsePositives] = useState('');
  const [priority, setPriority] = useState('Medium');
  const [response, setResponse] = useState('');
  // --- State for complex fields ---
  const [detectionRule, setDetectionRule] = useState('');
  const [detectionFormat, setDetectionFormat] = useState('KQL');
  const [attackMappings, setAttackMappings] = useState<{ value: string, label: string }[]>([]);
  const [nodeColor, setNodeColor] = useState<string>('');

  // Get the mutation function
  const [updateNodeTemplate, { loading, error }] = useMutation(UPDATE_NODE_TEMPLATE_MUTATION);
  type UpdateNodeAttackMappingsData = { updateNodeAttackMappings: { node: { id: string, mitreAttackMappings: AttackTechnique[] } } };
  type UpdateNodeAttackMappingsVars = { nodeId: string, mitreAttackIds: string[] };
  const [updateNodeAttackMappings] = useMutation<UpdateNodeAttackMappingsData, UpdateNodeAttackMappingsVars>(UPDATE_NODE_ATTACK_MAPPINGS_MUTATION);
  const [deleteNode, { loading: deleteLoading }] = useMutation(DELETE_PLAYBOOK_NODE_MUTATION);
  // --- Query for ATT&CK TTPs ---
  const { data: attackData, loading: attackLoading } = useQuery<GetAllAttackQueryResult>(GET_ALL_ATTACK_QUERY);
  const attackOptions = useMemo(() => {
    const techniques = attackData?.allAttackTechniques || [];
    // Sort by techniqueId for better browsing (T1001, T1002, etc.)
    const sorted = [...techniques].sort((a, b) => a.techniqueId.localeCompare(b.techniqueId));
    return sorted.map((tech: AttackTechnique) => ({
      value: tech.id,
      label: `${tech.techniqueId}: ${tech.name}`,
      techniqueId: tech.techniqueId, // Keep for filtering
    }));
  }, [attackData]);

  // Custom filter for react-select to match both technique ID and name
  const filterAttackOption = (option: any, inputValue: string) => {
    const search = inputValue.toLowerCase();
    const label = option.label?.toLowerCase() || '';
    const techniqueId = option.data?.techniqueId?.toLowerCase() || '';
    return label.includes(search) || techniqueId.includes(search);
  };

  // --- Playbook tags management (autotag format) ---
  const GET_PLAYBOOK_TAGS = gql`
    query GetPlaybookTags($id: UUID!) {
      playbookGraph(id: $id) { id tags }
    }
  `;
  const UPDATE_PLAYBOOK_TAGS = gql`
    mutation UpdatePlaybookTags($graphId: UUID!, $tags: [String]!) {
      updatePlaybookDetails(graphId: $graphId, tags: $tags) { graph { id tags } }
    }
  `;
  const [updatePlaybookTags] = useMutation(UPDATE_PLAYBOOK_TAGS);
  const { data: graphTagsData, refetch: refetchGraphTags } = useQuery<{ playbookGraph: { id: string, tags: string[] } }>(GET_PLAYBOOK_TAGS, {
    skip: !selectedNode?.graphId,
    variables: { id: selectedNode?.graphId || '' },
  });

  const formatApolloError = (err: any): string => {
    if (!err) return '';
    try {
      const parts: string[] = [];
      const network: any = err.networkError;
      const gqlErrs: any[] = err.graphQLErrors || [];
      if (network) {
        const status = network.statusCode ? `HTTP ${network.statusCode}` : 'HTTP error';
        const message = network.message || '';
        let resultStr = '';
        if (network.result) {
          try { resultStr = JSON.stringify(network.result, null, 2); } catch { resultStr = String(network.result); }
        }
        parts.push([status, message].filter(Boolean).join(' '));
        if (resultStr) parts.push(resultStr);
      }
      if (gqlErrs.length) {
        const cleaned = gqlErrs.map(e => ({ message: e.message, path: e.path, extensions: e.extensions }));
        parts.push(JSON.stringify(cleaned, null, 2));
      }
      if (!parts.length && err.message) parts.push(err.message);
      return parts.join('\n');
    } catch (e) {
      return err.message || String(e) || 'Unknown error';
    }
  };

  // --- Effect to populate the form when the node changes ---
  useEffect(() => {
    if (!selectedNode) return;
    // Only reset the form and leave edit mode when switching to a different node
    if (lastNodeIdRef.current !== selectedNode.id) {
      const t: any = selectedNode.templateData || {};
      setGoal(t.goal || t.v1_hypothesis || '');
      setStrategyAbstract(t.strategyAbstract || '');
      setTechnicalContext(t.technicalContext || '');
      setFalsePositives(t.falsePositives || '');
      setPriority(t.priority || 'Medium');
      setResponse(t.response || '');
      setNodeColor(t.color || '');
      // --- Populate complex fields ---
      setDetectionRule(t.detectionRule?.rule || '');
      setDetectionFormat(t.detectionRule?.format || 'KQL');
      const currentTTPs = selectedNode.mitreAttackMappings?.map((tech: any) => ({
        value: tech.id,
        label: `${tech.techniqueId}: ${tech.name}`,
      })) || [];
      setAttackMappings(currentTTPs);
      setIsEditing(false);
      lastNodeIdRef.current = selectedNode.id;
    }
  }, [selectedNode]);

  // --- Handle Save (for simple fields) ---
  const handleSave = async () => {
    if (!selectedNode) return;

    // 1. Get the current template data from the store
    const currentTemplate = { ...(selectedNode.templateData as any) };

    // 2. Create the new templateData JSON object
    const newTemplateData = {
      ...currentTemplate,
      goal: goal,
      strategyAbstract: strategyAbstract,
      technicalContext: technicalContext,
      falsePositives: falsePositives,
      priority: priority,
      response: response,
      // --- ADD COMPLEX FIELDS ---
      detectionRule: {
        format: detectionFormat,
        rule: detectionRule,
      },
      color: nodeColor || undefined,
    };

    try {
      // 3. Call the mutation
      await updateNodeTemplate({
        variables: {
          nodeId: selectedNode.id,
          templateData: newTemplateData,
          // We will add mitreAttackIds tomorrow
        },
        update: (cache, result) => {
          try {
            const cacheId = cache.identify({ __typename: 'PlaybookNodeType', id: selectedNode.id });
            if (cacheId) {
              cache.modify({
                id: cacheId,
                fields: {
                  templateData() {
                    return newTemplateData as any;
                  }
                }
              });
            }
          } catch (e) {
            // eslint-disable-next-line no-console
            console.warn('Apollo cache update failed for templateData:', e);
          }
        }
      });
      // 4. Save ATT&CK mappings
      const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
      const ids = attackMappings.map((a) => String(a.value)).filter((v) => uuidRegex.test(v));
      if (ids.length !== attackMappings.length) {
        console.warn('Some selected ATT&CK items did not have valid UUID ids. Skipping invalid entries.');
      }
      const mappingsRes = await updateNodeAttackMappings({
        variables: { nodeId: selectedNode.id, mitreAttackIds: ids },
        update: (cache, { data }) => {
          try {
            const cacheId = cache.identify({ __typename: 'PlaybookNodeType', id: selectedNode.id });
            if (cacheId && data?.updateNodeAttackMappings?.node?.mitreAttackMappings) {
              const newMappings = data.updateNodeAttackMappings.node.mitreAttackMappings;
              cache.modify({
                id: cacheId,
                fields: {
                  mitreAttackMappings() { return newMappings; }
                }
              });
            }
          } catch (e) {
            console.warn('Apollo cache update failed for mitreAttackMappings:', e);
          }
        }
      });

      const updatedMappings = mappingsRes.data?.updateNodeAttackMappings?.node?.mitreAttackMappings || [];

      // On success, update the store so read-only view reflects saved state (both template and mappings)
      setSelectedNode({ ...(selectedNode as any), templateData: newTemplateData, mitreAttackMappings: updatedMappings } as any);
      setIsEditing(false); // Exit edit mode
    } catch (e) {
      console.error('Failed to save node:', e);
      // Stay in edit mode; keep the form values so the user doesn't lose input
    }
  };

  const handleDeleteNode = async () => {
    if (!selectedNode) return;
    const confirmed = window.confirm(`Are you sure you want to delete the node "${selectedNode.layerName}"?`);
    if (!confirmed) return;
    try {
      await deleteNode({
        variables: { nodeId: selectedNode.id },
        refetchQueries: [{ query: GET_PLAYBOOK_GRAPH_QUERY, variables: { id: selectedNode.graphId } }],
      });
      setSelectedNode(null as any);
    } catch (e) {
      console.error('Failed to delete node:', e);
    }
  };

  if (!selectedNode) {
    return (
      <aside className="w-1/3 p-4 bg-white border-l-2 border-hefaistos-border overflow-y-auto" style={{ height: '80vh' }}>
        <h3 className="text-xl font-bold mb-2">Detection Template Explorer</h3>
        <Skeleton active paragraph={{ rows: 3 }} />
        <div className="mt-4">
          <Skeleton active title={false} paragraph={{ rows: 4 }} />
        </div>
        <div className="mt-4">
          <Skeleton active title={false} paragraph={{ rows: 2 }} />
        </div>
      </aside>
    );
  }

  // Extract the *original* template for the read-only view
  const template = (selectedNode.templateData || {}) as Dcg420DetectionTemplate;

  return (
    <aside className="w-1/3 p-4 bg-white border-l-2 border-hefaistos-border overflow-y-auto" style={{ height: '80vh' }}>
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">{selectedNode.layerName}</h2>
        {/* --- EDIT / SAVE / CANCEL BUTTONS --- */}
        {isEditing ? (
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setIsEditing(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleSave} disabled={loading}>
              {loading ? 'Saving...' : 'Save'}
            </Button>
          </div>
        ) : (
          <div className="flex gap-2">
            <Button variant="danger" onClick={handleDeleteNode} disabled={deleteLoading} title="Delete node">
              <PixelIcon name="delete" className="w-4 h-4" />
            </Button>
            <Button variant="secondary" onClick={() => setIsEditing(true)}>
              <PixelIcon name="edit" className="w-4 h-4 mr-2" />
              Edit
            </Button>
          </div>
        )}
      </div>
      <p className="sidebar-subtitle font-medium text-hefaistos-primary">
        Detection Engineering Template
      </p>

      {error && (
        <div className="my-2 text-xs bg-red-50 border border-red-200 rounded p-2">
          <p className="font-semibold text-red-700">Save failed</p>
          <pre className="mt-1 whitespace-pre-wrap text-red-800 overflow-auto max-h-48">{formatApolloError(error)}</pre>
        </div>
      )}

      <div className="mt-6 space-y-4">

        {/* --- TERNARY: Show Edit Form or Read-Only View --- */}

        {isEditing ? (
          /* --- EDIT MODE --- */
          <>
            <div className="mb-4">
              <label className="block mb-1 text-sm font-medium">Goal / Hypothesis</label>
              <Textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3} />
            </div>
            <div className="mb-4">
              <label className="block mb-1 text-sm font-medium">Priority</label>
              <NativeSelect value={priority} onChange={(e) => setPriority((e.target as HTMLSelectElement).value)}>
                <option value="Low">Low</option>
                <option value="Medium">Medium</option>
                <option value="High">High</option>
                <option value="Critical">Critical</option>
              </NativeSelect>
            </div>
            <div className="mb-4">
              <label className="block mb-1 text-sm font-medium">Strategy Abstract</label>
              <Textarea value={strategyAbstract} onChange={(e) => setStrategyAbstract(e.target.value)} rows={3} />
            </div>
            <div className="mb-4">
              <label className="block mb-1 text-sm font-medium">Technical Context (Markdown supported)</label>
              <Tabs
                activeKey={technicalContextTab}
                onChange={setTechnicalContextTab}
                tabBarStyle={{ marginBottom: 0 }}
                items={[
                  {
                    key: 'editor',
                    label: '✏️ Editor',
                    children: (
                      <div style={{ border: '1px solid #d9d9d9', borderRadius: '6px', overflow: 'hidden' }}>
                        <SimpleMDE
                          value={technicalContext}
                          onChange={setTechnicalContext}
                          options={technicalContextOptions}
                          getMdeInstance={configureMdeInstance}
                        />
                      </div>
                    ),
                  },
                  {
                    key: 'preview',
                    label: '👁️ Preview',
                    children: (
                      <Card size="small" style={{ marginBottom: 16, background: '#f5f5f5', minHeight: 200 }}>
                        {technicalContext.trim() ? (
                          <MarkdownRenderer content={technicalContext} variant="small" />
                        ) : (
                          <p style={{ color: '#999', fontStyle: 'italic' }}>No content to preview...</p>
                        )}
                      </Card>
                    ),
                  },
                ]}
              />
            </div>
            <div className="mb-4">
              <label className="block mb-1 text-sm font-medium">False Positives (Markdown supported)</label>
              <Tabs
                activeKey={falsePositivesTab}
                onChange={setFalsePositivesTab}
                tabBarStyle={{ marginBottom: 0 }}
                items={[
                  {
                    key: 'editor',
                    label: '✏️ Editor',
                    children: (
                      <div style={{ border: '1px solid #d9d9d9', borderRadius: '6px', overflow: 'hidden' }}>
                        <SimpleMDE
                          value={falsePositives}
                          onChange={setFalsePositives}
                          options={falsePositivesOptions}
                          getMdeInstance={configureMdeInstance}
                        />
                      </div>
                    ),
                  },
                  {
                    key: 'preview',
                    label: '👁️ Preview',
                    children: (
                      <Card size="small" style={{ marginBottom: 16, background: '#f5f5f5', minHeight: 200 }}>
                        {falsePositives.trim() ? (
                          <MarkdownRenderer content={falsePositives} variant="small" />
                        ) : (
                          <p style={{ color: '#999', fontStyle: 'italic' }}>No content to preview...</p>
                        )}
                      </Card>
                    ),
                  },
                ]}
              />
            </div>
            <div className="mb-4">
              <label className="block mb-1 text-sm font-medium">Response Steps (Triage - Markdown supported)</label>
              <Tabs
                activeKey={responseTab}
                onChange={setResponseTab}
                tabBarStyle={{ marginBottom: 0 }}
                items={[
                  {
                    key: 'editor',
                    label: '✏️ Editor',
                    children: (
                      <div style={{ border: '1px solid #d9d9d9', borderRadius: '6px', overflow: 'hidden' }}>
                        <SimpleMDE
                          value={response}
                          onChange={setResponse}
                          options={responseOptions}
                          getMdeInstance={configureMdeInstance}
                        />
                      </div>
                    ),
                  },
                  {
                    key: 'preview',
                    label: '👁️ Preview',
                    children: (
                      <Card size="small" style={{ marginBottom: 16, background: '#f5f5f5', minHeight: 200 }}>
                        {response.trim() ? (
                          <MarkdownRenderer content={response} variant="small" />
                        ) : (
                          <p style={{ color: '#999', fontStyle: 'italic' }}>No content to preview...</p>
                        )}
                      </Card>
                    ),
                  },
                ]}
              />
            </div>
            <div className="mb-4">
              <label className="block mb-1 text-sm font-medium">Node Color</label>
              <NativeSelect value={nodeColor} onChange={(e) => setNodeColor((e.target as HTMLSelectElement).value)}>
                <option value="">Default</option>
                <option value="blue">Light Blue</option>
                <option value="green">Light Green</option>
                <option value="red">Light Red</option>
                <option value="yellow">Light Yellow</option>
              </NativeSelect>
            </div>
            {/* --- ADD COMPLEX EDIT FIELDS --- */}
            <div className="mb-4">
              <label className="block mb-1 text-sm font-medium">Node ATT&CK Mappings</label>
              <p className="text-xs text-gray-500 mb-2">Type a technique ID (e.g., T1059) or name to search</p>
              <Select
                isMulti
                isSearchable
                isLoading={attackLoading}
                options={attackOptions}
                value={attackMappings}
                onChange={(selected) => setAttackMappings(selected as any)}
                filterOption={filterAttackOption}
                getOptionValue={(opt) => String((opt as any).value)}
                getOptionLabel={(opt) => String((opt as any).label)}
                placeholder={attackLoading ? 'Loading ATT&CK techniques…' : 'Type T1059 or technique name...'}
                noOptionsMessage={({ inputValue }) => 
                  attackLoading ? 'Loading…' : 
                  inputValue ? `No techniques matching "${inputValue}"` : 
                  'Start typing to search techniques'
                }
                classNames={{
                  control: () => 'p-1 border-2 border-hefaistos-border rounded-md bg-white',
                  multiValue: () => 'bg-blue-100 rounded-sm px-1',
                  multiValueLabel: () => 'text-blue-800 text-sm',
                  multiValueRemove: () => 'text-blue-600 hover:bg-blue-200 hover:text-blue-900 rounded-r-sm',
                  menu: () => 'bg-white border-2 border-hefaistos-border rounded-md mt-1 z-50 shadow-lg',
                  option: (state) => state.isFocused ? 'bg-blue-50 px-3 py-2 cursor-pointer' : 'px-3 py-2 cursor-pointer hover:bg-gray-50',
                }}
                styles={{
                  menuPortal: (base) => ({ ...base, zIndex: 9999 }),
                }}
                menuPortalTarget={typeof document !== 'undefined' ? document.body : null}
              />
            </div>

            <div className="mb-4">
              <label className="block mb-1 text-sm font-medium">Detection Rule Format</label>
              <NativeSelect value={detectionFormat} onChange={async (e) => {
                const next = (e.target as HTMLSelectElement).value;
                setDetectionFormat(next);
                try {
                  const graphId = selectedNode?.graphId;
                  if (!graphId) return;
                  // Load current tags (from query cache or refetch if missing)
                  const current = graphTagsData?.playbookGraph?.tags || [];
                  // Normalize format tags to upper-case for comparison
                  const fmt = String(next).toUpperCase();
                  const formatTags = ['KQL','WAZUH','SPLUNK','GENERIC'];
                  // Remove any other format tags, keep non-format tags intact
                  const filtered = current.filter(t => !formatTags.includes(String(t).toUpperCase()) || String(t).toUpperCase() === fmt);
                  const hasFmt = filtered.some(t => String(t).toUpperCase() === fmt);
                  const updated = hasFmt ? filtered : [...filtered, fmt];
                  await updatePlaybookTags({ variables: { graphId, tags: updated } });
                  // Refresh local tags snapshot
                  await refetchGraphTags?.();
                } catch {}
              }}>
                <option value="KQL">KQL</option>
                <option value="Splunk">Splunk</option>
                <option value="Generic">Generic</option>
              </NativeSelect>
            </div>

            <div className="mb-4">
              <label className="block mb-1 text-sm font-medium">Detection Rule</label>
              <div className="border-2 border-hefaistos-border rounded-md">
                <SimpleMDE 
                  value={detectionRule} 
                  onChange={setDetectionRule}
                  getMdeInstance={configureMdeInstance}
                />
              </div>
            </div>
          </>

        ) : (
          /* --- READ-ONLY MODE --- */
          <>
            <TemplateSection title="Goal" hasData={Boolean(template.goal || template.v1_hypothesis)}>
              <p>{template.goal || template.v1_hypothesis}</p>
            </TemplateSection>
            <TemplateSection title="Priority" hasData={Boolean(template.priority)}>
              <p>{template.priority}</p>
            </TemplateSection>
            <TemplateSection title="Strategy Abstract" hasData={Boolean(template.strategyAbstract)}>
              <p>{template.strategyAbstract}</p>
            </TemplateSection>
            <TemplateSection title="Technical Context" hasData={Boolean(template.technicalContext)}>
              <MarkdownRenderer content={template.technicalContext} variant="small" />
            </TemplateSection>
            <TemplateSection title="False Positives" hasData={Boolean(template.falsePositives)}>
              <MarkdownRenderer content={template.falsePositives} variant="small" />
            </TemplateSection>
            <TemplateSection title="Response Steps (Triage)" hasData={Boolean(template.response)}>
              <MarkdownRenderer content={template.response} variant="small" />
            </TemplateSection>

            {/* Read-only complex fields */}
            <TemplateSection title="Node ATT&CK Mappings" hasData={Boolean(selectedNode.mitreAttackMappings && selectedNode.mitreAttackMappings.length > 0)}>
              <div className="flex flex-wrap gap-2">
                {selectedNode.mitreAttackMappings?.map((tech: any) => (
                  <span 
                    key={tech.id} 
                    className="inline-flex items-center px-2 py-1 rounded-md text-sm font-medium bg-blue-100 text-blue-800 border border-blue-200"
                    title={tech.name}
                  >
                    {tech.techniqueId}
                  </span>
                ))}
              </div>
            </TemplateSection>
            <TemplateSection title={`Detection Rule (${template.detectionRule?.format || 'KQL'})`} hasData={Boolean(template.detectionRule?.rule)}>
              <RuleBlock rule={template.detectionRule} />
            </TemplateSection>
            <TemplateSection title="Active Defense (MITRE Engage)" hasData={Boolean(template.acdElements && template.acdElements.length > 0)}>
              {/* ... (from Day 190) ... */}
            </TemplateSection>
          </>
        )}
      </div>
    </aside>
  );
}