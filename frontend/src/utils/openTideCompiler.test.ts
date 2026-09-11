import { compileMetadataFromWorkbench } from './openTideCompiler';

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
