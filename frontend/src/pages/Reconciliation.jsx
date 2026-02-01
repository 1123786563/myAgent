import React, { useState, useRef } from 'react';
import { PageContainer, ProTable } from '@ant-design/pro-components';
import { Button, Upload, Card, Row, Col, Statistic, message, Tag, Space, Popconfirm } from 'antd';
import { InboxOutlined, SyncOutlined, CheckCircleOutlined, CloudUploadOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Dragger } = Upload;

const Reconciliation = () => {
  const actionRef = useRef();
  const [stats, setStats] = useState({
    total_statements: 0,
    unreconciled: 0,
    matched: 0,
    reconciled: 0
  });

  // Fetch stats
  const fetchStats = async () => {
    try {
      const res = await axios.get('/api/v1/reconciliation/stats');
      setStats(res.data);
    } catch (error) {
      console.error("Failed to fetch stats", error);
    }
  };

  React.useEffect(() => {
    fetchStats();
  }, []);

  // Trigger auto reconciliation
  const handleRunReconciliation = async () => {
    try {
      await axios.post('/api/v1/reconciliation/run');
      message.success('自动对账任务已在后台启动');
      actionRef.current?.reload();
    } catch (error) {
      message.error('启动失败: ' + error.message);
    }
  };

  // Manual confirm
  const handleConfirm = async (record) => {
    // Assuming we have a log_id from the record (in real implementation, we'd join with logs)
    // For demo, we might need an endpoint to confirm by statement_id or log_id
    message.info("人工确认功能需对接 ReconciliationLog ID");
  };

  const columns = [
    {
      title: '交易日期',
      dataIndex: 'transaction_date',
      valueType: 'dateTime',
      sorter: true,
    },
    {
      title: '来源',
      dataIndex: 'source_type',
      valueEnum: {
        ALIPAY: { text: '支付宝', status: 'Success' },
        WECHAT: { text: '微信支付', status: 'Success' },
        BANK: { text: '银行流水', status: 'Processing' },
      },
    },
    {
      title: '对方户名',
      dataIndex: 'counterparty_name',
    },
    {
      title: '金额',
      dataIndex: 'amount',
      valueType: 'money',
      align: 'right',
      sorter: true,
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      valueEnum: {
        UNRECONCILED: { text: '未对账', status: 'Default' },
        MATCHED: { text: '已匹配', status: 'Warning' },
        RECONCILED: { text: '已完成', status: 'Success' },
      },
    },
    {
      title: '操作',
      valueType: 'option',
      render: (text, record, _, action) => [
        record.status === 'MATCHED' && (
          <a key="confirm" onClick={() => handleConfirm(record)}>
            确认匹配
          </a>
        ),
      ],
    },
  ];

  return (
    <PageContainer title="对账中心">
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="总流水数" value={stats.total_statements} prefix={<InboxOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="待对账" value={stats.unreconciled} valueStyle={{ color: '#cf1322' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="已匹配 (待确认)" value={stats.matched} valueStyle={{ color: '#faad14' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="已完成" value={stats.reconciled} valueStyle={{ color: '#3f8600' }} prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={18}>
          <ProTable
            columns={columns}
            actionRef={actionRef}
            request={async (params = {}, sort, filter) => {
              // Convert ProTable params to API params
              const res = await axios.get('/api/v1/reconciliation/statements', {
                params: {
                  page: params.current,
                  size: params.pageSize,
                  status: params.status,
                },
              });
              return {
                data: res.data,
                success: true,
                total: res.data.length * 10, // Mock total for demo
              };
            }}
            rowKey="id"
            search={{
              labelWidth: 'auto',
            }}
            toolBarRender={() => [
              <Button
                key="run"
                type="primary"
                icon={<SyncOutlined />}
                onClick={handleRunReconciliation}
              >
                开始自动对账
              </Button>,
            ]}
          />
        </Col>
        <Col span={6}>
          <Card title="导入流水" style={{ marginBottom: 24 }}>
            <Dragger
              name="file"
              action="/api/v1/reconciliation/upload"
              data={{ source_type: 'ALIPAY' }} // Default for demo
              onChange={(info) => {
                const { status } = info.file;
                if (status === 'done') {
                  message.success(`${info.file.name} 上传成功.`);
                  actionRef.current?.reload();
                  fetchStats();
                } else if (status === 'error') {
                  message.error(`${info.file.name} 上传失败.`);
                }
              }}
            >
              <p className="ant-upload-drag-icon">
                <CloudUploadOutlined />
              </p>
              <p className="ant-upload-text">点击或拖拽文件上传</p>
              <p className="ant-upload-hint">
                支持 CSV, Excel 格式。
              </p>
            </Dragger>
          </Card>
          <Card title="对账规则">
            <p>当前启用规则：</p>
            <Tag color="blue">金额容差 ±0.01</Tag>
            <Tag color="blue">日期范围 ±3天</Tag>
            <Tag color="purple">AI 语义匹配</Tag>
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
};

export default Reconciliation;
