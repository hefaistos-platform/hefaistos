// TypeScript interfaces for Maieutic Engine data structures

export interface MaieuticHypothesis {
  intent: string; // What adversary capability or behavior to detect
  capability: string; // Technical capability or technique being targeted
}

export interface MaieuticQAEntry {
  question: string;
  answer: string;
}

export interface MaieuticRobustness {
  dataQuality: string; // Assessment of data source reliability
  falsePositiveRate: string; // Expected FP rate justification
  coverage: string; // Coverage gaps and blind spots
  justification: string; // Overall robustness reasoning
}

export interface MaieuticPlaybookDesign {
  manualSteps: string; // Manual investigation/response steps
  soarPlaybook: string; // Automated SOAR playbook content
}

export interface MaieuticDetectionRule {
  format: string; // e.g., 'KQL', 'SPL', 'Pseudocode', 'Other'
  rule: string; // The actual detection rule content
}

export interface MaieuticRobustnessRecommendation {
  level: number; // 1-5 (Pyramid of Pain level)
  source_type: string; // e.g., 'APPLICATION', 'USER_MODE', 'KERNEL_MODE'
  confidence: string; // e.g., 'high', 'medium', 'low'
}

export interface MaieuticCompletionCheck {
  step_ready: boolean;
  quality_score: number; // 0-100
  missing_items: string[];
  next_best_action: string;
}

export interface MaieuticAutofillCandidates {
  target_fields: string[];
  proposed_text: Record<string, unknown>;
}

export interface MaieuticSynthesisOutput {
  triage_guidance?: string;
  test_scenario?: string;
  test_expected_output?: string;
  alert_trigger?: string;
  default_severity?: string;
  enrichment_steps?: string[];
  containment_steps?: string[];
  notification_steps?: string[];
  downstream_correlation_requirements?: Record<string, unknown>;
}

export interface MaieuticChatMessage {
  role: 'user' | 'ai';
  content: string;
}

export interface MaieuticOutput {
  hypothesis: MaieuticHypothesis;
  qaLog: MaieuticQAEntry[]; // Interrogation log
  robustness: MaieuticRobustness;
  playbookDesign: MaieuticPlaybookDesign;
  detectionRule: MaieuticDetectionRule;
  robustnessRecommendation?: MaieuticRobustnessRecommendation; // AI-generated robustness assessment
  conversationHistory?: MaieuticChatMessage[]; // Full chat log for audit trail
  synthesis?: MaieuticSynthesisOutput; // AI-synthesized workbench sections from review step
}

// Import selection toggles - which parts to import into workbench
export interface MaieuticImportSelections {
  importHypothesis: boolean;
  importQALog: boolean;
  importRobustness: boolean;
  importPlaybook: boolean;
  importDetectionRule: boolean;
  importSynthesis: boolean;
}

// Step identifiers for modal navigation
export type MaieuticStep = 'Hypothesis' | 'Interrogation' | 'Robustness' | 'Playbook' | 'Review';
