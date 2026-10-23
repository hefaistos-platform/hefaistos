import React, { useState } from 'react';
import { gql, useMutation, useQuery } from '@apollo/client';
import { Button, Modal, Select, Space, Tag, message } from 'antd';
import { Link } from 'react-router-dom';
const LINKS = gql`query WorkbenchRuleLinks($workbenchId: UUID!) { workbenchRuleLinks(workbenchId: $workbenchId) { id title format canEdit } }`;
const SEARCH = gql`query AttachRuleSearch($query: String!) { searchAllRules(query: $query, limit: 30) { id title workbenchId canEdit workbenchOwned } }`;
const LINK = gql`mutation AttachWorkbenchRule($ruleId: ID!, $workbenchId: UUID) { linkRuleWorkbench(ruleId: $ruleId, workbenchId: $workbenchId) { rule { id workbenchId } } }`;
export default function WorkbenchLinkedRules({ workbenchId, canManage }: { workbenchId: string; canManage: boolean }) {
  const { data, refetch } = useQuery(LINKS, { variables: { workbenchId } });
  const [open, setOpen] = useState(false); const [query, setQuery] = useState(''); const [ruleId, setRuleId] = useState<string>();
  const { data: search, loading } = useQuery(SEARCH, { variables: { query }, skip: !open });
  const [link, { loading: saving }] = useMutation(LINK);
  const apply = async (id: string, target: string | null) => {
    try { await link({ variables: { ruleId: id, workbenchId: target } }); await refetch(); setOpen(false); setRuleId(undefined); message.success(target ? 'Rule attached.' : 'Rule unlinked.'); }
    catch (e: any) { message.error(e.message); }
  };
  return <div style={{ marginTop: 16, padding: 16, border: '1px solid var(--hef-border)', borderRadius: 8 }}>
    <Space style={{ width: '100%', justifyContent: 'space-between' }}><strong>Linked Rules</strong>
      {canManage && <Button size="small" onClick={() => setOpen(true)}>Add existing rule</Button>}
    </Space>
    <p className="text-sm text-gray-500">Additional rules remain in Rule Hub. Workbench export, review and deployment continue to use the primary rule.</p>
    {(data?.workbenchRuleLinks || []).map((rule: any) => <div key={rule.id} style={{ padding: '8px 0' }}><Space>
      <Link to={`/rules/${rule.id}/edit`}>{rule.title}</Link><Tag>{rule.format}</Tag>
      {canManage && rule.canEdit && <Button size="small" loading={saving} onClick={() => apply(rule.id, null)}>Unlink</Button>}
    </Space></div>)}
    {!data?.workbenchRuleLinks?.length && <span className="text-sm text-gray-500">No additional rules linked.</span>}
    <Modal open={open} title="Add existing rule" onCancel={() => setOpen(false)} onOk={() => ruleId && apply(ruleId, workbenchId)} okButtonProps={{ disabled: !ruleId }} confirmLoading={saving}>
      <p>Select an independent rule from Rule Hub. The primary Workbench rule will be preserved.</p>
      <Select aria-label="Select rule to attach" style={{ width: '100%' }} showSearch filterOption={false} onSearch={setQuery} loading={loading}
        value={ruleId} onChange={setRuleId} options={(search?.searchAllRules || []).filter((r: any) => r.canEdit && !r.workbenchOwned && !r.workbenchId).map((r: any) => ({ value: r.id, label: r.title }))} />
    </Modal>
  </div>;
}
