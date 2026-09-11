import React, { useEffect, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { gql } from '@apollo/client';
import { useMutation, useQuery } from '@apollo/client/react';
import { Layout, Menu, Button, Typography, App, Space, Dropdown, Alert } from 'antd';
import type { MenuProps } from 'antd';
import {
  DatabaseOutlined,
  DeploymentUnitOutlined,
  ApartmentOutlined,
  LogoutOutlined,
  RadarChartOutlined,
  HeatMapOutlined,
  BookOutlined,
  TeamOutlined,
  CrownOutlined,
  BulbOutlined,
  TableOutlined,
  ExclamationCircleOutlined,
  UserOutlined,
  FileTextOutlined,
  ReadOutlined,
  AppstoreOutlined,
  SyncOutlined,
  FileSearchOutlined,
  MonitorOutlined,
  MoonOutlined,
  SunOutlined,
  InboxOutlined,
} from '@ant-design/icons';
import { NotificationBell } from './NotificationBell';
import { NewsIcon } from './NewsIcon';


const { Header, Sider, Content } = Layout;

const ME_ROLE_QUERY = gql`
  query GetMyRole {
    me {
      id
      role
      username
      email
      avatarUrl
      isSuperuser
      organization {
        id
        name
      }
    }
    myOrganizations {
      id
      name
      isDefault
      isActive
    }
  }
`;

const SWITCH_ACTIVE_ORGANIZATION_MUTATION = gql`
  mutation SwitchActiveOrganization($organizationId: UUID!, $setAsDefault: Boolean) {
    switchActiveOrganization(organizationId: $organizationId, setAsDefault: $setAsDefault) {
      ok
      message
      activeOrganization {
        id
      }
    }
  }
`;

interface MeRoleData {
  me: {
    id: string;
    role: string;
    username: string;
    email: string;
    avatarUrl?: string | null;
    isSuperuser?: boolean;
    organization?: {
      id: string;
      name: string;
    } | null;
  };
  myOrganizations?: Array<{
    id: string;
    name: string;
    isDefault: boolean;
    isActive: boolean;
  }>;
}

export const MainLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { logout } = useAuth();
  const { mode, resolvedTheme, setMode } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();

  const { data: meData } = useQuery<MeRoleData>(ME_ROLE_QUERY);
  const [switchActiveOrganization, { loading: switchingOrg }] = useMutation(SWITCH_ACTIVE_ORGANIZATION_MUTATION);
  const userRole = meData?.me?.role;
  const currentRole = userRole?.toUpperCase();
  const isSuperuser = meData?.me?.isSuperuser;
  const username = meData?.me?.username;
  const email = meData?.me?.email;
  const orgs = meData?.myOrganizations || [];
  const activeOrg = orgs.find((org) => org.isActive) || orgs[0];
  const isElOne = currentRole === 'ELONE' && !isSuperuser;
  const isBotAuditorOrg = currentRole === 'BOT_AUDITOR_ORG';
  const isBotAuditorGlobal = currentRole === 'BOT_AUDITOR_GLOBAL';
  const isBotAuditor = isBotAuditorOrg || isBotAuditorGlobal;

  // Map route prefixes to menu keys
  const selectedKey = useMemo(() => {
    if (location.pathname.startsWith('/mgmt/framework-updates')) return 'framework-updates';
    if (location.pathname.startsWith('/mgmt/news')) return 'news';
    if (location.pathname.startsWith('/mgmt/config')) return 'config';
    if (location.pathname.startsWith('/mgmt/logs')) return 'logs';
    if (location.pathname.startsWith('/mgmt/users')) return 'config';
    if (location.pathname.startsWith('/mgmt/cave')) return 'mgmt-cave';
    if (location.pathname.startsWith('/mgmt/superuser')) return 'superuser';
    if (location.pathname.startsWith('/coverage')) return 'coverage';
    if (location.pathname.startsWith('/catalog')) return 'catalog';
    if (location.pathname.startsWith('/playbooks')) return 'playbooks';
    if (location.pathname.startsWith('/waiting-room')) return 'waiting-room';
    if (location.pathname.startsWith('/l1-portal')) return 'l1-portal';
    if (location.pathname.startsWith('/rules')) return 'rules';
    if (location.pathname.startsWith('/repos')) return 'config';
    if (location.pathname.startsWith('/kb')) return 'kb';
    if (location.pathname.startsWith('/profile')) return 'profile';
    if (location.pathname.startsWith('/tools/ach')) return 'tools-ach';
    if (location.pathname.startsWith('/tools/dld')) return 'tools-dld';
    if (location.pathname.startsWith('/pain-points')) return 'pain-points';
    return 'board';
  }, [location.pathname]);

  const items = isElOne
    ? [
      { key: 'l1-portal', icon: <ReadOutlined />, label: 'L1 Portal', onClick: () => navigate('/l1-portal') },
      { key: 'kb', icon: <BookOutlined />, label: 'Knowledge Base', onClick: () => navigate('/kb') },
      { key: 'pain-points', icon: <ExclamationCircleOutlined />, label: 'Pain Points', onClick: () => navigate('/pain-points') },
      { key: 'profile', icon: <TeamOutlined />, label: 'My Profile', onClick: () => navigate('/profile') },
    ]
    : [
      { key: 'board', icon: <RadarChartOutlined />, label: 'Lifecycle Hub', onClick: () => navigate('/') },
      { key: 'tools-ach', icon: <TableOutlined />, label: 'ACH Matrix', onClick: () => navigate('/tools/ach') },
      { key: 'playbooks', icon: <DeploymentUnitOutlined />, label: 'Workbench Hub', onClick: () => navigate('/playbooks') },
      { key: 'waiting-room', icon: <InboxOutlined />, label: 'Waiting Room', onClick: () => navigate('/waiting-room') },
      { key: 'l1-portal', icon: <ReadOutlined />, label: 'L1 Portal', onClick: () => navigate('/l1-portal') },
      { key: 'rules', icon: <ApartmentOutlined />, label: 'Rule Hub', onClick: () => navigate('/rules') },
      { key: 'catalog', icon: <DatabaseOutlined />, label: 'Data Catalog', onClick: () => navigate('/catalog') },
      { key: 'coverage', icon: <HeatMapOutlined />, label: 'Coverage Map', onClick: () => navigate('/coverage') },
      { key: 'tools-dld', icon: <RadarChartOutlined />, label: 'Logic Deconstructor', onClick: () => navigate('/tools/dld') },
      { key: 'kb', icon: <BookOutlined />, label: 'Knowledge Base', onClick: () => navigate('/kb') },
      { key: 'pain-points', icon: <ExclamationCircleOutlined />, label: 'Pain Points', onClick: () => navigate('/pain-points') },
      ...(currentRole === 'ADMIN' || currentRole === 'REVIEWER' ? [{
        key: 'mgmt-cave',
        icon: <CrownOutlined />,
        label: 'MGMT Cave',
        onClick: () => navigate('/mgmt/cave')
      }] : []),
      { key: 'profile', icon: <TeamOutlined />, label: 'My Profile', onClick: () => navigate('/profile') },
    ];

  if (!isElOne && (currentRole === 'ADMIN' || isSuperuser || isBotAuditor)) {
    items.push({ key: 'news', icon: <BulbOutlined />, label: 'News Management', onClick: () => navigate('/mgmt/news') });
    items.push({ key: 'config', icon: <AppstoreOutlined />, label: 'Configuration', onClick: () => navigate('/mgmt/config') });
    items.push({ key: 'logs', icon: <FileSearchOutlined />, label: 'Logs', onClick: () => navigate('/mgmt/logs') });
  }

  if (!isElOne && isSuperuser) {
    items.push({ key: 'framework-updates', icon: <SyncOutlined />, label: 'Framework Updates', onClick: () => navigate('/mgmt/framework-updates') });
  }

  // Superuser management - only for Django superusers
  if (!isElOne && (isSuperuser || isBotAuditorGlobal)) {
    items.push({ key: 'superuser', icon: <CrownOutlined />, label: 'Superuser Mgmt', onClick: () => navigate('/mgmt/superuser') });
  }

  useEffect(() => {
    if (!isElOne) return;

    const path = location.pathname;
    const allowed =
      path === '/l1-portal' ||
      /^\/l1-portal\/[^/]+\/?$/.test(path) ||
      path === '/kb' ||
      path.startsWith('/kb/article/') ||
      path === '/pain-points' ||
      path.startsWith('/pain-points/') ||
      path === '/profile' ||
      path.startsWith('/profile/');

    if (!allowed) {
      navigate('/l1-portal', { replace: true });
    }
  }, [isElOne, location.pathname, navigate]);

  const userMenuItems: MenuProps['items'] = isElOne
    ? [
      {
        key: 'profile',
        icon: <UserOutlined />,
        label: 'My Profile',
        onClick: () => navigate('/profile')
      },
      {
        type: 'divider'
      },
      {
        key: 'logout',
        icon: <LogoutOutlined />,
        label: 'Log Out',
        onClick: () => {
          void logout();
        },
        danger: true
      }
    ]
    : [
      {
        key: 'profile',
        icon: <UserOutlined />,
        label: 'My Profile',
        onClick: () => navigate('/profile')
      },
      {
        key: 'my-rules',
        icon: <FileTextOutlined />,
        label: 'My Rules',
        onClick: () => navigate(`/rules?author=${encodeURIComponent(username || '')}`)
      },
      {
        key: 'my-workbench',
        icon: <AppstoreOutlined />,
        label: 'My Workbench',
        onClick: () => navigate(`/playbooks?author=${encodeURIComponent(username || '')}`)
      },
      {
        type: 'divider'
      },
      {
        key: 'logout',
        icon: <LogoutOutlined />,
        label: 'Log Out',
        onClick: () => {
          void logout();
        },
        danger: true
      }
    ];

  const themeMenuItems: MenuProps['items'] = [
    {
      key: 'light',
      icon: <SunOutlined />,
      label: 'Light',
      onClick: () => setMode('light'),
    },
    {
      key: 'dark',
      icon: <MoonOutlined />,
      label: 'Dark',
      onClick: () => setMode('dark'),
    },
    {
      key: 'system',
      icon: <MonitorOutlined />,
      label: 'System',
      onClick: () => setMode('system'),
    },
  ];

  const activeThemeIcon = mode === 'light' ? <SunOutlined /> : mode === 'dark' ? <MoonOutlined /> : <MonitorOutlined />;
  const activeThemeLabel = mode === 'system' ? `System (${resolvedTheme})` : mode;
  const orgMenuItems: MenuProps['items'] = orgs.map((org) => ({
    key: org.id,
    label: org.name,
    onClick: async () => {
      if (org.isActive) return;
      await switchActiveOrganization({ variables: { organizationId: org.id, setAsDefault: false } });
      window.location.reload();
    },
  }));

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider breakpoint="lg" collapsedWidth={60} width={230} className="main-sider">
        <div style={{ height: 56 }} />
        <Menu
          mode="inline"
          theme={resolvedTheme === 'dark' ? 'dark' : 'light'}
          selectedKeys={[selectedKey]}
          items={items}
          style={{ borderInlineEnd: 'none' }}
        />
          <div className="menu-footer" style={{ position: 'absolute', bottom: 0, width: '100%', padding: 12 }}>
          <Button
            type="text"
            icon={<LogoutOutlined />}
            block
            onClick={() => {
              void logout();
            }}
            style={{ textAlign: 'left' }}
          >
            Logout
          </Button>
        </div>
      </Sider>
      <Layout>
          <Header className="main-header" style={{ padding: '0 24px', display: 'flex', alignItems: 'center', gap: 24, justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div className="logo-brand" onClick={() => navigate('/')} title="Go to Lifecycle Hub" role="button" aria-label="Go home">
              <span className="logo-title">HEFAISTOS</span>
            </div>
            <Typography.Text className="layout-section-title">
              {items.find(i => i.key === selectedKey)?.label}
            </Typography.Text>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {orgs.length > 1 && (
              <Dropdown
                menu={{
                  items: orgMenuItems,
                  selectable: true,
                  selectedKeys: activeOrg ? [activeOrg.id] : [],
                }}
                trigger={['click']}
              >
                <Button loading={switchingOrg}>
                  Organization: {activeOrg?.name || 'Select'}
                </Button>
              </Dropdown>
            )}
            <Dropdown menu={{ items: themeMenuItems, selectable: true, selectedKeys: [mode] }} trigger={['click']}>
              <Button icon={activeThemeIcon}>
                Theme: {activeThemeLabel}
              </Button>
            </Dropdown>
            {/* User Dropdown Menu */}
            <Dropdown
              menu={{
                items: userMenuItems
              }}
              trigger={['click']}
            >
              <div
                className="user-chip"
                title={email ? `${username || 'User'} (${userRole || ''}) • ${email}` : `${username || 'User'} (${userRole || ''})`}
                role="button"
                aria-label="User menu"
              >
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  maxWidth: '100%'
                }}>
                  {/* Avatar Thumbnail */}
                  <span className="user-avatar">
                    {meData?.me?.avatarUrl ? (
                      <img
                        src={meData.me.avatarUrl}
                        alt="avatar"
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      />
                    ) : (
                      (username || 'U').charAt(0).toUpperCase()
                    )}
                  </span>
                  <span className="user-name">{username || 'User'}</span>
                  {userRole && (
                    <span className="user-role-badge">{userRole}</span>
                  )}
                  {email && (
                    <span className="user-email">{email}</span>
                  )}
                </span>
              </div>
            </Dropdown>
            <Space>
              <NewsIcon />
              <NotificationBell />
            </Space>
          </div>
        </Header>
          <Content className="main-content" style={{ margin: 0, padding: '24px 32px' }}>
          <App>
            {isBotAuditor && (
              <Alert
                type="warning"
                showIcon
                message="Bot Auditor Read-Only Mode"
                description="This account can inspect features, but all write operations are blocked and sensitive fields are redacted."
                style={{ marginBottom: 16 }}
              />
            )}
            {children}
          </App>
        </Content>
      </Layout>
    </Layout>
  );
};
