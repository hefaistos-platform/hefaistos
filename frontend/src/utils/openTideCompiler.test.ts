import { compileMetadataFromWorkbench, getConfiguredPlatforms, restoreOpenTideRule } from './openTideCompiler';
import { DETECTION_FORMAT_REGISTRY } from '../components/detectionFormatRegistry';
import { OpenTideRule } from '../types/opentide';

describe('restoreOpenTideRule', () => {
  const graph = { title: 'Pulled Workbench', goal: 'Imported detection context' };

  it.each(['{}', {}, null, undefined, 'null', '[]', '{broken', { platforms: null }])(
    'restores an imported KQL query from incomplete saved data: %p',
    (saved) => {
      const rule = restoreOpenTideRule(graph, saved, 'DeviceEvents | take 10', 'KQL');

      // Both the Workbench badges and editor tabs previously dereferenced missing platforms.
      expect(getConfiguredPlatforms(rule)).toEqual(['kql']);
      expect(DETECTION_FORMAT_REGISTRY.find((entry) => entry.format === 'KQL')!.getContent(rule))
        .toBe('DeviceEvents | take 10');
      expect(rule.metadata.title).toBe(graph.title);
    },
  );

  it('opens an empty pulled Workbench without configured platforms', () => {
    const rule = restoreOpenTideRule(graph, '{}', '', 'KQL');
    expect(getConfiguredPlatforms(rule)).toEqual([]);
    for (const entry of DETECTION_FORMAT_REGISTRY) expect(entry.getContent(rule)).toBe('');
  });

  it.each([
    ['EQL', 'elastic', 'process where true'],
    ['SPL', 'spl', 'index=security'],
    ['WAZUH', 'wazuh', '<rule id="100001" />'],
    ['AQL', 'qradar', 'SELECT * FROM events'],
  ] as const)('restores an imported %s rule into its editor tab', (format, platform, content) => {
    const rule = restoreOpenTideRule(graph, '{}', content, format);
    expect(getConfiguredPlatforms(rule)).toEqual([platform]);
    expect(DETECTION_FORMAT_REGISTRY.find((entry) => entry.format === format)!.getContent(rule)).toBe(content);
  });

  it.each([false, true])('preserves saved queries and recompiles metadata (JSON string: %p)', (encoded) => {
    const saved = {
      metadata: { title: 'Old title' },
      platforms: { kql: { query: 'saved query', data_source: 'DeviceEvents' }, spl: { query: 'index=saved' } },
    };
    const rule = restoreOpenTideRule(graph, encoded ? JSON.stringify(saved) : saved, 'legacy query', 'KQL');
    expect(rule.platforms).toEqual(saved.platforms);
    expect(getConfiguredPlatforms(rule)).toEqual(['kql', 'spl']);
    expect(rule.metadata.title).toBe(graph.title);
    expect(rule.metadata.description).toBe(graph.goal);
  });

  it('preserves FREE-format details when the saved payload has no platforms', () => {
    const freeRule = { content: 'title: Sigma detection', label: 'Sigma', language: 'yaml', extension: 'yml' };
    const rule = restoreOpenTideRule(graph, JSON.stringify({ freeRule }), freeRule.content, 'FREE');
    expect(rule.freeRule).toEqual(freeRule);
    expect(getConfiguredPlatforms(rule)).toEqual([]);
    expect(DETECTION_FORMAT_REGISTRY.find((entry) => entry.format === 'FREE')!.getContent(rule)).toBe(freeRule.content);
  });

  it('restores FREE content when no structured rule was saved', () => {
    expect(restoreOpenTideRule(graph, '{}', 'manual content', 'FREE').freeRule?.content).toBe('manual content');
  });

  it('respects explicitly saved empty platforms', () => {
    expect(restoreOpenTideRule(graph, { platforms: {} }, 'legacy query', 'KQL').platforms).toEqual({});
  });

  it('handles missing platforms defensively when listing configured platforms', () => {
    expect(getConfiguredPlatforms({} as OpenTideRule)).toEqual([]);
  });
});

describe('compileMetadataFromWorkbench', () => {
  it('includes capability abstractions and focus layer in metadata', () => {
    const metadata = compileMetadataFromWorkbench({
      title: 'Workbench Detection',
      goal: 'Detect malicious mshta execution',
      author: { username: 'analyst' },
      mitreTechnique: { techniqueId: 'T1218.005', name: 'Mshta' },
      technicalContext: 'mshta launching remote script content',
      detectionFocusLayer: 'PROCESS_BEHAVIOR',
      selectedCapabilityAbstractions: [
        {
          abstractionLayer: 'PROCESS_BEHAVIOR',
          componentArtifact: 'mshta child process chain',
          detectionValue: 'Behavior anchor',
          robustnessLevel: 4,
        },
      ],
    });

    expect(metadata.capability.detection_focus_layer).toBe('PROCESS_BEHAVIOR');
    expect(metadata.capability.abstractions).toEqual([
      {
        layer: 'PROCESS_BEHAVIOR',
        component_artifact: 'mshta child process chain',
        detection_value: 'Behavior anchor',
        robustness_level: 4,
      },
    ]);
  });
});
