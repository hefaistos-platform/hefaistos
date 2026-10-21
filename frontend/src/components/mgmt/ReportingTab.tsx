import React, { useEffect, useMemo, useState } from 'react';
import { gql, useMutation, useQuery } from '@apollo/client';
import { Alert, Button, Card, Checkbox, Col, Empty, Row, Space, Statistic, Table, Typography, message } from 'antd';
import { CheckSquareOutlined, FileExcelOutlined, HistoryOutlined } from '@ant-design/icons';
import { CartesianGrid, Legend, Line, LineChart, Tooltip, XAxis, YAxis } from 'recharts';
import { EXPORT_REPORT_EXCEL, GET_MONTHLY_TRENDS, MonthlySnapshot } from '../../graphql/mgmtAIPrompts';
import { ChartTooltip, Doughnut, HorizontalBars, StableChart, useChartColors, xAxisDefaults, yAxisDefaults } from '../../sections/RuleStatisticsCharts';
import { buildHistoricalData, orderCategories, PRIORITY_ORDER, StatusCount, WORKFLOW_ORDER } from './reportingData';

const { Text, Title } = Typography;
const SHOW_EMPTY_CATEGORIES_KEY = 'mgmt.reporting.showEmptyCategories';
const SORT_BY_COUNT_KEY = 'mgmt.reporting.sortByCountDesc';
const ALL_SECTIONS = ['workbench', 'rules', 'advops', 'ach'] as const;
type SectionKey = typeof ALL_SECTIONS[number];
const SECTION_LABELS: Record<SectionKey, string> = {
  ach: 'ACH Analyses', advops: 'AdvOps Hunts', workbench: 'Detection Workbenches', rules: 'Detection Rules',
};
const ROBUSTNESS_LABELS: Record<string, string> = {
  '0': 'No robustness rating (0)', '1': 'Short-lived indicators (1)', '2': 'Specific tools (2)',
  '3': 'Built-in system tools (3)', '4': 'Attacker behavior (4)', '5': 'Essential attack properties (5)',
};
const titleCase = (value: string) => value.toLowerCase().replace(/(^|\s)\S/g, letter => letter.toUpperCase());
const percentage = (count: number, total: number) => total ? `${(count / total * 100).toFixed(1)}% of total` : 'No items available';
const cardStyle = { height: '100%' };

const MGMT_CAVE_STATS_QUERY = gql`
  query MgmtCaveStats {
    mgmtCaveStats {
      ach {
        total
        createdLast30d
        byStatus { status count }
      }
      advops {
        total
        createdLast30d
        byStatus  { status count }
        byPriority { status count }
      }
      workbench {
        total
        createdLast30d
        activeCount
        byStatus  { status count }
        byRobustness { status count }
      }
      rules {
        total
        createdLast30d
        activeCount
        deprecatedCount
        withPlaybooksCount
        standaloneCount
      }
    }
  }
`;

interface MgmtCaveStats {
  ach: {
    total: number;
    createdLast30d: number;
    byStatus: StatusCount[];
  };
  advops: {
    total: number;
    createdLast30d: number;
    byStatus: StatusCount[];
    byPriority: StatusCount[];
  };
  workbench: {
    total: number;
    createdLast30d: number;
    activeCount: number;
    byStatus: StatusCount[];
    byRobustness: StatusCount[];
  };
  rules: {
    total: number;
    createdLast30d: number;
    activeCount: number;
    deprecatedCount: number;
    withPlaybooksCount: number;
    standaloneCount: number;
  };
}

function downloadBase64File(fileData: string, filename: string, contentType: string) {
  const binary = atob(fileData);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  const blob = new Blob([bytes], { type: contentType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}


function useStatusColor() {
  const c = useChartColors();
  const colors: Record<string, string> = {
    IDEA: c.gray, RESEARCH: c.blue, DEVELOPMENT: c.amber, REVIEW: c.purple,
    TESTING: c.teal, APPROVED: c.green, DEPLOYED: c.green, TUNING: c.amber,
    FINISHED: c.teal, CRITICAL: c.red, HIGH: c.amber, MEDIUM: c.purple, LOW: c.blue, UNCLASSIFIED: c.gray,
  };
  return (status: string) => colors[status] ?? c.gray;
}

function CategoryChart({ data, order, total, unit, showEmpty, sortByCount, robustness = false }: {
  data: StatusCount[]; order: string[]; total: number; unit: string; showEmpty: boolean; sortByCount: boolean; robustness?: boolean;
}) {
  const c = useChartColors();
  const statusColor = useStatusColor();
  const palette = [c.gray, c.amber, c.purple, c.blue, c.teal, c.green];
  const categories = orderCategories(data, order, total, showEmpty, sortByCount);
  return <HorizontalBars unit={unit} minHeight={340} data={categories.map(d => ({
    name: robustness ? ROBUSTNESS_LABELS[d.status] ?? titleCase(d.status) : titleCase(d.status), count: d.count,
    color: robustness ? palette[Number(d.status)] ?? c.gray : statusColor(d.status),
    detail: `${robustness ? ROBUSTNESS_LABELS[d.status] ?? d.status : titleCase(d.status)} · ${percentage(d.count, total)}`,
  }))} />;
}

function HistoricalTrendsPanel() {
  const c = useChartColors();
  const { data, loading, error } = useQuery<{ monthlyTrends: MonthlySnapshot[] }>(GET_MONTHLY_TRENDS, { variables: { months: 6 } });
  const trends = useMemo(() => buildHistoricalData(data?.monthlyTrends ?? []), [data]);
  if (loading) return <Card loading />;
  if (error) return <Alert type="error" showIcon title="Failed to load trend data" description={error.message} />;
  if (!trends.length) return <Empty description="No monthly report snapshots are available yet." />;
  type TrendKey = 'wbActive' | 'rulesActive' | 'achTotal' | 'advopsTotal' | 'wbTotal' | 'rulesTotal';
  const deployment = [
    { key: 'wbActive' as TrendKey, name: 'Recorded deployed workbenches', color: c.green },
    { key: 'rulesActive' as TrendKey, name: 'Rules linked to deployed workbenches', color: c.teal },
  ];
  const inventory = [
    { key: 'achTotal' as TrendKey, name: 'ACH Analyses', color: c.purple },
    { key: 'advopsTotal' as TrendKey, name: 'AdvOps Hunts', color: c.amber },
    { key: 'wbTotal' as TrendKey, name: 'Detection Workbenches', color: c.blue },
    { key: 'rulesTotal' as TrendKey, name: 'Detection Rules', color: c.green },
  ];
  const latest = trends[trends.length - 1];
  const previous = trends[trends.length - 2];
  const renderTrend = (series: typeof inventory) => <>
    <StableChart height={300}>{width => <LineChart width={width} height={300} data={trends}
      margin={{ top: 15, right: 20, left: 0, bottom: 10 }} accessibilityLayer>
      <CartesianGrid stroke={c.grid} strokeDasharray="3 3" />
      <XAxis {...xAxisDefaults} dataKey="label" tick={{ fill: c.muted, fontSize: 12 }} minTickGap={30} stroke={c.grid} />
      <YAxis {...yAxisDefaults} domain={[0, Math.max(1, ...trends.flatMap(row => series.map(s => row[s.key] ?? 0)))]}
        allowDecimals={false} tick={{ fill: c.muted, fontSize: 12 }} stroke={c.grid} />
      <Tooltip content={<ChartTooltip />} />
      <Legend height={48} formatter={value => <span style={{ color: c.text }}>{value}</span>} />
      {series.map((s, i) => <Line key={s.key} xAxisId={0} yAxisId={0} dataKey={s.key} name={s.name} stroke={s.color}
        strokeWidth={3} strokeDasharray={['', '7 3', '2 3', '9 3 2 3'][i]} dot={{ r: 4, fill: s.color }}
        connectNulls={false} isAnimationActive={false} />)}
    </LineChart>}</StableChart>
    <Table size="small" rowKey="name" pagination={false} scroll={{ x: 440 }} dataSource={series.map(s => {
      const value = latest[s.key];
      const earlier = previous?.[s.key];
      const delta = value != null && earlier != null ? value - earlier : null;
      return { name: s.name, value, delta };
    })} columns={[
      { title: 'Measure', dataIndex: 'name' },
      { title: latest.label, dataIndex: 'value', render: (value: number | null) => value == null ? 'Unavailable' : value.toLocaleString() },
      { title: previous ? `Change since ${previous.label}` : 'Change', dataIndex: 'delta',
        render: (value: number | null) => value == null ? 'Unavailable' : `${value > 0 ? '+' : ''}${value.toLocaleString()}` },
    ]} />
  </>;
  return <Space orientation="vertical" size={16} style={{ width: '100%' }}>
    <Text type="secondary">Monthly snapshots · Missing values appear as gaps. Changes compare the two latest available snapshots.</Text>
    <Card title="Recorded Deployment Trends">{renderTrend(deployment)}
      <Text type="secondary">Recorded workflow status does not confirm live execution or platform health.</Text>
    </Card>
    <Card title="Portfolio Inventory Trends">{renderTrend(inventory)}</Card>
  </Space>;
}

function CustomReportBuilder() {
  const [selectedSections, setSelectedSections] = useState<SectionKey[]>([...ALL_SECTIONS]);
  const [exportExcel, { loading }] = useMutation(EXPORT_REPORT_EXCEL);
  const exportSelected = async () => {
    if (!selectedSections.length) return;
    try {
      const res = await exportExcel({ variables: { sections: ALL_SECTIONS.filter(key => selectedSections.includes(key)) } });
      const payload = res.data?.exportReportExcel;
      if (!payload?.success || !payload.fileData) { message.error(payload?.message || 'Export failed.'); return; }
      downloadBase64File(payload.fileData, payload.filename, payload.contentType);
      message.success('Excel report downloaded.');
    } catch (err: any) { message.error(err?.message || 'Export failed.'); }
  };
  return <Card title="Choose Report Sections">
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Text type="secondary">Choose which sections to include in your Excel report.</Text>
      {ALL_SECTIONS.map(key => <Checkbox key={key} checked={selectedSections.includes(key)} onChange={event =>
        setSelectedSections(previous => event.target.checked ? [...previous, key] : previous.filter(s => s !== key))}>
        {SECTION_LABELS[key]}
      </Checkbox>)}
      <Space wrap><Button aria-label="Export selected sections" icon={<FileExcelOutlined />} type="primary" loading={loading} disabled={!selectedSections.length}
        onClick={exportSelected}>Export selected sections</Button><Text type="secondary">{selectedSections.length} of 4 sections selected</Text></Space>
    </Space>
  </Card>;
}

export const ReportingTab: React.FC = () => {
  const c = useChartColors();
  const statusColor = useStatusColor();
  const { data, loading, error, refetch } = useQuery<{ mgmtCaveStats: MgmtCaveStats }>(MGMT_CAVE_STATS_QUERY, { notifyOnNetworkStatusChange: true });
  const [exportExcel, { loading: exportingExcel }] = useMutation(EXPORT_REPORT_EXCEL);
  const [activeView, setActiveView] = useState<'current' | 'trends' | 'builder'>('current');
  const [showEmpty, setShowEmpty] = useState(() => window.localStorage.getItem(SHOW_EMPTY_CATEGORIES_KEY) === '1');
  const [sortByCount, setSortByCount] = useState(() => window.localStorage.getItem(SORT_BY_COUNT_KEY) === '1');
  const stats = data?.mgmtCaveStats;
  useEffect(() => { window.localStorage.setItem(SHOW_EMPTY_CATEGORIES_KEY, showEmpty ? '1' : '0'); }, [showEmpty]);
  useEffect(() => { window.localStorage.setItem(SORT_BY_COUNT_KEY, sortByCount ? '1' : '0'); }, [sortByCount]);
  const exportAll = async () => {
    try {
      const res = await exportExcel({ variables: { sections: null } });
      const payload = res.data?.exportReportExcel;
      if (!payload?.success || !payload.fileData) { message.error(payload?.message || 'Export failed.'); return; }
      downloadBase64File(payload.fileData, payload.filename, payload.contentType);
      message.success('Excel report downloaded.');
    } catch (err: any) { message.error(err?.message || 'Export failed.'); }
  };
  const pending = stats?.workbench.byStatus.filter(d => ['REVIEW', 'TESTING'].includes(d.status)).reduce((sum, d) => sum + d.count, 0) ?? 0;
  const portfolio = [
    { key: 'ach' as const, color: c.purple }, { key: 'advops' as const, color: c.amber },
    { key: 'workbench' as const, color: c.blue }, { key: 'rules' as const, color: c.teal },
  ];
  const summary = (title: string, value: number | undefined, color: string, description: string) => <Card loading={loading}
    style={{ height: '100%', borderTop: `3px solid ${color}` }}><Statistic title={title} value={value ?? '—'} styles={{ content: { color } }} />
    <Text type="secondary">{description}</Text></Card>;
  const chartProps = { showEmpty, sortByCount };

  return <Space orientation="vertical" size={20} style={{ width: '100%', minWidth: 0 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
      <Space wrap>
        <Button type={activeView === 'current' ? 'primary' : 'default'} onClick={() => setActiveView('current')}>Current Report</Button>
        <Button aria-label="Historical Trends" icon={<HistoryOutlined />} type={activeView === 'trends' ? 'primary' : 'default'} onClick={() => setActiveView('trends')}>Historical Trends</Button>
        <Button aria-label="Custom Report" icon={<CheckSquareOutlined />} type={activeView === 'builder' ? 'primary' : 'default'} onClick={() => setActiveView('builder')}>Custom Report</Button>
      </Space>
      <Space wrap>
        {activeView === 'current' && <Button onClick={() => refetch()} loading={loading}>Refresh report</Button>}
        <Button aria-label="Export all sections" icon={<FileExcelOutlined />} onClick={exportAll} loading={exportingExcel}>Export all sections</Button>
      </Space>
    </div>
    {activeView === 'trends' && <><Title level={4} style={{ margin: 0 }}>Historical Trends</Title><HistoricalTrendsPanel /></>}
    {activeView === 'builder' && <><Title level={4} style={{ margin: 0 }}>Custom Report</Title><CustomReportBuilder /></>}
    {activeView === 'current' && <>
      {error && <Alert type="error" showIcon title="Failed to load report data" description={error.message} action={<Button onClick={() => refetch()}>Retry</Button>} />}
      {!loading && !error && !stats && <Empty description="No report data available" />}
      <section aria-label="Portfolio Summary">
        <Title level={4} style={{ marginTop: 0 }}>Portfolio Summary</Title>
        <Row gutter={[16, 16]}>{portfolio.map(d => <Col key={d.key} xs={24} sm={12} xl={6}>
          {summary(SECTION_LABELS[d.key], stats?.[d.key].total, d.color,
            `New in last 30 days: ${stats?.[d.key].createdLast30d ?? '—'}`)}
        </Col>)}</Row>
        <Text type="secondary">ACH = Analysis of Competing Hypotheses. Totals count records in each area; one workbench can produce several rule formats.</Text>
      </section>
      <section aria-label="Deployment & Attention">
        <Title level={4} style={{ marginTop: 0 }}>Deployment & Attention</Title>
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} xl={6}>{summary('Recorded deployed workbenches', stats?.workbench.activeCount, c.green,
            stats ? percentage(stats.workbench.activeCount, stats.workbench.total) : 'Awaiting report data')}</Col>
          <Col xs={24} sm={12} xl={6}>{summary('Rules linked to deployed workbenches', stats?.rules.activeCount, c.teal,
            stats ? percentage(stats.rules.activeCount, stats.rules.total) : 'Awaiting report data')}</Col>
          <Col xs={24} sm={12} xl={6}>{summary('Workbenches awaiting review or testing', stats ? pending : undefined, c.amber,
            'Pending workflow stages; no deadline or overdue status is inferred')}</Col>
          <Col xs={24} sm={12} xl={6}>{summary('Standalone rules', stats?.rules.standaloneCount, c.gray,
            'Rules without a linked detection workbench')}</Col>
        </Row>
        <Text type="secondary">Deployment is recorded workflow status. Live execution and platform health require separate operational evidence.</Text>
      </section>
      <Space wrap>
        <Checkbox checked={showEmpty} onChange={event => setShowEmpty(event.target.checked)}>Show empty categories</Checkbox>
        <Checkbox checked={sortByCount} onChange={event => setSortByCount(event.target.checked)}>Sort by count (descending)</Checkbox>
        <Text type="secondary">Default order follows workflow stages, priority, and robustness level.</Text>
      </Space>
      <section aria-label="Detection Workbenches">
        <Title level={4} style={{ marginTop: 0 }}>Detection Workbenches</Title>
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}><Card title="Workflow Status" loading={loading} style={cardStyle}>
            <CategoryChart {...chartProps} data={stats?.workbench.byStatus ?? []} order={WORKFLOW_ORDER} total={stats?.workbench.total ?? 0} unit="Workbenches" />
          </Card></Col>
          <Col xs={24} lg={12}><Card title="Robustness Distribution" loading={loading} style={cardStyle}>
            <CategoryChart {...chartProps} data={stats?.workbench.byRobustness ?? []} order={['0', '1', '2', '3', '4', '5']} total={stats?.workbench.total ?? 0} unit="Workbenches" robustness />
            <Text type="secondary">Higher levels describe detections based on more enduring attacker behavior. This rating does not measure test success or production health.</Text>
          </Card></Col>
        </Row>
      </section>
      <section aria-label="Detection Rules">
        <Title level={4} style={{ marginTop: 0 }}>Detection Rules</Title>
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}><Card title="Workbench Linkage" loading={loading} style={cardStyle}>
            <Doughnut data={[
              { name: 'With Workbench', count: stats?.rules.withPlaybooksCount ?? 0, color: c.teal },
              { name: 'Standalone', count: stats?.rules.standaloneCount ?? 0, color: c.gray },
            ]} />
          </Card></Col>
          <Col xs={24} lg={12}><Card title="Deployment & Deprecation" loading={loading} style={cardStyle}>
            <Space orientation="vertical" size={24} style={{ width: '100%' }}>
              <div><Statistic title="Rules linked to deployed workbenches" value={stats?.rules.activeCount ?? '—'} styles={{ content: { color: c.green } }} />
                <Text type="secondary">{stats ? percentage(stats.rules.activeCount, stats.rules.total) : 'Awaiting report data'}</Text></div>
              <div><Statistic title="Rules marked deprecated" value={stats?.rules.deprecatedCount ?? '—'} styles={{ content: { color: c.red } }} />
                <Text type="secondary">{stats ? percentage(stats.rules.deprecatedCount, stats.rules.total) : 'Awaiting report data'}</Text></div>
              <Text type="secondary">These measures can overlap: a deprecated rule may still be linked to a deployed workbench.</Text>
            </Space>
          </Card></Col>
        </Row>
      </section>
      <section aria-label="AdvOps Hunts">
        <Title level={4} style={{ marginTop: 0 }}>AdvOps Hunts</Title>
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}><Card title="Hunt Workflow Status" loading={loading} style={cardStyle}>
            <CategoryChart {...chartProps} data={stats?.advops.byStatus ?? []} order={WORKFLOW_ORDER} total={stats?.advops.total ?? 0} unit="Hunts" />
          </Card></Col>
          <Col xs={24} lg={12}><Card title="Hunt Priority" loading={loading} style={cardStyle}>
            <CategoryChart {...chartProps} data={stats?.advops.byPriority ?? []} order={PRIORITY_ORDER} total={stats?.advops.total ?? 0} unit="Hunts" />
          </Card></Col>
        </Row>
      </section>
      <section aria-label="ACH Analyses">
        <Title level={4} style={{ marginTop: 0 }}>ACH Analyses</Title>
        <Card title="Analysis Status" loading={loading}>
          <Row gutter={[24, 16]} align="middle"><Col xs={24} lg={12}>
            <Doughnut unit="analyses" data={orderCategories(stats?.ach.byStatus ?? [], ['RESEARCH', 'FINISHED', 'APPROVED'], stats?.ach.total ?? 0, showEmpty, sortByCount)
              .map(d => ({ name: titleCase(d.status), count: d.count, color: statusColor(d.status) }))} />
          </Col><Col xs={24} lg={12}><Text>Analysis of Competing Hypotheses helps evaluate competing explanations for observed activity.</Text>
            <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>Status shows how far analyses have progressed. It does not establish deployment or detection coverage.</Typography.Paragraph>
          </Col></Row>
        </Card>
      </section>
      <section aria-label="Portfolio Comparison">
        <Title level={4} style={{ marginTop: 0 }}>Portfolio Comparison</Title>
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}><Card title="Total Inventory" loading={loading} style={cardStyle}>
            <HorizontalBars unit="Records" data={stats ? portfolio.map(d => ({ name: SECTION_LABELS[d.key], count: stats[d.key].total, color: d.color })) : []} />
          </Card></Col>
          <Col xs={24} lg={12}><Card title="New in Last 30 Days" loading={loading} style={cardStyle}>
            <HorizontalBars unit="New records" data={stats ? portfolio.map(d => ({ name: SECTION_LABELS[d.key], count: stats[d.key].createdLast30d, color: d.color })) : []} />
          </Card></Col>
        </Row>
      </section>
    </>}
  </Space>;
};
export default ReportingTab;
