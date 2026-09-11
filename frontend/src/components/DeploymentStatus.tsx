import React from 'react';
import { Alert, Space, Spin, Tag } from 'antd';
import { WarningOutlined } from '@ant-design/icons';

interface DeploymentStatusProps {
  deploymentStatus: 'PENDING' | 'DEPLOYED' | 'FAILED' | 'TIMEOUT';
  deployedToSiems?: string[] | null;
}

/**
 * Renders a compact deployment status indicator showing the overall status
 * and the list of SIEM platforms that were successfully deployed to.
 */
const DeploymentStatus: React.FC<DeploymentStatusProps> = ({ deploymentStatus, deployedToSiems }) => {
  if (deploymentStatus === 'PENDING') {
    return (
      <Space size={4}>
        <Spin size="small" />
        <span className="text-xs text-gray-500">Waiting for deployment…</span>
      </Space>
    );
  }

  if (deploymentStatus === 'TIMEOUT') {
    return (
      <Space size={4}>
        <WarningOutlined style={{ color: '#faad14' }} />
        <span className="text-xs text-yellow-600">Deployment timed out — no response received from CoreTide.</span>
      </Space>
    );
  }

  if (deploymentStatus === 'FAILED') {
    return <Alert type="error" message="Deployment failed" banner showIcon={false} />;
  }

  // DEPLOYED
  const siems = Array.isArray(deployedToSiems) ? deployedToSiems : [];
  return (
    <Space size={4} wrap>
      <span className="text-xs text-gray-500">Deployed to:</span>
      {siems.length > 0 ? (
        siems.map((siem) => (
          <Tag key={siem} color="green" className="text-xs">
            {siem}
          </Tag>
        ))
      ) : (
        <Tag color="green" className="text-xs">deployed</Tag>
      )}
    </Space>
  );
};

export default DeploymentStatus;
