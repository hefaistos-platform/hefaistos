import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { WorkbenchSectionControls } from './WorkbenchSectionControls';
import { WorkbenchSectionKey } from '../../utils/workbenchVisibility';

const buildSections = (
  overrides: Partial<Record<WorkbenchSectionKey, Partial<{ visible: boolean; locked: boolean; reason: string }>>> = {},
) => {
  const sections: Record<WorkbenchSectionKey, { key: WorkbenchSectionKey; visible: boolean; locked: boolean; reason?: string }> = {
    part1: { key: 'part1' as const, visible: true, locked: true, reason: 'Required section' },
    part2: { key: 'part2' as const, visible: true, locked: true, reason: 'Required section' },
    part3: { key: 'part3' as const, visible: true, locked: true, reason: 'Required section' },
    part4: { key: 'part4' as const, visible: true, locked: false },
    part5: { key: 'part5' as const, visible: true, locked: false },
    part6: { key: 'part6' as const, visible: true, locked: true, reason: 'Required section' },
  };
  (Object.keys(overrides) as WorkbenchSectionKey[]).forEach((key) => {
    sections[key] = { ...sections[key], ...(overrides[key] || {}) };
  });
  return sections;
};

describe('WorkbenchSectionControls', () => {
  test('renders lock reason text for locked sections', () => {
    render(
      <WorkbenchSectionControls
        sections={buildSections({ part4: { locked: true, reason: 'Locked by organization policy' } })}
        onToggleSection={jest.fn()}
        onApplyPreset={jest.fn()}
        onSaveDefaults={jest.fn()}
      />,
    );

    expect(screen.getByText('Part 4: SOAR Configuration: Locked by organization policy')).toBeInTheDocument();
  });

  test('disables toggle when section is locked', () => {
    render(
      <WorkbenchSectionControls
        sections={buildSections({ part4: { visible: true, locked: true, reason: 'Locked by system policy' } })}
        onToggleSection={jest.fn()}
        onApplyPreset={jest.fn()}
        onSaveDefaults={jest.fn()}
      />,
    );

    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes[0]).toBeDisabled();
  });

  test('calls preset handlers', () => {
    const onApplyPreset = jest.fn();
    render(
      <WorkbenchSectionControls
        sections={buildSections()}
        onToggleSection={jest.fn()}
        onApplyPreset={onApplyPreset}
        onSaveDefaults={jest.fn()}
      />,
    );

    fireEvent.click(screen.getByText('Simple Mode'));
    fireEvent.click(screen.getByText('Advanced Mode'));

    expect(onApplyPreset).toHaveBeenCalledWith('SIMPLE');
    expect(onApplyPreset).toHaveBeenCalledWith('ADVANCED');
  });
});
