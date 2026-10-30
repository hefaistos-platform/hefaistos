import React, { useMemo, useRef, useState } from 'react';
import { gql, useMutation, useQuery } from '@apollo/client';
import { useNavigate, useParams } from 'react-router-dom';
import { Alert, Button, Space, message } from 'antd';
import DetectionRuleEditorModal, { AIRuleAttribution } from '../components/DetectionRuleEditorModal';
import RulePublishModal from '../components/RulePublishModal';
import RuleWorkbenchLinkModal from '../components/RuleWorkbenchLinkModal';
import { OpenTideRule } from '../types/opentide';
const GET = gql`query RuleEditor($id: ID!) { rule(id: $id) {
  id title editorDocument canEdit workbenchOwned workbenchId workbenchTitle
} }`;
const ME = gql`query RuleEditorMe { me { username role } }`;
const SAVE = gql`mutation SaveRuleDraft($ruleId: ID, $document: JSONString!, $aiAttributions: [AIRuleAttributionInput!]) {
  saveRuleDraft(ruleId: $ruleId, document: $document, aiAttributions: $aiAttributions) { rule { id title editorDocument } }
}`;
const DUPLICATE = gql`mutation DuplicateRule($ruleId: ID!) { duplicateRule(ruleId: $ruleId) { rule { id } } }`;
export default function RuleEditorPage() {
  const { ruleId } = useParams(); const navigate = useNavigate();
  const { data, loading, error, refetch } = useQuery(GET, { variables: { id: ruleId }, skip: !ruleId });
  const { data: me, loading: loadingMe } = useQuery(ME);
  const [save] = useMutation(SAVE, { fetchPolicy: 'no-cache' }); const [duplicate] = useMutation(DUPLICATE);
  const savedId = useRef(ruleId); const lastDocument = useRef('');
  const [publishId, setPublishId] = useState<string>(); const [linkId, setLinkId] = useState<string>();
  const [savedTitle, setSavedTitle] = useState('');
  const [initial] = useState<OpenTideRule>(() => ({ metadata: { title: 'Untitled Rule', description: '', author: '',
    created: '', modified: '', mitre: {}, capability: {}, response: { severity: 'MEDIUM' }, tags: [], status: 'experimental' }, platforms: {} }));
  const editorDocument = useMemo<OpenTideRule>(() => data?.rule ? JSON.parse(data.rule.editorDocument) : { ...initial, metadata: { ...initial.metadata, author: me?.me?.username || '' } }, [data?.rule?.editorDocument, initial, me?.me?.username]);
  if (loading || loadingMe) return <p>Loading rule editor…</p>;
  if (error) return <Alert type="error" message={error.message} />;
  if (ruleId && !data?.rule) return <Alert type="error" message="Rule not found." />;
  const rule = data?.rule;
  const doc = editorDocument;
  const persist = async (document: OpenTideRule, aiAttributions?: AIRuleAttribution[]) => {
    const serialized = JSON.stringify(document);
    if (savedId.current && serialized === lastDocument.current && !aiAttributions?.length) return savedId.current;
    const response = await save({ variables: { ruleId: savedId.current, document: serialized, aiAttributions } });
    const saved = response.data.saveRuleDraft.rule;
    savedId.current = saved.id; lastDocument.current = serialized; setSavedTitle(saved.title);
    return saved.id as string;
  };
  const copy = async () => {
    try { const response = await duplicate({ variables: { ruleId: rule.id } }); navigate(`/rules/${response.data.duplicateRule.rule.id}/edit`); }
    catch (e: any) { message.error(e.message); }
  };
  if (rule && (rule.workbenchOwned || !rule.canEdit)) return <Space direction="vertical" style={{ padding: 24 }}>
    <Alert type="info" message={rule.workbenchOwned ? 'This rule uses the existing Workbench editor.' : 'You can view this rule or duplicate it to create your own editable rule.'} />
    {rule.workbenchOwned && <Button onClick={() => navigate(`/playbooks/${rule.workbenchId}`)}>Open Workbench</Button>}
    <Button onClick={copy}>Duplicate into Rule Hub</Button><Button onClick={() => navigate(`/rules/${ruleId}`)}>View rule</Button>
  </Space>;
  const current = rule?.workbenchId ? { id: rule.workbenchId, title: rule.workbenchTitle } : undefined;
  return <>
    <DetectionRuleEditorModal visible standalone initialRule="" initialFormat="KQL" initialMode="manual"
      initialOpenTideRule={doc} ruleId={ruleId || savedId.current} onClose={() => navigate('/rules')} linkedWorkbench={current}
      onSave={async (_content, _format, _mode, _source, document, attributions) => { if (document) { const id = await persist(document, attributions); if (!ruleId) navigate(`/rules/${id}/edit`, { replace: true }); } }}
      onPublish={async (document, attributions) => { try { setPublishId(await persist(document, attributions)); } catch (e: any) { message.error(e.message); } }}
      onLink={async (document, attributions) => { try { setLinkId(await persist(document, attributions)); } catch (e: any) { message.error(e.message); } }}
      onDuplicate={async (document, attributions) => { try { const id = await persist(document, attributions); const response = await duplicate({ variables: { ruleId: id } }); navigate(`/rules/${response.data.duplicateRule.rule.id}/edit`); } catch (e: any) { message.error(e.message); } }} />
    {publishId && <RulePublishModal ruleId={publishId} title={savedTitle || doc.metadata.title} onClose={() => { setPublishId(undefined); if (!ruleId) navigate(`/rules/${savedId.current}/edit`, { replace: true }); }} />}
    {linkId && <RuleWorkbenchLinkModal ruleId={linkId} current={current} onClose={() => setLinkId(undefined)} onChanged={() => { if (ruleId) void refetch(); else navigate(`/rules/${savedId.current}/edit`); }} />}
  </>;
}
