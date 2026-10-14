import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { KanbanBoardPage } from './KanbanBoardPage';

const mockUseQuery = jest.fn();
const mockLoadTags = jest.fn();
jest.mock('@apollo/client', () => ({ gql: (parts: TemplateStringsArray) => parts.join('') }));
jest.mock('@apollo/client/react', () => ({
  useQuery: (...args: unknown[]) => mockUseQuery(...args),
  useMutation: () => [jest.fn()],
  useLazyQuery: () => [mockLoadTags, { data: { allTags: [] } }],
}));
jest.mock('../context/PlaybookMetaContext', () => ({ usePlaybookMeta: () => ({ data: undefined }) }));
jest.mock('@hello-pangea/dnd', () => ({
  DragDropContext: ({ children }: any) => children,
  Droppable: ({ children }: any) => children({ innerRef: jest.fn(), droppableProps: {}, placeholder: null }),
  Draggable: ({ children }: any) => children({ innerRef: jest.fn(), draggableProps: {}, dragHandleProps: {} }),
}));
const deployedRules = Array.from({ length: 13 }, (_, i) => ({
  id: `rule-${i}`, title: `Deployed rule ${i + 1}`, status: 'DEPLOYED',
  playbookType: 'DETECTION', author: { username: 'alice' },
  tags: [{ id: 'tag', name: 'Production' }], tasks: [],
}));
const renderBoard = () => render(<MemoryRouter><KanbanBoardPage /></MemoryRouter>);
beforeEach(() => {
  localStorage.clear();
  window.history.replaceState(null, '', '/');
  mockUseQuery.mockReset();
  mockUseQuery.mockImplementation((query: string) => {
    const data = query.includes('query GetAllPlaybooks') ? { allPlaybooks: [
      ...deployedRules,
      { ...deployedRules[0], id: 'research', title: 'Research rule', status: 'RESEARCH' },
      { ...deployedRules[0], id: 'hunt', title: 'Abandoned hunt', playbookType: 'HUNT' },
    ] } : query.includes('query GetAllPlaybookGraphs') ? { allPlaybookGraphs: [{
      id: 'graph', title: 'Deployed workbench', status: 'DEPLOYED',
      author: { username: 'bob' }, tags: [], pngSnapshotUrl: null,
    }] } : query.includes('query GetAllACHAnalyses') ? { achAnalyses: [] }
      : query.includes('query GetAllAdvopsReports') ? { allAdvopsReports: [] }
      : query.includes('query GetAllMveDraftsForKanban') ? { allMveDrafts: [] }
      : { me: { username: 'alice', role: 'VIEWER' } };
    return { data, loading: false };
  });
});
it('shows every DEPLOYED item after selecting the status filter in card and list views', () => {
  renderBoard();
  fireEvent.mouseDown(screen.getAllByRole('combobox')[3]);
  fireEvent.click(screen.getByText('Deployed', { selector: '.ant-select-item-option-content' }));
  expect(screen.getByText('Showing 14 of 15 playbooks')).toBeInTheDocument();
  expect(screen.getAllByRole('link', { name: /^Deployed (rule|workbench)/ })).toHaveLength(14);
  expect(screen.getByRole('link', { name: 'Deployed rule 13' })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Research rule' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByLabelText('List view'));
  expect(screen.getAllByRole('link', { name: /^Deployed (rule|workbench)/ })).toHaveLength(14);
  fireEvent.click(screen.getByText('Reset Filters'));
  expect(screen.getByText('Showing 15 of 15 playbooks')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Research rule' })).toBeInTheDocument();
});
it.each([
  ['status=DEPLOYED', 14], ['type=DETECTION', 14], ['author=alice', 14],
  ['ptags=Production', 14], ['q=Deployed+rule', 13],
  ['status=DEPLOYED&type=DETECTION&author=alice&ptags=Production&q=Deployed', 13],
])('loads all matching items from shared-link filters: %s', (params, count) => {
  localStorage.setItem('kanban-statuses', JSON.stringify(['RESEARCH']));
  window.history.replaceState(null, '', `/?${params}${params.includes('status=') ? '' : '&status='}`);
  renderBoard();
  expect(screen.getByText(`Showing ${count} of 15 playbooks`)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Deployed rule 13' })).toBeInTheDocument();
});
it('refreshes all five datasets on mount', () => {
  renderBoard();
  const calls = mockUseQuery.mock.calls.filter(([query]) => query.includes('query GetAll'));
  expect(calls).toHaveLength(5);
  calls.forEach(([, options]) => expect(options.fetchPolicy).toBe('network-only'));
});
