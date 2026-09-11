import React from 'react';
import { render, screen } from '@testing-library/react';

import { ReferenceContextPanel } from './ReferenceContextPanel';


describe('ReferenceContextPanel', () => {
  test('renders retrieved grounding references', () => {
    render(
      <ReferenceContextPanel
        references={[
          {
            title: 'Suspicious PowerShell Parent',
            description: 'Detect office spawning PowerShell.',
            content: 'DeviceProcessEvents | where ProcessCommandLine has "powershell"',
            source_ref: 'rules/templates/windows.jsonl:4',
            source_branch: 'main',
            repository_name: 'KQL Templates',
            language: 'KQL',
            score: 0.944,
          },
        ]}
      />
    );

    expect(screen.getByText('Retrieved grounding context:')).toBeInTheDocument();
    expect(screen.getByText('Suspicious PowerShell Parent')).toBeInTheDocument();
    expect(screen.getByText('KQL')).toBeInTheDocument();
    expect(screen.getByText(/score:\s*0\.944/i)).toBeInTheDocument();
    expect(screen.getByText(/rules\/templates\/windows\.jsonl:4/i)).toBeInTheDocument();
    expect(screen.getByText(/DeviceProcessEvents/)).toBeInTheDocument();
  });

  test('renders nothing when references are empty', () => {
    const { container } = render(<ReferenceContextPanel references={[]} />);
    expect(container.firstChild).toBeNull();
  });
});

