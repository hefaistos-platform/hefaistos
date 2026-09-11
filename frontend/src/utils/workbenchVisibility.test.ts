import {
  WORKBENCH_PRESETS,
  normalizeVisibilityLayer,
  resolveWorkbenchSections,
} from './workbenchVisibility';

describe('workbench visibility resolver', () => {
  test('enforces mandatory sections even when lower layers hide them', () => {
    const resolved = resolveWorkbenchSections({
      userDefaults: normalizeVisibilityLayer({
        sectionVisibility: {
          part1: false,
          part2: false,
          part3: false,
          part6: false,
        },
      }),
    });

    expect(resolved.sections.part1.visible).toBe(true);
    expect(resolved.sections.part2.visible).toBe(true);
    expect(resolved.sections.part3.visible).toBe(true);
    expect(resolved.sections.part6.visible).toBe(true);
    expect(resolved.sections.part1.locked).toBe(true);
    expect(resolved.sections.part1.reason).toBe('Required section');
  });

  test('applies precedence order system > org > local > user', () => {
    // System wins even when everything else disagrees
    const resolved = resolveWorkbenchSections({
      system: normalizeVisibilityLayer({ sectionVisibility: { part4: false } }),
      organization: normalizeVisibilityLayer({ sectionVisibility: { part4: true } }),
      userDefaults: normalizeVisibilityLayer({ sectionVisibility: { part4: true } }),
      localState: { part4: true },
    });

    expect(resolved.sections.part4.visible).toBe(false);

    // Local session state overrides saved user defaults
    const resolvedLocalOverride = resolveWorkbenchSections({
      userDefaults: normalizeVisibilityLayer({ sectionVisibility: { part4: true } }),
      localState: { part4: false },
    });

    expect(resolvedLocalOverride.sections.part4.visible).toBe(false);
  });

  test('simple and advanced presets map to expected optional visibility', () => {
    expect(WORKBENCH_PRESETS.SIMPLE.part4).toBe(false);
    expect(WORKBENCH_PRESETS.SIMPLE.part5).toBe(false);
    expect(WORKBENCH_PRESETS.SIMPLE.capabilityMap).toBe(false);
    expect(WORKBENCH_PRESETS.SIMPLE.capabilityLibrary).toBe(false);
    expect(WORKBENCH_PRESETS.SIMPLE.activityOverview).toBe(false);
    expect(WORKBENCH_PRESETS.ADVANCED.part4).toBe(true);
    expect(WORKBENCH_PRESETS.ADVANCED.part5).toBe(true);
    expect(WORKBENCH_PRESETS.ADVANCED.capabilityMap).toBe(true);
    expect(WORKBENCH_PRESETS.ADVANCED.capabilityLibrary).toBe(true);
    expect(WORKBENCH_PRESETS.ADVANCED.activityOverview).toBe(true);
  });

  test('new sections default to visible when no layer specifies them', () => {
    const resolved = resolveWorkbenchSections({});
    expect(resolved.sections.capabilityMap.visible).toBe(true);
    expect(resolved.sections.capabilityLibrary.visible).toBe(true);
    expect(resolved.sections.activityOverview.visible).toBe(true);
    expect(resolved.sections.capabilityMap.locked).toBe(false);
    expect(resolved.sections.capabilityLibrary.locked).toBe(false);
    expect(resolved.sections.activityOverview.locked).toBe(false);
  });

  test('new sections can be independently toggled via local state', () => {
    const resolved = resolveWorkbenchSections({
      localState: { capabilityMap: false, activityOverview: false },
    });
    expect(resolved.sections.capabilityMap.visible).toBe(false);
    expect(resolved.sections.capabilityLibrary.visible).toBe(true);
    expect(resolved.sections.activityOverview.visible).toBe(false);
  });
});
