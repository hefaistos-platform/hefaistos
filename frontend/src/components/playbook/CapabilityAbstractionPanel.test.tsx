import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { CapabilityAbstractionPanel } from './CapabilityAbstractionPanel';

const mockUseLazyQuery = jest.fn();
const mockUseMutation = jest.fn();
const mockUseQuery = jest.fn();

jest.mock('@apollo/client', () => ({
  gql: (literals: TemplateStringsArray, ...placeholders: string[]) =>
    literals.reduce((acc, lit, i) => acc + lit + (placeholders[i] ?? ''), ''),
}));

jest.mock('@apollo/client/react', () => ({
  useLazyQuery: (...args: unknown[]) => mockUseLazyQuery(...args),
  useMutation: (...args: unknown[]) => mockUseMutation(...args),
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
}));

type Entry = {
  id: string;
  abstractionLayer: string;
  componentArtifact: string;
  robustnessLevel?: number;
  reviewStatus?: string;
  sourceKind?: string;
  technique?: {
    techniqueId: string;
    name: string;
  };
};

const entriesByTechnique: Record<string, Entry[]> = {
  'T1218.005': [
    {
      id: 'mshta-1',
      abstractionLayer: 'TOOL',
      componentArtifact: 'mshta.exe',
      robustnessLevel: 4,
      reviewStatus: 'REVIEWED',
      sourceKind: 'SEEDED',
      technique: { techniqueId: 'T1218.005', name: 'Mshta' },
    },
    {
      id: 'mshta-2',
      abstractionLayer: 'PROCESS_BEHAVIOR',
      componentArtifact: 'mshta child process chain',
      robustnessLevel: 5,
      reviewStatus: 'APPROVED',
      sourceKind: 'CUSTOM',
      technique: { techniqueId: 'T1218.005', name: 'Mshta' },
    },
  ],
  T1543: [
    {
      id: 'service-1',
      abstractionLayer: 'PROCESS_BEHAVIOR',
      componentArtifact: 'service registry persistence',
      robustnessLevel: 3,
      reviewStatus: 'DRAFT',
      sourceKind: 'CUSTOM',
      technique: { techniqueId: 'T1543', name: 'Create or Modify System Process' },
    },
  ],
};

const allEntries = Object.values(entriesByTechnique).flat();

function TestHarness() {
  const [selectedIds, setSelectedIds] = React.useState<string[]>([]);
  const [techniqueId, setTechniqueId] = React.useState<string>('T1218.005');

  const selectedEntryObjects = React.useMemo(
    () => allEntries.filter((entry) => selectedIds.includes(entry.id)),
    [selectedIds]
  );

  return (
    <>
      <button type="button" onClick={() => setTechniqueId('T1543')}>
        Switch to T1543
      </button>
      <CapabilityAbstractionPanel
        techniqueId={techniqueId}
        selectedIds={selectedIds}
        selectedEntryObjects={selectedEntryObjects}
        detectionFocusLayer=""
        userRole="ADMIN"
        onSelectionChange={(ids) => setSelectedIds(ids)}
      />
    </>
  );
}

describe('CapabilityAbstractionPanel', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    mockUseQuery.mockImplementation((_query: unknown, options?: { variables?: { techniqueId?: string } }) => ({
      data: {
        capabilityAbstractions: entriesByTechnique[options?.variables?.techniqueId || 'T1218.005'] || [],
      },
      refetch: jest.fn(),
    }));

    mockUseLazyQuery.mockReturnValue([
      jest.fn(),
      {
        data: {
          allAttackTechniques: [
            { id: 'tech-1', techniqueId: 'T1218.005', name: 'Mshta' },
            { id: 'tech-2', techniqueId: 'T1543', name: 'Create or Modify System Process' },
          ],
        },
        loading: false,
        refetch: jest.fn(),
      },
    ]);

    mockUseMutation.mockReturnValue([jest.fn(), { loading: false }]);
  });

  it('preserves earlier selections when a new technique is shown and another entry is added', async () => {
    render(<TestHarness />);

    let checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[0]);

    await waitFor(() =>
      expect(screen.getByText('📌 Selected abstractions (1)')).toBeInTheDocument()
    );

    checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[1]);

    await waitFor(() =>
      expect(screen.getByText('📌 Selected abstractions (2)')).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole('button', { name: 'Switch to T1543' }));

    await waitFor(() =>
      expect(screen.getAllByText('service registry persistence').length).toBeGreaterThan(0)
    );

    checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[0]);

    await waitFor(() =>
      expect(screen.getByText('📌 Selected abstractions (3)')).toBeInTheDocument()
    );

    expect(screen.getByText('mshta.exe')).toBeInTheDocument();
    expect(screen.getByText('mshta child process chain')).toBeInTheDocument();
    expect(screen.getAllByText('service registry persistence').length).toBeGreaterThan(0);
  });
});
