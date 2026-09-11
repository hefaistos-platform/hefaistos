import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

jest.mock('@apollo/client', () => ({
  gql: (lits: any) => lits,
}));
jest.mock('@apollo/client/react', () => ({
  useMutation: () => [jest.fn(), { loading: false, error: null }],
}));

import { RegistrationPage } from './RegistrationPage';

test('renders registration page form fields', () => {
  render(
    <MemoryRouter>
      <RegistrationPage />
    </MemoryRouter>
  );

  expect(screen.getByText(/registration request/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/subject/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/message/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument();
});
