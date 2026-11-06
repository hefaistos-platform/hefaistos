import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MockedProvider } from '@apollo/client/testing';
import MaieuticCapabilityPicker, { CAPABILITIES_QUERY, LAYERS, staleRefs } from './MaieuticCapabilityPicker';

const entry = (id: string, over: Record<string, any> = {}) => ({
  id, abstractionLayer: 'API_EXPORT', componentArtifact: `artifact-${id}`, adversaryPurpose: 'dump memory',
  commonEvasions: 'ordinal call', isSharedBaseline: false, ...over,
});
const mock = (entries: any[], technique = 'T1003.001') => ({
  request: { query: CAPABILITIES_QUERY, variables: { technique } },
  result: { data: { capabilityAbstractions: entries } },
});
const setup = (props: Partial<React.ComponentProps<typeof MaieuticCapabilityPicker>>, mocks: any[]) => {
  const onChange = jest.fn();
  render(
    <MockedProvider mocks={mocks} addTypename={false}>
      <MaieuticCapabilityPicker techniqueId="T1003.001" refs={[]} focusLayer="" onChange={onChange} {...props} />
    </MockedProvider>,
  );
  return onChange;
};

describe('staleRefs', () => {
  it('returns the picks the current technique does not offer', () => {
    expect(staleRefs(['a', 'b', 'c'], ['b'])).toEqual(['a', 'c']);
    expect(staleRefs([], ['b'])).toEqual([]);
  });
});

it('offers every layer the backend accepts', () => {
  expect(LAYERS.map((l) => l.value)).toEqual(['TOOL', 'API_EXPORT', 'COM_IPC', 'REGISTRY_OBJECT', 'PROTOCOL', 'PROCESS_BEHAVIOR', 'NETWORK_BEHAVIOR']);
});

describe('MaieuticCapabilityPicker', () => {
  it('asks for a technique first, and still lets the user set a focus layer', () => {
    setup({ techniqueId: undefined }, []);
    expect(screen.getByText(/once you have chosen an ATT&CK technique/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Capability Library entries')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Focus layer')).toBeInTheDocument();
  });

  it('says plainly when the library has nothing for the technique', async () => {
    setup({}, [mock([])]);
    expect(await screen.findByText(/no entries for T1003.001 yet/)).toBeInTheDocument();
  });

  it('reports a failed load instead of claiming the library is empty', async () => {
    setup({}, [{ request: { query: CAPABILITIES_QUERY, variables: { technique: 'T1003.001' } }, error: new Error('boom') }]);
    expect(await screen.findByText(/Could not load the Capability Library/)).toBeInTheDocument();
    expect(screen.queryByText(/no entries for/)).not.toBeInTheDocument();
  });

  it('shows what the library says about a picked entry, labelled as library text', async () => {
    setup({ refs: ['e1'] }, [mock([entry('e1', { isSharedBaseline: true }), entry('e2')])]);
    expect(await screen.findByTestId('cap-e1')).toHaveTextContent('Purpose (from the library): dump memory');
    expect(screen.getByTestId('cap-e1')).toHaveTextContent('Known evasions (from the library): ordinal call');
    expect(screen.getByTestId('cap-e1')).toHaveTextContent('shared baseline');
    expect(screen.queryByTestId('cap-e2')).not.toBeInTheDocument();
  });

  it('warns about picks that belong to another technique', async () => {
    setup({ refs: ['e1', 'old'] }, [mock([entry('e1')])]);
    expect(await screen.findByText(/1 earlier pick\(s\) do not belong to T1003.001/)).toBeInTheDocument();
  });

  it('does not warn while the library is still loading', () => {
    setup({ refs: ['old'] }, [mock([entry('e1')])]);
    expect(screen.queryByText(/earlier pick/)).not.toBeInTheDocument();
  });

  it('clearing the focus layer sends an empty string and keeps the picks', async () => {
    const onChange = setup({ refs: ['e1'], focusLayer: 'TOOL' }, [mock([entry('e1')])]);
    await screen.findByTestId('cap-e1');
    const clear = document.querySelector('.ant-select-clear') as HTMLElement;
    expect(clear).not.toBeNull();
    fireEvent.mouseDown(clear); fireEvent.click(clear);
    expect(onChange).toHaveBeenLastCalledWith({ capability_refs: ['e1'], focus_layer: '' });
  });

  it('states that it does not answer evasion questions', () => {
    setup({ techniqueId: undefined }, []);
    expect(screen.getByText(/does not answer any evasion question for you/)).toBeInTheDocument();
  });
});
