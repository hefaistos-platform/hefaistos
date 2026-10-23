import React, { useState } from 'react';
import { gql, useMutation, useQuery } from '@apollo/client';
import { Alert, Button, Input, Modal, Select, Space, Tabs, message } from 'antd';
const REPOS = gql`query RulePublishRepositories { allRuleRepositories { id name url provider } }`;
const PREVIEW = gql`mutation PreviewRulePublish($ruleId: ID!, $repositoryId: ID!, $branch: String!, $path: String!) {
  previewRulePublish(ruleId: $ruleId, repositoryId: $repositoryId, branch: $branch, path: $path) {
    preview { content diff token unchanged }
  }
}`;
const PUBLISH = gql`mutation PublishRuleToGit($previewToken: String!, $commitMessage: String) {
  publishRuleToGit(previewToken: $previewToken, commitMessage: $commitMessage) { commitSha fileUrl }
}`;
export default function RulePublishModal({ ruleId, title, onClose }: { ruleId: string; title: string; onClose: () => void }) {
  const { data, loading } = useQuery(REPOS);
  const [repositoryId, setRepositoryId] = useState<string>();
  const [branch, setBranch] = useState('main');
  const [path, setPath] = useState(`rules/${title.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'rule'}.yaml`);
  const [commitMessage, setCommitMessage] = useState(`Publish rule: ${title}`);
  const [preview, setPreview] = useState<{ content: string; diff: string; token: string; unchanged: boolean }>();
  const [result, setResult] = useState<{ commitSha: string; fileUrl: string }>();
  const [error, setError] = useState('');
  const [getPreview, { loading: previewing }] = useMutation(PREVIEW);
  const [publish, { loading: publishing }] = useMutation(PUBLISH);
  const inspect = async () => {
    setError(''); setPreview(undefined); setResult(undefined);
    try { const response = await getPreview({ variables: { ruleId, repositoryId, branch, path } }); setPreview(response.data.previewRulePublish.preview); }
    catch (e: any) { setError(e.message); }
  };
  const push = async () => {
    setError('');
    try { const response = await publish({ variables: { previewToken: preview?.token, commitMessage } }); setResult(response.data.publishRuleToGit); setPreview(undefined); message.success('Rule published to Git.'); }
    catch (e: any) { setError(e.message); setPreview(undefined); }
  };
  return <Modal open title="Publish rule to Git" width={900} onCancel={publishing ? undefined : onClose} footer={<Space>
    <Button disabled={publishing} onClick={onClose}>Close</Button>
    <Button disabled={!repositoryId || !branch || !path || publishing} loading={previewing} onClick={inspect}>Preview</Button>
    <Button type="primary" disabled={!preview || preview.unchanged || previewing} loading={publishing} onClick={push}>Publish to Git</Button>
  </Space>}>
    <p>Publish this rule as one OpenTIDE YAML document using a repository configured in Configuration → Rules.</p>
    <Space direction="vertical" style={{ width: '100%' }}>
      <Select aria-label="Git repository" placeholder="Select configured repository" loading={loading} style={{ width: '100%' }} value={repositoryId} disabled={publishing}
        onChange={id => { setRepositoryId(id); setPreview(undefined); setResult(undefined); }}
        options={(data?.allRuleRepositories || []).filter((r: any) => r.url).map((r: any) => ({ value: r.id, label: `${r.name} (${r.provider})` }))} />
      {!loading && !(data?.allRuleRepositories || []).some((r: any) => r.url) && <Alert type="info" message="Configure a repository in Configuration → Rules before publishing." />}
      <label>Existing branch<Input aria-label="Git branch" value={branch} disabled={publishing} onChange={e => { setBranch(e.target.value); setPreview(undefined); }} /></label>
      <label>File path<Input aria-label="Git file path" value={path} disabled={publishing} onChange={e => { setPath(e.target.value); setPreview(undefined); }} /></label>
      <label>Commit message<Input aria-label="Commit message" value={commitMessage} disabled={publishing} onChange={e => setCommitMessage(e.target.value)} /></label>
      {error && <Alert type="error" message="Publishing failed; your saved draft is preserved" description={error} />}
      {result && <Alert type="success" message={`Commit: ${result.commitSha}`} description={<a href={result.fileUrl} target="_blank" rel="noreferrer">View published rule</a>} />}
      {preview && <><Alert type={preview.unchanged ? 'info' : 'warning'} message={preview.unchanged ? 'No changes to publish.' : 'Review the document and file changes before publishing.'} />
        <Tabs items={[{ key: 'diff', label: 'Changes', children: <pre style={{ maxHeight: 350, overflow: 'auto', whiteSpace: 'pre-wrap' }}>{preview.diff || 'No changes'}</pre> },
          { key: 'yaml', label: 'OpenTIDE YAML', children: <pre style={{ maxHeight: 350, overflow: 'auto', whiteSpace: 'pre-wrap' }}>{preview.content}</pre> }]} />
      </>}
    </Space>
  </Modal>;
}
