// Utility to map MaieuticOutput into PlaybookWorkbench form state

import { MaieuticOutput, MaieuticImportSelections } from '../types/maieutic';

/**
 * Merges Maieutic Engine output into the workbench form state.
 * Respects partial import selections.
 * 
 * @param maieuticData - The Maieutic output to merge
 * @param selections - Which parts to import
 * @param currentFormState - The existing workbench form state
 * @returns Updated form state with merged Maieutic data
 */
export function applyMaieuticToWorkbench(
  maieuticData: MaieuticOutput,
  selections: MaieuticImportSelections,
  currentFormState: {
    goal?: string;
    technicalContext?: string;
    blindSpots?: string;
    falsePositives?: string;
    responsePlaybook?: string;
    detectionRule?: string;
    triageGuidance?: string;
    testScenario?: string;
    testExpectedOutput?: string;
    alertTrigger?: string;
    defaultSeverity?: string;
    enrichmentSteps?: string[] | string;
    containmentSteps?: string[] | string;
    notificationSteps?: string[] | string;
    downstreamCorrelationRequirements?: Record<string, unknown> | string;
  }
): {
  goal?: string;
  technicalContext?: string;
  blindSpots?: string;
  falsePositives?: string;
  responsePlaybook?: string;
  detectionRule?: string;
  robustnessLevel?: number;
  dataSourceMaturity?: string;
  triageGuidance?: string;
  testScenario?: string;
  testExpectedOutput?: string;
  alertTrigger?: string;
  defaultSeverity?: string;
  enrichmentSteps?: string[];
  containmentSteps?: string[];
  notificationSteps?: string[];
  downstreamCorrelationRequirements?: Record<string, unknown>;
} {
  const result: {
    goal?: string;
    technicalContext?: string;
    blindSpots?: string;
    falsePositives?: string;
    responsePlaybook?: string;
    detectionRule?: string;
    robustnessLevel?: number;
    dataSourceMaturity?: string;
    triageGuidance?: string;
    testScenario?: string;
    testExpectedOutput?: string;
    alertTrigger?: string;
    defaultSeverity?: string;
    enrichmentSteps?: string[];
    containmentSteps?: string[];
    notificationSteps?: string[];
    downstreamCorrelationRequirements?: Record<string, unknown>;
  } = { ...currentFormState };

  const appendText = (existing?: string, incoming?: string, sectionTitle?: string): string | undefined => {
    if (!incoming || !incoming.trim()) return existing;
    const cleanIncoming = incoming.trim();
    if (!existing || !existing.trim()) {
      return sectionTitle ? `--- ${sectionTitle} ---\n${cleanIncoming}` : cleanIncoming;
    }
    return sectionTitle
      ? `${existing}\n\n--- ${sectionTitle} ---\n${cleanIncoming}`
      : `${existing}\n\n${cleanIncoming}`;
  };

  const toStringArray = (value: unknown): string[] | undefined => {
    if (Array.isArray(value)) {
      const normalized = value.map((item) => String(item).trim()).filter(Boolean);
      return normalized.length > 0 ? normalized : undefined;
    }
    if (typeof value === 'string') {
      const trimmed = value.trim();
      if (!trimmed) return undefined;
      try {
        const parsed = JSON.parse(trimmed);
        if (Array.isArray(parsed)) {
          const normalized = parsed.map((item) => String(item).trim()).filter(Boolean);
          return normalized.length > 0 ? normalized : undefined;
        }
      } catch {
        return [trimmed];
      }
      return [trimmed];
    }
    return undefined;
  };

  const toObject = (value: unknown): Record<string, unknown> | undefined => {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return value as Record<string, unknown>;
    }
    if (typeof value === 'string' && value.trim()) {
      try {
        const parsed = JSON.parse(value);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          return parsed as Record<string, unknown>;
        }
      } catch {
        return undefined;
      }
    }
    return undefined;
  };

  // Extract robustness level and data source maturity from AI recommendation
  if (maieuticData.robustnessRecommendation) {
    result.robustnessLevel = maieuticData.robustnessRecommendation.level;
    result.dataSourceMaturity = maieuticData.robustnessRecommendation.source_type;
  }

  // Import Hypothesis -> goal + technicalContext
  if (selections.importHypothesis) {
    const hypothesisText = `Intent: ${maieuticData.hypothesis.intent}\nCapability: ${maieuticData.hypothesis.capability}`;
    result.goal = appendText(result.goal, hypothesisText, 'Maieutic Hypothesis');
  }

  // Import QA Log -> technicalContext (append as investigation notes)
  if (selections.importQALog && maieuticData.qaLog.length > 0) {
    const qaText = maieuticData.qaLog
      .map((entry, idx) => `Q${idx + 1}: ${entry.question}\nA${idx + 1}: ${entry.answer}`)
      .join('\n\n');
    result.technicalContext = appendText(result.technicalContext, qaText, 'Maieutic Interrogation Log');
  }

  // Import Robustness -> blindSpots + falsePositives
  if (selections.importRobustness) {
    const robustnessBlindSpots = `Data Quality: ${maieuticData.robustness.dataQuality}\nCoverage: ${maieuticData.robustness.coverage}\nJustification: ${maieuticData.robustness.justification}`;
    result.blindSpots = appendText(result.blindSpots, robustnessBlindSpots, 'Maieutic Robustness');

    const robustnessFP = maieuticData.robustness.falsePositiveRate;
    result.falsePositives = appendText(result.falsePositives, robustnessFP, 'Maieutic FP Analysis');
  }

  // Import Playbook -> responsePlaybook (concatenate manual + SOAR)
  if (selections.importPlaybook) {
    const sections: string[] = [];
    if (maieuticData.playbookDesign.manualSteps) {
      sections.push(`--- Manual Steps ---\n${maieuticData.playbookDesign.manualSteps}`);
    }
    if (maieuticData.playbookDesign.soarPlaybook) {
      sections.push(`--- SOAR Playbook ---\n${maieuticData.playbookDesign.soarPlaybook}`);
    }
    const playbookText = sections.join('\n\n');
    result.responsePlaybook = appendText(result.responsePlaybook, playbookText);
  }

  // Import Detection Rule -> detectionRule (format: "format\n---\nrule")
  if (selections.importDetectionRule && maieuticData.detectionRule.rule.trim()) {
    const ruleText = `${maieuticData.detectionRule.format}\n---\n${maieuticData.detectionRule.rule}`;
    result.detectionRule = ruleText; // Overwrite instead of concatenate for detection rules
  }

  // Import AI synthesis (Review step) into additional workbench sections
  if (selections.importSynthesis && maieuticData.synthesis) {
    const s = maieuticData.synthesis;
    const triage = typeof s.triage_guidance === 'string' ? s.triage_guidance : '';
    const testScenario = typeof s.test_scenario === 'string' ? s.test_scenario : '';
    const testExpectedOutput = typeof s.test_expected_output === 'string' ? s.test_expected_output : '';
    const alertTrigger = typeof s.alert_trigger === 'string' ? s.alert_trigger : '';
    const defaultSeverity = typeof s.default_severity === 'string' ? s.default_severity : '';

    result.triageGuidance = appendText(result.triageGuidance, triage, 'Maieutic Triage Guidance');
    result.testScenario = appendText(result.testScenario, testScenario, 'Maieutic Test Scenario');
    result.testExpectedOutput = appendText(result.testExpectedOutput, testExpectedOutput, 'Maieutic Test Expectations');

    if (alertTrigger.trim() && !result.alertTrigger) {
      result.alertTrigger = alertTrigger.trim();
    }
    if (defaultSeverity.trim() && !result.defaultSeverity) {
      result.defaultSeverity = defaultSeverity.trim();
    }

    const enrichment = toStringArray(s.enrichment_steps);
    const containment = toStringArray(s.containment_steps);
    const notification = toStringArray(s.notification_steps);
    const downstream = toObject(s.downstream_correlation_requirements);

    if (enrichment && enrichment.length > 0) {
      result.enrichmentSteps = enrichment;
    }
    if (containment && containment.length > 0) {
      result.containmentSteps = containment;
    }
    if (notification && notification.length > 0) {
      result.notificationSteps = notification;
    }
    if (downstream) {
      result.downstreamCorrelationRequirements = downstream;
    }
  }

  return result;
}
