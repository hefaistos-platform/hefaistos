import {
  computeLayerLayout,
  getRobustnessColor,
  getRobustnessLabel,
  LAYER_LABELS,
  LAYER_ORDER,
  LAYER_Y,
  positionForEntry,
} from './capabilityAbstractionUtils';

describe('capabilityAbstractionUtils', () => {
  it('maps robustness levels to colors', () => {
    expect(getRobustnessColor(5)).toBe('#16a34a');
    expect(getRobustnessColor(4)).toBe('#2563eb');
    expect(getRobustnessColor(3)).toBe('#ca8a04');
    expect(getRobustnessColor(2)).toBe('#ea580c');
    expect(getRobustnessColor(1)).toBe('#dc2626');
  });

  it('maps robustness levels to labels with fallback', () => {
    expect(getRobustnessLabel(1)).toBe('Ephemeral');
    expect(getRobustnessLabel(5)).toBe('Invariant');
    expect(getRobustnessLabel(undefined)).toBe('Unknown');
  });

  it('includes expected layer metadata', () => {
    expect(LAYER_Y.PROCESS_BEHAVIOR).toBe(280);
    expect(LAYER_LABELS.NETWORK_BEHAVIOR).toBe('Network Behavior');
  });

  it('computes dynamic layer bands from counts', () => {
    const bands = computeLayerLayout({
      NETWORK_BEHAVIOR: 5,
      PROCESS_BEHAVIOR: 0,
      TOOL: 9,
    });

    expect(bands).toHaveLength(LAYER_ORDER.length);
    expect(bands[0]).toEqual({ layer: 'NETWORK_BEHAVIOR', y: 50, h: 300 });
    expect(bands[1]).toEqual({ layer: 'PROCESS_BEHAVIOR', y: 374, h: 170 });
    expect(bands[bands.length - 1]).toEqual({ layer: 'TOOL', y: 1344, h: 430 });
  });

  it('positions entries within a layer band grid', () => {
    const [networkBand] = computeLayerLayout({ NETWORK_BEHAVIOR: 5 });

    expect(positionForEntry(networkBand, 0)).toEqual({ x: 80, y: 80 });
    expect(positionForEntry(networkBand, 3)).toEqual({ x: 860, y: 80 });
    expect(positionForEntry(networkBand, 4)).toEqual({ x: 80, y: 210 });
  });
});
