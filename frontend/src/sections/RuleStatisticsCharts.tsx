import React from 'react';
import { Empty, Typography } from 'antd';
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Pie, PieChart, Tooltip, XAxis, YAxis } from 'recharts';
import { useTheme } from '../context/ThemeContext';

export type ChartDatum = { name: string; count: number; color?: string; detail?: string };
// Recharts 2 uses function defaultProps for axes, which React 19 no longer applies.
// Explicit defaults prevent missing axis dimensions from producing NaN coordinates.
export const xAxisDefaults = {
  orientation: 'bottom' as const, width: 0, height: 30, xAxisId: 0, type: 'category' as const,
  tickCount: 5, scale: 'auto' as const, padding: { left: 0, right: 0 },
  allowDuplicatedCategory: true, allowDataOverflow: false, reversed: false, mirror: false, hide: false,
};
export const yAxisDefaults = {
  orientation: 'left' as const, width: 60, height: 0, yAxisId: 0, type: 'number' as const,
  tickCount: 5, scale: 'auto' as const, padding: { top: 0, bottom: 0 },
  allowDuplicatedCategory: true, allowDataOverflow: false, reversed: false, mirror: false, hide: false,
};
export function useChartColors() {
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === 'dark';
  return {
    text: dark ? '#f1f5f9' : '#172033', muted: dark ? '#cbd5e1' : '#475569',
    grid: dark ? '#475569' : '#cbd5e1', surface: dark ? '#1e293b' : '#ffffff',
    blue: dark ? '#60a5fa' : '#2563eb', green: dark ? '#4ade80' : '#15803d',
    red: dark ? '#fb7185' : '#be123c', amber: dark ? '#fbbf24' : '#a16207',
    gray: dark ? '#94a3b8' : '#64748b', purple: dark ? '#c084fc' : '#7e22ce',
    teal: dark ? '#2dd4bf' : '#0f766e',
  };
}

export function StableChart({ height, children }: {
  height: number; children: (width: number) => React.ReactNode;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [width, setWidth] = React.useState(0);
  React.useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const measure = () => setWidth(Math.floor(node.getBoundingClientRect().width));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    window.addEventListener('resize', measure);
    return () => { observer.disconnect(); window.removeEventListener('resize', measure); };
  }, []);
  return <div ref={ref} style={{ width: '100%', minWidth: 0, height }}>{width > 0 && children(width)}</div>;
}

export function ChartTooltip({ active, payload, label }: {
  active?: boolean; label?: React.ReactNode;
  payload?: ReadonlyArray<{ name?: string; value?: string | number; payload?: { detail?: string } }>;
}) {
  const c = useChartColors();
  if (!active || !payload?.length) return null;
  return <div style={{ background: c.surface, color: c.text, border: `1px solid ${c.grid}`,
    padding: '10px 14px', borderRadius: 8, boxShadow: '0 4px 16px #0003', maxWidth: 300 }}>
    {label != null && <strong>{label}</strong>}
    {payload.map((p, i) => <div key={i}>{p.name}: <strong>{p.value}</strong></div>)}
    {payload[0]?.payload?.detail && <div>{payload[0].payload.detail}</div>}
  </div>;
}

export function Doughnut({ data, unit = 'rules', onSelect }: {
  data: ChartDatum[]; unit?: string; onSelect?: (datum: ChartDatum) => void;
}) {
  const c = useChartColors();
  const total = data.reduce((sum, d) => sum + d.count, 0);
  if (!total) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={`No ${unit} available`} />;
  return <div>
    <div role="img" aria-label={data.map(d => `${d.name}: ${d.count}`).join(', ')}>
      <StableChart height={210}>{width => <PieChart width={width} height={210} accessibilityLayer>
        <Pie data={data.filter(d => d.count > 0)} dataKey="count" nameKey="name" innerRadius={58} outerRadius={88}
          cx="50%" cy="50%" startAngle={0} endAngle={360} minAngle={0}
          paddingAngle={2} stroke={c.surface} strokeWidth={3} isAnimationActive={false}
          onClick={(_, index) => onSelect?.(data.filter(d => d.count > 0)[index])}>
          {data.filter(d => d.count > 0).map(d => <Cell key={d.name} fill={d.color || c.blue} cursor={onSelect ? 'pointer' : undefined} />)}
        </Pie>
        <text x={width / 2} y={100} textAnchor="middle" fill={c.text} fontSize={26} fontWeight={600}>{total.toLocaleString()}</text>
        <text x={width / 2} y={123} textAnchor="middle" fill={c.muted} fontSize={12}>{unit}</text>
        <Tooltip content={<ChartTooltip />} />
      </PieChart>}</StableChart>
    </div>
    <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
      {data.map(d => <li key={d.name} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '5px 0', color: c.text }}>
        <span aria-hidden style={{ width: 12, height: 12, borderRadius: 3, background: d.color || c.blue, flexShrink: 0 }} />
        {onSelect ? <button onClick={() => onSelect(d)} style={{ background: 'none', border: 0, padding: 0,
          color: c.blue, cursor: 'pointer', font: 'inherit', textAlign: 'left' }}>{d.name}</button> : <span>{d.name}</span>}
        <span style={{ marginLeft: 'auto', whiteSpace: 'nowrap' }}><strong>{d.count.toLocaleString()}</strong> · {(d.count / total * 100).toFixed(1)}%</span>
      </li>)}
    </ul>
  </div>;
}

export function HorizontalBars({ data, onSelect }: { data: ChartDatum[]; onSelect?: (datum: ChartDatum) => void }) {
  const c = useChartColors();
  if (!data.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No data available" />;
  const height = Math.max(230, data.length * 36 + 40);
  return <div role="img" aria-label={data.map(d => `${d.name}: ${d.count}`).join(', ')}>
    <StableChart height={height}>{width => <BarChart width={width} height={height} data={data} layout="vertical"
      margin={{ top: 5, right: 40, bottom: 5, left: 0 }} accessibilityLayer>
      <CartesianGrid stroke={c.grid} strokeDasharray="3 3" horizontal={false} />
      <XAxis {...xAxisDefaults} type="number" allowDecimals={false} tick={{ fill: c.muted, fontSize: 12 }} stroke={c.grid} />
      <YAxis {...yAxisDefaults} type="category" dataKey="name" width={Math.min(160, width * .4)} tick={{ fill: c.text, fontSize: 12 }}
        tickFormatter={value => String(value).length > 22 ? `${String(value).slice(0, 21)}…` : String(value)} stroke={c.grid} />
      <Tooltip content={<ChartTooltip />} cursor={{ fill: c.grid, fillOpacity: .2 }} />
      <Bar xAxisId={0} yAxisId={0} dataKey="count" name="Rules" radius={[0, 4, 4, 0]} isAnimationActive={false}
        onClick={(_, index) => onSelect?.(data[index])}>
        {data.map(d => <Cell key={d.name} fill={d.color || c.blue} cursor={onSelect ? 'pointer' : undefined} />)}
        <LabelList dataKey="count" position="right" fill={c.text} />
      </Bar>
    </BarChart>}</StableChart>
    {onSelect && <Typography.Text type="secondary">Select a bar to view matching rules.</Typography.Text>}
  </div>;
}
