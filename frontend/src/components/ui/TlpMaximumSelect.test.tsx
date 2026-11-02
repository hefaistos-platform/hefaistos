import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Button, Form } from 'antd';
import { TlpMaximumSelect } from './TlpMaximumSelect';

test('GREEN shows exactly GREEN, CLEAR, and UNCLEAR as permitted', () => {
  render(<TlpMaximumSelect value="GREEN" />);
  expect(screen.getByText('Permits TLP:CLEAR, TLP:GREEN, TLP:UNCLEAR.')).toBeInTheDocument();
  expect(screen.getByRole('link')).toHaveAttribute('href', 'https://tlp-unclear.org/');
});

test('maximum selection offers all six classifications and saves UNCLEAR', async () => {
  const onFinish = jest.fn();
  render(
    <Form initialValues={{ maximum: 'RED' }} onFinish={onFinish}>
      <Form.Item name="maximum"><TlpMaximumSelect /></Form.Item>
      <Button htmlType="submit">Save maximum</Button>
    </Form>,
  );
  fireEvent.mouseDown(screen.getByRole('combobox'));
  for (const level of ['CLEAR', 'GREEN', 'AMBER', 'AMBER+STRICT', 'RED', 'UNCLEAR']) {
    expect((await screen.findAllByText(`TLP:${level}`)).length).toBeGreaterThan(0);
  }
  fireEvent.click((await screen.findAllByText('TLP:UNCLEAR')).pop()!);
  expect(screen.getByText('Permits TLP:UNCLEAR.')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Save maximum' }));
  await waitFor(() => expect(onFinish).toHaveBeenCalledWith({ maximum: 'UNCLEAR' }));
});
