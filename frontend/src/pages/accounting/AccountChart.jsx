import React, { useRef } from 'react';
import { PageContainer, ProTable } from '@ant-design/pro-components';
import { Tag, Button, Space, message } from 'antd';
import { PlusOutlined, ApartmentOutlined } from '@ant-design/icons';
import request from '../../utils/request';

const AccountChart = () => {
  const actionRef = useRef();

  const columns = [
    {
      title: '科目编码',
      dataIndex: 'code',
      key: 'code',
      width: 150,
    },
    {
      title: '科目名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '科目类型',
      dataIndex: 'account_type',
      valueEnum: {
        ASSET: { text: '资产', status: 'Processing' },
        LIABILITY: { text: '负债', status: 'Error' },
        EQUITY: { text: '权益', status: 'Warning' },
        REVENUE: { text: '收入', status: 'Success' },
        EXPENSE: { text: '费用', status: 'Default' },
      },
    },
    {
      title: '层级',
      dataIndex: 'level',
      width: 80,
      align: 'center',
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      render: (active) => (
        <Tag color={active ? 'green' : 'red'}>
          {active ? '启用' : '禁用'}
        </Tag>
      ),
    },
    {
      title: '操作',
      valueType: 'option',
      width: 120,
      render: (_, record) => [
        <a key="add" onClick={() => message.info('添加子科目功能开发中')}>
          添加子项
        </a>,
        <a key="edit" onClick={() => message.info('编辑功能开发中')}>
          编辑
        </a>,
      ],
    },
  ];

  return (
    <PageContainer title="会计科目表">
      <ProTable
        actionRef={actionRef}
        rowKey="code"
        search={false}
        request={async () => {
          const data = await request.get('/accounting/accounts/tree');
          return {
            data: data,
            success: true,
          };
        }}
        columns={columns}
        pagination={false}
        toolBarRender={() => [
          <Button key="init" icon={<ApartmentOutlined />} onClick={() => message.info('初始化标准科目功能对接中')}>
            初始化标准科目
          </Button>,
          <Button key="add" type="primary" icon={<PlusOutlined />}>
            新建科目
          </Button>,
        ]}
        expandable={{
          childrenColumnName: 'children',
        }}
      />
    </PageContainer>
  );
};

export default AccountChart;
