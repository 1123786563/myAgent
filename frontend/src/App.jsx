import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, useLocation, useNavigate, Navigate } from 'react-router-dom';
import { ProLayout, PageContainer } from '@ant-design/pro-components';
import {
  BankOutlined,
  AuditOutlined,
  DashboardOutlined,
  SettingOutlined,
  UserOutlined,
  FileSearchOutlined,
} from '@ant-design/icons';
import { ConfigProvider, Dropdown, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';

import { AuthProvider, useAuth } from './contexts/AuthContext';

// Placeholder pages
import Reconciliation from './pages/Reconciliation';
import Workflow from './pages/Workflow';
import AccountChart from './pages/accounting/AccountChart';
import VoucherEntry from './pages/accounting/VoucherEntry';
import Reports from './pages/accounting/Reports';
import InvoiceWorkbench from './pages/invoice/InvoiceWorkbench';
import Dashboard from './pages/dashboard/Dashboard';
import Settings from './pages/Settings';
import Login from './pages/Login';

const ProtectedRoute = ({ children }) => {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return children;
};

const LayoutContent = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [pathname, setPathname] = useState(location.pathname);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const backgroundStyle = {
    position: 'relative',
    minHeight: '100vh',
    background: '#0F172A', // Deep Fintech Navy
    overflow: 'hidden',
  };

  const blobStyle = {
    position: 'absolute',
    borderRadius: '50%',
    filter: 'blur(100px)',
    zIndex: 0,
    opacity: 0.3,
  };

  return (
    <div style={backgroundStyle}>
      {/* Global Fintech Background Blobs */}
      <div style={{ ...blobStyle, width: '600px', height: '600px', background: '#1e40af', top: '-10%', right: '-5%' }} />
      <div style={{ ...blobStyle, width: '500px', height: '500px', background: '#7c3aed', bottom: '10%', left: '-5%' }} />

      <style>
        {`
          .ant-layout {
            background: transparent !important;
          }
          .ant-pro-layout-content {
            background: transparent !important;
            padding: 24px !important;
          }
          .ant-pro-page-container {
            background: transparent !important;
          }
          /* Glassmorphic Cards Global */
          .ant-card {
            background: rgba(255, 255, 255, 0.03) !important;
            backdrop-filter: blur(20px) !important;
            -webkit-backdrop-filter: blur(20px) !important;
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
            border-radius: 16px !important;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1) !important;
            transition: all 0.3s ease !important;
          }
          .ant-card:hover {
            border-color: rgba(22, 119, 255, 0.3) !important;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.4) !important;
            transform: translateY(-2px);
          }
          .ant-card-head {
            border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
          }
          .ant-card-head-title {
            color: #fff !important;
            font-weight: 600 !important;
          }
          .ant-table {
            background: transparent !important;
            color: rgba(255, 255, 255, 0.85) !important;
          }
          .ant-table-thead > tr > th {
            background: rgba(255, 255, 255, 0.05) !important;
            color: #fff !important;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1) !important;
          }
          .ant-table-tbody > tr > td {
            border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
          }
          .ant-table-tbody > tr:hover > td {
            background: rgba(255, 255, 255, 0.02) !important;
          }
          .ant-pro-page-container-content {
            color: rgba(255, 255, 255, 0.45) !important;
          }
          .ant-breadcrumb-link, .ant-breadcrumb-separator {
            color: rgba(255, 255, 255, 0.45) !important;
          }
        `}
      </style>

      <ProLayout
        title={<span style={{ color: '#fff', fontWeight: 700 }}>Ledger Alpha</span>}
        logo={<div style={{ width: 32, height: 32, background: 'linear-gradient(135deg, #1677ff 0%, #7c3aed 100%)', borderRadius: 8 }} />}
        location={{
          pathname,
        }}
        layout="mix"
        navTheme="realDark"
        fixedHeader
        fixSiderbar
        menu={{
          request: async () => [
            {
              path: '/',
              name: '仪表盘',
              icon: <DashboardOutlined />,
            },
            {
              path: '/accounting',
              name: '财务核算',
              icon: <AuditOutlined />,
              children: [
                {
                  path: '/accounting/chart',
                  name: '会计科目表',
                },
                {
                  path: '/accounting/voucher',
                  name: '凭证录入',
                },
                {
                  path: '/accounting/reports',
                  name: '财务报表',
                },
              ],
            },
            {
              path: '/invoice',
              name: '发票管理',
              icon: <FileSearchOutlined />,
            },
            {
              path: '/reconciliation',
              name: '对账中心',
              icon: <BankOutlined />,
            },
            {
              path: '/workflow',
              name: '审批中心',
              icon: <AuditOutlined />,
            },
            {
              path: '/settings',
              name: '系统设置',
              icon: <SettingOutlined />,
            },
          ],
        }}
        avatarProps={{
          src: 'https://gw.alipayobjects.com/zos/antfincdn/efFD%24IOql2/weixintupian_20170331104822.jpg',
          title: <span style={{ color: '#fff' }}>Admin User</span>,
          size: 'small',
          render: (props, dom) => {
            return (
              <Dropdown
                menu={{
                  items: [
                    {
                      key: 'logout',
                      icon: <UserOutlined />,
                      label: '退出登录',
                      onClick: handleLogout,
                    },
                  ],
                }}
              >
                {dom}
              </Dropdown>
            );
          },
        }}
        onMenuHeaderClick={(e) => console.log(e)}
        menuItemRender={(item, dom) => (
          <div
            onClick={() => {
              setPathname(item.path || '/');
              navigate(item.path || '/');
            }}
          >
            {dom}
          </div>
        )}
      >
        <PageContainer>
          {children}
        </PageContainer>
      </ProLayout>
    </div>
  );
};

function App() {
  return (
    <AuthProvider>
      <ConfigProvider
        locale={zhCN}
        theme={{
          algorithm: theme.darkAlgorithm,
          token: {
            colorPrimary: '#1677ff',
            borderRadius: 12,
            colorBgContainer: 'transparent',
            fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif',
          },
          components: {
            Layout: {
              headerBg: 'rgba(15, 23, 42, 0.8)',
              siderBg: 'rgba(15, 23, 42, 0.8)',
            },
            Menu: {
              itemBg: 'transparent',
              subMenuItemBg: 'transparent',
            }
          },
        }}
      >
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/*"
              element={
                <ProtectedRoute>
                  <LayoutContent>
                    <Routes>
                      <Route path="/" element={<Dashboard />} />
                      <Route path="/accounting/chart" element={<AccountChart />} />
                      <Route path="/accounting/voucher" element={<VoucherEntry />} />
                      <Route path="/accounting/reports" element={<Reports />} />
                      <Route path="/invoice" element={<InvoiceWorkbench />} />
                      <Route path="/reconciliation" element={<Reconciliation />} />
                      <Route path="/workflow" element={<Workflow />} />
                      <Route path="/settings" element={<Settings />} />
                    </Routes>
                  </LayoutContent>
                </ProtectedRoute>
              }
            />
          </Routes>
        </BrowserRouter>
      </ConfigProvider>
    </AuthProvider>
  );
}

export default App;