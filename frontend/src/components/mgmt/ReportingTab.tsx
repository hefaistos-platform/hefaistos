import React, { useEffect, useMemo, useRef, useState } from 'react';
import { gql, useMutation, useQuery } from '@apollo/client';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Divider,
  Empty,
  Row,
  Space,
  Spin,
  Statistic,
  Tag,
  Tooltip as AntTooltip,
  Typography,
  message,
} from 'antd';
import {
  CheckSquareOutlined,
  FileExcelOutlined,
  FilePdfOutlined,
  HistoryOutlined,
} from '@ant-design/icons';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Line,
  LineChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  EXPORT_REPORT_EXCEL,
  GET_MONTHLY_TRENDS,
  MonthlySnapshot,
} from '../../graphql/mgmtAIPrompts';
import { useTheme } from '../../context/ThemeContext';

const { Text, Title } = Typography;
const SHOW_EMPTY_CATEGORIES_KEY = 'mgmt.reporting.showEmptyCategories';
const SORT_BY_COUNT_KEY = 'mgmt.reporting.sortByCountDesc';

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

const STATUS_COLORS: Record<string, string> = {
  IDEA: '#94a3b8',
  RESEARCH: '#3b82f6',
  DEVELOPMENT: '#f59e0b',
  REVIEW: '#a855f7',
  TESTING: '#06b6d4',
  APPROVED: '#22c55e',
  DEPLOYED: '#15803d',
  TUNING: '#f97316',
  FINISHED: '#0ea5a4',
  CRITICAL: '#dc2626',
  HIGH: '#ea580c',
  MEDIUM: '#ca8a04',
  LOW: '#0284c7',
};

function statusColor(status: string): string {
  return STATUS_COLORS[status.toUpperCase()] ?? '#1677ff';
}

const ROBUSTNESS_LABELS: Record<string, string> = {
  '0': 'None (0)',
  '1': 'Ephemeral (1)',
  '2': 'Tool (2)',
  '3': 'LOLBin (3)',
  '4': 'Behavior (4)',
  '5': 'Invariant (5)',
};

const ALL_SECTIONS = ['ach', 'advops', 'workbench', 'rules'] as const;
type SectionKey = typeof ALL_SECTIONS[number];

const SECTION_LABELS: Record<SectionKey, string> = {
  ach: 'ACH Analyses',
  advops: 'AdvOps Hunts',
  workbench: 'Detection Workbenches',
  rules: 'Detection Rules',
};

interface StatusCount {
  status: string;
  count: number;
}

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

function StableChart({
  height,
  minWidth = 0,
  render,
}: {
  height: number;
  minWidth?: number;
  render: (size: { width: number; height: number }) => React.ReactNode;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return undefined;

    const updateWidth = () => {
      const nextWidth = Math.floor(node.getBoundingClientRect().width);
      setWidth((prev) => (prev !== nextWidth ? nextWidth : prev));
    };

    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(node);
    window.addEventListener('resize', updateWidth);

    return () => {
      observer.disconnect();
      window.removeEventListener('resize', updateWidth);
    };
  }, []);

  const effectiveWidth = Math.max(width, minWidth);

  return (
    <div ref={containerRef} style={{ width: '100%', minWidth, height }}>
      {effectiveWidth > 0 ? render({ width: effectiveWidth, height }) : null}
    </div>
  );
}

function StatusBarChart({
  data,
  colorFn,
  isDark,
  showEmpty,
  sortByCount,
}: {
  data: StatusCount[];
  colorFn: (s: string) => string;
  isDark: boolean;
  showEmpty: boolean;
  sortByCount: boolean;
}) {
  const filteredData = data.filter((d) => showEmpty || d.count > 0);
  const orderedData = sortByCount
    ? [...filteredData].sort((a, b) => {
        if (b.count !== a.count) return b.count - a.count;
        return a.status.localeCompare(b.status);
      })
    : filteredData;
  const chartData = orderedData.map((d) => ({ name: d.status, count: d.count }));
  const chartHeight = Math.max(220, chartData.length * 34 + 36);
  const mutedZero = isDark ? '#334155' : '#d9d9d9';
  const tickColor = isDark ? '#d1d5db' : '#475569';
  const labelColor = isDark ? '#f3f4f6' : '#0f172a';
  const gridColor = isDark ? '#334155' : '#e2e8f0';

  if (chartData.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No data available" />;
  }

  return (
    <StableChart
      height={chartHeight}
      minWidth={280}
      render={({ width, height }) => (
        <BarChart
          width={width}
          height={height}
          data={chartData}
          layout="vertical"
          margin={{ top: 8, right: 16, bottom: 8, left: 18 }}
        >
          <CartesianGrid stroke={gridColor} strokeDasharray="3 3" />
          <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11, fill: tickColor }} />
          <YAxis type="category" dataKey="name" width={96} tick={{ fontSize: 11, fill: tickColor }} />
          <Tooltip
            formatter={(value: number) => [value, 'Count']}
            contentStyle={{
              backgroundColor: isDark ? '#111827' : '#ffffff',
              borderColor: isDark ? '#334155' : '#d9d9d9',
              color: labelColor,
            }}
            labelStyle={{ color: labelColor }}
            itemStyle={{ color: labelColor }}
          />
          <Bar dataKey="count" barSize={18} minPointSize={6} radius={[0, 6, 6, 0]}>
            {chartData.map((entry) => (
              <Cell
                key={entry.name}
                fill={entry.count === 0 ? mutedZero : colorFn(entry.name)}
                fillOpacity={entry.count === 0 ? 0.45 : 0.95}
                stroke={entry.count === 0 ? mutedZero : colorFn(entry.name)}
                strokeOpacity={entry.count === 0 ? 0.6 : 1}
              />
            ))}
            <LabelList
              dataKey="count"
              position="right"
              fill={labelColor}
              fontSize={12}
              formatter={(value: number) => (value > 0 ? String(value) : showEmpty ? '0' : '')}
            />
          </Bar>
        </BarChart>
      )}
    />
  );
}

// ---------------------------------------------------------------------------
// Historical Trends Panel
// ---------------------------------------------------------------------------
function HistoricalTrendsPanel({ isDark }: { isDark: boolean }) {
  const { data, loading, error } = useQuery<{ monthlyTrends: MonthlySnapshot[] }>(
    GET_MONTHLY_TRENDS,
    { variables: { months: 6 } },
  );

  const snapshots = data?.monthlyTrends ?? [];
  const tickColor = isDark ? '#d1d5db' : '#475569';
  const labelColor = isDark ? '#f3f4f6' : '#0f172a';
  const gridColor = isDark ? '#334155' : '#e2e8f0';

  const trendData = useMemo(() =>
    snapshots.map((snap) => {
      let stats: Record<string, any> = {};
      try { stats = typeof snap.stats === 'string' ? JSON.parse(snap.stats) : snap.stats; } catch {}
      return {
        label: snap.label,
        achTotal: stats?.ach?.total ?? 0,
        advopsTotal: stats?.advops?.total ?? 0,
        wbTotal: stats?.workbench?.total ?? 0,
        wbActive: stats?.workbench?.active_count ?? 0,
        rulesTotal: stats?.rules?.total ?? 0,
        rulesActive: stats?.rules?.active_count ?? 0,
      };
    }),
  [snapshots]);

  if (loading) return <Spin tip="Loading historical trends..." />;
  if (error) return <Alert type="error" showIcon message="Failed to load trend data" description={error.message} />;
  if (trendData.length === 0) {
    return (
      <Empty
        description="No historical snapshots yet. Snapshots are captured automatically each month via the capture_monthly_snapshot management command."
      />
    );
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={16}>
      <Card title="Total Items by Domain (Month-over-Month)" size="small">
        <StableChart
          height={240}
          render={({ width, height }) => (
            <LineChart width={width} height={height} data={trendData} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={gridColor} strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: tickColor }} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: tickColor }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: isDark ? '#111827' : '#ffffff',
                  borderColor: isDark ? '#334155' : '#d9d9d9',
                  color: labelColor,
                }}
                labelStyle={{ color: labelColor }}
                itemStyle={{ color: labelColor }}
              />
              <Legend />
              <Line type="monotone" dataKey="achTotal" name="ACH" stroke="#722ed1" strokeWidth={2} dot />
              <Line type="monotone" dataKey="advopsTotal" name="AdvOps" stroke="#fa8c16" strokeWidth={2} dot />
              <Line type="monotone" dataKey="wbTotal" name="Workbenches" stroke="#1677ff" strokeWidth={2} dot />
              <Line type="monotone" dataKey="rulesTotal" name="Rules" stroke="#52c41a" strokeWidth={2} dot />
            </LineChart>
          )}
        />
      </Card>
      <Card title="Active / Deployed (Month-over-Month)" size="small">
        <StableChart
          height={220}
          render={({ width, height }) => (
            <LineChart width={width} height={height} data={trendData} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={gridColor} strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: tickColor }} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: tickColor }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: isDark ? '#111827' : '#ffffff',
                  borderColor: isDark ? '#334155' : '#d9d9d9',
                  color: labelColor,
                }}
                labelStyle={{ color: labelColor }}
                itemStyle={{ color: labelColor }}
              />
              <Legend />
              <Line type="monotone" dataKey="wbActive" name="Deployed Workbenches" stroke="#389e0d" strokeWidth={2} dot />
              <Line type="monotone" dataKey="rulesActive" name="Active Rules" stroke="#13c2c2" strokeWidth={2} dot />
            </LineChart>
          )}
        />
      </Card>
    </Space>
  );
}

// ---------------------------------------------------------------------------
// Custom Report Builder
// ---------------------------------------------------------------------------
function CustomReportBuilder() {
  const [selectedSections, setSelectedSections] = useState<SectionKey[]>([...ALL_SECTIONS]);
  const [exportExcel, { loading: exportingExcel }] = useMutation(EXPORT_REPORT_EXCEL);

  const handleToggle = (key: SectionKey, checked: boolean) => {
    setSelectedSections((prev) =>
      checked ? [...prev, key] : prev.filter((s) => s !== key),
    );
  };

  const handleExportExcel = async () => {
    if (selectedSections.length === 0) {
      message.warning('Select at least one section to export.');
      return;
    }
    try {
      const res = await exportExcel({ variables: { sections: selectedSections } });
      const payload = res.data?.exportReportExcel;
      if (!payload?.success || !payload.fileData) {
        message.error(payload?.message || 'Export failed.');
        return;
      }
      downloadBase64File(payload.fileData, payload.filename, payload.contentType);
      message.success('Excel report downloaded.');
    } catch (err: any) {
      message.error(err?.message || 'Export failed.');
    }
  };

  return (
    <Card
      size="small"
      title={<><CheckSquareOutlined /> Custom Report Builder</>}
      extra={
        <Space>
          <AntTooltip title="Export selected sections as Excel (.xlsx)">
            <Button
              icon={<FileExcelOutlined />}
              onClick={handleExportExcel}
              loading={exportingExcel}
              disabled={selectedSections.length === 0}
            >
              Export Excel
            </Button>
          </AntTooltip>
        </Space>
      }
    >
      <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
        Select which sections to include in the exported report.
      </Text>
      <Space wrap>
        {ALL_SECTIONS.map((key) => (
          <Checkbox
            key={key}
            checked={selectedSections.includes(key)}
            onChange={(e) => handleToggle(key, e.target.checked)}
          >
            {SECTION_LABELS[key]}
          </Checkbox>
        ))}
      </Space>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main Reporting Tab
// ---------------------------------------------------------------------------
export const ReportingTab: React.FC = () => {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const tickColor = isDark ? '#d1d5db' : '#475569';
  const labelColor = isDark ? '#f3f4f6' : '#0f172a';
  const gridColor = isDark ? '#334155' : '#e2e8f0';
  const { data, loading, error } = useQuery<{ mgmtCaveStats: MgmtCaveStats }>(MGMT_CAVE_STATS_QUERY);
  const [exportExcel, { loading: exportingExcel }] = useMutation(EXPORT_REPORT_EXCEL);
  const [activeView, setActiveView] = useState<'current' | 'trends' | 'builder'>('current');
  const [showEmptyCategories, setShowEmptyCategories] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem(SHOW_EMPTY_CATEGORIES_KEY) === '1';
  });
  const [sortCategoriesByCount, setSortCategoriesByCount] = useState<boolean>(() => {
    if (typeof window === 'undefined') return true;
    const saved = window.localStorage.getItem(SORT_BY_COUNT_KEY);
    return saved == null ? true : saved === '1';
  });
  const stats = data?.mgmtCaveStats;

  useEffect(() => {
    // Recharts can render blank when parent width is measured before Tabs layout settles.
    // Triggering a resize after view changes forces a reliable recalculation.
    const id = window.setTimeout(() => {
      window.dispatchEvent(new Event('resize'));
    }, 60);
    return () => window.clearTimeout(id);
  }, [activeView, loading]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(SHOW_EMPTY_CATEGORIES_KEY, showEmptyCategories ? '1' : '0');
  }, [showEmptyCategories]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(SORT_BY_COUNT_KEY, sortCategoriesByCount ? '1' : '0');
  }, [sortCategoriesByCount]);

  const overviewTrend = useMemo(() => ([
    { name: 'ACH', total: stats?.ach.total ?? 0, createdLast30d: stats?.ach.createdLast30d ?? 0 },
    { name: 'AdvOps', total: stats?.advops.total ?? 0, createdLast30d: stats?.advops.createdLast30d ?? 0 },
    { name: 'Workbench', total: stats?.workbench.total ?? 0, createdLast30d: stats?.workbench.createdLast30d ?? 0 },
    { name: 'Rules', total: stats?.rules.total ?? 0, createdLast30d: stats?.rules.createdLast30d ?? 0 },
  ]), [stats]);

  const handleExportAllExcel = async () => {
    try {
      const res = await exportExcel({ variables: { sections: null } });
      const payload = res.data?.exportReportExcel;
      if (!payload?.success || !payload.fileData) {
        message.error(payload?.message || 'Export failed.');
        return;
      }
      downloadBase64File(payload.fileData, payload.filename, payload.contentType);
      message.success('Excel report downloaded.');
    } catch (err: any) {
      message.error(err?.message || 'Export failed.');
    }
  };

  return (
    <div style={{ padding: '0 4px' }}>
      {loading && (
        <div style={{ marginBottom: 16 }}>
          <Spin tip="Loading monthly report data..." />
        </div>
      )}
      {error && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message="Failed to load report data"
          description={error.message}
        />
      )}

      {/* Toolbar */}
      <div
        style={{
          marginBottom: 16,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          flexWrap: 'nowrap',
          overflowX: 'auto',
        }}
      >
        <Space size={8} wrap={false}>
          <Button
            type={activeView === 'current' ? 'primary' : 'default'}
            onClick={() => setActiveView('current')}
          >
            Current Report
          </Button>
          <Button
            icon={<HistoryOutlined />}
            type={activeView === 'trends' ? 'primary' : 'default'}
            onClick={() => setActiveView('trends')}
          >
            Historical Trends
          </Button>
          <Button
            icon={<CheckSquareOutlined />}
            type={activeView === 'builder' ? 'primary' : 'default'}
            onClick={() => setActiveView('builder')}
          >
            Custom Report
          </Button>
        </Space>
        <Space size={12} wrap={false}>
          {activeView === 'current' && (
            <>
              <Checkbox
                checked={showEmptyCategories}
                onChange={(e) => setShowEmptyCategories(e.target.checked)}
              >
                Show empty categories
              </Checkbox>
              <Checkbox
                checked={sortCategoriesByCount}
                onChange={(e) => setSortCategoriesByCount(e.target.checked)}
              >
                Sort by count (desc)
              </Checkbox>
            </>
          )}
          <AntTooltip title="Export full report as Excel (.xlsx)">
            <Button
              icon={<FileExcelOutlined />}
              onClick={handleExportAllExcel}
              loading={exportingExcel}
            >
              Export Excel
            </Button>
          </AntTooltip>
        </Space>
      </div>

      {/* Historical Trends View */}
      {activeView === 'trends' && (
        <>
          <Title level={4} style={{ marginTop: 0 }}>Historical Trends (Month-over-Month)</Title>
          <HistoricalTrendsPanel isDark={isDark} />
        </>
      )}

      {/* Custom Report Builder View */}
      {activeView === 'builder' && (
        <>
          <Title level={4} style={{ marginTop: 0 }}>Custom Report Builder</Title>
          <CustomReportBuilder />
        </>
      )}

      {/* Current Report View */}
      {activeView === 'current' && (
        <>
          <Title level={4} style={{ marginTop: 0 }}>Cross-Domain Overview</Title>
          <Card loading={loading} style={{ marginBottom: 24 }} title="Total vs Created (30d)">
            <StableChart
              height={220}
              minWidth={300}
              render={({ width, height }) => (
                <LineChart width={width} height={height} data={overviewTrend} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke={gridColor} strokeDasharray="3 3" />
                  <XAxis dataKey="name" tick={{ fill: tickColor }} />
                  <YAxis allowDecimals={false} tick={{ fill: tickColor }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: isDark ? '#111827' : '#ffffff',
                      borderColor: isDark ? '#334155' : '#d9d9d9',
                      color: labelColor,
                    }}
                    labelStyle={{ color: labelColor }}
                    itemStyle={{ color: labelColor }}
                  />
                  <Legend />
                  <Line type="monotone" dataKey="total" name="Total" stroke="#1677ff" strokeWidth={2} />
                  <Line type="monotone" dataKey="createdLast30d" name="Created (30d)" stroke="#52c41a" strokeWidth={2} />
                </LineChart>
              )}
            />
          </Card>

          {/* ACH */}
          <Title level={4} style={{ marginTop: 0 }}>ACH Analyses</Title>
          <Row gutter={[16, 16]}>
            <Col xs={12} md={6}>
              <Card loading={loading}>
                <Statistic title="Total Analyses" value={stats?.ach.total ?? 0} />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card loading={loading}>
                <Statistic title="Created (30d)" value={stats?.ach.createdLast30d ?? 0} />
              </Card>
            </Col>
            <Col xs={24} md={12}>
              <Card title="By Status" loading={loading}>
                <StatusBarChart
                  data={stats?.ach.byStatus ?? []}
                  colorFn={statusColor}
                  isDark={isDark}
                  showEmpty={showEmptyCategories}
                  sortByCount={sortCategoriesByCount}
                />
              </Card>
            </Col>
          </Row>

          {/* AdvOps */}
          <Title level={4} style={{ marginTop: 24 }}>AdvOps Hunts</Title>
          <Row gutter={[16, 16]}>
            <Col xs={12} md={6}>
              <Card loading={loading}>
                <Statistic title="Total Hunts" value={stats?.advops.total ?? 0} />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card loading={loading}>
                <Statistic title="Created (30d)" value={stats?.advops.createdLast30d ?? 0} />
              </Card>
            </Col>
            <Col xs={24} md={12}>
              <Row gutter={[16, 16]}>
                <Col xs={24} sm={12}>
                  <Card title="By Status" loading={loading}>
                    <StatusBarChart
                      data={stats?.advops.byStatus ?? []}
                      colorFn={statusColor}
                      isDark={isDark}
                      showEmpty={showEmptyCategories}
                      sortByCount={sortCategoriesByCount}
                    />
                  </Card>
                </Col>
                <Col xs={24} sm={12}>
                  <Card title="By Priority" loading={loading}>
                    <StatusBarChart
                      data={stats?.advops.byPriority ?? []}
                      colorFn={statusColor}
                      isDark={isDark}
                      showEmpty={showEmptyCategories}
                      sortByCount={sortCategoriesByCount}
                    />
                  </Card>
                </Col>
              </Row>
            </Col>
          </Row>

          {/* Workbench */}
          <Title level={4} style={{ marginTop: 24 }}>Detection Workbenches</Title>
          <Row gutter={[16, 16]}>
            <Col xs={12} md={4}>
              <Card loading={loading}>
                <Statistic title="Total Workbenches" value={stats?.workbench.total ?? 0} />
              </Card>
            </Col>
            <Col xs={12} md={4}>
              <Card loading={loading}>
                <Statistic title="Created (30d)" value={stats?.workbench.createdLast30d ?? 0} />
              </Card>
            </Col>
            <Col xs={12} md={4}>
              <Card loading={loading}>
                <AntTooltip title="Workbenches with status DEPLOYED — rule has been pushed to GitHub and the target platform and is actively running.">
                  <Statistic
                    title="Active (Deployed)"
                    value={stats?.workbench.activeCount ?? 0}
                    valueStyle={{ color: '#389e0d' }}
                  />
                </AntTooltip>
              </Card>
            </Col>
            <Col xs={24} md={12}>
              <Row gutter={[16, 16]}>
                <Col xs={24} sm={12}>
                  <Card title="By Status" loading={loading}>
                    <StatusBarChart
                      data={stats?.workbench.byStatus ?? []}
                      colorFn={statusColor}
                      isDark={isDark}
                      showEmpty={showEmptyCategories}
                      sortByCount={sortCategoriesByCount}
                    />
                  </Card>
                </Col>
                <Col xs={24} sm={12}>
                  <Card title="By Robustness Level" loading={loading}>
                    <StatusBarChart
                      data={(stats?.workbench.byRobustness ?? []).map((d) => ({
                        status: ROBUSTNESS_LABELS[d.status] ?? d.status,
                        count: d.count,
                      }))}
                      colorFn={() => '#1677ff'}
                      isDark={isDark}
                      showEmpty={showEmptyCategories}
                      sortByCount={sortCategoriesByCount}
                    />
                  </Card>
                </Col>
              </Row>
            </Col>
          </Row>

          {/* Rules */}
          <Title level={4} style={{ marginTop: 24 }}>Detection Rules</Title>
          <Row gutter={[16, 16]}>
            <Col xs={12} md={4}>
              <Card loading={loading}>
                <Statistic title="Total Rules" value={stats?.rules.total ?? 0} />
              </Card>
            </Col>
            <Col xs={12} md={4}>
              <Card loading={loading}>
                <Statistic title="Created (30d)" value={stats?.rules.createdLast30d ?? 0} />
              </Card>
            </Col>
            <Col xs={12} md={4}>
              <Card loading={loading}>
                <Statistic
                  title="Active"
                  value={stats?.rules.activeCount ?? 0}
                  valueStyle={{ color: '#52c41a' }}
                />
              </Card>
            </Col>
            <Col xs={12} md={4}>
              <Card loading={loading}>
                <Statistic
                  title="Deprecated"
                  value={stats?.rules.deprecatedCount ?? 0}
                  valueStyle={{ color: '#cf1322' }}
                />
              </Card>
            </Col>
            <Col xs={12} md={4}>
              <Card loading={loading}>
                <Statistic title="With Workbench" value={stats?.rules.withPlaybooksCount ?? 0} />
              </Card>
            </Col>
            <Col xs={12} md={4}>
              <Card loading={loading}>
                <Statistic title="Standalone" value={stats?.rules.standaloneCount ?? 0} />
              </Card>
            </Col>
          </Row>

          <Divider />
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {Object.entries(STATUS_COLORS).map(([s, c]) => (
              <Tag key={s} color={c} style={{ marginBottom: 4 }}>{s}</Tag>
            ))}
          </div>
        </>
      )}
    </div>
  );
};

export default ReportingTab;
