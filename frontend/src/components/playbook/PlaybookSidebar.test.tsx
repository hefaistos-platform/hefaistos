import React from 'react';
import { render, screen } from '@testing-library/react';
import { PlaybookSidebar } from './PlaybookSidebar';

jest.mock('./PlaybookNotes', () => ({ PlaybookNotes: () => null }));

const technique = { id: 'technique-1', techniqueId: 'T1003.001', name: 'LSASS Memory' };
const playbook = {
  customId: 'WB-1',
  version: 1,
  minorVersion: 0,
  status: 'DEVELOPMENT',
  author: { username: 'analyst' },
  robustnessLevel: 0,
  dataSourceRobustness: '',
  tags: [],
  createdAt: '2026-10-13T00:00:00Z',
  mitreTechnique: null,
  nodes: [],
};
const props = {
  onUpdate: jest.fn(),
  canClearNotes: true,
  activeTab: 'DETAILS' as const,
  onTabChange: jest.fn(),
  collapsed: false,
  onCollapsedChange: jest.fn(),
};

describe('PlaybookSidebar ATT&CK mappings', () => {
  test('shows the selected TTP immediately without detection logic or a selected node', () => {
    const { rerender } = render(<PlaybookSidebar {...props} playbook={playbook} />);
    expect(screen.queryByText('T1003.001')).not.toBeInTheDocument();

    rerender(<PlaybookSidebar {...props} playbook={{ ...playbook, mitreTechnique: technique }} />);

    expect(screen.getByText('Selected Workbench technique')).toBeInTheDocument();
    expect(screen.getByText('T1003.001')).toHaveAttribute('title', 'LSASS Memory');
  });

  test('keeps the selected TTP visible when selecting a node without its own mappings', () => {
    render(
      <PlaybookSidebar
        {...props}
        selectedNodeId="node-1"
        playbook={{ ...playbook, mitreTechnique: technique, nodes: [{ id: 'node-1', mitreAttackMappings: [] }] }}
      />,
    );

    expect(screen.getByText('T1003.001')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Enter comma-separated technique IDs/)).toBeInTheDocument();
  });

  test('preserves node mappings alongside the Workbench technique', () => {
    render(
      <PlaybookSidebar
        {...props}
        selectedNodeId="node-1"
        playbook={{
          ...playbook,
          mitreTechnique: technique,
          nodes: [{ id: 'node-1', mitreAttackMappings: [{ id: 'technique-2', techniqueId: 'T1059', name: 'Command and Scripting Interpreter' }] }],
        }}
      />,
    );

    expect(screen.getByText('T1003.001')).toBeInTheDocument();
    expect(screen.getByText('T1059')).toBeInTheDocument();
  });

  test('updates the displayed mapping when the TTP changes or is cleared', () => {
    const { rerender } = render(<PlaybookSidebar {...props} playbook={{ ...playbook, mitreTechnique: technique }} />);

    rerender(<PlaybookSidebar {...props} playbook={{ ...playbook, mitreTechnique: { ...technique, techniqueId: 'T1059' } }} />);
    expect(screen.queryByText('T1003.001')).not.toBeInTheDocument();
    expect(screen.getByText('T1059')).toBeInTheDocument();

    rerender(<PlaybookSidebar {...props} playbook={playbook} />);
    expect(screen.queryByText('T1059')).not.toBeInTheDocument();
  });
});
