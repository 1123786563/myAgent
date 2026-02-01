import React from 'react';
import { PageContainer, ProTable } from '@ant-design/pro-components';
import { Card, Tabs, Select, Switch, Space, Tag, message } from 'antd';
import {
  TeamOutlined,
  SafetyCertificateOutlined,
  GlobalOutlined,
  BellOutlined
} from '@ant-design/icons';

const Settings = () => {
  return (
    <PageContainer title="系统设置与管理">
      <Card>
        <Tabs
          tabPosition="left"
          items={[
            {
              key: 'tenant',
              label: (
                <span>
                  <GlobalOutlined /> 租户与组织
                </span>
              ),
              children: (
                <div style={{ padding: '0 24px' }}>
                  <h3>租户管理</h3>
                  <div style={{ marginBottom: 24 }}>
                    <span style={{ marginRight: 16 }}>当前工作空间:</span>
                    <Select
                      defaultValue="t1"
                      style={{ width: 200 }}
                      onChange={(val) => {
                        localStorage.setItem('tenant_id', val);
                        message.success('已切换工作空间，正在重新加载数据...');
                        setTimeout(() => window.location.reload(), 1000);
                      }}
                      options={[
                        { label: '领航科技 (默认)', value: 't1' },
                        { label: '深蓝国际', value: 't2' },
                        { label: '星河贸易', value: 't3' },
                      ]}
                    />
                  </div>
                  <h3>安全设置</h3>
                  <div>
                    <Space direction="vertical">
                      <Space>
                        <Switch defaultChecked />
                        <span>开启敏感数据脱敏</span>
                      </Space>
                      <Space>
                        <Switch defaultChecked />
                        <span>自动审计所有导出操作</span>
                      </Space>
                    </Space>
                  </div>
                </div>
              ),
            },
            {
              key: 'rbac',
              label: (
                <span>
                  <TeamOutlined /> 角色权限控制
                </span>
              ),
              children: (
                <ProTable
                  headerTitle="系统角色列表"
                  search={false}
                  pagination={false}
                  request={async () => {
                    return {
                      data: [
                        { name: '超级管理员', key: 'super_admin', desc: '拥有系统所有权限', tags: ['系统预设'] },
                        { name: '财务经理', key: 'finance_manager', desc: '负责凭证复核与报表生成', tags: ['自定义'] },
                        { name: '出纳', key: 'cashier', desc: '负责对账与流水导入', tags: ['自定义'] },
                      ],
                      success: true,
                    };
                  }}
                  columns={[
                    { title: '角色名称', dataIndex: 'name' },
                    { title: '标识', dataIndex: 'key', render: (val) => <code>{val}</code> },
                    { title: '描述', dataIndex: 'desc' },
                    {
                      title: '类型',
                      dataIndex: 'tags',
                      render: (tags) => (
                        <Space>
                          {tags.map(t => <Tag key={t}>{t}</Tag>)}
                        </Space>
                      ),
                    },
                    {
                      title: '操作',
                      valueType: 'option',
                      render: () => [<a key="perm">权限配置</a>, <a key="edit">编辑</a>],
                    },
                  ]}
                />
              ),
            },
          ]}
        />
      </Card>
    </PageContainer>
  );
};

export default Settings;
