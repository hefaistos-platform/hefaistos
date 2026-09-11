import React from 'react';
import { Card, Tag, Progress, List, Typography, Space, Spin, Alert, Button, Tooltip, Collapse } from 'antd';
import { CheckCircleOutlined, ExclamationCircleOutlined, InfoCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { useQuery, gql } from '@apollo/client';
import { Link } from 'react-router-dom';

const { Title, Text, Paragraph } = Typography;
const { Panel } = Collapse;

// GraphQL query for gap analysis
const D3FEND_GAP_ANALYSIS = gql`
  query D3fendGapAnalysis($attackTechniqueId: String!) {
    d3fendGapAnalysis(attackTechniqueId: $attackTechniqueId) {
      attackTechnique {
        techniqueId
        name
      }
      recommendedCountermeasures {
        id
        d3fendId
        name
        definition
        tactic
      }
      currentCoverage {
        id
        d3fendId
        name
        tactic
      }
      gaps {
        id
        d3fendId
        name
        definition
        tactic
      }
      coveragePercentage
    }
  }
`;

interface D3fendGapAnalysisProps {
  attackTechniqueId: string;
  playbookId?: string;  // Optional: if provided, show "Add to Workbench" button
  currentD3fendIds?: string[];  // Currently attached D3FEND technique IDs
  onAddTechnique?: (d3fendId: string) => void;  // Callback when adding technique
}

const D3fendGapAnalysis: React.FC<D3fendGapAnalysisProps> = ({ 
  attackTechniqueId, 
  playbookId, 
  currentD3fendIds, 
  onAddTechnique 
}) => {
  const { loading, error, data } = useQuery(D3FEND_GAP_ANALYSIS, {
    variables: { attackTechniqueId },
    skip: !attackTechniqueId
  });

  if (!attackTechniqueId) {
    return (
      <Alert
        message="No ATT&CK Technique Selected"
        description="Select an ATT&CK technique to view D3FEND gap analysis"
        type="info"
        showIcon
        icon={<InfoCircleOutlined />}
      />
    );
  }

  if (loading) return <Spin />;
  if (error) return <Alert message="Error loading gap analysis" description={error.message} type="error" />;
  if (!data?.d3fendGapAnalysis) {
    return <Alert message="No gap analysis data available" type="warning" showIcon />;
  }

  const { attackTechnique, recommendedCountermeasures, currentCoverage, gaps, coveragePercentage } = data.d3fendGapAnalysis;

  const getCoverageColor = () => {
    if (coveragePercentage >= 80) return '#52c41a'; // Green
    if (coveragePercentage >= 50) return '#faad14'; // Yellow
    return '#ff4d4f'; // Red
  };

  return (
    <div>
      <Card style={{ marginBottom: '16px' }}>
        <Title level={4}>D3FEND Coverage Analysis</Title>
        <Paragraph>
          <Tag color="blue">{attackTechnique.techniqueId}</Tag>
          <Text strong>{attackTechnique.name}</Text>
        </Paragraph>
        
        <Space direction="vertical" style={{ width: '100%' }}>
          <div>
            <Text>Coverage: </Text>
            <Progress 
              percent={Math.round(coveragePercentage)} 
              strokeColor={getCoverageColor()}
              status={coveragePercentage >= 80 ? 'success' : coveragePercentage >= 50 ? 'normal' : 'exception'}
            />
          </div>
          <Space size="large">
            <div>
              <CheckCircleOutlined style={{ color: '#52c41a', marginRight: '8px' }} />
              <Text strong>{currentCoverage.length}</Text>
              <Text type="secondary"> Implemented</Text>
            </div>
            <div>
              <ExclamationCircleOutlined style={{ color: '#ff4d4f', marginRight: '8px' }} />
              <Text strong>{gaps.length}</Text>
              <Text type="secondary"> Gaps</Text>
            </div>
            <div>
              <InfoCircleOutlined style={{ color: '#1890ff', marginRight: '8px' }} />
              <Text strong>{recommendedCountermeasures.length}</Text>
              <Text type="secondary"> Recommended</Text>
            </div>
          </Space>
        </Space>
      </Card>

      {/* Current Coverage */}
      {currentCoverage.length > 0 && (
        <Card 
          title={
            <Space>
              <CheckCircleOutlined style={{ color: '#52c41a' }} />
              <Text strong>Current Coverage</Text>
            </Space>
          }
          style={{ marginBottom: '16px' }}
          size="small"
        >
          <List
            size="small"
            dataSource={currentCoverage}
            renderItem={(item: any) => (
              <List.Item>
                <Space>
                  <Tag color="green">{item.d3fendId}</Tag>
                  <Text>{item.name}</Text>
                  <Tag color="purple">{item.tactic}</Tag>
                </Space>
              </List.Item>
            )}
          />
        </Card>
      )}

      {/* Gaps and Recommendations with Collapse */}
      <Collapse defaultActiveKey={[]} ghost style={{ marginBottom: '16px' }}>
        {/* Gaps */}
        {gaps.length > 0 && (
          <Panel 
            header={
              <Space>
                <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />
                <Title level={5} style={{ margin: 0, display: 'inline' }}>Coverage Gaps ({gaps.length})</Title>
              </Space>
            }
            key="gaps"
          >
            <List
              size="small"
              dataSource={gaps}
              renderItem={(item: any) => {
                const isAdded = currentD3fendIds?.includes(item.d3fendId);
                return (
                  <List.Item
                    actions={[
                      <Link key="create" to={`/playbooks/new?technique=${attackTechniqueId}&d3fend=${item.d3fendId}&techniqueeName=${encodeURIComponent(attackTechnique.name)}&d3fendName=${encodeURIComponent(item.name)}`}>
                        <Button size="small" type="primary">Create Detection</Button>
                      </Link>,
                      // NEW: "Add to Workbench" button if in workbench context
                      onAddTechnique && playbookId && (
                        <Button 
                          key="add"
                          size="small" 
                          type="default"
                          icon={<PlusOutlined />}
                          onClick={() => onAddTechnique(item.d3fendId)}
                          disabled={isAdded}
                        >
                          {isAdded ? 'Added' : 'Add'}
                        </Button>
                      )
                    ].filter(Boolean)}
                  >
                    <List.Item.Meta
                      title={
                        <Space>
                          <Tag color="orange">{item.d3fendId}</Tag>
                          <Text strong>{item.name}</Text>
                          <Tag color="purple">{item.tactic}</Tag>
                        </Space>
                      }
                      description={
                        <Tooltip title={item.definition} placement="topLeft" overlayStyle={{ maxWidth: 500 }}>
                          <Text type="secondary" ellipsis style={{ cursor: 'help' }}>
                            {item.definition}
                          </Text>
                        </Tooltip>
                    }
                  />
                </List.Item>
                );
              }}
            />
          </Panel>
        )}

        {/* All Recommendations */}
        {recommendedCountermeasures.length > 0 && (
          <Panel 
            header={
              <Space>
                <CheckCircleOutlined style={{ color: '#52c41a' }} />
                <Title level={5} style={{ margin: 0, display: 'inline' }}>All Recommended Countermeasures ({recommendedCountermeasures.length})</Title>
              </Space>
            }
            key="recommended"
          >
            <List
              size="small"
              dataSource={recommendedCountermeasures}
              renderItem={(item: any) => {
                const isImplemented = currentCoverage.some((c: any) => c.id === item.id);
                return (
                  <List.Item>
                    <Space>
                      <Tag color={isImplemented ? 'green' : 'default'}>{item.d3fendId}</Tag>
                      <Text style={{ textDecoration: isImplemented ? 'line-through' : 'none' }}>
                        {item.name}
                      </Text>
                      <Tag color="purple">{item.tactic}</Tag>
                      {isImplemented && <CheckCircleOutlined style={{ color: '#52c41a' }} />}
                    </Space>
                  </List.Item>
                );
              }}
            />
          </Panel>
        )}
      </Collapse>

      {gaps.length === 0 && currentCoverage.length > 0 && (
        <Alert
          message="Full Coverage Achieved"
          description="All recommended D3FEND countermeasures are implemented for this ATT&CK technique."
          type="success"
          showIcon
          icon={<CheckCircleOutlined />}
        />
      )}
    </div>
  );
};

export default D3fendGapAnalysis;
