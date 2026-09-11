import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { SoarConfiguration } from './SoarConfiguration';

describe('SoarConfiguration downstream correlation requirements', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  test('saves downstream correlation requirements when edited', () => {
    const onSave = jest.fn();

    render(
      <SoarConfiguration
        data={{
          trigger: '',
          severity: 'MEDIUM',
          enrichment: [],
          containment: [],
          notifications: [],
        }}
        onSave={onSave}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Downstream Correlation Requirements/i }));
    fireEvent.click(screen.getByRole('checkbox', { name: /Host-Based/i }));
    fireEvent.click(screen.getByRole('button', { name: /Save Changes/i }));

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      downstreamCorrelationRequirements: expect.objectContaining({
        correlationScope: ['Host-Based'],
        temporalLogic: expect.objectContaining({
          windowSize: '',
          windowUnit: 'seconds',
          sequenceType: 'strict',
        }),
      }),
    }));
  });
});
