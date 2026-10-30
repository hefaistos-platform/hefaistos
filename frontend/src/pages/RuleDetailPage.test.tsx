import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useMutation, useQuery } from '@apollo/client';
import { useNavigate } from 'react-router-dom';
import { RuleDetailPage } from './RuleDetailPage';

jest.mock('@apollo/client', () => ({ gql: jest.fn(), useQuery: jest.fn(), useMutation: jest.fn() }));
jest.mock('@apollo/client/react', () => ({
  useQuery: (...args: unknown[]) => require('@apollo/client').useQuery(...args),
  useMutation: (...args: unknown[]) => require('@apollo/client').useMutation(...args),
}));
jest.mock('react-router-dom', () => ({ useParams: () => ({ ruleId: '7' }), useNavigate: jest.fn() }));
jest.mock('../context/ThemeContext', () => ({ useTheme: () => ({ resolvedTheme: 'light' }) }));
jest.mock('../components/RuleConversionModal', () => ({ RuleConversionModal: () => null }));
jest.mock('../components/RuleDeploymentModal', () => ({ RuleDeploymentModal: () => null }));
jest.mock('react-syntax-highlighter', () => ({ Prism: ({ children }: { children: React.ReactNode }) => <pre>{children}</pre> }));
jest.mock('react-syntax-highlighter/dist/esm/styles/prism', () => ({ solarizedlight: {}, oneDark: {} }));

const rule = { id: '7', title: 'Existing rule', rawContent: 'DeviceProcessEvents | take 1', format: 'KQL',
  author: 'analyst', canEdit: true, workbenchOwned: true, workbenchId: 'wb', workbenchTitle: 'Detection' };
const update = jest.fn();
const navigate = jest.fn();
const refetch = jest.fn().mockResolvedValue({});
beforeEach(() => {
  jest.clearAllMocks();
  refetch.mockResolvedValue({});
  (useNavigate as jest.Mock).mockReturnValue(navigate);
  (useQuery as jest.Mock).mockReturnValue({ refetch, data: { rule, me: { username: 'analyst', role: 'ANALYST' } } });
  (useMutation as jest.Mock).mockReturnValue([update, { loading: false }]);
});

test('Workbench-owned Edit opens raw content and saves the selected rule', async () => {
  update.mockResolvedValue({ data: { updateDetectionRule: { success: true } } });
  render(<RuleDetailPage />);
  fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
  const input = screen.getByLabelText('Raw rule content');
  expect(input).toHaveValue(rule.rawContent);
  fireEvent.change(input, { target: { value: 'DeviceProcessEvents | take 2' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(update).toHaveBeenCalledWith(expect.objectContaining({ variables: { ruleId: '7', rawContent: 'DeviceProcessEvents | take 2' } })));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(navigate).not.toHaveBeenCalled();
});

test('Workbench editor button opens Workbench directly', () => {
  render(<RuleDetailPage />);
  fireEvent.click(screen.getByRole('button', { name: 'Open Workbench editor' }));
  expect(navigate).toHaveBeenCalledWith('/playbooks/wb');
});

test('standalone Edit continues to open the full Rule Hub editor', () => {
  (useQuery as jest.Mock).mockReturnValue({ data: { rule: { ...rule, workbenchOwned: false } } });
  render(<RuleDetailPage />);
  fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
  expect(navigate).toHaveBeenCalledWith('/rules/7/edit');
  expect(screen.queryByLabelText('Raw rule content')).not.toBeInTheDocument();
});


test('saved rule details expose AI feedback and a simple how-to', () => {
  render(<RuleDetailPage />);
  fireEvent.click(screen.getByRole('button', { name: 'AI feedback' }));
  expect(screen.getByText('AI feedback: explain a saved correction')).toBeInTheDocument();
  expect(screen.getByText(/Correct the rule in the editor, then save it/)).toBeInTheDocument();
});
