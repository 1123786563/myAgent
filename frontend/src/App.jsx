import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, useLocation, useNavigate } from 'react-router-dom';
import { ProLayout, PageContainer } from '@ant-design/pro-components';
import {
  BankOutlined,
  AuditOutlined,
  DashboardOutlined,
  SettingOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { ConfigProvider, Dropdown } from 'antd';
import zhCN from 'antd/locale/zh_CN';

// Placeholder pages
import Reconciliation from './pages/Reconciliation';
import Workflow from './pages/Workflow';
import AccountChart from './pages/accounting/AccountChart';
import VoucherEntry from './pages/accounting/VoucherEntry';

const Dashboard = () => <div>Dashboard Content (TODO)</div>;
const Settings = () => <div>System Settings (TODO)</div>;

const Layout = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const [pathname, setPathname] = useState(location.pathname);

  return (
    <div
      id="test-pro-layout"
      style={{
        height: '100vh',
      }}
    >
      <ProLayout
        title="Ledger Alpha"
        logo="https://gw.alipayobjects.com/zos/antfincdn/upvrAjAPQX/Logo_Tech%252520UI.svg"
        location={{
          pathname,
        }}
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
              ],
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
          title: 'Admin User',
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
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/accounting/chart" element={<AccountChart />} />
            <Route path="/accounting/voucher" element={<VoucherEntry />} />
            <Route path="/reconciliation" element={<Reconciliation />} />
            <Route path="/workflow" element={<Workflow />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </ConfigProvider>
  );
}

export default App;
