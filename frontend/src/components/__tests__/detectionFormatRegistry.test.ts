import { buildSaveButtonLabel, DETECTION_FORMAT_REGISTRY } from '../detectionFormatRegistry';

describe('detection format registry', () => {
  it('derives save button labels from registry display names', () => {
    expect(buildSaveButtonLabel(DETECTION_FORMAT_REGISTRY[0])).toBe('SAVE KQL');
  });

  it('supports new formats without modal code changes', () => {
    const dummy = { displayName: 'DummyX' };
    expect(buildSaveButtonLabel(dummy)).toBe('SAVE DUMMYX');
  });

  it('includes Elastic EQL in the platform registry', () => {
    const eql = DETECTION_FORMAT_REGISTRY.find((entry) => entry.format === 'EQL');
    expect(eql).toBeDefined();
    expect(eql?.fileExtension).toBe('eql');
  });
});
