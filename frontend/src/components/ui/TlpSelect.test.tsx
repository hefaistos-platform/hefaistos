import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Button, Form } from 'antd';
import { TlpSelect } from './TlpSelect';

test('saves the selected classification through an Ant Design form', async () => {
  const onFinish = jest.fn();
  render(
    <Form initialValues={{ tlp: 'UNCLEAR' }} onFinish={onFinish}>
      <Form.Item name="tlp"><TlpSelect /></Form.Item>
      <Button htmlType="submit">Save classification</Button>
    </Form>,
  );

  expect(screen.getByRole('link', { name: 'About TLP:UNCLEAR' })).toHaveAttribute('href', 'https://tlp-unclear.org/');
  fireEvent.mouseDown(screen.getByRole('combobox'));
  fireEvent.click(await screen.findByText('TLP:RED — Personal for named recipients'));
  fireEvent.click(screen.getByRole('button', { name: 'Save classification' }));

  await waitFor(() => expect(onFinish).toHaveBeenCalledWith({ tlp: 'RED' }));
  expect(screen.queryByRole('link', { name: 'About TLP:UNCLEAR' })).not.toBeInTheDocument();
});

test('ACH can omit the source link while retaining the purple UNCLEAR badge', () => {
  render(<TlpSelect value="UNCLEAR" showUnclearSourceLink={false} />);
  expect(screen.getByText('TLP:UNCLEAR')).toHaveClass('text-purple-700');
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
});

test('a locked classification remains visible and cannot be changed', () => {
  render(<TlpSelect value="UNCLEAR" disabled />);
  expect(screen.getByText('TLP:UNCLEAR')).toHaveClass('text-purple-700');
  expect(screen.getByRole('combobox')).toBeDisabled();
});
