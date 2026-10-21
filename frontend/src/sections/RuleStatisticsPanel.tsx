import React from 'react';
import { gql } from '@apollo/client';
import { useQuery } from '@apollo/client/react';
import { Link, useNavigate } from 'react-router-dom';
import { Alert, Button, Card, Col, Collapse, Empty, Row, Segmented, Space, Statistic, Table, Tag, Typography } from 'antd';
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, Tooltip, XAxis, YAxis } from 'recharts';
import { ChartTooltip, Doughnut, HorizontalBars, StableChart, useChartColors, xAxisDefaults, yAxisDefaults } from './RuleStatisticsCharts';

type NamedCount = { name: string; count: number };
type Technique = { techniqueId: string; name: string; count: number };
type Repository = { id: string; name: string; ruleCount: number; lastSync: string | null; stale: boolean };
type Stats = {
  generatedAt: string; total: number; createdLast24h: number; createdLast7d: number; createdLast30d: number;
  unchanged90dPlus: number; activeCount: number; deprecatedCount: number; avgTechniquesPerRule: number;
  withPlaybooksCount: number; standaloneCount: number; rulesWithTechniques: number; linkedWorkbenchCount: number;
  byStatus: NamedCount[]; byFormat: NamedCount[]; validation: NamedCount[];
  deploymentByFormat: Array<{ name: string; deployed: number; testing: number; development: number; unlinked: number }>;
  topTechniques: Technique[]; topSubtechniques: Technique[];
  createdSeries: Array<{ date: string; count: number }>; updatedSeries: Array<{ date: string; count: number }>;
  repositories: Repository[]; topTags: Array<{ tag: string; count: number }>;
  tagCooccurrence: Array<{ tagA: string; tagB: string; count: number }>;
  topAuthors: Array<{ name: string; count: number; lastActivity: string | null }>;
  inactiveAuthors: Array<{ name: string }>;
  recentChanges: Array<{ id: string; title: string; status: string; updatedAt: string; changeType: string }>;
};
export const RULE_STATS_QUERY = gql`
  query RuleStatistics($topN: Int, $seriesDays: Int) {
    ruleStatistics(topN: $topN, seriesDays: $seriesDays) {
      generatedAt total createdLast24h createdLast7d createdLast30d unchanged90dPlus activeCount deprecatedCount
      avgTechniquesPerRule withPlaybooksCount standaloneCount rulesWithTechniques linkedWorkbenchCount
      byStatus { name count } byFormat { name count } validation { name count }
      deploymentByFormat { name deployed testing development unlinked }
      topTechniques { techniqueId name count } topSubtechniques { techniqueId name count }
      createdSeries { date count } updatedSeries { date count }
      repositories { id name ruleCount lastSync stale }
      topTags { tag count } tagCooccurrence { tagA tagB count }
      topAuthors { name count lastActivity } inactiveAuthors { name }
      recentChanges { id title status updatedAt changeType }
    }
  }
`;
const dateTime = (value: string | null) => value ? new Date(value).toLocaleString() : '—';
const validationNames: Record<string, string> = {
  PASSED: 'Passed', FAILED: 'Failed', NOT_TESTED: 'Not tested', OUTDATED: 'Outdated test evidence',
};

export const RuleStatisticsPanel: React.FC<{ onSearch?: () => void }> = ({ onSearch }) => {
  const [seriesDays, setSeriesDays] = React.useState(30);
  const navigate = useNavigate();
  const c = useChartColors();
  const { data, loading, error, refetch } = useQuery<{ ruleStatistics: Stats }, { topN: number; seriesDays: number }>(
    RULE_STATS_QUERY, { variables: { topN: 10, seriesDays }, notifyOnNetworkStatusChange: true }
  );
  const s = data?.ruleStatistics;
  const search = (key: string, value: string) => {
    navigate(`/rules?${new URLSearchParams({ [key]: value })}`);
    onSearch?.();
  };
  const percent = (value: number) => s?.total ? `${(value / s.total * 100).toFixed(1)}% of rules` : 'No rules available';
  const stateColor = (name: string) => {
    const n = name.toUpperCase();
    if (['PASSED', 'ACTIVE', 'DEPLOYED', 'STABLE'].includes(n)) return c.green;
    if (['FAILED', 'DEPRECATED'].includes(n)) return c.red;
    if (['OUTDATED', 'TESTING', 'EXPERIMENTAL', 'TUNING'].includes(n)) return c.amber;
    if (['UNKNOWN', 'NOT_TESTED'].includes(n)) return c.gray;
    return c.blue;
  };
  const repositories = s?.repositories ?? [];
  const repositoryStatus = (r: Repository) => !r.lastSync ? 'Never synced' : r.stale ? 'Stale (≥7 days)' : 'Recently synced';
  const repoData = [
    { name: 'Recently synced', color: c.green }, { name: 'Stale (≥7 days)', color: c.amber }, { name: 'Never synced', color: c.gray },
  ].map(d => ({ ...d, count: repositories.filter(r => repositoryStatus(r) === d.name).length }));
  const updatedByDate = new Map((s?.updatedSeries ?? []).map(p => [p.date, p.count]));
  const trend = (s?.createdSeries ?? []).map(p => ({ date: p.date, created: p.count, updated: updatedByDate.get(p.date) ?? 0 }));
  const failed = s?.validation.find(v => v.name === 'FAILED')?.count ?? 0;
  const outdated = s?.validation.find(v => v.name === 'OUTDATED')?.count ?? 0;
  const untested = s?.validation.find(v => v.name === 'NOT_TESTED')?.count ?? 0;
  const deployed = s?.deploymentByFormat.reduce((sum, d) => sum + d.deployed, 0) ?? 0;
  const palette = [c.blue, c.purple, c.teal, c.amber, c.green];
  const techniqueBars = (values: Technique[]) => values.map((t, i) => ({
    name: t.techniqueId, count: t.count, color: palette[i % palette.length],
    detail: `${t.name} (${t.techniqueId})`,
  }));
  const techniqueTable = (values: Technique[]) => <Table size="small" rowKey="techniqueId" pagination={false} dataSource={values}
    columns={[
      { title: 'Technique', dataIndex: 'techniqueId', render: (id: string) => <Button type="link" size="small" onClick={() => search('technique', id)}>{id}</Button> },
      { title: 'Name', dataIndex: 'name' }, { title: 'Rules', dataIndex: 'count', sorter: (a, b) => a.count - b.count },
    ]} />;

  return <Space orientation="vertical" size={16} style={{ width: '100%' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
      <div><Typography.Title level={4} style={{ margin: 0 }}>Detection readiness & library statistics</Typography.Title>
        <Typography.Text type="secondary">{s?.generatedAt ? `Data refreshed: ${dateTime(s.generatedAt)}` : 'Loading statistics…'}</Typography.Text></div>
      <Button onClick={() => refetch()} loading={loading}>Refresh statistics</Button>
    </div>
    {error && <Alert type="error" showIcon title="Statistics could not be loaded" description={error.message}
      action={<Button onClick={() => refetch()}>Retry</Button>} />}
    {!loading && !error && !s && <Empty description="No statistics available" />}
    <Row gutter={[16, 16]}>
      {[
        { title: 'Total Rules', value: s?.total, color: c.blue, description: 'Rule records across all formats' },
        { title: 'New Rules (30d)', value: s?.createdLast30d, color: c.purple,
          description: `${s?.createdLast24h ?? '—'} in 24h · ${s?.createdLast7d ?? '—'} in 7d` },
        { title: 'Linked to deployed workbenches', value: deployed, color: c.green, description: 'Recorded deployment status' },
        { title: 'Not modified in ≥90 days', value: s?.unchanged90dPlus, color: c.amber,
          description: `${percent(s?.unchanged90dPlus ?? 0)} · Review age; not a failure indicator` },
      ].map(item => <Col xs={24} sm={12} xl={6} key={item.title}><Card loading={loading} style={{ height: '100%', borderTop: `3px solid ${item.color}` }}>
        <Statistic title={item.title} value={item.value ?? '—'} styles={{ content: { color: item.color } }} />
        <Typography.Text type="secondary">{item.description}</Typography.Text>
      </Card></Col>)}
    </Row>
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={8}><Card title="Rule Lifecycle" loading={loading} style={{ height: '100%' }}>
        <Doughnut data={(s?.byStatus ?? []).map(d => ({ ...d, color: stateColor(d.name) }))}
          />
        <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>Lifecycle labels describe rule metadata. “Active” does not confirm live platform health.</Typography.Paragraph>
      </Card></Col>
      <Col xs={24} xl={8}><Card title="Validation Results" loading={loading} style={{ height: '100%' }}>
        <Doughnut unit="workbenches" data={(s?.validation ?? []).map(d => ({ ...d, name: validationNames[d.name] ?? d.name, color: stateColor(d.name) }))} />
        <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
          Each linked workbench is counted once. Results apply to the workbench, not necessarily every generated rule format. Evidence is outdated when the workbench changed after testing or the test timestamp is missing.
        </Typography.Paragraph>
      </Card></Col>
      <Col xs={24} xl={8}><Card title="Playbook Linkage" loading={loading} style={{ height: '100%' }}>
        <Doughnut data={[
          { name: 'With Playbooks', count: s?.withPlaybooksCount ?? 0, color: c.teal },
          { name: 'Standalone', count: s?.standaloneCount ?? 0, color: c.gray },
        ]} />
        <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>Standalone rules have no linked workbench validation or workflow status.</Typography.Paragraph>
      </Card></Col>
    </Row>
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={16}><Card title="Deployment Overview by Rule Format" loading={loading}>
        {s?.deploymentByFormat.length ? <StableChart height={300}>{width => <BarChart width={width} height={300}
          data={s.deploymentByFormat} margin={{ top: 10, right: 10, bottom: 10, left: 0 }} accessibilityLayer>
          <CartesianGrid stroke={c.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis {...xAxisDefaults} dataKey="name" tick={{ fill: c.text }} stroke={c.grid} /><YAxis {...yAxisDefaults} allowDecimals={false} tick={{ fill: c.muted }} stroke={c.grid} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: c.grid, fillOpacity: .2 }} />
          <Legend formatter={value => <span style={{ color: c.text }}>{value}</span>} />
          <Bar xAxisId={0} yAxisId={0} dataKey="deployed" name="Recorded deployed" stackId="status" fill={c.green} isAnimationActive={false} />
          <Bar xAxisId={0} yAxisId={0} dataKey="testing" name="Testing" stackId="status" fill={c.amber} isAnimationActive={false} />
          <Bar xAxisId={0} yAxisId={0} dataKey="development" name="Other workflow stages" stackId="status" fill={c.blue} isAnimationActive={false} />
          <Bar xAxisId={0} yAxisId={0} dataKey="unlinked" name="No linked workbench" stackId="status" fill={c.gray} isAnimationActive={false} />
        </BarChart>}</StableChart> : <Empty description="No deployment records available" />}
        <Typography.Text type="secondary">Formats identify rule syntax. Deployment reflects linked workbench status; live execution and telemetry health are not collected here.</Typography.Text>
      </Card></Col>
      <Col xs={24} xl={8}><Card title="Needs Attention" loading={loading} style={{ height: '100%' }}>
        <Space orientation="vertical" size={16} style={{ width: '100%' }}>
          <Statistic title="Workbenches with current failed tests" value={s ? failed : '—'} styles={{ content: { color: c.red } }} />
          <Statistic title="Workbenches not tested" value={s ? untested : '—'} styles={{ content: { color: c.gray } }} />
          <Statistic title="Workbenches with outdated test evidence" value={s ? outdated : '—'} styles={{ content: { color: c.amber } }} />
          <Statistic title="Repositories stale or never synced" value={s ? repoData[1].count + repoData[2].count : '—'} styles={{ content: { color: c.amber } }} />
        </Space>
      </Card></Col>
    </Row>
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={12}><Card title="Top Techniques" loading={loading}>
        <HorizontalBars data={techniqueBars(s?.topTechniques ?? [])} onSelect={d => search('technique', d.name)} />
        {techniqueTable(s?.topTechniques ?? [])}
      </Card></Col>
      <Col xs={24} lg={12}><Card title="Top Subtechniques" loading={loading}>
        <HorizontalBars data={techniqueBars(s?.topSubtechniques ?? [])} onSelect={d => search('technique', d.name)} />
        {techniqueTable(s?.topSubtechniques ?? [])}
      </Card></Col>
    </Row>
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={12}><Card title="ATT&CK Mapping" loading={loading}>
        <Row gutter={[16, 16]}><Col xs={24} sm={12}><Statistic title="Rules with technique references" value={s?.rulesWithTechniques ?? '—'} />
          <Typography.Text type="secondary">{percent(s?.rulesWithTechniques ?? 0)}</Typography.Text></Col>
          <Col xs={24} sm={12}><Statistic title="Avg. Techniques per Rule" value={s?.avgTechniquesPerRule ?? '—'} precision={2} /></Col></Row>
        <Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>References are extracted from rule text, including parent techniques derived from subtechniques. They indicate documented mapping; coverage gaps require a defined priority technique set.</Typography.Paragraph>
      </Card></Col>
      <Col xs={24} lg={12}><Card title="Rule Format Breakdown" loading={loading}>
        <HorizontalBars data={(s?.byFormat ?? []).map((d, i) => ({ ...d, color: palette[i % palette.length] }))} />
      </Card></Col>
    </Row>
    <Card title={`Library Maintenance (Last ${seriesDays} Days)`} loading={loading}
      extra={<Segmented options={[{ label: '7d', value: 7 }, { label: '30d', value: 30 }, { label: '90d', value: 90 }]}
        value={seriesDays} onChange={value => setSeriesDays(Number(value))} />}>
      {trend.length ? <StableChart height={280}>{width => <LineChart width={width} height={280} data={trend}
        margin={{ top: 10, right: 20, bottom: 10, left: 0 }} accessibilityLayer>
        <CartesianGrid stroke={c.grid} strokeDasharray="3 3" />
        <XAxis {...xAxisDefaults} dataKey="date" tick={{ fill: c.muted, fontSize: 12 }} stroke={c.grid} minTickGap={35}
          tickFormatter={value => String(value).slice(5)} />
        <YAxis {...yAxisDefaults} allowDecimals={false} tick={{ fill: c.muted }} stroke={c.grid} />
        <Tooltip content={<ChartTooltip />} /><Legend formatter={value => <span style={{ color: c.text }}>{value}</span>} />
        <Line xAxisId={0} yAxisId={0} dataKey="created" name="Created" stroke={c.teal} strokeWidth={3} dot={false} isAnimationActive={false} />
        <Line xAxisId={0} yAxisId={0} dataKey="updated" name="Last modified" stroke={c.purple} strokeWidth={3} strokeDasharray="6 3" dot={false} isAnimationActive={false} />
      </LineChart>}</StableChart> : <Empty description="No trend data available" />}
      <Typography.Text type="secondary">Selected period: {trend.reduce((sum, d) => sum + d.created, 0)} created · {trend.reduce((sum, d) => sum + d.updated, 0)} last modified. Modification counts use each rule’s latest timestamp, not a history of all edits.</Typography.Text>
    </Card>
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={12}><Card title="Repository Health" loading={loading}>
        <Space wrap style={{ marginBottom: 16 }}>{repoData.map(d => <span key={d.name} style={{ color: c.text }}>
          <span aria-hidden style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 3, background: d.color, marginRight: 6 }} />
          {d.name}: <strong>{d.count}</strong>
        </span>)}</Space>
        <Table size="small" rowKey="id" dataSource={repositories} pagination={{ pageSize: 10 }} scroll={{ x: 550 }} columns={[
          { title: 'Repository', dataIndex: 'name', render: (name: string, r) => <Button type="link" size="small" onClick={() => search('repo', r.id)}>{name}</Button> },
          { title: 'Rules', dataIndex: 'ruleCount' },
          { title: 'Last Sync', dataIndex: 'lastSync', render: dateTime },
          { title: 'Status', render: (_, r) => <Tag color={!r.lastSync ? 'default' : r.stale ? 'warning' : 'success'}>{repositoryStatus(r)}</Tag> },
        ]} />
      </Card></Col>
      <Col xs={24} lg={12}><Card title="Tag Analysis" loading={loading}>
        <HorizontalBars data={(s?.topTags ?? []).map((d, i) => ({ name: d.tag, count: d.count, color: palette[i % palette.length] }))}
          onSelect={d => search('tags', d.name)} />
        <Collapse style={{ marginTop: 12 }} items={[{ key: 'pairs', label: 'Tag co-occurrence details', children:
          <Table size="small" rowKey={r => JSON.stringify([r.tagA, r.tagB])} dataSource={s?.tagCooccurrence ?? []}
            pagination={{ pageSize: 5 }} columns={[{ title: 'Tag A', dataIndex: 'tagA' }, { title: 'Tag B', dataIndex: 'tagB' }, { title: 'Rules', dataIndex: 'count' }]} /> }]} />
      </Card></Col>
    </Row>
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={12}><Card title="Change Log" loading={loading}>
        <Table size="small" rowKey="id" pagination={{ pageSize: 10 }} dataSource={s?.recentChanges ?? []} scroll={{ x: 600 }} columns={[
          { title: 'Title', dataIndex: 'title', render: (title: string, r) => <Link to={`/rules/${r.id}`}>{title}</Link> },
          { title: 'Type', dataIndex: 'changeType', render: (value: string) => <Tag color={value === 'DEPRECATED' ? 'error' : value === 'CREATED' ? 'success' : 'processing'}>{value}</Tag> },
          { title: 'Status', dataIndex: 'status', render: (value: string) => <Tag>{value || 'Unknown'}</Tag> },
          { title: 'Updated', dataIndex: 'updatedAt', render: dateTime },
        ]} />
        <Typography.Text type="secondary">Latest rule records; this list does not contain a complete revision history.</Typography.Text>
      </Card></Col>
      <Col xs={24} lg={12}><Card title="Authors & Activity" loading={loading}>
        <HorizontalBars data={(s?.topAuthors ?? []).map(d => ({ ...d, color: c.purple }))} onSelect={d => search('author', d.name)} />
        <Table size="small" rowKey="name" pagination={{ pageSize: 10 }} dataSource={s?.topAuthors ?? []} columns={[
          { title: 'Author', dataIndex: 'name' }, { title: 'Rules', dataIndex: 'count' },
          { title: 'Last Activity', dataIndex: 'lastActivity', render: dateTime },
        ]} />
        <Typography.Text type="secondary">Inactive authors (≥30d): {(s?.inactiveAuthors ?? []).map(a => a.name).join(', ') || 'None'}</Typography.Text>
      </Card></Col>
    </Row>
  </Space>;
};
