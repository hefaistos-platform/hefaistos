import React, { useEffect } from 'react';
import { gql } from '@apollo/client';
import { Form, Input, Modal, Select } from 'antd';

const { TextArea } = Input;

export const CAPABILITY_ABSTRACTIONS_QUERY = gql`
  query CapabilityAbstractions($techniqueId: String, $includeBaseline: Boolean) {
    capabilityAbstractions(techniqueId: $techniqueId, includeBaseline: $includeBaseline) {
      id
      abstractionLayer
      componentArtifact
      adversaryPurpose
      commonEvasions
      expectedObservables
      applicableTelemetry
      detectionValue
      robustnessLevel
      sourceKind
      reviewStatus
      version
      organizationName
      isEditable
      isSharedBaseline
      createdAt
      updatedAt
      technique {
        techniqueId
        name
      }
    }
  }
`;

export const ALL_ATTACK_TECHNIQUES_QUERY = gql`
  query AllAttackTechniquesForCAL($search: String, $limit: Int) {
    allAttackTechniques(search: $search, limit: $limit) {
      id
      techniqueId
      name
    }
  }
`;

export const CREATE_CAPABILITY_ABSTRACTION_MUTATION = gql`
  mutation CreateCapabilityAbstraction(
    $techniqueId: String!
    $abstractionLayer: String!
    $componentArtifact: String!
    $adversaryPurpose: String
    $commonEvasions: String
    $expectedObservables: String
    $applicableTelemetry: String
    $detectionValue: String
    $robustnessLevel: Int
    $reviewStatus: String
  ) {
    createCapabilityAbstraction(
      techniqueId: $techniqueId
      abstractionLayer: $abstractionLayer
      componentArtifact: $componentArtifact
      adversaryPurpose: $adversaryPurpose
      commonEvasions: $commonEvasions
      expectedObservables: $expectedObservables
      applicableTelemetry: $applicableTelemetry
      detectionValue: $detectionValue
      robustnessLevel: $robustnessLevel
      reviewStatus: $reviewStatus
    ) {
      capabilityAbstraction {
        id
        abstractionLayer
      }
    }
  }
`;

export const UPDATE_CAPABILITY_ABSTRACTION_MUTATION = gql`
  mutation UpdateCapabilityAbstraction(
    $capabilityAbstractionId: UUID!
    $abstractionLayer: String
    $componentArtifact: String
    $adversaryPurpose: String
    $commonEvasions: String
    $expectedObservables: String
    $applicableTelemetry: String
    $detectionValue: String
    $robustnessLevel: Int
    $reviewStatus: String
  ) {
    updateCapabilityAbstraction(
      capabilityAbstractionId: $capabilityAbstractionId
      abstractionLayer: $abstractionLayer
      componentArtifact: $componentArtifact
      adversaryPurpose: $adversaryPurpose
      commonEvasions: $commonEvasions
      expectedObservables: $expectedObservables
      applicableTelemetry: $applicableTelemetry
      detectionValue: $detectionValue
      robustnessLevel: $robustnessLevel
      reviewStatus: $reviewStatus
    ) {
      capabilityAbstraction {
        id
      }
    }
  }
`;

export const DELETE_CAPABILITY_ABSTRACTION_MUTATION = gql`
  mutation DeleteCapabilityAbstraction($capabilityAbstractionId: UUID!) {
    deleteCapabilityAbstraction(capabilityAbstractionId: $capabilityAbstractionId) {
      ok
    }
  }
`;

export const LAYER_OPTIONS = [
  { value: 'TOOL', label: 'Tool / Binary' },
  { value: 'API_EXPORT', label: 'API / Export' },
  { value: 'COM_IPC', label: 'COM / IPC' },
  { value: 'REGISTRY_OBJECT', label: 'Registry Object' },
  { value: 'PROTOCOL', label: 'Protocol' },
  { value: 'PROCESS_BEHAVIOR', label: 'Process Behavior' },
  { value: 'NETWORK_BEHAVIOR', label: 'Network Behavior' },
];

export const REVIEW_STATUS_OPTIONS = [
  { value: 'DRAFT', label: 'Draft' },
  { value: 'REVIEWED', label: 'Reviewed' },
  { value: 'APPROVED', label: 'Approved' },
];

export const ROBUSTNESS_LEVEL_OPTIONS = [
  { value: 1, label: '1 - Ephemeral' },
  { value: 2, label: '2 - Tool / artifact' },
  { value: 3, label: '3 - Moderate' },
  { value: 4, label: '4 - Strong behavior' },
  { value: 5, label: '5 - Invariant / technique' },
];

export type CapabilityAbstractionEntry = {
  id: string;
  abstractionLayer: string;
  componentArtifact: string;
  adversaryPurpose?: string;
  commonEvasions?: string;
  expectedObservables?: string;
  applicableTelemetry?: string;
  detectionValue?: string;
  robustnessLevel?: number;
  sourceKind?: string;
  reviewStatus?: string;
  version?: number;
  organizationName?: string;
  isEditable?: boolean;
  isSharedBaseline?: boolean;
  createdAt?: string;
  updatedAt?: string;
  technique?: {
    techniqueId: string;
    name: string;
  };
};

export type AttackTechniqueOption = {
  id: string;
  techniqueId: string;
  name: string;
};

export type CapabilityAbstractionFormValues = {
  techniqueId?: string;
  abstractionLayer: string;
  componentArtifact: string;
  adversaryPurpose?: string;
  commonEvasions?: string;
  expectedObservables?: string;
  applicableTelemetry?: string;
  detectionValue?: string;
  robustnessLevel?: number;
  reviewStatus?: string;
};

export function getLayerLabel(layer: string): string {
  return LAYER_OPTIONS.find((option) => option.value === layer)?.label || layer;
}

interface CapabilityAbstractionFormModalProps {
  open: boolean;
  editingEntry: CapabilityAbstractionEntry | null;
  defaultTechniqueId?: string;
  techniqueOptions: Array<{ value: string; label: string }>;
  attackTechniquesLoading?: boolean;
  saving?: boolean;
  onTechniqueSearch: (search: string) => void;
  onTechniqueFocus: () => void;
  onCancel: () => void;
  onSave: (values: CapabilityAbstractionFormValues) => Promise<void> | void;
}

export const CapabilityAbstractionFormModal: React.FC<CapabilityAbstractionFormModalProps> = ({
  open,
  editingEntry,
  defaultTechniqueId,
  techniqueOptions,
  attackTechniquesLoading = false,
  saving = false,
  onTechniqueSearch,
  onTechniqueFocus,
  onCancel,
  onSave,
}) => {
  const [form] = Form.useForm<CapabilityAbstractionFormValues>();

  useEffect(() => {
    if (!open) {
      return;
    }

    if (editingEntry) {
      form.setFieldsValue({
        abstractionLayer: editingEntry.abstractionLayer,
        componentArtifact: editingEntry.componentArtifact,
        adversaryPurpose: editingEntry.adversaryPurpose,
        commonEvasions: editingEntry.commonEvasions,
        expectedObservables: editingEntry.expectedObservables,
        applicableTelemetry: editingEntry.applicableTelemetry,
        detectionValue: editingEntry.detectionValue,
        robustnessLevel: editingEntry.robustnessLevel,
        reviewStatus: editingEntry.reviewStatus,
      });
      return;
    }

    form.resetFields();
    form.setFieldsValue({
      reviewStatus: 'DRAFT',
      techniqueId: defaultTechniqueId,
    });
  }, [defaultTechniqueId, editingEntry, form, open]);

  return (
    <Modal
      title={editingEntry ? 'Edit Capability Abstraction' : 'Add Capability Abstraction'}
      open={open}
      onCancel={onCancel}
      onOk={async () => {
        const values = await form.validateFields();
        await onSave(values);
      }}
      okButtonProps={{ loading: saving }}
      destroyOnClose
      className="capability-library-modal"
    >
      <Form<CapabilityAbstractionFormValues> form={form} layout="vertical">
        {!editingEntry && (
          <Form.Item
            name="techniqueId"
            label="ATT&CK technique"
            rules={[{ required: true, message: 'Please select an ATT&CK technique.' }]}
          >
            <Select
              showSearch
              allowClear
              filterOption={false}
              placeholder="Select ATT&CK technique"
              options={techniqueOptions}
              loading={attackTechniquesLoading}
              onSearch={onTechniqueSearch}
              onFocus={onTechniqueFocus}
            />
          </Form.Item>
        )}
        <Form.Item name="abstractionLayer" label="Abstraction layer" rules={[{ required: true }]}>
          <Select options={LAYER_OPTIONS} />
        </Form.Item>
        <Form.Item name="componentArtifact" label="Component / artifact" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="adversaryPurpose" label="Adversary purpose">
          <TextArea rows={2} />
        </Form.Item>
        <Form.Item name="commonEvasions" label="Common evasions / variations">
          <TextArea rows={2} />
        </Form.Item>
        <Form.Item name="expectedObservables" label="Expected observables">
          <TextArea rows={2} />
        </Form.Item>
        <Form.Item name="applicableTelemetry" label="Applicable telemetry">
          <TextArea rows={2} />
        </Form.Item>
        <Form.Item name="detectionValue" label="Detection value">
          <TextArea rows={2} />
        </Form.Item>
        <Form.Item name="robustnessLevel" label="Robustness level">
          <Select options={ROBUSTNESS_LEVEL_OPTIONS} />
        </Form.Item>
        <Form.Item name="reviewStatus" label="Review status">
          <Select options={REVIEW_STATUS_OPTIONS} />
        </Form.Item>
      </Form>
    </Modal>
  );
};
