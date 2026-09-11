import React, { useState } from 'react';
import { gql } from '@apollo/client';
import { useMutation } from '@apollo/client/react';
import { Link } from 'react-router-dom';
import { Card, Form, Input, Button, Typography, Alert } from 'antd';

const SUBMIT_REGISTRATION_REQUEST_MUTATION = gql`
  mutation SubmitRegistrationRequest($name: String!, $email: String!, $subject: String!, $message: String!) {
    submitRegistrationRequest(name: $name, email: $email, subject: $subject, message: $message) {
      ok
      message
    }
  }
`;

interface SubmitRegistrationRequestData {
  submitRegistrationRequest: {
    ok: boolean;
    message: string;
  };
}

interface SubmitRegistrationRequestVars {
  name: string;
  email: string;
  subject: string;
  message: string;
}

export const RegistrationPage = () => {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [validationError, setValidationError] = useState('');

  const [submitRegistrationRequest, { loading, error }] = useMutation<
    SubmitRegistrationRequestData,
    SubmitRegistrationRequestVars
  >(SUBMIT_REGISTRATION_REQUEST_MUTATION);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setValidationError('');

    const normalizedName = name.trim();
    const normalizedEmail = email.trim();
    const normalizedSubject = subject.trim();
    const normalizedMessage = message.trim();

    if (!normalizedName || !normalizedEmail || !normalizedSubject || !normalizedMessage) {
      setValidationError('All fields are required.');
      return;
    }

    try {
      const { data } = await submitRegistrationRequest({
        variables: {
          name: normalizedName,
          email: normalizedEmail,
          subject: normalizedSubject,
          message: normalizedMessage,
        },
      });
      if (data?.submitRegistrationRequest?.ok) {
        setSubmitted(true);
        setName('');
        setEmail('');
        setSubject('');
        setMessage('');
      }
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('Registration request failed:', e);
    }
  };

  return (
    <div className="auth-shell">
      <Card className="auth-card" style={{ width: 520 }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <span className="logo-title" style={{ display: 'block', fontSize: 32 }}>
            HEFAISTOS
          </span>
        </div>
        <Typography.Paragraph className="auth-subtitle">
          Registration Request
        </Typography.Paragraph>

        {submitted && (
          <Alert
            type="success"
            showIcon
            style={{ marginBottom: 16 }}
            message="Request submitted"
            description="Your registration request was sent. We will contact you soon."
          />
        )}
        {(error || validationError) && (
          <Alert
            type="error"
            showIcon
            style={{ marginBottom: 16 }}
            message={validationError || error?.message}
          />
        )}

        <Form layout="vertical" onSubmitCapture={handleSubmit}>
          <Form.Item label="Name" required>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              size="large"
              autoFocus
              disabled={loading}
              placeholder="Enter your name"
            />
          </Form.Item>
          <Form.Item label="Email" required>
            <Input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              size="large"
              disabled={loading}
              placeholder="Enter your email"
            />
          </Form.Item>
          <Form.Item label="Subject" required>
            <Input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              size="large"
              disabled={loading}
              placeholder="Enter subject"
            />
          </Form.Item>
          <Form.Item label="Message" required>
            <Input.TextArea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={5}
              disabled={loading}
              placeholder="Enter your message"
            />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            block
            size="large"
            loading={loading}
            style={{ marginTop: 8, fontWeight: 600 }}
          >
            {loading ? 'Sending...' : 'SEND'}
          </Button>
        </Form>

        <div style={{ textAlign: 'center', marginTop: 16 }}>
          <Link to="/login" className="theme-link">
            ← Back to Login
          </Link>
        </div>

        <Typography.Paragraph className="auth-footer">
          © {new Date().getFullYear()} HEFAISTOS Platform
        </Typography.Paragraph>
      </Card>
    </div>
  );
};
