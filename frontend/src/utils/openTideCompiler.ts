import { OpenTideMetadata, OpenTideRule } from '../types/opentide';

/**
 * Shape of a PlaybookGraph as returned by the GraphQL query in PlaybookWorkbench.
 * Only the fields needed for metadata compilation are listed here.
 */
interface PlaybookGraphSnapshot {
  title?: string;
  goal?: string;
  author?: { username?: string } | null;
  createdAt?: string;
  updatedAt?: string;
  mitreTechnique?: { techniqueId?: string; name?: string } | null;
  technicalContext?: string;
  blindSpots?: string;
  falsePositives?: string;
  responsePlaybook?: string;
  defaultSeverity?: string;
  alertTrigger?: string;
  robustnessLevel?: number;
  dataSourceMaturity?: string;
  detectionFocusLayer?: string;
  selectedCapabilityAbstractions?: Array<{
    abstractionLayer?: string;
    componentArtifact?: string;
    detectionValue?: string;
    robustnessLevel?: number;
  }>;
}

/**
 * Compile OpenTide metadata from the workbench's GraphQL data.
 * All analytical context (MITRE, capability, response) is auto-populated.
 */
export function compileMetadataFromWorkbench(playbook: PlaybookGraphSnapshot): OpenTideMetadata {
  return {
    title: playbook.title || 'Untitled Detection',
    description: playbook.goal || '',
    author: playbook.author?.username || 'Unknown',
    created: playbook.createdAt || new Date().toISOString(),
    modified: playbook.updatedAt || new Date().toISOString(),

    mitre: {
      technique_id: playbook.mitreTechnique?.techniqueId,
      technique_name: playbook.mitreTechnique?.name,
    },

    capability: {
      goal: playbook.goal,
      technical_context: playbook.technicalContext,
      blind_spots: playbook.blindSpots,
      false_positives: playbook.falsePositives,
      detection_focus_layer: playbook.detectionFocusLayer,
      abstractions: (playbook.selectedCapabilityAbstractions || []).map((entry) => ({
        layer: entry.abstractionLayer || '',
        component_artifact: entry.componentArtifact || '',
        detection_value: entry.detectionValue,
        robustness_level: entry.robustnessLevel,
      })).filter((entry) => entry.layer || entry.component_artifact),
    },

    response: {
      playbook: playbook.responsePlaybook,
      severity: playbook.defaultSeverity,
      alert_trigger: playbook.alertTrigger,
    },

    validation: {
      robustness_level: playbook.robustnessLevel,
      data_source_maturity: playbook.dataSourceMaturity,
    },
  };
}

/**
 * Build an initial OpenTideRule by migrating a legacy single-format rule
 * into the appropriate platform subschema.
 */
export function buildInitialOpenTideRule(
  playbookData: PlaybookGraphSnapshot,
  legacyRule: string,
  legacyFormat: 'KQL' | 'EQL' | 'WAZUH' | 'SPL' | 'AQL' | 'OTHER' | 'OPENTIDE',
): OpenTideRule {
  const metadata = compileMetadataFromWorkbench(playbookData);

  // If the rule is already an OpenTide YAML, return with empty platforms
  // (the caller should parse the YAML separately)
  if (legacyFormat === 'OPENTIDE') {
    return { metadata, platforms: {} };
  }

  const platforms: OpenTideRule['platforms'] = {};

  if (legacyFormat === 'KQL' && legacyRule.trim()) {
    platforms.kql = { query: legacyRule };
  } else if (legacyFormat === 'EQL' && legacyRule.trim()) {
    platforms.elastic = { query: legacyRule };
  } else if (legacyFormat === 'SPL' && legacyRule.trim()) {
    platforms.spl = { query: legacyRule };
  } else if (legacyFormat === 'WAZUH' && legacyRule.trim()) {
    platforms.wazuh = { rule: legacyRule };
  }

  return { metadata, platforms };
}

/**
 * Return the list of platform keys that have non-empty content.
 */
export function getConfiguredPlatforms(rule: OpenTideRule): string[] {
  const configured: string[] = [];
  if (rule.platforms.kql?.query?.trim()) configured.push('kql');
  if (rule.platforms.elastic?.query?.trim()) configured.push('elastic');
  if (rule.platforms.spl?.query?.trim()) configured.push('spl');
  if (rule.platforms.wazuh?.rule?.trim()) configured.push('wazuh');
  if (rule.platforms.qradar?.query?.trim()) configured.push('qradar');
  return configured;
}

/**
 * Validate the OpenTide metadata object and return a list of errors.
 */
export function validateOpenTideMetadata(metadata: OpenTideMetadata): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (!metadata.title || metadata.title.trim().length === 0) {
    errors.push('Title is required');
  }

  const techniqueId = metadata.mitre?.technique_id;
  if (techniqueId && !/^T\d{4}(\.\d{3})?$/.test(techniqueId)) {
    errors.push(`Invalid MITRE ATT&CK Technique ID '${techniqueId}': expected format T1234 or T1234.001`);
  }

  const severity = metadata.response?.severity;
  if (severity) {
    const validSeverities = ['Informational', 'Low', 'Medium', 'High', 'Critical'];
    if (!validSeverities.includes(severity)) {
      errors.push('Severity must be Informational, Low, Medium, High, or Critical (Title Case)');
    }
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}
