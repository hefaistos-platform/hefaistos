import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Button, Form } from 'antd';
import { TlpMaximumSelect } from './TlpMaximumSelect';

test('GREEN shows exactly GREEN, CLEAR, and UNCLEAR as permitted', () => {
  render(<TlpMaximumSelect value="GREEN" />);
  expect(screen.getByText('Permits TLP:CLEAR, TLP:GREEN, TLP:UNCLEAR.')).toBeInTheDocument();
  expect(screen.getByRole('link')).toHaveAttribute('href', 'https://tlp-unclear.org/');
});

test('maximum selection binds to a form and excludes UNCLEAR as an option', async () => {
  const onFinish = jest.fn();
  render(
    <Form initialValues={{ maximum: 'RED' }} onFinish={onFinish}>
      <Form.Item name="maximum"><TlpMaximumSelect /></Form.Item>
      <Button htmlType="submit">Save maximum</Button>
    </Form>,
  );
  fireEvent.mouseDown(screen.getByRole('combobox'));
  expect(screen.queryByText('TLP:UNCLEAR', { selector: 'span' })).not.toBeInTheDocument();
  fireEvent.click((await screen.findAllByText('TLP:CLEAR')).pop()!);
  expect(screen.getByText('Permits TLP:CLEAR, TLP:UNCLEAR.')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Save maximum' }));
  await waitFor(() => expect(onFinish).toHaveBeenCalledWith({ maximum: 'CLEAR' }));
});
