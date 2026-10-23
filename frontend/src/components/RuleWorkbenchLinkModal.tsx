import React, { useState } from 'react';
import { gql, useMutation, useQuery } from '@apollo/client';
import { Modal, Select, Button, Space, message } from 'antd';

const WORKBENCHES = gql`query RuleLinkWorkbenches { allPlaybookGraphs { id title isReadOnly } }`;
const LINK = gql`mutation LinkRuleWorkbench($ruleId: ID!, $workbenchId: UUID) {
  linkRuleWorkbench(ruleId: $ruleId, workbenchId: $workbenchId) { rule { id workbenchId workbenchTitle } }
}`;
export default function RuleWorkbenchLinkModal({ ruleId, current, onClose, onChanged }: {
  ruleId: string; current?: { id: string; title: string }; onClose: () => void; onChanged: () => void;
}) {
  const [workbenchId, setWorkbenchId] = useState<string>();
  const { data, loading } = useQuery(WORKBENCHES);
  const [link, { loading: saving }] = useMutation(LINK);
  const apply = async (id?: string) => {
    try {
      await link({ variables: { ruleId, workbenchId: id || null } });
      message.success(id ? 'Rule linked to Workbench.' : 'Rule unlinked.'); onChanged(); onClose();
    } catch (error: any) { message.error(error.message); }
  };
  return <Modal open title="Workbench link" onCancel={onClose} footer={<Space>
    <Button onClick={onClose}>Cancel</Button>
    {current ? <Button loading={saving} onClick={() => apply()}>Unlink rule</Button> :
      <Button type="primary" disabled={!workbenchId} loading={saving} onClick={() => apply(workbenchId)}>Link rule</Button>}
  </Space>}>
    {current ? <p>Linked to {current.title}. Unlinking keeps the rule in Rule Hub.</p> : <>
      <p>The rule remains independent. Linking preserves the Workbench’s primary rule and metadata.</p>
      <Select aria-label="Select Workbench" style={{ width: '100%' }} showSearch optionFilterProp="label" loading={loading}
        value={workbenchId} onChange={setWorkbenchId} options={(data?.allPlaybookGraphs || []).filter((g: any) => !g.isReadOnly).map((g: any) => ({ value: g.id, label: g.title }))} />
    </>}
  </Modal>;
}
