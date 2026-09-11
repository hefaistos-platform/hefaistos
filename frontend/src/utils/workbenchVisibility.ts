export const WORKBENCH_SECTION_KEYS = [
  'part1',
  'part2',
  'part3',
  'part4',
  'part5',
  'part6',
  'capabilityMap',
  'capabilityLibrary',
  'activityOverview',
] as const;
export type WorkbenchSectionKey = (typeof WORKBENCH_SECTION_KEYS)[number];

export type WorkbenchSectionVisibilityMap = Partial<Record<WorkbenchSectionKey, boolean>>;

export interface WorkbenchVisibilityLayer {
  sectionVisibility?: WorkbenchSectionVisibilityMap;
  lockedSections?: WorkbenchSectionKey[];
  mandatorySections?: WorkbenchSectionKey[];
}

export interface ResolvedWorkbenchSectionState {
  key: WorkbenchSectionKey;
  visible: boolean;
  locked: boolean;
  reason?: string;
}

export const MANDATORY_WORKBENCH_SECTIONS: WorkbenchSectionKey[] = ['part1', 'part2', 'part3', 'part6'];

export const WORKBENCH_PRESETS: Record<'SIMPLE' | 'ADVANCED', WorkbenchSectionVisibilityMap> = {
  SIMPLE: {
    part1: true,
    part2: true,
    part3: true,
    part4: false,
    part5: false,
    part6: true,
    capabilityMap: false,
    capabilityLibrary: false,
    activityOverview: false,
  },
  ADVANCED: {
    part1: true,
    part2: true,
    part3: true,
    part4: true,
    part5: true,
    part6: true,
    capabilityMap: true,
    capabilityLibrary: true,
    activityOverview: true,
  },
};

const isSectionKey = (value: string): value is WorkbenchSectionKey =>
  (WORKBENCH_SECTION_KEYS as readonly string[]).includes(value);

const normalizeVisibilityMap = (raw: unknown): WorkbenchSectionVisibilityMap => {
  if (!raw || typeof raw !== 'object') return {};
  const normalized: WorkbenchSectionVisibilityMap = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (!isSectionKey(key)) continue;
    normalized[key] = Boolean(value);
  }
  return normalized;
};

export const normalizeVisibilityLayer = (raw: unknown): WorkbenchVisibilityLayer => {
  if (!raw) return {};
  let payload: unknown = raw;
  if (typeof raw === 'string') {
    try {
      payload = JSON.parse(raw);
    } catch {
      return {};
    }
  }
  if (!payload || typeof payload !== 'object') return {};
  const obj = payload as Record<string, unknown>;
  const mandatorySections = Array.isArray(obj.mandatorySections)
    ? obj.mandatorySections.filter((key): key is WorkbenchSectionKey => isSectionKey(String(key)))
    : [];
  const lockedSections = Array.isArray(obj.lockedSections)
    ? obj.lockedSections.filter((key): key is WorkbenchSectionKey => isSectionKey(String(key)))
    : [];
  return {
    sectionVisibility: normalizeVisibilityMap(obj.sectionVisibility),
    mandatorySections,
    lockedSections,
  };
};

const getSectionVisibilityFromLayer = (layer: WorkbenchVisibilityLayer | undefined, key: WorkbenchSectionKey): boolean | undefined =>
  layer?.sectionVisibility && key in layer.sectionVisibility ? Boolean(layer.sectionVisibility[key]) : undefined;

export const resolveWorkbenchSections = (input: {
  system?: WorkbenchVisibilityLayer;
  organization?: WorkbenchVisibilityLayer;
  userDefaults?: WorkbenchVisibilityLayer;
  localState?: WorkbenchSectionVisibilityMap;
}) => {
  const system = input.system ?? {};
  const organization = input.organization ?? {};
  const userDefaults = input.userDefaults ?? {};
  const localState = input.localState ?? {};

  const mandatory = new Set<WorkbenchSectionKey>([
    ...MANDATORY_WORKBENCH_SECTIONS,
    ...(system.mandatorySections ?? []),
    ...(organization.mandatorySections ?? []),
  ]);
  const systemLocked = new Set<WorkbenchSectionKey>(system.lockedSections ?? []);
  const organizationLocked = new Set<WorkbenchSectionKey>(organization.lockedSections ?? []);

  const sections: Record<WorkbenchSectionKey, ResolvedWorkbenchSectionState> = {
    part1: { key: 'part1', visible: true, locked: false },
    part2: { key: 'part2', visible: true, locked: false },
    part3: { key: 'part3', visible: true, locked: false },
    part4: { key: 'part4', visible: true, locked: false },
    part5: { key: 'part5', visible: true, locked: false },
    part6: { key: 'part6', visible: true, locked: false },
    capabilityMap: { key: 'capabilityMap', visible: true, locked: false },
    capabilityLibrary: { key: 'capabilityLibrary', visible: true, locked: false },
    activityOverview: { key: 'activityOverview', visible: true, locked: false },
  };

  WORKBENCH_SECTION_KEYS.forEach((key) => {
    const resolvedValue =
      getSectionVisibilityFromLayer(system, key)
      ?? getSectionVisibilityFromLayer(organization, key)
      ?? (key in localState ? Boolean(localState[key]) : undefined)
      ?? getSectionVisibilityFromLayer(userDefaults, key)
      ?? true;

    let visible = resolvedValue;
    let locked = false;
    let reason: string | undefined;

    if (mandatory.has(key)) {
      visible = true;
      locked = true;
      reason = 'Required section';
    } else if (systemLocked.has(key)) {
      visible = true;
      locked = true;
      reason = 'Locked by system policy';
    } else if (organizationLocked.has(key)) {
      visible = true;
      locked = true;
      reason = 'Locked by organization policy';
    }

    sections[key] = { key, visible, locked, reason };
  });

  return {
    sections,
    visibility: Object.fromEntries(
      WORKBENCH_SECTION_KEYS.map((key) => [key, sections[key].visible]),
    ) as Record<WorkbenchSectionKey, boolean>,
  };
};
