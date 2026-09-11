import { applyMaieuticToWorkbench } from './maieuticMapping';
import { MaieuticOutput, MaieuticImportSelections } from '../types/maieutic';

describe('applyMaieuticToWorkbench', () => {
  const mockMaieuticOutput: MaieuticOutput = {
    hypothesis: {
      intent: 'Detect credential dumping',
      capability: 'LSASS memory access',
    },
    qaLog: [
      { question: 'What tools are used?', answer: 'Mimikatz, ProcDump' },
      { question: 'What telemetry is needed?', answer: 'Process creation logs' },
    ],
    robustness: {
      dataQuality: 'High - comprehensive logging',
      falsePositiveRate: 'Low - specific to credential access',
      coverage: 'Limited to Windows endpoints',
      justification: 'Reliable detection with minimal FPs',
    },
    playbookDesign: {
      manualSteps: 'Investigate process tree\nCheck for lateral movement',
      soarPlaybook: 'Isolate host\nRevoke credentials',
    },
    detectionRule: {
      format: 'KQL',
      rule: 'title: LSASS Access\nlogsource:\n  product: windows',
    },
  };

  const allSelectionsOn: MaieuticImportSelections = {
    importHypothesis: true,
    importQALog: true,
    importRobustness: true,
    importPlaybook: true,
    importDetectionRule: true,
    importSynthesis: true,
  };

  const allSelectionsOff: MaieuticImportSelections = {
    importHypothesis: false,
    importQALog: false,
    importRobustness: false,
    importPlaybook: false,
    importDetectionRule: false,
    importSynthesis: false,
  };

  test('should merge hypothesis into goal field when importHypothesis is true', () => {
    const currentState = { goal: 'Existing goal' };
    const selections = { ...allSelectionsOff, importHypothesis: true };

    const result = applyMaieuticToWorkbench(mockMaieuticOutput, selections, currentState);

    expect(result.goal).toContain('Detect credential dumping');
    expect(result.goal).toContain('LSASS memory access');
    expect(result.goal).toContain('Existing goal');
  });

  test('should merge QA log into technicalContext when importQALog is true', () => {
    const currentState = { technicalContext: 'Existing context' };
    const selections = { ...allSelectionsOff, importQALog: true };

    const result = applyMaieuticToWorkbench(mockMaieuticOutput, selections, currentState);

    expect(result.technicalContext).toContain('Q1: What tools are used?');
    expect(result.technicalContext).toContain('A1: Mimikatz, ProcDump');
    expect(result.technicalContext).toContain('Existing context');
  });

  test('should merge robustness into blindSpots and falsePositives when importRobustness is true', () => {
    const currentState = { blindSpots: 'Old blind spots', falsePositives: 'Old FPs' };
    const selections = { ...allSelectionsOff, importRobustness: true };

    const result = applyMaieuticToWorkbench(mockMaieuticOutput, selections, currentState);

    expect(result.blindSpots).toContain('Data Quality: High');
    expect(result.blindSpots).toContain('Old blind spots');
    expect(result.falsePositives).toContain('Low - specific to credential access');
    expect(result.falsePositives).toContain('Old FPs');
  });

  test('should merge playbook design into responsePlaybook when importPlaybook is true', () => {
    const currentState = { responsePlaybook: 'Existing playbook' };
    const selections = { ...allSelectionsOff, importPlaybook: true };

    const result = applyMaieuticToWorkbench(mockMaieuticOutput, selections, currentState);

    expect(result.responsePlaybook).toContain('Manual Steps');
    expect(result.responsePlaybook).toContain('Investigate process tree');
    expect(result.responsePlaybook).toContain('SOAR Playbook');
    expect(result.responsePlaybook).toContain('Isolate host');
    expect(result.responsePlaybook).toContain('Existing playbook');
  });

  test('should overwrite detectionRule when importDetectionRule is true', () => {
    const currentState = { detectionRule: 'Old rule content' };
    const selections = { ...allSelectionsOff, importDetectionRule: true };

    const result = applyMaieuticToWorkbench(mockMaieuticOutput, selections, currentState);

    expect(result.detectionRule).toContain('KQL');
    expect(result.detectionRule).toContain('title: LSASS Access');
    expect(result.detectionRule).not.toContain('Old rule content'); // Overwrites, doesn't concatenate
  });

  test('should not import detection rule when rule content is empty', () => {
    const currentState = { detectionRule: 'Old rule content' };
    const selections = { ...allSelectionsOff, importDetectionRule: true };
    const emptyRuleOutput = {
      ...mockMaieuticOutput,
      detectionRule: { format: 'KQL', rule: '' },
    };

    const result = applyMaieuticToWorkbench(emptyRuleOutput, selections, currentState);

    expect(result.detectionRule).toBe('Old rule content'); // Should not change
  });

  test('should not modify fields when selections are off', () => {
    const currentState = {
      goal: 'Original goal',
      technicalContext: 'Original context',
      blindSpots: 'Original blind spots',
      falsePositives: 'Original FPs',
      responsePlaybook: 'Original playbook',
      detectionRule: 'Original rule',
    };

    const result = applyMaieuticToWorkbench(mockMaieuticOutput, allSelectionsOff, currentState);

    expect(result).toEqual(currentState);
  });

  test('should handle empty current state correctly', () => {
    const currentState = {};

    const result = applyMaieuticToWorkbench(mockMaieuticOutput, allSelectionsOn, currentState);

    expect(result.goal).toContain('Detect credential dumping');
    expect(result.technicalContext).toContain('Q1:');
    expect(result.blindSpots).toContain('Data Quality:');
    expect(result.falsePositives).toContain('Low - specific');
    expect(result.responsePlaybook).toContain('Manual Steps');
    expect(result.detectionRule).toContain('KQL');
  });

  test('should handle partial selections correctly', () => {
    const currentState = {};
    const selections: MaieuticImportSelections = {
      importHypothesis: true,
      importQALog: false,
      importRobustness: true,
      importPlaybook: false,
      importDetectionRule: true,
      importSynthesis: false,
    };

    const result = applyMaieuticToWorkbench(mockMaieuticOutput, selections, currentState);

    expect(result.goal).toContain('Detect credential dumping');
    expect(result.technicalContext).toBeUndefined();
    expect(result.blindSpots).toContain('Data Quality:');
    expect(result.responsePlaybook).toBeUndefined();
    expect(result.detectionRule).toContain('KQL');
  });

  test('should format detection rule correctly with format and delimiter', () => {
    const currentState = {};
    const selections = { ...allSelectionsOff, importDetectionRule: true };

    const result = applyMaieuticToWorkbench(mockMaieuticOutput, selections, currentState);

    expect(result.detectionRule).toMatch(/^KQL\n---\n/);
  });

  test('should extract robustnessLevel and dataSourceMaturity from robustnessRecommendation', () => {
    const outputWithRecommendation: MaieuticOutput = {
      ...mockMaieuticOutput,
      robustnessRecommendation: {
        level: 4,
        source_type: 'KERNEL_MODE',
        confidence: 'high',
      },
    };

    const result = applyMaieuticToWorkbench(outputWithRecommendation, allSelectionsOff, {});

    expect(result.robustnessLevel).toBe(4);
    expect(result.dataSourceMaturity).toBe('KERNEL_MODE');
  });

  test('should not set robustnessLevel or dataSourceMaturity when robustnessRecommendation is missing', () => {
    const result = applyMaieuticToWorkbench(mockMaieuticOutput, allSelectionsOff, {});

    expect(result.robustnessLevel).toBeUndefined();
    expect(result.dataSourceMaturity).toBeUndefined();
  });

  test('should map synthesis output into extended workbench fields when importSynthesis is true', () => {
    const withSynthesis: MaieuticOutput = {
      ...mockMaieuticOutput,
      synthesis: {
        triage_guidance: 'Validate parent process and isolate if confirmed.',
        test_scenario: 'Replay suspicious process tree from Atomic test.',
        test_expected_output: 'Alert with process lineage and account context.',
        alert_trigger: 'PROCESS_ANOMALY_DETECTED',
        default_severity: 'HIGH',
        enrichment_steps: ['Fetch process tree', 'Lookup host risk score'],
        containment_steps: ['Isolate endpoint'],
        notification_steps: ['Create P1 incident'],
        downstream_correlation_requirements: {
          window_minutes: 15,
          require_related_auth_alert: true,
        },
      },
    };

    const selections = {
      ...allSelectionsOff,
      importSynthesis: true,
    };

    const result = applyMaieuticToWorkbench(withSynthesis, selections, {});
    expect(result.triageGuidance).toContain('Maieutic Triage Guidance');
    expect(result.testScenario).toContain('Maieutic Test Scenario');
    expect(result.testExpectedOutput).toContain('Maieutic Test Expectations');
    expect(result.alertTrigger).toBe('PROCESS_ANOMALY_DETECTED');
    expect(result.defaultSeverity).toBe('HIGH');
    expect(result.enrichmentSteps).toEqual(['Fetch process tree', 'Lookup host risk score']);
    expect(result.containmentSteps).toEqual(['Isolate endpoint']);
    expect(result.notificationSteps).toEqual(['Create P1 incident']);
    expect(result.downstreamCorrelationRequirements).toEqual({
      window_minutes: 15,
      require_related_auth_alert: true,
    });
  });
});
