import React from 'react';
import { Button, Input, Select, Space, Typography } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';

const { Text } = Typography;

export const newId = (prefix: string) => `${prefix}${Math.random().toString(36).slice(2, 7)}`;

/** A list of plain text entries the user can add to and remove from. */
export const StringList: React.FC<{
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  addLabel: string;
  rows?: number;
}> = ({ value, onChange, placeholder, addLabel, rows = 1 }) => (
  <Space direction="vertical" style={{ width: '100%' }}>
    {value.map((text, i) => (
      <Space key={i} align="start" style={{ width: '100%' }}>
        <Input.TextArea
          autoSize={{ minRows: rows, maxRows: 6 }}
          style={{ width: 520 }}
          value={text}
          placeholder={placeholder}
          onChange={(e) => onChange(value.map((v, j) => (j === i ? e.target.value : v)))}
        />
        <Button icon={<DeleteOutlined />} aria-label="Remove" onClick={() => onChange(value.filter((_, j) => j !== i))} />
      </Space>
    ))}
    <Button size="small" icon={<PlusOutlined />} onClick={() => onChange([...value, ''])}>{addLabel}</Button>
  </Space>
);

export interface ObjField {
  key: string;
  label: string;
  width?: number;
  options?: { value: string; label: string }[];
  multiline?: boolean;
}

/** A list of small records (match elements, exclusions, fields), edited inline. */
export const RecordList: React.FC<{
  value: any[];
  onChange: (next: any[]) => void;
  fields: ObjField[];
  blank: () => any;
  addLabel: string;
  empty?: string;
}> = ({ value, onChange, fields, blank, addLabel, empty }) => (
  <Space direction="vertical" style={{ width: '100%' }}>
    {value.length === 0 && empty && <Text type="secondary">{empty}</Text>}
    {value.map((row, i) => (
      <div key={row.id ?? i} style={{ border: '1px solid #f0f0f0', borderRadius: 6, padding: 8 }}>
        <Space wrap align="start">
          {fields.map((f) => (
            <div key={f.key}>
              <div><Text type="secondary" style={{ fontSize: 12 }}>{f.label}</Text></div>
              {f.options ? (
                <Select
                  style={{ width: f.width ?? 200 }}
                  value={row[f.key] || undefined}
                  options={f.options}
                  placeholder="Choose"
                  onChange={(v) => onChange(value.map((r, j) => (j === i ? { ...r, [f.key]: v } : r)))}
                />
              ) : f.multiline ? (
                <Input.TextArea
                  autoSize={{ minRows: 1, maxRows: 5 }}
                  style={{ width: f.width ?? 300 }}
                  value={row[f.key] ?? ''}
                  onChange={(e) => onChange(value.map((r, j) => (j === i ? { ...r, [f.key]: e.target.value } : r)))}
                />
              ) : (
                <Input
                  style={{ width: f.width ?? 200 }}
                  value={row[f.key] ?? ''}
                  onChange={(e) => onChange(value.map((r, j) => (j === i ? { ...r, [f.key]: e.target.value } : r)))}
                />
              )}
            </div>
          ))}
          <Button
            icon={<DeleteOutlined />}
            aria-label="Remove"
            style={{ marginTop: 20 }}
            onClick={() => onChange(value.filter((_, j) => j !== i))}
          />
        </Space>
      </div>
    ))}
    <Button size="small" icon={<PlusOutlined />} onClick={() => onChange([...value, blank()])}>{addLabel}</Button>
  </Space>
);

export const Field: React.FC<{ label: string; help?: string; required?: boolean; children: React.ReactNode }> = ({
  label, help, required, children,
}) => (
  <div style={{ marginBottom: 20 }}>
    <div style={{ marginBottom: 4 }}>
      <Text strong>{label}</Text>{required && <Text type="danger"> *</Text>}
    </div>
    {help && <div style={{ marginBottom: 6 }}><Text type="secondary">{help}</Text></div>}
    {children}
  </div>
);
