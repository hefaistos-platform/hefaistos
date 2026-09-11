export interface OpenTideMetadata {
  title: string;
  description: string;
  author: string;
  created: string;
  modified: string;
  mitre: {
    technique_id?: string;
    technique_name?: string;
    tactic?: string;
  };
  capability: {
    goal?: string;
    technical_context?: string;
    blind_spots?: string;
    false_positives?: string;
    detection_focus_layer?: string;
    abstractions?: Array<{
      layer: string;
      component_artifact: string;
      detection_value?: string;
      robustness_level?: number;
    }>;
  };
  response: {
    playbook?: string;
    severity?: string;
    alert_trigger?: string;
  };
  validation?: {
    robustness_level?: number;
    data_source_maturity?: string;
    test_status?: string;
  };
}

export interface OpenTidePlatforms {
  kql?: {
    query: string;
    data_source?: string;
  };
  elastic?: {
    query: string;
  };
  spl?: {
    query: string;
    index?: string;
  };
  wazuh?: {
    rule: string;
  };
  qradar?: {
    query: string;
    scope?: 'local' | 'global';
  };
}

export interface OpenTideRule {
  metadata: OpenTideMetadata;
  platforms: OpenTidePlatforms;
}
