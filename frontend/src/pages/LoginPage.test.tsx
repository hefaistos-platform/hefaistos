import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
// Minimal Apollo hook mock: only useMutation needed, returns tuple expected by component
jest.mock('@apollo/client', () => ({
  gql: (lits: any) => lits,
}));
jest.mock('@apollo/client/react', () => ({
  useMutation: () => [jest.fn(), { loading: false, error: null }],
  useQuery: () => ({ data: undefined }),
  useApolloClient: () => ({ query: jest.fn(), clearStore: jest.fn() }),
}));
import { AuthProvider } from '../context/AuthContext';
import { ThemeProvider } from '../context/ThemeContext';
import { LoginPage } from './LoginPage';

test('renders login page and opens terms modal', () => {
  render(
    <MemoryRouter>
      <ThemeProvider>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </ThemeProvider>
    </MemoryRouter>
  );

  expect(screen.getByRole('heading', { name: /hefaistos detection platform/i })).toBeInTheDocument();

  expect(screen.getByPlaceholderText(/enter your username/i)).toBeInTheDocument();
  expect(screen.getByPlaceholderText(/enter your password/i)).toBeInTheDocument();

  expect(screen.getByRole('button', { name: /^sign in$/i })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /forgot password/i })).toBeInTheDocument();

  const termsButton = screen.getByRole('button', { name: /terms and conditions/i });
  expect(termsButton).toBeInTheDocument();

  fireEvent.click(termsButton);

  expect(screen.getByText(/these terms summarize the agpl-3\.0 license model used by hefaistos/i)).toBeInTheDocument();
  expect(screen.getByText(/the responsibility lies with the person using the platform/i)).toBeInTheDocument();
  expect(screen.getByText(/contact \(obfuscated\): m3c4n1sm0\\@xprivacy\.cz/i)).toBeInTheDocument();
});
