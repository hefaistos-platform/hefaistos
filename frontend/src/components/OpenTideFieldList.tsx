/**
 * OpenTideFieldList
 *
 * Displays a list of AI-tracked OpenTIDE metadata fields with source indicators
 * and inline/modal override editing capabilities.
 */

import React, { useState } from 'react';
import {
  List,
  Tag,
  Button,
  Modal,
  Input,
  Typography,
  Space,
  Tooltip,
} from 'antd';
import {
  RobotOutlined,
  UserOutlined,
  SettingOutlined,
  EditOutlined,
  UndoOutlined,
} from '@ant-design/icons';
import { FieldMetadata, FieldType } from '../graphql/opentide';

const { Text, Paragraph } = Typography;

// ---------------------------------------------------------------------------
// Source tag helpers
// ---------------------------------------------------------------------------

function SourceTag({ source, overridden }: { source: string; overridden: boolean }) {
  if (overridden) {
    return (
      <Tag color="orange" style={{ marginLeft: 4 }}>
        ✏️ Overridden
      </Tag>
    );
  }
  if (source === 'ai') {
    return (
      <Tag color="blue" style={{ marginLeft: 4 }}>
        <RobotOutlined /> AI
      </Tag>
    );
  }
  if (source === 'user') {
    return (
      <Tag color="green" style={{ marginLeft: 4 }}>
        <UserOutlined /> User
      </Tag>
    );
  }
  return (
    <Tag color="default" style={{ marginLeft: 4 }}>
      <SettingOutlined /> Default
    </Tag>
  );
}

function FieldTypeTag({ fieldType }: { fieldType: FieldType }) {
  const typeColors: Record<string, string> = {
    string: 'geekblue',
    array: 'purple',
    object: 'cyan',
    number: 'volcano',
    boolean: 'magenta',
    unknown: 'default',
  };
  return (
    <Tag color={typeColors[fieldType] || 'default'} style={{ fontSize: 10 }}>
      {fieldType}
    </Tag>
  );
}

// ---------------------------------------------------------------------------
// Value display helper
// ---------------------------------------------------------------------------

function formatValue(jsonStr: string): string {
  try {
    const parsed = JSON.parse(jsonStr);
    if (typeof parsed === 'string') return parsed;
    return JSON.stringify(parsed, null, 2);
  } catch {
    return jsonStr;
  }
}

function isComplexType(fieldType: FieldType): boolean {
  return fieldType === 'array' || fieldType === 'object';
}

// ---------------------------------------------------------------------------
// Single field row editor
// ---------------------------------------------------------------------------

interface FieldRowProps {
  field: FieldMetadata;
  overrideValue: string | undefined; // JSON string or undefined
  onSave: (fieldPath: string, jsonValue: string) => void;
  onReset: (fieldPath: string) => void;
}

const FieldRow: React.FC<FieldRowProps> = ({ field, overrideValue, onSave, onReset }) => {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState('');
  const [editError, setEditError] = useState<string | null>(null);
  const [complexModalOpen, setComplexModalOpen] = useState(false);

  const currentJsonValue = overrideValue !== undefined ? overrideValue : field.value;
  const isOverridden = overrideValue !== undefined;
  const displayValue = formatValue(currentJsonValue);
  const complex = isComplexType(field.fieldType as FieldType);

  const startEdit = () => {
    setEditText(formatValue(currentJsonValue));
    setEditError(null);
    if (complex) {
      setComplexModalOpen(true);
    } else {
      setEditing(true);
    }
  };

  const handleSaveSimple = () => {
    // For simple types (string/number/boolean) wrap in JSON if not already valid JSON
    let jsonVal: string;
    const trimmed = editText.trim();
    try {
      JSON.parse(trimmed); // already valid JSON? if so, use as-is
      jsonVal = trimmed;
    } catch {
      // Treat as plain string value
      jsonVal = JSON.stringify(editText);
    }
    onSave(field.fieldPath, jsonVal);
    setEditing(false);
    setEditError(null);
  };

  const handleSaveComplex = () => {
    try {
      // Validate JSON before saving – the parsed value is intentionally discarded;
      // we save the original string to avoid any serialisation round-trip differences.
      JSON.parse(editText);
      onSave(field.fieldPath, editText);
      setComplexModalOpen(false);
      setEditError(null);
    } catch {
      setEditError('Invalid JSON – please correct the syntax before saving.');
    }
  };

  return (
    <List.Item
      style={{ padding: '8px 0', flexDirection: 'column', alignItems: 'flex-start' }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 4, width: '100%' }}>
        <Text strong style={{ fontFamily: 'monospace', fontSize: 12 }}>
          {field.fieldPath}
        </Text>
        <FieldTypeTag fieldType={field.fieldType as FieldType} />
        <SourceTag source={field.source} overridden={isOverridden} />
        <Space style={{ marginLeft: 'auto' }}>
          {isOverridden && (
            <Tooltip title="Reset to original AI/default value">
              <Button
                size="small"
                icon={<UndoOutlined />}
                onClick={() => onReset(field.fieldPath)}
              >
                Reset
              </Button>
            </Tooltip>
          )}
          <Tooltip title="Override this field value">
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={startEdit}
            >
              Override
            </Button>
          </Tooltip>
        </Space>
      </div>

      {/* Inline editor (simple types) */}
      {editing && !complex ? (
        <div style={{ marginTop: 6, width: '100%' }}>
          <Input.TextArea
            autoFocus
            rows={3}
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            style={{ fontFamily: 'monospace', fontSize: 12 }}
          />
          <Space style={{ marginTop: 4 }}>
            <Button size="small" type="primary" onClick={handleSaveSimple}>
              Save
            </Button>
            <Button size="small" onClick={() => { setEditing(false); setEditError(null); }}>
              Cancel
            </Button>
          </Space>
        </div>
      ) : (
        /* Value display */
        <Paragraph
          style={{
            marginTop: 4,
            marginBottom: 0,
            fontFamily: 'monospace',
            fontSize: 11,
            color: 'var(--hef-text-secondary)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            maxHeight: 80,
            overflow: 'hidden',
          }}
        >
          {displayValue}
        </Paragraph>
      )}

      {/* Complex editor modal (arrays / objects) */}
      <Modal
        open={complexModalOpen}
        title={`Edit: ${field.fieldPath}`}
        onCancel={() => { setComplexModalOpen(false); setEditError(null); }}
        onOk={handleSaveComplex}
        okText="Save"
        width={600}
        className="opentide-field-editor-modal"
      >
        <Input.TextArea
          rows={12}
          value={editText}
          onChange={(e) => { setEditText(e.target.value); setEditError(null); }}
          style={{
            fontFamily: 'monospace',
            fontSize: 12,
            background: 'var(--hef-bg-subtle)',
            color: 'var(--hef-text-primary)',
            borderColor: 'var(--hef-border)',
          }}
        />
        {editError && (
          <Text type="danger" style={{ marginTop: 4, display: 'block' }}>
            {editError}
          </Text>
        )}
      </Modal>
    </List.Item>
  );
};

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

export interface OpenTideFieldListProps {
  fields: FieldMetadata[];
  overrides: Map<string, string>; // fieldPath → JSON value
  onOverride: (fieldPath: string, jsonValue: string) => void;
  onReset: (fieldPath: string) => void;
}

const OpenTideFieldList: React.FC<OpenTideFieldListProps> = ({
  fields,
  overrides,
  onOverride,
  onReset,
}) => {
  if (!fields.length) {
    return (
      <Text type="secondary" italic>
        No AI-tracked fields found for this playbook.
      </Text>
    );
  }

  return (
    <List
      dataSource={fields}
      renderItem={(field) => (
        <FieldRow
          key={field.fieldPath}
          field={field}
          overrideValue={overrides.get(field.fieldPath)}
          onSave={onOverride}
          onReset={onReset}
        />
      )}
      style={{ maxHeight: 500, overflowY: 'auto' }}
    />
  );
};

export default OpenTideFieldList;
