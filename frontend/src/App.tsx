import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';

// Page components
import { RepoListPage } from './pages/RepoListPage';
import { CreateRepoPage } from './pages/CreateRepoPage';
import { KanbanBoardPage } from './pages/KanbanBoardPage'
import { LoginPage } from './pages/LoginPage';
import { RegistrationPage } from './pages/RegistrationPage';
import { ForgotPasswordPage } from './pages/ForgotPasswordPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';
import { ActivateAccountPage } from './pages/ActivateAccountPage';
import { PlaybooksHubPage } from './pages/PlaybooksHubPage';
import PlaybookWorkbenchPage from './pages/PlaybookWorkbench';
import { PlaybookDetailPage } from './pages/PlaybookDetailPage';
import { RuleHubPage } from './pages/RuleHubPage';
import { RuleDetailPage } from './pages/RuleDetailPage';
import { DataCatalogPage } from './pages/DataCatalogPage';
import { CreateDataSourcePage } from './pages/CreateDataSourcePage';
import { DataSourceDetailPage } from './pages/DataSourceDetailPage';
import { OrganizationsPage } from './pages/OrganizationsPage';
import { TagsPage } from './pages/TagsPage';
import { KnowledgeBasePage } from './pages/KnowledgeBasePage';
import { CreateKBArticlePage } from './pages/CreateKBArticlePage';
import { KBArticleDetailPage } from './pages/KBArticleDetailPage';
import { EditKBArticlePage } from './pages/EditKBArticlePage';
import { CoverageMapPage } from './pages/CoverageMapPage';
import { EditRepoPage } from './pages/EditRepoPage';
import { UserManagementPage } from './pages/UserManagementPage';
import { AdminNewsPage } from './pages/AdminNewsPage';
import UserProfile from './pages/UserProfile';
import { LogicDeconstructorPage } from './pages/LogicDeconstructorPage';
import { ACHPage } from './pages/ACHPage';
import { ACHDetailPage } from './pages/ACHDetailPage';
import PainPointsPage from './pages/PainPointsPage';
import { ConfigurationPage } from './pages/ConfigurationPage';
import { FrameworkUpdatesPage } from './pages/FrameworkUpdatesPage';
import { MGMTCavePage } from './pages/MGMTCavePage';
import { LogsPage } from './pages/LogsPage';
import { L1PortalPage } from './pages/L1PortalPage';
import { L1PortalDetailPage } from './pages/L1PortalDetailPage';
import { WaitingRoomPage } from './pages/WaitingRoomPage';

// Layout
import { MainLayout } from './components/MainLayout';

const AppRoutes = () => {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  const locationForRedirect = React.useMemo(
    () => ({ pathname: location.pathname, search: location.search, hash: location.hash }),
    [location.pathname, location.search, location.hash]
  );

  const redirectAfterLogin = React.useMemo(() => {
    const from = (location.state as { from?: { pathname?: string; search?: string; hash?: string } } | null)?.from;
    const target = `${from?.pathname || ''}${from?.search || ''}${from?.hash || ''}`;
    if (!target || !target.startsWith('/') || target.startsWith('//') || target === '/login') {
      return '/';
    }
    return target;
  }, [location.state]);

  return (
    <Routes>
      <Route
        path="/login"
        element={!isAuthenticated ? <LoginPage /> : <Navigate to={redirectAfterLogin} replace />}
      />
      <Route path="/register" element={<RegistrationPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/activate-account" element={<ActivateAccountPage />} />
      <Route
        path="/*"
        element={
          isAuthenticated ? (
            <MainLayout>
              <Routes>
                <Route path="/" element={<KanbanBoardPage />} />
                <Route path="/playbooks/list" element={<PlaybooksHubPage />} />
                <Route path="/playbooks" element={<PlaybooksHubPage />} />
                <Route path="/waiting-room" element={<WaitingRoomPage />} />
                <Route path="/playbooks/detail/:playbookId" element={<PlaybookDetailPage />} />
                <Route path="/rules" element={<RuleHubPage />} />
                <Route path="/rules/:ruleId" element={<RuleDetailPage />} />
                <Route path="/playbooks/:playbookId" element={<PlaybookWorkbenchPage />} />
                <Route path="/catalog" element={<DataCatalogPage />} />
                <Route path="/catalog/new" element={<CreateDataSourcePage />} />
                <Route path="/catalog/:dataSourceId" element={<DataSourceDetailPage />} />
                <Route path="/organizations" element={<OrganizationsPage />} />
                <Route path="/tags" element={<TagsPage />} />
                <Route path="/kb" element={<KnowledgeBasePage />} />
                <Route path="/kb/new" element={<CreateKBArticlePage />} />
                <Route path="/kb/article/:articleId" element={<KBArticleDetailPage />} />
                <Route path="/kb/edit/:articleId" element={<EditKBArticlePage />} />
                <Route path="/coverage" element={<CoverageMapPage />} />
                <Route path="/repos" element={<RepoListPage />} />
                <Route path="/repos/new" element={<CreateRepoPage />} />
                <Route path="/repos/edit/:repoId" element={<EditRepoPage />} />
                <Route path="/mgmt/users" element={<UserManagementPage />} />
                <Route path="/mgmt/news" element={<AdminNewsPage />} />
                <Route path="/mgmt/superuser" element={<OrganizationsPage />} />
                <Route path="/mgmt/inittide" element={<Navigate to="/mgmt/config?tab=hef" replace />} />
                <Route path="/mgmt/config" element={<ConfigurationPage />} />
                <Route path="/mgmt/framework-updates" element={<FrameworkUpdatesPage />} />
                <Route path="/mgmt/cave" element={<MGMTCavePage />} />
                <Route path="/mgmt/logs" element={<LogsPage />} />
                <Route path="/profile" element={<UserProfile />} />
                <Route path="/tools/dld" element={<LogicDeconstructorPage />} />
                <Route path="/tools/ach" element={<ACHPage />} />
                <Route path="/tools/ach/:id" element={<ACHDetailPage />} />
                <Route path="/pain-points" element={<PainPointsPage />} />
                <Route path="/l1-portal" element={<L1PortalPage />} />
                <Route path="/l1-portal/:token/*" element={<L1PortalDetailPage />} />
                <Route path="/advops" element={<Navigate to="/playbooks?tab=advops" />} />
                <Route path="/advops/:id" element={<Navigate to={`/playbooks?tab=advops&id=${new URLSearchParams(window.location.search).get('id') || window.location.pathname.split('/').pop()}`} />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </MainLayout>
          ) : (
            <Navigate to="/login" state={{ from: locationForRedirect }} replace />
          )
        }
      />
    </Routes>
  );
};

function App() {
  return (
    <Router>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </Router>
  );
}

export default App;
