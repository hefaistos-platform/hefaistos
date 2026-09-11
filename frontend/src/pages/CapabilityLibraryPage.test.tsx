import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import CapabilityLibraryPage from './CapabilityLibraryPage';

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
  adversaryPurpose?: string;
  expectedObservables?: string;
  applicableTelemetry?: string;
  detectionValue?: string;
  robustnessLevel?: number;
  reviewStatus?: string;
  organizationName?: string;
  isEditable?: boolean;
  updatedAt?: string;
  version?: number;
  technique?: {
    techniqueId: string;
    name: string;
  };
};

const entries: Entry[] = [
  {
    id: 'cap-1',
    abstractionLayer: 'TOOL',
    componentArtifact: 'mshta.exe',
    adversaryPurpose: 'Proxy execution',
    expectedObservables: 'Process start',
    applicableTelemetry: 'EDR',
    detectionValue: 'High confidence',
    robustnessLevel: 4,
    reviewStatus: 'REVIEWED',
    organizationName: 'Capability Org',
    isEditable: true,
    updatedAt: '2026-09-10T12:00:00Z',
    version: 2,
    technique: { techniqueId: 'T1218.005', name: 'Mshta' },
  },
  {
    id: 'cap-2',
    abstractionLayer: 'PROCESS_BEHAVIOR',
    componentArtifact: 'powershell child chain',
    reviewStatus: 'DRAFT',
    organizationName: 'Shared Baseline',
    isEditable: false,
    updatedAt: '2026-09-09T12:00:00Z',
    version: 1,
    technique: { techniqueId: 'T1059.001', name: 'PowerShell' },
  },
];

const pageRefetch = jest.fn().mockResolvedValue(undefined);
const attackTechniquesRefetch = jest.fn();
const createMutation = jest.fn().mockResolvedValue({
  data: {
    createCapabilityAbstraction: {
      capabilityAbstraction: {
        id: 'cap-new',
      },
    },
  },
});
const updateMutation = jest.fn().mockResolvedValue({ data: { updateCapabilityAbstraction: { capabilityAbstraction: { id: 'cap-1' } } } });

describe('CapabilityLibraryPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    pageRefetch.mockClear();
    attackTechniquesRefetch.mockClear();
    createMutation.mockClear();
    updateMutation.mockClear();

    mockUseQuery.mockReturnValue({
      data: {
        capabilityAbstractions: entries,
        allPlaybookGraphs: [
          {
            id: 'graph-1',
            title: 'Workbench Alpha',
            status: 'DEVELOPMENT',
            selectedCapabilityAbstractions: [{ id: 'cap-1' }],
          },
        ],
      },
      loading: false,
      error: undefined,
      refetch: pageRefetch,
    });

    mockUseLazyQuery.mockReturnValue([
      jest.fn(),
      {
        data: {
          allAttackTechniques: [
            { id: 'tech-1', techniqueId: 'T1218.005', name: 'Mshta' },
            { id: 'tech-2', techniqueId: 'T1059.001', name: 'PowerShell' },
          ],
        },
        loading: false,
        refetch: attackTechniquesRefetch,
      },
    ]);

    mockUseMutation.mockImplementation((query: unknown) => {
      const queryText = String(query);
      if (queryText.includes('CreateCapabilityAbstraction')) {
        return [createMutation, { loading: false }];
      }
      if (queryText.includes('UpdateCapabilityAbstraction')) {
        return [updateMutation, { loading: false }];
      }
      return [jest.fn(), { loading: false }];
    });
  });

  it('shows usage detail when a capability row is opened', async () => {
    render(
      <MemoryRouter initialEntries={['/capability-library']}>
        <CapabilityLibraryPage />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByText('mshta.exe'));

    expect(await screen.findByText('Workbench Alpha')).toBeInTheDocument();
    expect(screen.getAllByText('Capability ID').length).toBeGreaterThan(0);
    expect(screen.getByText('Used by (1)')).toBeInTheDocument();
  });

  it('creates a capability abstraction from the library using the shared form fields', async () => {
    render(
      <MemoryRouter initialEntries={['/capability-library?techniqueId=T1218.005']}>
        <CapabilityLibraryPage />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole('button', { name: /Add Capability Abstraction/i }));

    const modal = (await screen.findAllByRole('dialog')).slice(-1)[0];
    fireEvent.mouseDown(within(modal).getAllByRole('combobox')[1]);
    fireEvent.click(await screen.findByText('Tool / Binary'));
    fireEvent.change(within(modal).getAllByRole('textbox')[0], {
      target: { value: 'calc.exe' },
    });

    fireEvent.click(within(modal).getByRole('button', { name: /^OK$/i }));

    await waitFor(() =>
      expect(createMutation).toHaveBeenCalledWith({
        variables: expect.objectContaining({
          techniqueId: 'T1218.005',
          abstractionLayer: 'TOOL',
          componentArtifact: 'calc.exe',
        }),
      })
    );
    expect(pageRefetch).toHaveBeenCalled();
  });

  it('edits an existing capability abstraction from the detail drawer', async () => {
    render(
      <MemoryRouter initialEntries={['/capability-library?capabilityId=cap-1']}>
        <CapabilityLibraryPage />
      </MemoryRouter>
    );

    fireEvent.click(await screen.findByRole('button', { name: /^Edit$/i }));
    const modal = (await screen.findAllByRole('dialog')).slice(-1)[0];
    fireEvent.change(within(modal).getAllByRole('textbox')[0], {
      target: { value: 'mshta.exe renamed' },
    });

    fireEvent.click(within(modal).getByRole('button', { name: /^OK$/i }));

    await waitFor(() =>
      expect(updateMutation).toHaveBeenCalledWith({
        variables: expect.objectContaining({
          capabilityAbstractionId: 'cap-1',
          componentArtifact: 'mshta.exe renamed',
        }),
      })
    );
  });
});
