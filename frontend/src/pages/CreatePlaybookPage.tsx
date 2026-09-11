import React, { useMemo, useState, useCallback, useRef } from 'react';
import { gql } from '@apollo/client';
import { useMutation } from '@apollo/client/react';
import { useNavigate } from 'react-router-dom';
import { Input, Select, Button, message, Row, Col, Collapse } from 'antd';
import { usePlaybookMeta } from '../context/PlaybookMetaContext';
import { PixelIcon } from '../components/ui/PixelIcon';
import { useLazyQuery } from '@apollo/client/react';
import SimpleMDEReact from 'react-simplemde-editor';

// Framework technique queries (ATT&CK, D3FEND, Engage, ICS, Mobile) are exposed via GraphQL and lazily loaded here.

// Robustness & Event Source Choices centralized in constants.ts

// --- GraphQL Mutation ---
const CREATE_PLAYBOOK_MUTATION = gql`
  mutation CreatePlaybook(
    $title: String!, $description: String, $playbookType: String,
    $analyticId: String, $version: String, $hypothesis: String,
    $triageGuidance: String, $knownFalsePositives: String, $exclusionStrategy: String,
    $falsePositiveRate: Int, $robustnessLevel: Int, $dataSourceRobustness: String,
    $testingProcedures: String, $soarEnrichment: String, $soarTriage: String, $soarContainment: String,
    $operationalPath: String, $functionCallGraphs: String, $executionModalities: String,
    $mitreAttackMappings: [ID], $mitreD3fendMappings: [ID], $mitreEngageMappings: [ID],
    $mitreIcsMappings: [ID], $mitreMobileMappings: [ID]
  ) {
    createPlaybook(
      title: $title, description: $description, playbookType: $playbookType,
      analyticId: $analyticId, version: $version, hypothesis: $hypothesis,
      triageGuidance: $triageGuidance, knownFalsePositives: $knownFalsePositives, exclusionStrategy: $exclusionStrategy,
      falsePositiveRate: $falsePositiveRate, robustnessLevel: $robustnessLevel, dataSourceRobustness: $dataSourceRobustness,
      testingProcedures: $testingProcedures, soarEnrichment: $soarEnrichment, soarTriage: $soarTriage, soarContainment: $soarContainment,
      operationalPath: $operationalPath, functionCallGraphs: $functionCallGraphs, executionModalities: $executionModalities,
      mitreAttackMappings: $mitreAttackMappings, mitreD3fendMappings: $mitreD3fendMappings, mitreEngageMappings: $mitreEngageMappings,
      mitreIcsMappings: $mitreIcsMappings, mitreMobileMappings: $mitreMobileMappings
    ) {
      playbook { id }
    }
  }
`;

// Query to refresh playbook list after creation
const GET_ALL_PLAYBOOKS_QUERY = gql`
  query GetAllPlaybooks {
    allPlaybooks {
      id
      title
      status
      playbookType
      updatedAt
      author {
        username
      }
    }
  }
`;

// --- Queries to populate mapping selectors ---
const GET_ALL_ATTACK_QUERY = gql`
  query GetAllAttack($search: String, $limit: Int, $offset: Int) {
    allAttackTechniques(search: $search, limit: $limit, offset: $offset) { id techniqueId name }
  }
`;
const GET_ALL_D3FEND_QUERY = gql`
  query GetAllD3fend($search: String, $limit: Int, $offset: Int) {
    allD3fendTechniques(search: $search, limit: $limit, offset: $offset) { id d3fendId name }
  }
`;
const GET_ALL_ENGAGE_QUERY = gql`
  query GetAllEngage($search: String, $limit: Int, $offset: Int) {
    allEngageTechniques(search: $search, limit: $limit, offset: $offset) { id engageId name }
  }
`;
const GET_ALL_ICS_QUERY = gql`
  query GetAllIcs($search: String, $limit: Int, $offset: Int) {
    allIcsTechniques(search: $search, limit: $limit, offset: $offset) { id techniqueId name }
  }
`;
const GET_ALL_MOBILE_QUERY = gql`
  query GetAllMobile($search: String, $limit: Int, $offset: Int) {
    allMobileTechniques(search: $search, limit: $limit, offset: $offset) { id techniqueId name }
  }
`;

interface CreatePlaybookData {
  createPlaybook: { playbook: { id: string } };
}
interface CreatePlaybookVars {
  title: string;
  description?: string;
  playbookType?: string;
  analyticId?: string;
  version?: string;
  hypothesis?: string | null;
  triageGuidance?: string | null;
  knownFalsePositives?: string | null;
  exclusionStrategy?: string | null;
  falsePositiveRate?: number | null;
  robustnessLevel?: number | null;
  dataSourceRobustness?: string | null;
  testingProcedures?: string | null;
  soarEnrichment?: string | null;
  soarTriage?: string | null;
  soarContainment?: string | null;
  operationalPath?: string | null;
  functionCallGraphs?: string | null;
  executionModalities?: string | null;
  mitreAttackMappings?: string[];
  mitreD3fendMappings?: string[];
  mitreEngageMappings?: string[];
  mitreIcsMappings?: string[];
  mitreMobileMappings?: string[];
}

export const CreatePlaybookPage = () => {
  const meta = usePlaybookMeta();
  const navigate = useNavigate();
  const [createPlaybook, { loading, error }] = useMutation<CreatePlaybookData, CreatePlaybookVars>(CREATE_PLAYBOOK_MUTATION);

  // --- State for ALL fields ---
  const [playbookType, setPlaybookType] = useState('DETECTION');
  // Uncontrolled one-line inputs to prevent focus loss while typing
  const titleRef = useRef<string>('');
  // Use uncontrolled refs for long text fields to avoid rerender-induced focus loss
  const descriptionRef = useRef<string>('');
  const analyticIdRef = useRef<string>('');
  const versionRef = useRef<string>('1.0');
  const hypothesisRef = useRef<string>('');
  const triageGuidanceRef = useRef<string>('');
  const knownFalsePositivesRef = useRef<string>('');
  const exclusionStrategyRef = useRef<string>('');
  const falsePositiveRateRef = useRef<string>('');
  // Rich text editor state mirrors refs to preserve submit logic
  const [description, setDescription] = useState<string>(descriptionRef.current);
  const [knownFalsePositives, setKnownFalsePositives] = useState<string>(knownFalsePositivesRef.current);
  const [exclusionStrategy, setExclusionStrategy] = useState<string>(exclusionStrategyRef.current);
  const [triageGuidance, setTriageGuidance] = useState<string>(triageGuidanceRef.current);
  const [testingProcedures, setTestingProcedures] = useState<string>('');
  const [soarEnrichment, setSoarEnrichment] = useState<string>('');
  const [soarTriage, setSoarTriage] = useState<string>('');
  const [soarContainment, setSoarContainment] = useState<string>('');

  // Shared SimpleMDE options: add preview, side-by-side, fullscreen
  const simpleMdeOptions = useMemo(() => ({
    spellChecker: false,
    status: false,
    toolbar: [
      'bold','italic','heading','|',
      'quote','unordered-list','ordered-list','table','code','link','image','horizontal-rule','|',
      'preview','side-by-side','fullscreen','guide'
    ] as const,
  } as const), []);

  // Memoized options for each field to prevent recreating on each render
  const descriptionOptions = useMemo(() => ({ ...simpleMdeOptions, placeholder: 'Short summary of purpose' }), [simpleMdeOptions]);
  const hypothesisOptions = useMemo(() => ({ ...simpleMdeOptions, placeholder: 'The testable question this hunt will answer' }), [simpleMdeOptions]);
  const knownFalsePositivesOptions = useMemo(() => ({ ...simpleMdeOptions, placeholder: 'Known benign triggers' }), [simpleMdeOptions]);
  const exclusionStrategyOptions = useMemo(() => ({ ...simpleMdeOptions, placeholder: 'Surgically precise exclusions' }), [simpleMdeOptions]);
  const triageGuidanceOptions = useMemo(() => ({ ...simpleMdeOptions, placeholder: 'Step-by-step triage advice' }), [simpleMdeOptions]);
  const testingProceduresOptions = useMemo(() => ({ ...simpleMdeOptions, placeholder: 'Test cases & synonym tools' }), [simpleMdeOptions]);
  const soarEnrichmentOptions = useMemo(() => ({ ...simpleMdeOptions, placeholder: 'List enrichment steps' }), [simpleMdeOptions]);
  const soarTriageOptions = useMemo(() => ({ ...simpleMdeOptions, placeholder: 'Describe automated triage logic' }), [simpleMdeOptions]);
  const soarContainmentOptions = useMemo(() => ({ ...simpleMdeOptions, placeholder: 'Containment and response steps' }), [simpleMdeOptions]);
  const [robustnessLevel, setRobustnessLevel] = useState<number | null>(null);
  const [dataSourceRobustness, setDataSourceRobustness] = useState<string | null>(null);
  const testingProceduresRef = useRef<string>('');
  const soarEnrichmentRef = useRef<string>('');
  const soarTriageRef = useRef<string>('');
  const soarContainmentRef = useRef<string>('');
  // Capability Abstraction
  const operationalPathRef = useRef<string>('');
  const functionCallGraphsRef = useRef<string>('');
  const executionModalitiesRef = useRef<string>('');

  // --- Mapping state (IDs) ---
  const [attackIds, setAttackIds] = useState<string[]>([]);
  const [d3fendIds, setD3fendIds] = useState<string[]>([]);
  const [engageIds, setEngageIds] = useState<string[]>([]);
  const [icsIds, setIcsIds] = useState<string[]>([]);
  const [mobileIds, setMobileIds] = useState<string[]>([]);

  // --- Load lists ---
  type AttackQuery = { allAttackTechniques: Array<{ id: string; techniqueId: string; name: string }> };
  type D3fendQuery = { allD3fendTechniques: Array<{ id: string; d3fendId: string; name: string }> };
  type EngageQuery = { allEngageTechniques: Array<{ id: string; engageId: string; name: string }> };
  type IcsQuery = { allIcsTechniques: Array<{ id: string; techniqueId: string; name: string }> };
  type MobileQuery = { allMobileTechniques: Array<{ id: string; techniqueId: string; name: string }> };

  const defaultListVars = useMemo(() => ({ search: undefined, limit: 50, offset: 0 } as const), []);
  // Lazy queries – only fire when mappings panel first opens or when searching.
  const [loadAttack, { data: attackData, loading: attackLoading, refetch: refetchAttack }] = useLazyQuery<AttackQuery>(GET_ALL_ATTACK_QUERY, { fetchPolicy: 'network-only' });
  const [loadD3fend, { data: d3fendData, loading: d3fendLoading, refetch: refetchD3fend }] = useLazyQuery<D3fendQuery>(GET_ALL_D3FEND_QUERY, { fetchPolicy: 'network-only' });
  const [loadEngage, { data: engageData, loading: engageLoading, refetch: refetchEngage }] = useLazyQuery<EngageQuery>(GET_ALL_ENGAGE_QUERY, { fetchPolicy: 'network-only' });
  const [loadIcs, { data: icsData, loading: icsLoading, refetch: refetchIcs }] = useLazyQuery<IcsQuery>(GET_ALL_ICS_QUERY, { fetchPolicy: 'network-only' });
  const [loadMobile, { data: mobileData, loading: mobileLoading, refetch: refetchMobile }] = useLazyQuery<MobileQuery>(GET_ALL_MOBILE_QUERY, { fetchPolicy: 'network-only' });

  const [mappingPanelLoaded, setMappingPanelLoaded] = useState(false);

  const ensureMappingsLoaded = useCallback(() => {
    if (mappingPanelLoaded) return;
    setMappingPanelLoaded(true);
    // Kick off parallel loads with default vars.
    loadAttack({ variables: defaultListVars });
    loadD3fend({ variables: defaultListVars });
    loadEngage({ variables: defaultListVars });
    loadIcs({ variables: defaultListVars });
    loadMobile({ variables: defaultListVars });
  }, [mappingPanelLoaded, loadAttack, loadD3fend, loadEngage, loadIcs, loadMobile, defaultListVars]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const { data } = await createPlaybook({
        variables: {
          title: titleRef.current,
          description: descriptionRef.current || undefined,
          playbookType,
          analyticId: analyticIdRef.current || undefined,
            version: versionRef.current || undefined,
          hypothesis: playbookType === 'HUNT' ? hypothesisRef.current : null,
          triageGuidance: playbookType === 'DETECTION' ? triageGuidanceRef.current : null,
          knownFalsePositives: playbookType === 'DETECTION' ? knownFalsePositivesRef.current : null,
          exclusionStrategy: playbookType === 'DETECTION' ? exclusionStrategyRef.current : null,
          falsePositiveRate: playbookType === 'DETECTION' && falsePositiveRateRef.current !== '' ? parseInt(falsePositiveRateRef.current, 10) : null,
          robustnessLevel,
          dataSourceRobustness,
          testingProcedures: playbookType === 'DETECTION' ? testingProceduresRef.current : null,
          soarEnrichment: playbookType === 'DETECTION' ? soarEnrichmentRef.current : null,
          soarTriage: playbookType === 'DETECTION' ? soarTriageRef.current : null,
          soarContainment: playbookType === 'DETECTION' ? soarContainmentRef.current : null,
          operationalPath: operationalPathRef.current || null,
          functionCallGraphs: functionCallGraphsRef.current || null,
          executionModalities: executionModalitiesRef.current || null,
          mitreAttackMappings: attackIds,
          mitreD3fendMappings: d3fendIds,
          mitreEngageMappings: engageIds,
          mitreIcsMappings: icsIds,
          mitreMobileMappings: mobileIds,
        },
        refetchQueries: [{ query: GET_ALL_PLAYBOOKS_QUERY }],
        awaitRefetchQueries: true,
      });
      const newId = data?.createPlaybook.playbook.id;
      message.success('Playbook created');
      if (newId) navigate(`/playbooks/${newId}`);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('Failed to create playbook', err);
      message.error('Failed to create playbook');
    }
  };

  const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
    <fieldset style={{ border: '2px solid var(--hefaistos-border)', borderRadius: 8, padding: 16, marginTop: 24 }}>
      <legend style={{ padding: '0 8px', fontWeight: 600 }}>{title}</legend>
      <div className="space-y-4">{children}</div>
    </fieldset>
  );

  return (
    <div className="max-w-4xl p-6 mx-auto bg-white border-2 border-hefaistos-border rounded-lg shadow-md">
      <h2 className="text-2xl font-bold mb-6 border-b-2 border-hefaistos-border pb-4">Create New Playbook</h2>
      <form onSubmit={handleSubmit}>
        {/* Section 1: Metadata */}
        <Section title="Section 1: Metadata">
          <div>
            <label className="block mb-1 text-sm font-medium">Playbook Title</label>
            <Input defaultValue={titleRef.current} onChange={(e) => { titleRef.current = e.target.value; }} required placeholder="e.g., Suspicious LSASS Access" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block mb-1 text-sm font-medium">Analytic ID</label>
              <Input defaultValue={analyticIdRef.current} onChange={(e) => { analyticIdRef.current = e.target.value; }} placeholder="DE-2025-001" />
            </div>
            <div>
              <label className="block mb-1 text-sm font-medium">Version</label>
              <Input defaultValue={versionRef.current} onChange={(e) => { versionRef.current = e.target.value; }} />
            </div>
          </div>
        </Section>

    {/* Section 2: Detection Overview */}
    <Section title="Section 2: Detection Overview">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block mb-1 text-sm font-medium">Type</label>
              <Select
                value={playbookType}
                onChange={(value) => setPlaybookType(value)}
                options={(meta.data?.playbookTypes || []).map(o => ({ label: o.label, value: o.value }))}
                loading={meta.loading}
                style={{ width: '100%' }}
              />
            </div>
          </div>
          <div className="mt-4">
            <label className="block mb-1 text-sm font-medium">Description</label>
            <SimpleMDEReact
              value={description}
              onChange={(val) => { setDescription(val); descriptionRef.current = val; }}
              options={descriptionOptions}
            />
          </div>
          {playbookType === 'HUNT' && (
            <div>
              <label className="block mb-1 text-sm font-medium">Hypothesis</label>
              <textarea
                defaultValue={hypothesisRef.current}
                onChange={(e) => { hypothesisRef.current = e.target.value; }}
                rows={5}
                placeholder="The testable question this hunt will answer"
                style={{ width: '100%', padding: 8, border: '1px solid #d9d9d9', borderRadius: 6 }}
                autoComplete="off"
                autoCorrect="off"
                spellCheck={false}
              />
            </div>
          )}
        </Section>

        {/* Sections 3 & 4: Analytic & Logic Details (Detection Only) */}
        {playbookType === 'DETECTION' && (
          <Section title="Sections 3 & 4: Analytic & Logic Details">
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block mb-1 text-sm font-medium">Robustness Level</label>
                <Select
                  value={robustnessLevel ?? undefined}
                  onChange={(value) => setRobustnessLevel(value as number)}
                  options={(meta.data?.robustnessLevels || []).map(o => ({ label: o.label, value: o.value }))}
                  loading={meta.loading}
                  allowClear
                  placeholder="Select level"
                  style={{ width: '100%' }}
                />
              </div>
              <div>
                <label className="block mb-1 text-sm font-medium">Data Robustness</label>
                <Select
                  value={dataSourceRobustness ?? undefined}
                  onChange={(value) => setDataSourceRobustness(value as string)}
                  options={(meta.data?.eventRobustness || []).map(o => ({ label: o.label, value: o.value }))}
                  loading={meta.loading}
                  allowClear
                  placeholder="Event source"
                  style={{ width: '100%' }}
                />
              </div>
              <div>
                <label className="block mb-1 text-sm font-medium">False Positive Rate (%)</label>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  defaultValue={falsePositiveRateRef.current}
                  onChange={(e) => { falsePositiveRateRef.current = e.target.value; }}
                  placeholder="0-100"
                />
              </div>
            </div>
            <div>
              <label className="block mb-1 text-sm font-medium">Known False Positives</label>
              <SimpleMDEReact
                value={knownFalsePositives}
                onChange={(val) => { setKnownFalsePositives(val); knownFalsePositivesRef.current = val; }}
                options={{ placeholder: 'Known benign triggers' }}
              />
            </div>
            <div>
              <label className="block mb-1 text-sm font-medium">Exclusion Strategy</label>
              <SimpleMDEReact
                value={exclusionStrategy}
                onChange={(val) => { setExclusionStrategy(val); exclusionStrategyRef.current = val; }}
                options={exclusionStrategyOptions}
              />
            </div>
          </Section>
        )}

        {playbookType === 'DETECTION' && (
          <Section title="Section 5: Validation & Response">
            <div>
              <label className="block mb-1 text-sm font-medium">Triage Guidance</label>
              <SimpleMDEReact
                value={triageGuidance}
                onChange={(val) => { setTriageGuidance(val); triageGuidanceRef.current = val; }}
                options={triageGuidanceOptions}
              />
            </div>
            <div>
              <label className="block mb-1 text-sm font-medium">Testing Procedures</label>
              <SimpleMDEReact
                value={testingProcedures}
                onChange={(val) => { setTestingProcedures(val); testingProceduresRef.current = val; }}
                options={testingProceduresOptions}
              />
            </div>
          </Section>
        )}

        {playbookType === 'DETECTION' && (
          <Section title="Section 6: SOAR Automation">
            <div>
              <label className="block mb-1 text-sm font-medium">Enrichment Steps</label>
              <SimpleMDEReact
                value={soarEnrichment}
                onChange={(val) => { setSoarEnrichment(val); soarEnrichmentRef.current = val; }}
                options={soarEnrichmentOptions}
              />
            </div>
            <div>
              <label className="block mb-1 text-sm font-medium">Triage Logic (Automated)</label>
              <SimpleMDEReact
                value={soarTriage}
                onChange={(val) => { setSoarTriage(val); soarTriageRef.current = val; }}
                options={soarTriageOptions}
              />
            </div>
            <div>
              <label className="block mb-1 text-sm font-medium">Containment Steps</label>
              <SimpleMDEReact
                value={soarContainment}
                onChange={(val) => { setSoarContainment(val); soarContainmentRef.current = val; }}
                options={soarContainmentOptions}
              />
            </div>
          </Section>
        )}

        <Section title="Capability Abstraction">
          <div>
            <label className="block mb-1 text-sm font-medium">Operational Path</label>
            <textarea
              defaultValue={operationalPathRef.current}
              onChange={(e) => { operationalPathRef.current = e.target.value; }}
              rows={3}
              placeholder="High-level phases / steps"
              style={{ width: '100%', padding: 8, border: '1px solid #d9d9d9', borderRadius: 6 }}
            />
          </div>
          <div>
            <label className="block mb-1 text-sm font-medium">Function Call Graphs</label>
            <textarea
              defaultValue={functionCallGraphsRef.current}
              onChange={(e) => { functionCallGraphsRef.current = e.target.value; }}
              rows={3}
              placeholder="APIs / function graph abstractions"
              style={{ width: '100%', padding: 8, border: '1px solid #d9d9d9', borderRadius: 6 }}
            />
          </div>
          <div>
            <label className="block mb-1 text-sm font-medium">Execution Modalities</label>
            <textarea
              defaultValue={executionModalitiesRef.current}
              onChange={(e) => { executionModalitiesRef.current = e.target.value; }}
              rows={3}
              placeholder="Behavioral variants / execution modes"
              style={{ width: '100%', padding: 8, border: '1px solid #d9d9d9', borderRadius: 6 }}
            />
          </div>
        </Section>

        <Section title="Section 7: Framework Mappings">
          <Collapse
            destroyInactivePanel
            onChange={(keys) => {
              if (Array.isArray(keys) ? keys.includes('fw-create') : keys === 'fw-create') {
                ensureMappingsLoaded();
              }
            }}
            items={[{
              key: 'fw-create',
              label: mappingPanelLoaded ? 'Hide Mapping Selectors' : 'Show Mapping Selectors',
              children: (
                <Row gutter={[16,16]}>
                  <Col xs={24} md={12}>
                    <label className="block mb-1 text-sm font-medium">MITRE ATT&CK</label>
                    <Select
                      mode="multiple"
                      value={attackIds}
                      onChange={setAttackIds}
                      options={(attackData?.allAttackTechniques || []).map((t: any) => ({ value: t.id, label: `${t.techniqueId}: ${t.name}` }))}
                      placeholder="Select ATT&CK techniques"
                      style={{ width: '100%' }}
                      showSearch
                      filterOption={false}
                      onSearch={(val) => refetchAttack && refetchAttack({ search: val || undefined, limit: 50, offset: 0 })}
                      loading={attackLoading}
                      optionFilterProp="label"
                      allowClear
                      disabled={!mappingPanelLoaded}
                    />
                  </Col>
                  <Col xs={24} md={12}>
                    <label className="block mb-1 text-sm font-medium">MITRE D3FEND</label>
                    <Select
                      mode="multiple"
                      value={d3fendIds}
                      onChange={setD3fendIds}
                      options={(d3fendData?.allD3fendTechniques || []).map((t: any) => ({ value: t.id, label: `${t.d3fendId}: ${t.name}` }))}
                      placeholder="Select D3FEND techniques"
                      style={{ width: '100%' }}
                      showSearch
                      filterOption={false}
                      onSearch={(val) => refetchD3fend && refetchD3fend({ search: val || undefined, limit: 50, offset: 0 })}
                      loading={d3fendLoading}
                      optionFilterProp="label"
                      allowClear
                      disabled={!mappingPanelLoaded}
                    />
                  </Col>
                  <Col xs={24} md={12}>
                    <label className="block mb-1 text-sm font-medium">MITRE Engage</label>
                    <Select
                      mode="multiple"
                      value={engageIds}
                      onChange={setEngageIds}
                      options={(engageData?.allEngageTechniques || []).map((t: any) => ({ value: t.id, label: `${t.engageId}: ${t.name}` }))}
                      placeholder="Select Engage techniques"
                      style={{ width: '100%' }}
                      showSearch
                      filterOption={false}
                      onSearch={(val) => refetchEngage && refetchEngage({ search: val || undefined, limit: 50, offset: 0 })}
                      loading={engageLoading}
                      optionFilterProp="label"
                      allowClear
                      disabled={!mappingPanelLoaded}
                    />
                  </Col>
                  <Col xs={24} md={12}>
                    <label className="block mb-1 text-sm font-medium">MITRE ICS</label>
                    <Select
                      mode="multiple"
                      value={icsIds}
                      onChange={setIcsIds}
                      options={(icsData?.allIcsTechniques || []).map((t: any) => ({ value: t.id, label: `${t.techniqueId}: ${t.name}` }))}
                      placeholder="Select ICS techniques"
                      style={{ width: '100%' }}
                      showSearch
                      filterOption={false}
                      onSearch={(val) => refetchIcs && refetchIcs({ search: val || undefined, limit: 50, offset: 0 })}
                      loading={icsLoading}
                      optionFilterProp="label"
                      allowClear
                      disabled={!mappingPanelLoaded}
                    />
                  </Col>
                  <Col xs={24} md={12}>
                    <label className="block mb-1 text-sm font-medium">MITRE Mobile</label>
                    <Select
                      mode="multiple"
                      value={mobileIds}
                      onChange={setMobileIds}
                      options={(mobileData?.allMobileTechniques || []).map((t: any) => ({ value: t.id, label: `${t.techniqueId}: ${t.name}` }))}
                      placeholder="Select Mobile techniques"
                      style={{ width: '100%' }}
                      showSearch
                      filterOption={false}
                      onSearch={(val) => refetchMobile && refetchMobile({ search: val || undefined, limit: 50, offset: 0 })}
                      loading={mobileLoading}
                      optionFilterProp="label"
                      allowClear
                      disabled={!mappingPanelLoaded}
                    />
                  </Col>
                </Row>
              )
            }]}
          />
        </Section>

        <div className="pt-6">
          <Button htmlType="submit" type="primary" disabled={loading} icon={<PixelIcon name="add" />}> {loading ? 'Creating...' : 'Create Playbook'} </Button>
        </div>
        {error && <p className="mt-4 text-sm" style={{ color: 'var(--hefaistos-accent-red)' }}>Error: {error.message}</p>}
      </form>
    </div>
  );
};
