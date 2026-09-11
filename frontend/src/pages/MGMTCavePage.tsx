import React, { Suspense, lazy, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { gql, useQuery } from '@apollo/client';
import { Spin, Tabs, Typography } from 'antd';
import { BarChartOutlined, CrownOutlined, RobotOutlined, SettingOutlined } from '@ant-design/icons';
import { PromptLibrary } from '../components/PromptLibrary';
import { MailingListAdmin } from '../components/mgmt/MailingListAdmin';

const { Title, Paragraph } = Typography;

const GET_ACCESS_QUERY = gql`
  query GetMGMTAccess {
    me {
      id
      username
      role
      isSuperuser
      organization {
        id
      }
    }
  }
`;

const ReportingTabLazy = lazy(() => import('../components/mgmt/ReportingTab').then((m) => ({ default: m.ReportingTab })));

export const MGMTCavePage: React.FC = () => {
  const navigate = useNavigate();
  const { data: accessData, loading: accessLoading } = useQuery(GET_ACCESS_QUERY);

  const isMGMTUser = useMemo(() => {
    if (!accessData?.me) return false;
    const role = (accessData.me.role || '').toUpperCase();
    const hasOrganization = Boolean(accessData.me.organization?.id);
    return hasOrganization && (role === 'ADMIN' || role === 'REVIEWER');
  }, [accessData]);

  const isAdmin = useMemo(() => {
    if (!accessData?.me) return false;
    const role = (accessData.me.role || '').toUpperCase();
    const hasOrganization = Boolean(accessData.me.organization?.id);
    return hasOrganization && role === 'ADMIN';
  }, [accessData]);

  useEffect(() => {
    if (!accessLoading && !isMGMTUser) {
      navigate('/', { replace: true });
    }
  }, [accessLoading, isMGMTUser, navigate]);

  if (accessLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <Spin size="large" tip="Verifying access..." />
      </div>
    );
  }

  if (!isMGMTUser) {
    return null;
  }

  const tabItems = [
    {
      key: 'reporting',
      label: (
        <span>
          <BarChartOutlined /> Reporting
        </span>
      ),
      children: (
        <div style={{ padding: 24 }}>
          <Suspense fallback={<div style={{ display: 'flex', justifyContent: 'center' }}><Spin /></div>}>
            <ReportingTabLazy />
          </Suspense>
        </div>
      ),
    },
    {
      key: 'ai-assistant',
      label: (
        <span>
          <RobotOutlined /> AI Assistant
        </span>
      ),
      children: (
        <div style={{ padding: 24 }}>
          <PromptLibrary />
        </div>
      ),
    },
    ...(isAdmin ? [
      {
        key: 'administration',
        label: (
          <span>
            <SettingOutlined /> Administration
          </span>
        ),
        children: (
          <div style={{ padding: 24 }}>
            <MailingListAdmin />
          </div>
        ),
      },
    ] : []),
  ];

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={2}>
          <CrownOutlined style={{ marginRight: 8, color: '#faad14' }} />
          MGMT Cave
        </Title>
        <Paragraph type="secondary">
          Management dashboard for admins and reviewers. Access organizational reports and AI-powered insights.
        </Paragraph>
      </div>

      <Tabs items={tabItems} defaultActiveKey="reporting" size="large" />
    </div>
  );
};

export default MGMTCavePage;
