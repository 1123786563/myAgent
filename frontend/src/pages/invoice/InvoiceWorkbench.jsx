import React, { useRef, useState } from 'react';
import { PageContainer, ProTable } from '@ant-design/pro-components';
import { Button, Tag, Space, Modal, Card, Row, Col, Statistic, message, Upload } from 'antd';
import {
  FileSearchOutlined,
  SafetyCertificateOutlined,
  FileAddOutlined,
  PieChartOutlined,
  UploadOutlined
} from '@ant-design/icons';
import request from '../../utils/request';

const InvoiceWorkbench = () => {
  const actionRef = useRef();
  const [stats, setStats] = useState({ total_count: 0, total_amount: 0, tax_amount: 0 });

  // 获取发票统计数据
  const fetchStats = async () => {
    try {
      const data = await request.get('/invoices/tax/summary');
      setStats(data);
    } catch (error) {
      console.error("Failed to fetch invoice stats", error);
    }
  };

  React.useEffect(() => {
    fetchStats();
  }, []);

  const handleVerify = async (id) => {
    try {
      await request.post(`/invoices/${id}/verify`);
      message.success('发票查验已发起，结果将异步更新');
      actionRef.current?.reload();
    } catch (error) {
      // 错误已在拦截器处理
    }
  };

  const columns = [
    {
      title: '发票号码',
      dataIndex: 'invoice_number',
      copyable: true,
    },
    {
      title: '发票类型',
      dataIndex: 'invoice_type',
      valueEnum: {
        VAT_NORMAL: { text: '增值税普通发票' },
        VAT_SPECIAL: { text: '增值税专用发票' },
        ELECTRONIC: { text: '电子发票' },
      },
    },
    {
      title: '销售方',
      dataIndex: 'seller_name',
      ellipsis: true,
    },
    {
      title: '开票日期',
      dataIndex: 'issue_date',
      valueType: 'date',
      sorter: true,
    },
    {
      title: '不含税金额',
      dataIndex: 'total_amount',
      valueType: 'money',
      align: 'right',
    },
    {
      title: '税额',
      dataIndex: 'tax_amount',
      valueType: 'money',
      align: 'right',
    },
    {
      title: '状态',
      dataIndex: 'status',
      valueEnum: {
        DRAFT: { text: '草稿', status: 'Default' },
        VERIFIED: { text: '已查验', status: 'Success' },
        MATCHED: { text: '已勾稽', status: 'Processing' },
        VOID: { text: '已作废', status: 'Error' },
      },
    },
    {
      title: '操作',
      valueType: 'option',
      width: 150,
      render: (_, record) => [
        record.status === 'DRAFT' && (
          <a key="verify" onClick={() => handleVerify(record.id)}>
            <SafetyCertificateOutlined /> 查验
          </a>
        ),
        <a key="view" onClick={() => message.info('详情查看功能开发中')}>
          查看
        </a>,
      ],
    },
  ];

  return (
    <PageContainer title="发票管理工作台">
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card>
            <Statistic
              title="本月进项总额"
              value={stats.total_amount}
              precision={2}
              prefix={<FileSearchOutlined />}
              suffix="CNY"
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="预计抵扣税额"
              value={stats.tax_amount}
              precision={2}
              valueStyle={{ color: '#3f8600' }}
              prefix={<SafetyCertificateOutlined />}
              suffix="CNY"
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="待处理发票"
              value={stats.total_count}
              prefix={<PieChartOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <ProTable
        actionRef={actionRef}
        rowKey="id"
        headerTitle="发票列表"
        request={async (params) => {
          const data = await request.get('/invoices', { params });
          return {
            data: data,
            success: true,
          };
        }}
        columns={columns}
        search={{
          labelWidth: 'auto',
        }}
        toolBarRender={() => [
          <Upload key="upload" showUploadList={false}>
            <Button icon={<UploadOutlined />}>OCR 批量导入</Button>
          </Upload>,
          <Button key="add" type="primary" icon={<FileAddOutlined />}>
            手动录入
          </Button>,
        ]}
      />
    </PageContainer>
  );
};

export default InvoiceWorkbench;
