import React from 'react';
import { render, screen } from '@testing-library/react';
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

test('renders login page with form fields', () => {
  render(
    <MemoryRouter>
      <ThemeProvider>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </ThemeProvider>
    </MemoryRouter>
  );

  expect(screen.getByRole('heading', { name: /hefaistos by lemnian one/i })).toBeInTheDocument();

  // Check if the input fields are present
  expect(screen.getByPlaceholderText(/enter your username/i)).toBeInTheDocument();
  expect(screen.getByPlaceholderText(/enter your password/i)).toBeInTheDocument();

  // Check if the login button is present
  expect(screen.getByRole('button', { name: /^sign in$/i })).toBeInTheDocument();

  const registerLink = screen.getByRole('link', { name: /register/i });
  expect(registerLink).toBeInTheDocument();
  expect(registerLink).toHaveAttribute('href', 'https://payme.hefaistos.org/');
  expect(screen.getByText(/terms and conditions/i)).toBeInTheDocument();
});
