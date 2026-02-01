import React, { useState } from 'react';
import { PageContainer, ProTable } from '@ant-design/pro-components';
import { Card, Tabs, Space, Button, message } from 'antd';
import { DownloadOutlined, FileTextOutlined, PieChartOutlined } from '@ant-design/icons';
import request from '../../utils/request';

const Reports = () => {
  const [activeTab, setActiveTab] = useState('balance-sheet');

  const reportColumns = [
    {
      title: '项目',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '科目编码',
      dataIndex: 'code',
      key: 'code',
      width: 120,
    },
    {
      title: '余额 (CNY)',
      dataIndex: 'balance',
      key: 'balance',
      valueType: 'money',
      align: 'right',
      render: (val, record) => {
        const isBold = record.level === 1 || !record.code;
        return <span style={{ fontWeight: isBold ? 'bold' : 'normal' }}>{val}</span>;
      },
    },
  ];

  const incomeColumns = [
    {
      title: '项目',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '本期金额',
      dataIndex: 'period_amount',
      key: 'period_amount',
      valueType: 'money',
      align: 'right',
    },
    {
      title: '本年累计',
      dataIndex: 'year_amount',
      key: 'year_amount',
      valueType: 'money',
      align: 'right',
    },
  ];

  const handleExport = async (type) => {
    try {
      // 在实际环境中，这里会触发文件下载
      message.loading('正在准备报表导出...', 1.5);
      setTimeout(() => {
        message.success(`${type} 导出成功`);
      }, 2000);
    } catch (error) {
      message.error('导出失败');
    }
  };

  return (
    <PageContainer
      title="财务报表中心"
      extra={[
        <Button key="export" icon={<DownloadOutlined />} onClick={() => handleExport(activeTab)}>
          导出报表
        </Button>,
      ]}
    >
      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'balance-sheet',
              label: (
                <span>
                  <FileTextOutlined /> 资产负债表
                </span>
              ),
              children: (
                <ProTable
                  headerTitle="资产负债表"
                  request={async () => {
                    const data = await request.get('/reports/balance-sheet');
                    return { data, success: true };
                  }}
                  columns={reportColumns}
                  search={false}
                  pagination={false}
                  toolBarRender={false}
                />
              ),
            },
            {
              key: 'income-statement',
              label: (
                <span>
                  <PieChartOutlined /> 利润表
                </span>
              ),
              children: (
                <ProTable
                  headerTitle="利润表 (损益表)"
                  request={async () => {
                    const data = await request.get('/reports/income-statement');
                    return { data, success: true };
                  }}
                  columns={incomeColumns}
                  search={false}
                  pagination={false}
                  toolBarRender={false}
                />
              ),
            },
          ]}
        />
      </Card>
    </PageContainer>
  );
};

export default Reports;
