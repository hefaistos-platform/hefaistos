import { Link, useSearchParams } from 'react-router-dom';
import React, { useState, useEffect } from 'react';
import { gql } from '@apollo/client';
import { useLazyQuery, useMutation } from '@apollo/client/react';
import { Card, Input, Tag, Typography, Spin, Select, Checkbox, Switch, Space, Button, Modal, message } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';

// Define the GraphQL query for searching rules
const RULES_CONNECTION_QUERY = gql`
  query RulesConnection($text: String, $status: [String!], $repositoryId: ID, $author: String, $tags: [String!], $techniqueId: String, $sort: String, $first: Int!, $after: String) {
    rulesConnection(text: $text, status: $status, repositoryId: $repositoryId, author: $author, tags: $tags, techniqueId: $techniqueId, sort: $sort, first: $first, after: $after) {
      totalCount
      pageInfo { hasNextPage endCursor }
      edges {
        cursor
        node { id title description status tags author }
      }
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

const ALL_REPOS_QUERY = gql`
  query AllRuleRepositories {
    allRuleRepositories { id name }
  }
`;

const ALL_TAGS_QUERY = gql`
  query AllTags { allTags { id name usageCount } }
`;

// Define the TypeScript types for our data
interface Rule {
  id: string;
  title: string;
  description: string | null;
  status: string | null;
  author?: string | null;
}

interface CurrentUser {
  id: string;
  username: string;
  role: string;
}

interface RulesConnectionData {
  rulesConnection: {
    totalCount: number;
    pageInfo: { hasNextPage: boolean; endCursor: string | null };
    edges: { cursor: string; node: Rule }[];
  };
}

interface RulesConnectionVars {
  text?: string;
  status?: string[];
  repositoryId?: string;
  author?: string;
  tags?: string[];
  techniqueId?: string;
  sort?: string;
  first: number;
  after?: string;
}

export const RuleSearchPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialText = searchParams.get('text') || '';
  const initialAuthor = searchParams.get('author') || '';
  const initialRepo = searchParams.get('repo') || undefined;
  const initialSort = searchParams.get('sort') || 'UPDATED_DESC';
  const initialStatus = (searchParams.get('status') || '').split(',').filter(Boolean);
  const initialTags = (searchParams.get('tags') || '').split(',').filter(Boolean);
  const initialTechnique = searchParams.get('technique') || '';
  const initialCI = (searchParams.get('ci') || '1') === '1';
  const initialHL = searchParams.get('hl') || 'yellow';

  const [searchTerm, setSearchTerm] = useState(initialText);
  const [author, setAuthor] = useState(initialAuthor);
  const [repositoryId, setRepositoryId] = useState<string | undefined>(initialRepo);
  const [sort, setSort] = useState<string>(initialSort);
  const [status, setStatus] = useState<string[]>(initialStatus);
  const [tags, setTags] = useState<string[]>(initialTags);
  const [techniqueId, setTechniqueId] = useState<string>(initialTechnique);
  const [caseInsensitive, setCaseInsensitive] = useState<boolean>(initialCI);
  const [highlightColor, setHighlightColor] = useState<string>(initialHL);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [deletingRuleId, setDeletingRuleId] = useState<string | null>(null);

  const [loadRules, { loading, error, data }] = useLazyQuery<RulesConnectionData, RulesConnectionVars>(
    RULES_CONNECTION_QUERY
  );
  const [loadCurrentUser, userQuery] = useLazyQuery<{ me: CurrentUser }>(CURRENT_USER_QUERY);
  useEffect(() => { 
    loadCurrentUser().then(({ data: userData }) => {
      if (userData?.me) setCurrentUser(userData.me);
    });
  }, [loadCurrentUser]);

  interface AllReposData { allRuleRepositories: { id: string; name: string }[] }
  const [loadRepos, reposQuery] = useLazyQuery<AllReposData>(ALL_REPOS_QUERY);
  useEffect(() => { loadRepos(); }, [loadRepos]);

  interface AllTagsData { allTags: { id: string; name: string }[] }
  const [loadTags, tagsQuery] = useLazyQuery<AllTagsData>(ALL_TAGS_QUERY);
  useEffect(() => { loadTags(); }, [loadTags]);

  const [deleteRule] = useMutation(DELETE_RULE_MUTATION);

  const canDeleteRule = (rule: Rule) => {
    if (!currentUser) return false;
    const isOwner = rule.author === currentUser.username;
    const isAdmin = currentUser.role === 'ADMIN' || currentUser.role === 'SUPERADMIN';
    return isOwner || isAdmin;
  };

  const handleDeleteRule = async (rule: Rule) => {
    Modal.confirm({
      title: 'Delete Detection Rule',
      content: `Are you sure you want to delete the rule "${rule.title}"? This action cannot be undone.`,
      okText: 'Delete',
      okType: 'danger',
      onOk: async () => {
        try {
          setDeletingRuleId(rule.id);
          const { data: result } = await deleteRule({ variables: { ruleId: rule.id } });
          
          if (result?.deleteDetectionRule?.success) {
            message.success(result.deleteDetectionRule.message || 'Rule deleted successfully');
            // Refresh the search results
            const vars: RulesConnectionVars = {
              text: searchTerm || undefined,
              author: author || undefined,
              repositoryId: repositoryId || undefined,
              status: status.length ? status : undefined,
              tags: tags.length ? tags : undefined,
              techniqueId: techniqueId || undefined,
              sort: sort || undefined,
              first: 48,
              after: undefined,
            };
            setAfter(undefined);
            loadRules({ variables: vars });
          } else {
            message.error(result?.deleteDetectionRule?.message || 'Failed to delete rule');
          }
        } catch (err: any) {
          message.error(err.message || 'Error deleting rule');
        } finally {
          setDeletingRuleId(null);
        }
      },
    });
  };

  // Debounce effect: trigger the search only after the user stops typing
  const [pageSize] = useState<number>(48);
  const [after, setAfter] = useState<string | undefined>(undefined);

  useEffect(() => {
    const handler = setTimeout(() => {
      const vars: RulesConnectionVars = {
        text: searchTerm || undefined,
        author: author || undefined,
        repositoryId: repositoryId || undefined,
        status: status.length ? status : undefined,
        tags: tags.length ? tags : undefined,
        techniqueId: techniqueId || undefined,
        sort: sort || undefined,
        first: pageSize,
        after,
      };
      loadRules({ variables: vars });
      const nextParams: Record<string, string> = {};
      if (vars.text) nextParams.text = vars.text;
      if (vars.author) nextParams.author = vars.author;
      if (vars.repositoryId) nextParams.repo = vars.repositoryId;
      if (vars.sort) nextParams.sort = vars.sort;
      if (vars.status) nextParams.status = vars.status.join(',');
      if (vars.tags) nextParams.tags = vars.tags.join(',');
      if (vars.techniqueId) nextParams.technique = vars.techniqueId;
      nextParams.ci = caseInsensitive ? '1' : '0';
      nextParams.hl = highlightColor;
      setSearchParams(nextParams);
    }, 500);
    return () => clearTimeout(handler);
  }, [searchTerm, author, repositoryId, status, sort, tags, techniqueId, caseInsensitive, highlightColor, pageSize, after, loadRules, setSearchParams]);

  // Simple load more handler (increment offset)
  const handleLoadMore = () => {
    const nextCursor = data?.rulesConnection?.pageInfo?.endCursor || undefined;
    if (!nextCursor) return;
    setAfter(nextCursor);
    loadRules({ variables: { text: searchTerm || undefined, first: pageSize, after: nextCursor } });
  };

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>Search Detection Rules</Typography.Title>
        <Space>
          <Button onClick={() => { /* placeholder: refresh search */ }}>Refresh</Button>
        </Space>
      </Space>
      <Card size="small">
      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: 16 }}>
        <div>
          <Input
            placeholder="Free text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            disabled={loading}
            style={{ marginBottom: 12 }}
          />
          <Input
            placeholder="Author contains"
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            disabled={loading}
            style={{ marginBottom: 12 }}
          />
          <Select
            placeholder="Repository"
            value={repositoryId}
            onChange={(v) => setRepositoryId(v)}
            allowClear
            style={{ width: '100%', marginBottom: 12 }}
            options={(reposQuery.data?.allRuleRepositories || []).map((r: any) => ({ label: r.name, value: r.id }))}
          />
          <Typography.Text>Status</Typography.Text>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
            {['experimental','test','stable','deprecated'].map(s => (
              <Checkbox key={s} checked={status.includes(s)} onChange={(e) => {
                const checked = e.target.checked;
                setStatus(prev => checked ? [...prev, s] : prev.filter(x => x !== s));
              }}>{s}</Checkbox>
            ))}
          </div>
          <Select
            value={sort}
            onChange={setSort}
            style={{ width: '100%' }}
            options={[
              { label: 'Updated (newest)', value: 'UPDATED_DESC' },
              { label: 'Updated (oldest)', value: 'UPDATED_ASC' },
              { label: 'Created (newest)', value: 'CREATED_DESC' },
              { label: 'Created (oldest)', value: 'CREATED_ASC' },
              { label: 'Title A–Z', value: 'TITLE_ASC' },
              { label: 'Title Z–A', value: 'TITLE_DESC' },
            ]}
          />
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 12 }}>
            <Switch checked={caseInsensitive} onChange={setCaseInsensitive} />
            <Typography.Text>Case-insensitive matching</Typography.Text>
          </div>
          <div style={{ marginTop: 8 }}>
            <Typography.Text>Highlight color</Typography.Text>
            <Select
              value={highlightColor}
              onChange={setHighlightColor}
              style={{ width: '100%', marginTop: 6 }}
              options={[
                { label: 'Yellow', value: 'yellow' },
                { label: 'Blue', value: '#e0f2ff' },
                { label: 'Green', value: '#dcfce7' },
                { label: 'None', value: 'none' },
              ]}
            />
          </div>
          <Input
            placeholder="Technique ID (e.g., T1059)"
            value={techniqueId}
            onChange={(e) => setTechniqueId(e.target.value)}
            disabled={loading}
            style={{ marginTop: 12, marginBottom: 12 }}
          />
          <Typography.Text>Tags</Typography.Text>
          <Select
            mode="tags"
            value={tags}
            onChange={(vals) => setTags(vals as string[])}
            style={{ width: '100%', marginBottom: 12 }}
            placeholder="Type and press enter to add tags"
            options={(tagsQuery.data?.allTags || []).map(t => ({ label: t.name, value: t.name }))}
          />
          <Typography.Link onClick={() => {
            setSearchTerm(''); setAuthor(''); setRepositoryId(undefined); setStatus([]); setSort('UPDATED_DESC'); setTags([]); setTechniqueId(''); setAfter(undefined);
            setCaseInsensitive(true); setHighlightColor('yellow');
            setSearchParams({ ci: '1', hl: 'yellow' });
          }}>
            Clear All
          </Typography.Link>
        </div>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <Typography.Text>Total: {data?.rulesConnection?.totalCount ?? 0}</Typography.Text>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {searchTerm && <Tag>{searchTerm}</Tag>}
              {author && <Tag>author:{author}</Tag>}
              {repositoryId && <Tag>repo:{repositoryId}</Tag>}
              {status.map(s => <Tag key={s}>{s}</Tag>)}
              {tags.map(t => <Tag key={t}>tag:{t}</Tag>)}
              {techniqueId && <Tag>{techniqueId}</Tag>}
              {sort && <Tag>sort:{sort}</Tag>}
            </div>
          </div>
            {error && <Typography.Text type="danger">Error searching rules: {error.message}</Typography.Text>}
          {loading && <Spin style={{ marginBottom: 16 }} />}
            {searchTerm && (
              <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
                Showing best matches for "{searchTerm}" (fuzzy)
              </Typography.Text>
            )}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
              gap: 16,
            }}
          >
              {(data?.rulesConnection?.edges || []).map(({ node: rule }) => {
                const highlight = (text?: string | null) => {
                  if (!text) return '';
                  if (!searchTerm) return text;
                  const safe = searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                  const flags = caseInsensitive ? 'gi' : 'g';
                  const re = new RegExp(`(${safe})`, flags);
                  const styleAttr = highlightColor === 'none' ? '' : ` style="background:${highlightColor}"`;
                  return text.replace(re, `<mark${styleAttr}>$1</mark>`);
                };
                const canDelete = canDeleteRule(rule);
                return (
              <Card
                key={rule.id}
                size="small"
                hoverable
                style={{ borderLeft: '4px solid #1677ff' }}
                title={
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', gap: 8 }}>
                    <Link to={`/rules/${rule.id}`} dangerouslySetInnerHTML={{ __html: highlight(rule.title) }} style={{ flex: 1 }} />
                    {canDelete && (
                      <Button
                        type="text"
                        danger
                        size="small"
                        icon={<DeleteOutlined />}
                        onClick={() => handleDeleteRule(rule)}
                        loading={deletingRuleId === rule.id}
                        style={{ minWidth: 0 }}
                      />
                    )}
                  </div>
                }
              >
                <Tag color="blue" style={{ marginBottom: 8 }}>Status: {rule.status || 'N/A'}</Tag>
                {rule.author && (
                  <Tag style={{ marginBottom: 8 }}>Author: {rule.author}</Tag>
                )}
                {!!(rule as any).tags?.length && (
                  <div style={{ marginBottom: 8 }}>
                    {(rule as any).tags.slice(0, 6).map((t: string) => (
                      <Tag key={t} bordered>{t}</Tag>
                    ))}
                  </div>
                )}
                  <Typography.Paragraph style={{ margin: 0 }}>
                    {rule.description ? (
                      <span dangerouslySetInnerHTML={{ __html: highlight(rule.description) }} />
                    ) : (
                      'No description available.'
                    )}
                  </Typography.Paragraph>
              </Card>
              ); })}
          </div>
          {data?.rulesConnection?.pageInfo?.hasNextPage && (
            <div style={{ marginTop: 16, textAlign: 'center' }}>
              <Typography.Link onClick={handleLoadMore} disabled={loading}>Load more</Typography.Link>
            </div>
          )}
        </div>
      </div>
      </Card>
    </div>
  );
};
