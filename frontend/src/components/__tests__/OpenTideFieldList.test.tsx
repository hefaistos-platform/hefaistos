/**
 * Tests for OpenTideFieldList component.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import OpenTideFieldList from '../OpenTideFieldList';
import { FieldMetadata } from '../../graphql/opentide';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const AI_FIELD: FieldMetadata = {
  fieldPath: 'mdr.response.procedure.analysis',
  value: JSON.stringify('Check Event ID 4769'),
  aiGenerated: true,
  source: 'ai',
  fieldType: 'string',
};

const USER_FIELD: FieldMetadata = {
  fieldPath: 'mdr.metadata.title',
  value: JSON.stringify('Detect Kerberoasting'),
  aiGenerated: false,
  source: 'user',
  fieldType: 'string',
};

const ARRAY_FIELD: FieldMetadata = {
  fieldPath: 'mdr.platforms',
  value: JSON.stringify(['Windows', 'Active Directory']),
  aiGenerated: true,
  source: 'ai',
  fieldType: 'array',
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('OpenTideFieldList', () => {
  const onOverride = jest.fn();
  const onReset = jest.fn();

  beforeEach(() => {
    onOverride.mockClear();
    onReset.mockClear();
  });

  function renderList(
    fields: FieldMetadata[] = [AI_FIELD, USER_FIELD],
    overrides: Map<string, string> = new Map()
  ) {
    render(
      <OpenTideFieldList
        fields={fields}
        overrides={overrides}
        onOverride={onOverride}
        onReset={onReset}
      />
    );
  }

  test('renders field paths', () => {
    renderList();
    expect(screen.getByText('mdr.response.procedure.analysis')).toBeInTheDocument();
    expect(screen.getByText('mdr.metadata.title')).toBeInTheDocument();
  });

  test('shows AI tag for AI-generated fields', () => {
    renderList([AI_FIELD]);
    expect(screen.getByText('AI')).toBeInTheDocument();
  });

  test('shows User tag for user-provided fields', () => {
    renderList([USER_FIELD]);
    expect(screen.getByText('User')).toBeInTheDocument();
  });

  test('shows field type badge', () => {
    renderList([AI_FIELD]);
    expect(screen.getByText('string')).toBeInTheDocument();
  });

  test('shows array type badge for array fields', () => {
    renderList([ARRAY_FIELD]);
    expect(screen.getByText('array')).toBeInTheDocument();
  });

  test('shows Override button for each field', () => {
    renderList([AI_FIELD]);
    expect(screen.getByRole('button', { name: /Override/i })).toBeInTheDocument();
  });

  test('shows Overridden tag and Reset button when field is overridden', () => {
    const overrides = new Map([['mdr.response.procedure.analysis', JSON.stringify('Custom analysis')]]);
    renderList([AI_FIELD], overrides);
    expect(screen.getByText(/Overridden/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Reset/i })).toBeInTheDocument();
  });

  test('calls onReset when Reset button is clicked', () => {
    const overrides = new Map([['mdr.response.procedure.analysis', JSON.stringify('Custom')]]);
    renderList([AI_FIELD], overrides);
    fireEvent.click(screen.getByRole('button', { name: /Reset/i }));
    expect(onReset).toHaveBeenCalledWith('mdr.response.procedure.analysis');
  });

  test('shows inline editor when Override button is clicked on a simple field', () => {
    renderList([AI_FIELD]);
    fireEvent.click(screen.getByRole('button', { name: /Override/i }));
    expect(screen.getByRole('textbox')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Save/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Cancel/i })).toBeInTheDocument();
  });

  test('calls onOverride when Save is clicked with new value', () => {
    renderList([AI_FIELD]);
    fireEvent.click(screen.getByRole('button', { name: /Override/i }));
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'New analysis text' } });
    fireEvent.click(screen.getByRole('button', { name: /Save/i }));
    expect(onOverride).toHaveBeenCalledWith(
      'mdr.response.procedure.analysis',
      expect.any(String)
    );
  });

  test('hides inline editor when Cancel is clicked', () => {
    renderList([AI_FIELD]);
    fireEvent.click(screen.getByRole('button', { name: /Override/i }));
    expect(screen.getByRole('button', { name: /Save/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Cancel/i }));
    expect(screen.queryByRole('button', { name: /Save/i })).not.toBeInTheDocument();
  });

  test('shows empty state message when no fields', () => {
    renderList([]);
    expect(screen.getByText(/No AI-tracked fields/i)).toBeInTheDocument();
  });

  test('opens modal editor for complex (array) fields', async () => {
    renderList([ARRAY_FIELD]);
    fireEvent.click(screen.getByRole('button', { name: /Override/i }));
    // Modal should open for complex types
    await waitFor(() => {
      expect(screen.getByText(/Edit: mdr.platforms/)).toBeInTheDocument();
    });
  });
});
