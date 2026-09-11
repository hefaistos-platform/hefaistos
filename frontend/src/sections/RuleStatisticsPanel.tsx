import React from 'react';
import { gql } from '@apollo/client';
import { useQuery } from '@apollo/client/react';
import { Card, Col, Row, Statistic, Table, Typography } from 'antd';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, CartesianGrid } from 'recharts';

type RuleStatisticsQueryVars = {
  topN?: number;
  seriesDays?: number;
};

type RuleStatisticsQuery = {
  ruleStatistics?: {
    total?: number;
    createdLast24h?: number;
    createdLast7d?: number;
    createdLast30d?: number;
    unchanged90dPlus?: number;
    sigmaCount?: number;    activeCount?: number;
    deprecatedCount?: number;
    avgTechniquesPerRule?: number;
    withPlaybooksCount?: number;
    standaloneCount?: number;
    topTechniques?: Array<{ techniqueId: string; count: number }>;
    topSubtechniques?: Array<{ techniqueId: string; count: number }>;
    createdSeries?: Array<{ date: string; count: number }>;
    updatedSeries?: Array<{ date: string; count: number }>;
    repositories?: Array<{ id: string; name: string; ruleCount: number; lastSync: string; stale: boolean }>;
    topTags?: Array<{ tag: string; count: number }>;
    tagCooccurrence?: Array<{ tagA: string; tagB: string; count: number }>;
    topAuthors?: Array<{ name: string; count: number; lastActivity: string }>;
    inactiveAuthors?: Array<{ name: string; count: number; lastActivity: string }>;
    recentChanges?: Array<{ id: string; title: string; status: string; createdAt: string; updatedAt: string; changeType: string }>;
  };
};

const RULE_STATS_QUERY = gql`
  query RuleStatistics($topN: Int, $seriesDays: Int) {
    ruleStatistics(topN: $topN, seriesDays: $seriesDays) {
      total
      createdLast24h
      createdLast7d
      createdLast30d
      unchanged90dPlus
      activeCount
      deprecatedCount
      avgTechniquesPerRule
      withPlaybooksCount
      standaloneCount
      topTechniques { techniqueId count }
      topSubtechniques { techniqueId count }
      createdSeries { date count }
      updatedSeries { date count }
      repositories { id name ruleCount lastSync stale }
      topTags { tag count }
      tagCooccurrence { tagA tagB count }
      topAuthors { name count lastActivity }
      inactiveAuthors { name count lastActivity }
      recentChanges { id title status createdAt updatedAt changeType }
    }
  }
`;

export const RuleStatisticsPanel: React.FC = () => {
  const [seriesDays, setSeriesDays] = React.useState<number>(30);
  const { data, loading, error, refetch } = useQuery<RuleStatisticsQuery, RuleStatisticsQueryVars>(
    RULE_STATS_QUERY,
    { variables: { topN: 10, seriesDays } }
  );
  const stats = data?.ruleStatistics;
  const handleSeriesDays = (days: number) => {
    setSeriesDays(days);
    refetch({ topN: 10, seriesDays: days });
  };


  const columns = [
    { title: 'Technique', dataIndex: 'techniqueId', key: 'techniqueId' },
    { title: 'Count', dataIndex: 'count', key: 'count', sorter: (a: any, b: any) => a.count - b.count },
  ];

  return (
    <div>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12} lg={6}>
          <Card loading={loading}>
            <Statistic title="Total Rules" value={stats?.total ?? 0} />
          </Card>
        </Col>
        <Col xs={24} md={12} lg={6}>
          <Card loading={loading}>
            <Statistic title="Created (24h)" value={stats?.createdLast24h ?? 0} />
          </Card>
        </Col>
        <Col xs={24} md={12} lg={6}>
          <Card loading={loading}>
            <Statistic title="Created (7d)" value={stats?.createdLast7d ?? 0} />
          </Card>
        </Col>
        <Col xs={24} md={12} lg={6}>
          <Card loading={loading}>
            <Statistic title="Created (30d)" value={stats?.createdLast30d ?? 0} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} md={12} lg={6}>
          <Card loading={loading}>
            <Statistic title="Unchanged (≥90d)" value={stats?.unchanged90dPlus ?? 0} />
          </Card>
        </Col>
        <Col xs={24} md={12} lg={6}>
          <Card loading={loading}>
            <Statistic title="Active Rules" value={stats?.activeCount ?? 0} />
          </Card>
        </Col>
        <Col xs={24} md={12} lg={6}>
          <Card loading={loading}>
            <Statistic title="Deprecated Rules" value={stats?.deprecatedCount ?? 0} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} md={8}>
          <Card loading={loading}>
            <Statistic title="Avg. Techniques per Rule" value={stats?.avgTechniquesPerRule ?? 0} precision={2} />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card loading={loading}>
            <Statistic title="With Playbooks" value={stats?.withPlaybooksCount ?? 0} />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card loading={loading}>
            <Statistic title="Standalone" value={stats?.standaloneCount ?? 0} />
          </Card>
        </Col>
      </Row>

      {error && <Typography.Text type="danger">Failed to load statistics: {error.message}</Typography.Text>}

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card title="Top Techniques" loading={loading}>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={(stats?.topTechniques ?? []).map((t: any) => ({ name: t.techniqueId, count: t.count }))}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" hide={false} />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" fill="#1677ff" />
              </BarChart>
            </ResponsiveContainer>
            <Table
              size="small"
              pagination={{ pageSize: 10 }}
              columns={columns as any}
              dataSource={(stats?.topTechniques ?? []).map((t: any) => ({ ...t, key: t.techniqueId }))}
              style={{ marginTop: 12 }}
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Top Subtechniques" loading={loading}>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={(stats?.topSubtechniques ?? []).map((t: any) => ({ name: t.techniqueId, count: t.count }))}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" hide={false} />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" fill="#52c41a" />
              </BarChart>
            </ResponsiveContainer>
            <Table
              size="small"
              pagination={{ pageSize: 10 }}
              columns={columns as any}
              dataSource={(stats?.topSubtechniques ?? []).map((t: any) => ({ ...t, key: t.techniqueId }))}
              style={{ marginTop: 12 }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24}>
          <Card title={`Trend Analysis (Last ${seriesDays} Days)`} loading={loading} extra={
            <div style={{ display: 'flex', gap: 8 }}>
              <a onClick={() => handleSeriesDays(7)}>7d</a>
              <a onClick={() => handleSeriesDays(30)}>30d</a>
              <a onClick={() => handleSeriesDays(90)}>90d</a>
            </div>
          }>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={(stats?.createdSeries ?? []).map((p: any, i: number) => ({ ...p, updated: stats?.updatedSeries?.[i]?.count ?? 0 }))}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Line type="monotone" dataKey="count" name="Created" stroke="#faad14" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="updated" name="Updated" stroke="#722ed1" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card title="Repository Health" loading={loading}>
            <Table
              size="small"
              pagination={{ pageSize: 10 }}
              columns={[
                { title: 'Repository', dataIndex: 'name', key: 'name' },
                { title: 'Rules', dataIndex: 'ruleCount', key: 'ruleCount' },
                { title: 'Last Sync', dataIndex: 'lastSync', key: 'lastSync', render: (v: any) => v ? new Date(v).toLocaleString() : '—' },
                { title: 'Stale', dataIndex: 'stale', key: 'stale', render: (v: boolean) => v ? 'Yes' : 'No' },
              ] as any}
              dataSource={(stats?.repositories ?? []).map((r: any) => ({ ...r, key: r.id }))}
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Tag Analytics" loading={loading}>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={(stats?.topTags ?? []).map((t: any) => ({ name: t.tag, count: t.count }))}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" fill="#13c2c2" />
              </BarChart>
            </ResponsiveContainer>
            <Table
              size="small"
              pagination={{ pageSize: 10 }}
              columns={[
                { title: 'Tag A', dataIndex: 'tagA', key: 'tagA' },
                { title: 'Tag B', dataIndex: 'tagB', key: 'tagB' },
                { title: 'Co-occurrence', dataIndex: 'count', key: 'count' },
              ] as any}
              dataSource={(stats?.tagCooccurrence ?? []).map((p: any, idx: number) => ({ ...p, key: idx }))}
              style={{ marginTop: 12 }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card title="Change Log" loading={loading}>
            <Table
              size="small"
              pagination={{ pageSize: 10 }}
              columns={[
                { title: 'Title', dataIndex: 'title', key: 'title' },
                { title: 'Type', dataIndex: 'changeType', key: 'changeType' },
                { title: 'Status', dataIndex: 'status', key: 'status' },
                { title: 'Updated', dataIndex: 'updatedAt', key: 'updatedAt', render: (v: any) => v ? new Date(v).toLocaleString() : '—' },
              ] as any}
              dataSource={(stats?.recentChanges ?? []).map((c: any) => ({ ...c, key: c.id }))}
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Authors & Activity" loading={loading}>
              <Table
                size="small"
                pagination={{ pageSize: 10 }}
                columns={[
                  { title: 'Author', dataIndex: 'name', key: 'name' },
                  { title: 'Rules', dataIndex: 'count', key: 'count' },
                  { title: 'Last Activity', dataIndex: 'lastActivity', key: 'lastActivity', render: (v: any) => v ? new Date(v).toLocaleString() : '—' },
                ] as any}
                dataSource={(stats?.topAuthors ?? []).map((a: any, idx: number) => ({ ...a, key: idx }))}
            />
            <Typography.Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
              Inactive authors (≥30d): {(stats?.inactiveAuthors ?? []).map((a: any) => a.name).join(', ') || 'None'}
            </Typography.Text>
          </Card>
        </Col>
      </Row>
    </div>
  );
};
