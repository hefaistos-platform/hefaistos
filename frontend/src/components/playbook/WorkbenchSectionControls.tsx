import React, { useEffect, useState } from 'react';
import { Button } from '../ui/Button';
import {
  WORKBENCH_PRESETS,
  WORKBENCH_SECTION_KEYS,
  MANDATORY_WORKBENCH_SECTIONS,
  WorkbenchSectionKey,
  ResolvedWorkbenchSectionState,
} from '../../utils/workbenchVisibility';

const WORKBENCH_LAYOUT_DEFAULTS_COLLAPSED_KEY = 'wb-layout-defaults-collapsed';

const SECTION_LABELS: Record<WorkbenchSectionKey, string> = {
  part1: 'Part 1: Detection Strategy',
  part2: 'Part 2: Deep Dive',
  part3: 'Part 3: Detection Rule',
  part4: 'Part 4: SOAR Configuration',
  part5: 'Part 5: Testing & Validation',
  part6: 'Part 6: Review Workflow',
  capabilityMap: 'Capability Abstraction Map',
  capabilityLibrary: 'Capability Abstraction Library',
  activityOverview: 'Activity Overview',
};

interface WorkbenchSectionControlsProps {
  sections: Record<WorkbenchSectionKey, ResolvedWorkbenchSectionState>;
  onToggleSection: (section: WorkbenchSectionKey, value: boolean) => void;
  onApplyPreset: (preset: keyof typeof WORKBENCH_PRESETS) => void;
  onSaveDefaults: () => void;
  savingDefaults?: boolean;
}

export const WorkbenchSectionControls: React.FC<WorkbenchSectionControlsProps> = ({
  sections,
  onToggleSection,
  onApplyPreset,
  onSaveDefaults,
  savingDefaults = false,
}) => {
  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem(WORKBENCH_LAYOUT_DEFAULTS_COLLAPSED_KEY) === '1';
  });

  useEffect(() => {
    window.localStorage.setItem(WORKBENCH_LAYOUT_DEFAULTS_COLLAPSED_KEY, isCollapsed ? '1' : '0');
  }, [isCollapsed]);

  const optionalSections = WORKBENCH_SECTION_KEYS.filter((key) => !MANDATORY_WORKBENCH_SECTIONS.includes(key));
  const lockedSections = WORKBENCH_SECTION_KEYS.filter((key) => sections[key].locked && sections[key].reason);
  const isPresetSelected = (preset: keyof typeof WORKBENCH_PRESETS) => optionalSections.every(
    (key) => sections[key].locked || Boolean(sections[key].visible) === Boolean(WORKBENCH_PRESETS[preset][key]),
  );
  const isSimplePresetSelected = isPresetSelected('SIMPLE');
  const isAdvancedPresetSelected = isPresetSelected('ADVANCED');

  return (
    <div className="mb-6 p-4 rounded-lg border border-gray-200 bg-white space-y-3">
      <button
        type="button"
        className="w-full flex items-center justify-between text-left"
        onClick={() => setIsCollapsed((value) => !value)}
        aria-expanded={!isCollapsed}
      >
        <span className="text-base font-semibold text-gray-800">Workbench Layout Defaults</span>
        <span className="text-xs font-medium text-gray-600">{isCollapsed ? 'Show' : 'Hide'}</span>
      </button>

      {!isCollapsed && (
        <>
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                className={`workbench-defaults-button ${isSimplePresetSelected ? 'workbench-defaults-button-active' : ''}`}
                aria-pressed={isSimplePresetSelected}
                onClick={() => onApplyPreset('SIMPLE')}
              >
                Simple Mode
              </Button>
              <Button
                variant="secondary"
                className={`workbench-defaults-button ${isAdvancedPresetSelected ? 'workbench-defaults-button-active' : ''}`}
                aria-pressed={isAdvancedPresetSelected}
                onClick={() => onApplyPreset('ADVANCED')}
              >
                Advanced Mode
              </Button>
            </div>
            <Button variant="primary" onClick={onSaveDefaults} disabled={savingDefaults}>
              {savingDefaults ? 'Saving…' : 'Save current layout as my default'}
            </Button>
          </div>

          <div className="space-y-2">
            {optionalSections.map((key) => (
              <label key={key} className="flex items-start justify-between gap-3 text-sm">
                <span className="font-medium text-gray-700">{SECTION_LABELS[key]}</span>
                <span className="flex items-center gap-2">
                  {sections[key].locked && sections[key].reason && (
                    <span className="text-xs text-gray-500">{sections[key].reason}</span>
                  )}
                  <input
                    type="checkbox"
                    className="workbench-defaults-checkbox"
                    checked={sections[key].visible}
                    onChange={(event) => onToggleSection(key, event.target.checked)}
                    disabled={sections[key].locked}
                  />
                </span>
              </label>
            ))}
          </div>

          {lockedSections.length > 0 && (
            <div className="pt-2 border-t border-gray-100 text-xs text-gray-500 space-y-1">
              {lockedSections.map((key) => (
                <div key={`${key}-lock`}>
                  {SECTION_LABELS[key]}: {sections[key].reason}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
};
