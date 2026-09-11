import { create } from 'zustand';
import { MaieuticOutput, MaieuticStep, MaieuticImportSelections } from './types/maieutic';

// --- 1. Define the TypeScript interface for the node's data payload ---
// This matches the dcg420DetectionTemplate from your prompt
// We'll fetch this from our node's 'templateData' JSON field
export interface Dcg420DetectionTemplate {
  goal?: string;
  categorization?: {
    mitreAttackTactic?: string;
    mitreAttackTechnique?: string;
  };
  strategyAbstract?: string;
  technicalContext?: string;
  blindSpotsAndAssumptions?: string; // Mapped to 'blind_spots'
  falsePositives?: string; // Mapped to 'false_positives'
  validation?: {
    description?: string;
    testReference?: string;
  };
  priority?: string;
  response?: string; // Mapped to 'triage_guidance'

  detectionRule?: {
    format?: string;
    rule?: string;
  };
  acdElements?: {
    engageID?: string;
    description?: string;
  }[];

  // We'll also add our v1 fields for migrated data
  v1_hypothesis?: string;
  // Node styling extension
  color?: string;
}

// --- 2. This is the full data payload for a node ---
export interface MitreAttackMapping {
  id: string;
  techniqueId: string;
  name: string;
}

export interface AbstractionNodeData {
  [key: string]: unknown; // Allow React Flow Node generic constraint (Record<string, unknown>)
  id: string; // The node's own ID
  graphId: string; // Graph this node belongs to
  layerName: string;
  templateData: Dcg420DetectionTemplate;
  mitreAttackMappings?: MitreAttackMapping[]; // Optional in case it's omitted
  label?: string; // convenience mirror of layerName for nodes
}

// --- 3. Define the store's state and actions ---
interface AppState {
  selectedNode: AbstractionNodeData | null;
  setSelectedNode: (nodeData: AbstractionNodeData | null) => void;

  // Maieutic Engine draft state
  maieuticDraft: MaieuticOutput | null;
  maieuticCurrentStep: MaieuticStep;
  maieuticSelections: MaieuticImportSelections;
  setMaieuticDraft: (draft: MaieuticOutput | null) => void;
  setMaieuticCurrentStep: (step: MaieuticStep) => void;
  setMaieuticSelections: (selections: MaieuticImportSelections) => void;
  resetMaieutic: () => void;
}

// Default Maieutic selections - all ON by default
const defaultMaieuticSelections: MaieuticImportSelections = {
  importHypothesis: true,
  importQALog: true,
  importRobustness: true,
  importPlaybook: true,
  importDetectionRule: true,
  importSynthesis: true,
};

// --- 4. Create the store ---
export const useAppStore = create<AppState>((set) => ({
  selectedNode: null,
  setSelectedNode: (nodeData) => set({ selectedNode: nodeData }),

  // Maieutic Engine state
  maieuticDraft: null,
  maieuticCurrentStep: 'Hypothesis',
  maieuticSelections: defaultMaieuticSelections,
  setMaieuticDraft: (draft) => set({ maieuticDraft: draft }),
  setMaieuticCurrentStep: (step) => set({ maieuticCurrentStep: step }),
  setMaieuticSelections: (selections) => set({ maieuticSelections: selections }),
  resetMaieutic: () => set({ 
    maieuticDraft: null, 
    maieuticCurrentStep: 'Hypothesis', 
    maieuticSelections: defaultMaieuticSelections 
  }),
}));
