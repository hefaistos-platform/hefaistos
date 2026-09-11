export type CapabilityAbstractionEntry = {
  id: string;
  abstractionLayer: string;
  componentArtifact: string;
  adversaryPurpose?: string;
  commonEvasions?: string;
  expectedObservables?: string;
  applicableTelemetry?: string;
  detectionValue?: string;
  robustnessLevel?: number;
  sourceKind?: string;
  reviewStatus?: string;
  version?: number;
  organizationName?: string;
  isEditable?: boolean;
  isSharedBaseline?: boolean;
};

export const LAYER_Y: Record<string, number> = {
  NETWORK_BEHAVIOR: 50,
  PROCESS_BEHAVIOR: 280,
  PROTOCOL: 510,
  REGISTRY_OBJECT: 740,
  COM_IPC: 970,
  API_EXPORT: 1200,
  TOOL: 1430,
};

export const LAYER_ORDER = [
  'NETWORK_BEHAVIOR',
  'PROCESS_BEHAVIOR',
  'PROTOCOL',
  'REGISTRY_OBJECT',
  'COM_IPC',
  'API_EXPORT',
  'TOOL',
] as const;

export type LayerBand = { layer: string; y: number; h: number };

export const LAYER_BAND_COLORS: Record<string, string> = {
  NETWORK_BEHAVIOR: '#f0fdf4',
  PROCESS_BEHAVIOR: '#eff6ff',
  PROTOCOL: '#faf5ff',
  REGISTRY_OBJECT: '#fff7ed',
  COM_IPC: '#fefce8',
  API_EXPORT: '#fef2f2',
  TOOL: '#f9fafb',
};

const COMPACT_NODE_HEIGHT = 130;
const NODES_PER_ROW = 4;
const ROW_GAP = 24;
const TOP_OFFSET = 50;
const MIN_BAND_HEIGHT = 170;

export const LAYER_LABELS: Record<string, string> = {
  TOOL: 'Tool / Binary',
  API_EXPORT: 'API / Export',
  COM_IPC: 'COM / IPC',
  REGISTRY_OBJECT: 'Registry Object',
  PROTOCOL: 'Protocol',
  PROCESS_BEHAVIOR: 'Process Behavior',
  NETWORK_BEHAVIOR: 'Network Behavior',
};

export function getRobustnessColor(level?: number): string {
  if ((level ?? 0) >= 5) return '#16a34a';
  if ((level ?? 0) >= 4) return '#2563eb';
  if ((level ?? 0) >= 3) return '#ca8a04';
  if ((level ?? 0) >= 2) return '#ea580c';
  return '#dc2626';
}

export function getRobustnessLabel(level?: number): string {
  const labels: Record<number, string> = {
    1: 'Ephemeral',
    2: 'Weak',
    3: 'Moderate',
    4: 'Strong',
    5: 'Invariant',
  };

  return labels[level ?? 0] ?? 'Unknown';
}

export function computeLayerLayout(
  countsByLayer: Record<string, number>,
  opts?: { nodesPerRow?: number }
): LayerBand[] {
  const nodesPerRow = opts?.nodesPerRow ?? NODES_PER_ROW;
  let y = TOP_OFFSET;
  const bands: LayerBand[] = [];

  for (const layer of LAYER_ORDER) {
    const count = countsByLayer[layer] ?? 0;
    const rows = Math.max(1, Math.ceil(count / nodesPerRow));
    const h = Math.max(MIN_BAND_HEIGHT, rows * COMPACT_NODE_HEIGHT + 40);
    bands.push({ layer, y, h });
    y += h + ROW_GAP;
  }

  return bands;
}

export function positionForEntry(
  band: LayerBand,
  indexInLayer: number,
  opts?: { nodesPerRow?: number; xStart?: number; xPitch?: number }
): { x: number; y: number } {
  const nodesPerRow = opts?.nodesPerRow ?? NODES_PER_ROW;
  const xStart = opts?.xStart ?? 80;
  const xPitch = opts?.xPitch ?? 260;
  const col = indexInLayer % nodesPerRow;
  const row = Math.floor(indexInLayer / nodesPerRow);

  return {
    x: xStart + col * xPitch,
    y: band.y + 30 + row * COMPACT_NODE_HEIGHT,
  };
}
