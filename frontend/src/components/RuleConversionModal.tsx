/**
 * RuleConversionModal Component
 *
 * NOTE: Sigma conversion support has been removed from HEFAISTOS.
 * This component is kept as a stub to avoid breaking existing callers.
 */

import React from 'react';
import { Modal, Alert, Space } from 'antd';
import { SwapOutlined } from '@ant-design/icons';

interface RuleConversionModalProps {
  visible: boolean;
  ruleId: string;
  ruleTitle: string;
  originalFormat: string;
  onCancel: () => void;
}

export const RuleConversionModal: React.FC<RuleConversionModalProps> = ({
  visible,
  onCancel,
}) => {
  return (
    <Modal
      title={
        <Space>
          <SwapOutlined />
          <span>Convert Detection Rule</span>
        </Space>
      }
      open={visible}
      onCancel={onCancel}
      width={600}
      footer={null}
      destroyOnClose
    >
      <Alert
        message="Sigma conversion no longer supported"
        description="SIGMA format support has been removed from HEFAISTOS. Rule conversion via pySigma backends is no longer available. Please use KQL, SPL, or WAZUH formats directly."
        type="warning"
        showIcon
      />
    </Modal>
  );
};
