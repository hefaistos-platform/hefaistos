import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { MockedProvider } from '@apollo/client/testing';
import { OpenTidePreviewModal } from '../OpenTidePreviewModal';
import { GET_LATEST_OPENTIDE_PREVIEW } from '../../graphql/opentide';

jest.mock('react-syntax-highlighter', () => ({
  Prism: ({ children }: { children: string }) => <pre data-testid="syntax-hl">{children}</pre>,
}));
jest.mock('react-syntax-highlighter/dist/esm/styles/prism', () => ({ oneLight: {} }));
jest.mock('js-yaml', () => ({ dump: (obj: any) => JSON.stringify(obj, null, 2) }));

const PLAYBOOK_ID = '00000000-0000-0000-0000-000000000001';

function renderModal(props: Partial<React.ComponentProps<typeof OpenTidePreviewModal>> = {}) {
  const onClose = jest.fn();
  const onCommit = jest.fn();
  const mocks = [
    {
      request: {
        query: GET_LATEST_OPENTIDE_PREVIEW,
        variables: { playbookId: PLAYBOOK_ID },
      },
      result: {
        data: {
          latestOpentidePreview: null,
        },
      },
    },
  ];

  render(
    <MockedProvider mocks={mocks}>
      <OpenTidePreviewModal
        playbookId={PLAYBOOK_ID}
        visible
        onClose={onClose}
        onCommit={onCommit}
        {...props}
      />
    </MockedProvider>
  );

  return { onClose, onCommit };
}

describe('OpenTidePreviewModal', () => {
  test('renders modal when visible is true', () => {
    renderModal();
    expect(screen.getByText(/Preview OpenTIDE Metadata/i)).toBeInTheDocument();
  });

  test('shows generate preview prompt before preview exists', () => {
    renderModal();
    expect(screen.getByRole('button', { name: /Generate Preview/i })).toBeInTheDocument();
  });

  test('continue button is disabled before preview exists', () => {
    renderModal();
    expect(screen.getByRole('button', { name: /Continue to HEF Publish/i })).toBeDisabled();
  });

  test('calls onClose when cancel is clicked', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole('button', { name: /Cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
