import React from 'react';
import { render, screen } from '@testing-library/react';
import MaieuticFrameworkDrift from './MaieuticFrameworkDrift';

const drift = (over: Record<string, any> = {}) => ({ pinnedLabel: 'aaaa', activeLabel: 'bbbb', removed: [], changed: [], ...over });

describe('MaieuticFrameworkDrift', () => {
  it('renders nothing without drift, or when nothing relevant changed', () => {
    const { container, rerender } = render(<MaieuticFrameworkDrift drift={null} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<MaieuticFrameworkDrift drift={undefined} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<MaieuticFrameworkDrift drift={drift()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('names removed topics and says the answers are kept', () => {
    render(<MaieuticFrameworkDrift drift={drift({ removed: ['ADE2-01', 'ADE3-03'] })} />);
    expect(screen.getByTestId('framework-drift')).toHaveTextContent('aaaa to bbbb');
    expect(screen.getByTestId('framework-drift')).toHaveTextContent('No longer in the framework: ADE2-01, ADE3-03. Your answers to them are kept');
    expect(screen.queryByText(/Definition changed upstream/)).not.toBeInTheDocument();
  });

  it('names changed topics and says they are not reopened by it', () => {
    render(<MaieuticFrameworkDrift drift={drift({ changed: ['ADE2-02'] })} />);
    expect(screen.getByTestId('framework-drift')).toHaveTextContent('Definition changed upstream: ADE2-02');
    expect(screen.getByTestId('framework-drift')).toHaveTextContent('only reopened when its own text changes');
    expect(screen.queryByText(/No longer in the framework/)).not.toBeInTheDocument();
  });
});
