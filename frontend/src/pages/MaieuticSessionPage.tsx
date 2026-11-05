import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { gql, useLazyQuery, useMutation, useQuery } from '@apollo/client';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Alert, Button, Card, Checkbox, Input, InputNumber, Popconfirm, Radio, Select, Space, Spin, Steps, Tag, Typography,
} from 'antd';
import { ArrowLeftOutlined, ArrowRightOutlined, LockOutlined } from '@ant-design/icons';
import { Field, RecordList, StringList, newId } from '../components/maieutic/MaieuticFormParts';
import { MaieuticAdeStage, PLAN_QUERY } from '../components/maieutic/MaieuticAdeStage';

const { Title, Text, Paragraph } = Typography;

const STAGES = [
  { title: 'Hypothesis', help: 'What behaviour do you want to catch, and why?' },
  { title: 'Telemetry', help: 'What evidence would that behaviour leave?' },
  { title: 'Design', help: 'Describe in words what the detection will look for.' },
  { title: 'Evasion', help: 'Where could an attacker slip past the design?' },
  { title: 'Response', help: 'What should happen when it fires, and how is it tested?' },
  { title: 'Review', help: 'See what you captured and choose the output formats.' },
];

const DRAFT_QUERY = gql`
  query MaieuticSession($id: UUID!) {
    maieuticDraft(id: $id) {
      id name status currentStage spec isLocked tlpClassification updatedAt
    }
  }
`;
const UPDATE_MUTATION = gql`
  mutation UpdateMaieuticDraft($id: UUID!, $name: String, $stage: Int, $patch: GenericScalar, $level: String) {
    updateMaieuticDraft(draftId: $id, name: $name, currentStage: $stage, specPatch: $patch, challengeLevel: $level) {
      draft { id name currentStage updatedAt spec }
    }
  }
`;
const TECHNIQUE_QUERY = gql`
  query MaieuticTechniques($search: String) {
    allAttackTechniques(search: $search, limit: 30) { techniqueId name }
  }
`;
const SOURCES_QUERY = gql`
  query MaieuticSources {
    allLogSources { id name coverageStatus siemProduct }
    allDataSources { id name platform }
  }
`;

const CREATE_WORKBENCH = gql`
  mutation CreateWorkbenchFromMaieuticDraft($id: UUID!, $exit: String!) {
    createWorkbenchFromMaieuticDraft(draftId: $id, exit: $exit) { workbenchId queuedFormats }
  }
`;

const FIELDS_QUERY = gql`
  query MaieuticLogFields($ids: [UUID]!) {
    maieuticLogSourceFields(logSourceIds: $ids) { logSourceId standardName siemFieldName }
  }
`;

const ANCHORS = [
  ['FILE_OR_PROCESS_NAME', 'A file or process name'], ['COMMAND_LINE_TEXT', 'Text in a command line'],
  ['REGISTRY', 'A registry key or value'], ['API_OR_SYSCALL', 'An API or system call'],
  ['NETWORK', 'Network activity'], ['IDENTITY', 'An account or identity'], ['OTHER', 'Something else'],
].map(([value, label]) => ({ value, label }));
const CHANGEABLE = [
  ['FREELY', 'Yes, trivially'], ['WITH_EFFORT', 'Yes, with some effort'], ['NO', 'No'], ['UNKNOWN', 'I do not know'],
].map(([value, label]) => ({ value, label }));
const CONTROLLED = [
  ['YES', 'Yes'], ['PARTIAL', 'Partly'], ['NO', 'No'], ['UNKNOWN', 'I do not know'],
].map(([value, label]) => ({ value, label }));
const SEVERITIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((v) => ({ value: v, label: v }));
const FORMATS = [
  { value: 'KQL', label: 'KQL (Microsoft Defender / Sentinel)', locked: true },
  { value: 'SPL', label: 'SPL (Splunk)' },
  { value: 'EQL', label: 'EQL (Elastic)' },
  { value: 'WAZUH', label: 'Wazuh rule' },
  { value: 'AQL', label: 'AQL (QRadar query, not a QRadar rule)' },
];
const LEVELS = [
  { value: 'LIGHT', label: 'Light: only the points your design clearly raises' },
  { value: 'STANDARD', label: 'Standard: recommended' },
  { value: 'EXPERT', label: 'Expert: every evasion topic' },
];

type Section = 'hypothesis' | 'interrogation' | 'design' | 'playbook_tests' | 'review';
const arr = (v: any): any[] => (Array.isArray(v) ? v : []);
const str = (v: any): string => (typeof v === 'string' ? v : '');

export const MaieuticSessionPage: React.FC = () => {
  const { draftId = '' } = useParams();
  const navigate = useNavigate();
  const { data, loading, error } = useQuery(DRAFT_QUERY, { variables: { id: draftId }, fetchPolicy: 'network-only' });
  const [updateDraft] = useMutation(UPDATE_MUTATION);
  const [createWorkbench, { loading: creating }] = useMutation(CREATE_WORKBENCH);
  const [createError, setCreateError] = useState('');
  const [searchTech, { data: techData, loading: techLoading }] = useLazyQuery(TECHNIQUE_QUERY);
  const { data: srcData } = useQuery(SOURCES_QUERY);
  const [loadFields, { data: fieldData }] = useLazyQuery(FIELDS_QUERY, { fetchPolicy: 'network-only' });
  const [loadPlan, { data: planData }] = useLazyQuery(PLAN_QUERY, { fetchPolicy: 'network-only' });

  const [spec, setSpec] = useState<any>(null);
  const [name, setName] = useState('');
  const [stage, setStage] = useState(1);
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [saveError, setSaveError] = useState('');
  const dirty = useRef<Record<string, any>>({});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const nameDirty = useRef(false);
  const specRef = useRef<any>(null);

  const draft = data?.maieuticDraft;
  const locked = Boolean(draft?.isLocked);

  useEffect(() => {
    if (draft && spec === null) {
      setSpec(draft.spec || {});
      specRef.current = draft.spec || {};
      setName(draft.name);
      setStage(Math.min(6, Math.max(1, draft.currentStage || 1)));
    }
  }, [draft]); // eslint-disable-line react-hooks/exhaustive-deps

  const flush = useCallback(async () => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    const patch = dirty.current;
    const hasName = nameDirty.current;
    if (!Object.keys(patch).length && !hasName) return;
    dirty.current = {};
    nameDirty.current = false;
    setSaveState('saving');
    try {
      await updateDraft({
        variables: { id: draftId, patch: Object.keys(patch).length ? patch : null, name: hasName ? name : null },
      });
      setSaveState('saved');
      setSaveError('');
    } catch (err: any) {
      dirty.current = { ...patch, ...dirty.current };
      if (hasName) nameDirty.current = true;
      setSaveState('error');
      setSaveError(err?.message ?? 'Could not save');
    }
  }, [draftId, name, updateDraft]);

  const queueSave = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(flush, 700);
  }, [flush]);

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (Object.keys(dirty.current).length || nameDirty.current) { e.preventDefault(); e.returnValue = ''; }
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, []);

  const section = (key: Section): any => (spec || {})[key] || {};
  const setSection = (key: Section, change: Record<string, any>) => {
    const next = { ...section(key), ...change };
    const merged = { ...(specRef.current || {}), [key]: next };
    specRef.current = merged;
    setSpec(merged);
    dirty.current[key] = next;
    queueSave();
  };

  const create = async (exitMode: 'CREATE_AND_GENERATE' | 'CREATE_WITHOUT_RULE') => {
    setCreateError('');
    try {
      await flush();
      const res = await createWorkbench({ variables: { id: draftId, exit: exitMode } });
      const id = res.data?.createWorkbenchFromMaieuticDraft?.workbenchId;
      if (id) navigate(`/playbooks/${id}`);
    } catch (err: any) {
      setCreateError(err?.message ?? 'Could not create the Workbench');
    }
  };

  const goTo = async (n: number) => {
    await flush();
    setStage(n);
    try { await updateDraft({ variables: { id: draftId, stage: n } }); } catch { /* resume point only */ }
  };

  const hyp = section('hypothesis');
  const inter = section('interrogation');
  const design = section('design');
  const play = section('playbook_tests');
  const review = section('review');
  const level = (spec?.meta?.challenge_level as string) || 'STANDARD';

  const technique = hyp.technique || {};
  const techniqueState: string = technique.state || '';
  const missing: string[] = [];
  if (!str(hyp.title).trim()) missing.push('a title');
  if (techniqueState !== 'SET' && techniqueState !== 'NONE_CHOSEN') missing.push('a technique or the choice of none');
  if (!str(hyp.goal).trim()) missing.push('a goal');

  const refLabel = useCallback((ref: string): string => {
    const [kind, id] = ref.split(':');
    const d = (specRef.current || {}).design || {};
    if (kind === 'match_element') {
      const m = arr(d.match_elements).find((e: any) => e.id === id);
      return `Match: ${m ? str(m.description).slice(0, 60) || id : id}`;
    }
    if (kind === 'exclusion') {
      const x = arr(d.exclusions)[Number(id)] ?? arr(d.exclusions).find((e: any) => e.id === id);
      return `Exclusion: ${x ? str(x.what).slice(0, 60) || id : id}`;
    }
    if (kind === 'correlation') return `Correlation ${Number(id) + 1}`;
    if (kind === 'field') return `Field ${id}`;
    if (kind === 'log_source') return `Log source ${id}`;
    return ref;
  }, []);

  const changeLevel = async (value: string) => {
    const meta = { ...(spec?.meta || {}), challenge_level: value };
    const merged = { ...(specRef.current || {}), meta };
    specRef.current = merged;
    setSpec(merged);
    try { await updateDraft({ variables: { id: draftId, level: value } }); } catch (err: any) { setSaveError(err?.message ?? ''); setSaveState('error'); }
  };

  useEffect(() => {
    if (stage === 6 && draftId) flush().then(() => loadPlan({ variables: { id: draftId } }));
  }, [stage]); // eslint-disable-line react-hooks/exhaustive-deps

  const pickedLogIds = arr(spec?.interrogation?.log_sources)
    .filter((s: any) => s.kind === 'LOG_SOURCE').map((s: any) => s.ref_id).join(',');
  useEffect(() => {
    if (pickedLogIds) loadFields({ variables: { ids: pickedLogIds.split(',') } });
  }, [pickedLogIds]); // eslint-disable-line react-hooks/exhaustive-deps

  const sources = useMemo(() => ({
    logs: arr(srcData?.allLogSources), datas: arr(srcData?.allDataSources),
  }), [srcData]);

  if (loading || (draft && spec === null)) return <div style={{ padding: 48, textAlign: 'center' }}><Spin /></div>;
  if (error || !draft) {
    return (
      <div style={{ padding: 24 }}>
        <Alert type="error" showIcon message={error?.message || 'This session does not exist or is not yours.'} />
        <Link to="/playbooks?tab=maieutics">Back to Maieutics</Link>
      </div>
    );
  }
  if (locked) {
    return (
      <div style={{ padding: 24 }}>
        <Alert type="success" showIcon icon={<LockOutlined />} message="This session is finished and locked."
          description="Open it read-only from the Maieutics tab. Edit the Workbench created from it instead." />
        <Link to="/playbooks?tab=maieutics">Back to Maieutics</Link>
      </div>
    );
  }

  const pickedSources = arr(inter.log_sources);
  const addSource = (value: string) => {
    const [kind, id] = value.split('|');
    if (pickedSources.some((s: any) => s.ref_id === id)) return;
    const entry = kind === 'LOG_SOURCE'
      ? sources.logs.find((s: any) => s.id === id)
      : sources.datas.find((s: any) => String(s.id) === id);
    if (!entry) return;
    setSection('interrogation', {
      log_sources: [...pickedSources, {
        kind, ref_id: id, name: entry.name, coverage_status_at_pick: kind === 'LOG_SOURCE' ? entry.coverageStatus || null : null,
      }],
    });
  };
  const sourceOptions = [
    { label: 'Log Sources (recommended first)', options: sources.logs.map((s: any) => ({ value: `LOG_SOURCE|${s.id}`, label: s.name })) },
    { label: 'Data Catalog', options: sources.datas.map((s: any) => ({ value: `DATA_SOURCE|${s.id}`, label: `${s.name}${s.platform ? ` (${s.platform})` : ''}` })) },
  ];
  const fieldSuggestions = arr(fieldData?.maieuticLogSourceFields);
  const wt = design.windows_thresholds || {};
  const setWt = (c: Record<string, any>) => setSection('design', { windows_thresholds: { ...wt, ...c } });

  const formats: string[] = ['KQL', ...arr(review.output_formats).filter((f: string) => f !== 'KQL')];
  const plan = planData?.maieuticAdePlan;
  const answeredAde = plan ? plan.items.filter((i: any) => i.state === 'ANSWERED').length : null;
  const unknownAde = plan ? plan.items.filter((i: any) => i.ledgerEntry?.disposition === 'UNKNOWN').length : 0;
  const limitations = plan ? plan.items.filter((i: any) => i.ledgerEntry?.disposition === 'ACCEPTED_LIMITATION').length : 0;

  const saveLabel = saveState === 'saving' ? 'Saving…' : saveState === 'saved' ? 'All changes saved'
    : saveState === 'error' ? `Not saved: ${saveError}` : '';

  const body = (() => {
    switch (stage) {
      case 1: return (
        <>
          <Field label="Working title" required help="A short name for this detection idea.">
            <Input value={str(hyp.title)} maxLength={200} style={{ maxWidth: 560 }}
              onChange={(e) => setSection('hypothesis', { title: e.target.value })} />
          </Field>
          <Field label="ATT&CK technique" required help="Pick one, or say that you have none yet. Both are fine.">
            <Space direction="vertical">
              <Checkbox checked={techniqueState === 'NONE_CHOSEN'}
                onChange={(e) => setSection('hypothesis', { technique: e.target.checked ? { state: 'NONE_CHOSEN' } : {} })}>
                I have not chosen a technique
              </Checkbox>
              {techniqueState !== 'NONE_CHOSEN' && (
                <Select showSearch style={{ width: 560 }} filterOption={false} loading={techLoading}
                  placeholder="Search by ID or name, for example T1003.001"
                  value={techniqueState === 'SET' ? technique.id : undefined}
                  onSearch={(q) => searchTech({ variables: { search: q } })}
                  onFocus={() => searchTech({ variables: { search: '' } })}
                  options={arr(techData?.allAttackTechniques).map((t: any) => ({ value: t.techniqueId, label: `${t.techniqueId}  ${t.name}` }))}
                  notFoundContent={techLoading ? <Spin size="small" /> : 'No match'}
                  onChange={(id, opt: any) => setSection('hypothesis', {
                    technique: { state: 'SET', id, name: String(opt?.label || '').replace(`${id}  `, '') },
                  })} />
              )}
              {techniqueState === 'SET' && <Text type="secondary">Selected: {technique.id} {technique.name}</Text>}
            </Space>
          </Field>
          <Field label="Goal" required help="What do you want to be able to say when this detection fires?">
            <Input.TextArea rows={3} style={{ maxWidth: 700 }} value={str(hyp.goal)}
              onChange={(e) => setSection('hypothesis', { goal: e.target.value })} />
          </Field>
          <Field label="Ways an attacker could do this" help="Recommended. One entry per way you can think of. The evasion questions later build on this list.">
            <StringList value={arr(hyp.attacker_methods)} addLabel="Add a way" rows={2}
              onChange={(v) => setSection('hypothesis', { attacker_methods: v })} />
          </Field>
          <Field label="Notes on scope" help="Optional. What is deliberately out of scope?">
            <Input.TextArea rows={2} style={{ maxWidth: 700 }} value={str(hyp.scope_notes)}
              onChange={(e) => setSection('hypothesis', { scope_notes: e.target.value })} />
          </Field>
          <Field label="How demanding should the evasion questions be?" help="You can change this at any time.">
            <Radio.Group value={level} onChange={(e) => changeLevel(e.target.value)}>
              <Space direction="vertical">
                {LEVELS.map((l) => <Radio key={l.value} value={l.value}>{l.label}</Radio>)}
              </Space>
            </Radio.Group>
          </Field>
        </>
      );
      case 2: return (
        <>
          <Field label="Where would the evidence be logged?" help="Log Sources first, then the Data Catalog. Skipping this is allowed.">
            <Select showSearch style={{ width: 560 }} placeholder="Add a log source or data source" value={null as any}
              options={sourceOptions} optionFilterProp="label" onChange={addSource} />
            <div style={{ marginTop: 8 }}>
              <Space wrap>
                {pickedSources.map((s: any) => (
                  <Tag key={s.ref_id} closable
                    onClose={() => setSection('interrogation', { log_sources: pickedSources.filter((x: any) => x.ref_id !== s.ref_id) })}>
                    {s.name}{s.coverage_status_at_pick ? ` · ${s.coverage_status_at_pick}` : ''}
                  </Tag>
                ))}
              </Space>
            </div>
          </Field>
          <Field label="Fields you would rely on" help="For each field: could an attacker control or change the value?">
            {fieldSuggestions.length > 0 && (
              <Select style={{ width: 460, marginBottom: 8 }} placeholder="Add a field from your chosen log sources" value={null as any}
                showSearch optionFilterProp="label"
                options={fieldSuggestions.map((f: any) => ({ value: `${f.standardName}|${f.siemFieldName}`, label: `${f.standardName}  (${f.siemFieldName})` }))}
                onChange={(v: string) => {
                  const [standard_name, siem_field_name] = v.split('|');
                  setSection('interrogation', { fields: [...arr(inter.fields), { id: newId('f'), standard_name, siem_field_name, attacker_controlled: 'UNKNOWN', note: '' }] });
                }} />
            )}
            <RecordList value={arr(inter.fields)} addLabel="Add a field by hand" empty="No fields yet."
              blank={() => ({ id: newId('f'), standard_name: '', siem_field_name: '', attacker_controlled: 'UNKNOWN', note: '' })}
              onChange={(v) => setSection('interrogation', { fields: v })}
              fields={[
                { key: 'standard_name', label: 'Field', width: 170 },
                { key: 'siem_field_name', label: 'Name in your SIEM', width: 230 },
                { key: 'attacker_controlled', label: 'Attacker can control it?', options: CONTROLLED, width: 190 },
                { key: 'note', label: 'Note', width: 220 },
              ]} />
          </Field>
          <Field label="Harmless activity that looks similar" help="What legitimate behaviour could trigger a naive version of this detection?">
            <StringList value={arr(inter.benign_lookalikes)} addLabel="Add an example" rows={2}
              onChange={(v) => setSection('interrogation', { benign_lookalikes: v })} />
          </Field>
        </>
      );
      case 3: return (
        <>
          <Alert type="info" showIcon style={{ marginBottom: 16 }}
            message="Describe the detection in words, not in query syntax."
            description="Your answers here decide which evasion questions are asked in the next step." />
          <Field label="What will it look for?" help="One entry per thing that must be true for the detection to fire.">
            <RecordList value={arr(design.match_elements)} addLabel="Add something it looks for"
              blank={() => ({ id: newId('m'), description: '', anchor_type: undefined, attacker_changeable: 'UNKNOWN' })}
              onChange={(v) => setSection('design', { match_elements: v })}
              fields={[
                { key: 'description', label: 'In your words', width: 300, multiline: true },
                { key: 'anchor_type', label: 'It is...', options: ANCHORS, width: 210 },
                { key: 'attacker_changeable', label: 'Can an attacker change it?', options: CHANGEABLE, width: 200 },
              ]} />
          </Field>
          <Field label="What will it ignore?" help="Exclusions you already plan, and why.">
            <RecordList value={arr(design.exclusions)} addLabel="Add an exclusion"
              blank={() => ({ id: newId('x'), what: '', why: '' })}
              onChange={(v) => setSection('design', { exclusions: v })}
              fields={[{ key: 'what', label: 'Ignored', width: 300, multiline: true }, { key: 'why', label: 'Because', width: 300, multiline: true }]} />
          </Field>
          <Field label="Time window and thresholds" help="Leave empty if the detection fires on a single event.">
            <Space wrap>
              <div><div><Text type="secondary" style={{ fontSize: 12 }}>Time window</Text></div>
                <Input style={{ width: 130 }} placeholder="e.g. 5m" value={str(wt.time_window)} onChange={(e) => setWt({ time_window: e.target.value })} /></div>
              <div><div><Text type="secondary" style={{ fontSize: 12 }}>Alert at or above</Text></div>
                <InputNumber min={0} style={{ width: 130 }} value={wt.alert_threshold ?? null} onChange={(v) => setWt({ alert_threshold: v })} /></div>
              <div><div><Text type="secondary" style={{ fontSize: 12 }}>Count by field</Text></div>
                <Input style={{ width: 170 }} value={str(wt.aggregation_field)} onChange={(e) => setWt({ aggregation_field: e.target.value })} /></div>
              <div><div><Text type="secondary" style={{ fontSize: 12 }}>Suppress repeats for</Text></div>
                <Input style={{ width: 130 }} placeholder="e.g. 1h" value={str(wt.suppression_window)} onChange={(e) => setWt({ suppression_window: e.target.value })} /></div>
            </Space>
          </Field>
          <Field label="Events or fields that must be related" help="For example: the same host, or one process starting another.">
            <StringList value={arr(design.correlations).map((c: any) => (typeof c === 'string' ? c : str(c?.text)))} addLabel="Add a relation" rows={2}
              onChange={(v) => setSection('design', { correlations: v })} />
          </Field>
          <Field label="The design in plain language" help="Optional summary that travels with the Workbench.">
            <Input.TextArea rows={4} style={{ maxWidth: 700 }} value={str(design.blueprint_text)}
              onChange={(e) => setSection('design', { blueprint_text: e.target.value })} />
          </Field>
        </>
      );
      case 4: return (
        <MaieuticAdeStage draftId={draftId} refLabel={refLabel} beforeLoad={flush} />
      );
      case 5: return (
        <>
          <Field label="When this fires, what should an analyst check first?">
            <Input.TextArea rows={3} style={{ maxWidth: 700 }} value={str(play.triage_guidance)}
              onChange={(e) => setSection('playbook_tests', { triage_guidance: e.target.value })} />
          </Field>
          <Field label="What should the response be?">
            <Input.TextArea rows={3} style={{ maxWidth: 700 }} value={str(play.response_playbook)}
              onChange={(e) => setSection('playbook_tests', { response_playbook: e.target.value })} />
          </Field>
          <Field label="Alert trigger and default severity">
            <Space wrap>
              <Input style={{ width: 420 }} placeholder="When should an alert be raised?" value={str(play.alert_trigger)}
                onChange={(e) => setSection('playbook_tests', { alert_trigger: e.target.value })} />
              <Select style={{ width: 150 }} placeholder="Severity" options={SEVERITIES} value={play.default_severity || undefined}
                onChange={(v) => setSection('playbook_tests', { default_severity: v })} />
            </Space>
          </Field>
          <Field label="How would you test that it fires?" help="A scenario you can run, and what you expect to see.">
            <Input.TextArea rows={3} style={{ maxWidth: 700, marginBottom: 8 }} placeholder="Scenario" value={str(play.test_scenario)}
              onChange={(e) => setSection('playbook_tests', { test_scenario: e.target.value })} />
            <Input.TextArea rows={2} style={{ maxWidth: 700 }} placeholder="Expected result" value={str(play.test_expected_output)}
              onChange={(e) => setSection('playbook_tests', { test_expected_output: e.target.value })} />
          </Field>
        </>
      );
      default: return (
        <>
          <Field label="Output formats" help="KQL is always produced. Add others if you need them.">
            <Checkbox.Group value={formats} onChange={(vals) => setSection('review', { output_formats: (vals as string[]).filter((f) => f !== 'KQL') })}>
              <Space direction="vertical">
                {FORMATS.map((f) => (
                  <Checkbox key={f.value} value={f.value} disabled={f.locked}>{f.label}</Checkbox>
                ))}
              </Space>
            </Checkbox.Group>
          </Field>
          <Field label="What you captured">
            <ul>
              <li>Stage 1 minimum: {missing.length ? <Text type="danger">missing {missing.join(', ')}</Text> : <Text type="success">complete</Text>}</li>
              <li>Telemetry: {pickedSources.length} source(s), {arr(inter.fields).length} field(s)</li>
              <li>Design: {arr(design.match_elements).length} match element(s), {arr(design.exclusions).length} exclusion(s)</li>
              <li>Evasion questions: {plan ? `${answeredAde} of ${plan.items.length} answered, ${limitations} accepted as limitations, ${unknownAde} marked unknown` : 'loading…'}</li>
              <li>Test scenario: {str(play.test_scenario).trim() ? 'written' : 'not written'}</li>
            </ul>
            <Paragraph type="secondary">
              This is a record of how much of your own thinking was captured. It is not a quality score for the future rule.
            </Paragraph>
          </Field>
          {missing.length > 0 && (
            <Alert type="warning" showIcon style={{ marginBottom: 12 }}
              message={`To create a Workbench you still need ${missing.join(', ')} (stage 1).`}
              description="You can save and close at any time and come back later." />
          )}
          <Alert type="info" showIcon style={{ marginBottom: 12 }}
            message="Creating the Workbench closes this session."
            description="It stays in the Maieutics tab as a read-only record, and you keep working in the Workbench. The rule is generated with the usual checks, using your design and your answers. Evasion points you accepted as limitations are listed as blind spots, not hidden." />
          <Space wrap>
            <Popconfirm title="Create the Workbench and generate the rule?" description="This locks the session." okText="Create"
              disabled={missing.length > 0} onConfirm={() => create('CREATE_AND_GENERATE')}>
              <Button type="primary" disabled={missing.length > 0} loading={creating}>Create Workbench and generate rule</Button>
            </Popconfirm>
            <Popconfirm title="Create the Workbench without a rule?" description="This locks the session." okText="Create"
              disabled={missing.length > 0} onConfirm={() => create('CREATE_WITHOUT_RULE')}>
              <Button disabled={missing.length > 0} loading={creating}>Create Workbench without a rule</Button>
            </Popconfirm>
            <Button onClick={async () => { await flush(); navigate('/playbooks?tab=maieutics'); }}>Save and close</Button>
          </Space>
          {createError && <Alert type="error" showIcon style={{ marginTop: 12 }} message={createError} />}
        </>
      );
    }
  })();

  return (
    <div style={{ padding: 24, maxWidth: 1100 }} data-testid="maieutic-session-page">
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
          <Button icon={<ArrowLeftOutlined />} onClick={async () => { await flush(); navigate('/playbooks?tab=maieutics'); }}>Maieutics</Button>
          <Text type={saveState === 'error' ? 'danger' : 'secondary'}>{saveLabel}</Text>
        </Space>
        <Input variant="borderless" style={{ fontSize: 22, fontWeight: 600, padding: 0 }} maxLength={255} value={name}
          onChange={(e) => { setName(e.target.value); nameDirty.current = true; queueSave(); }} />
        <Steps current={stage - 1} size="small" onChange={(n) => goTo(n + 1)}
          items={STAGES.map((s) => ({ title: s.title }))} />
        <Card>
          <Title level={4} style={{ marginTop: 0 }}>{stage}. {STAGES[stage - 1].title}</Title>
          <Paragraph type="secondary">{STAGES[stage - 1].help}</Paragraph>
          {body}
        </Card>
        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
          <Button disabled={stage === 1} icon={<ArrowLeftOutlined />} onClick={() => goTo(stage - 1)}>Back</Button>
          <Button type="primary" disabled={stage === 6} onClick={() => goTo(stage + 1)}>
            Next <ArrowRightOutlined />
          </Button>
        </Space>
      </Space>
    </div>
  );
};

export default MaieuticSessionPage;
