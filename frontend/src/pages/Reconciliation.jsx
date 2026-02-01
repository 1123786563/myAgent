import React, { useState, useRef } from 'react';
import { PageContainer, ProTable } from '@ant-design/pro-components';
import { Button, Upload, Card, Row, Col, Statistic, message, Tag, Space, ConfigProvider, theme, Modal, Table } from 'antd';
import { InboxOutlined, SyncOutlined, CheckCircleOutlined, CloudUploadOutlined, ThunderboltOutlined } from '@ant-design/icons';
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

  const [matchModalVisible, setMatchModalVisible] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState(null);

  // Mock candidates for matching
  const matchCandidates = [
    { key: 1, date: '2024-01-20', description: '报销-餐饮费', amount: 500.00, similarity: 0.95 },
    { key: 2, date: '2024-01-21', description: '未定义支出', amount: 500.00, similarity: 0.60 },
  ];

  const handleMatchClick = (record) => {
    setSelectedRecord(record);
    setMatchModalVisible(true);
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
      render: (text, record) => {
        if (record.status === 'UNRECONCILED' || record.status === 'MATCHED') {
          return [
            <a key="match" onClick={() => handleMatchClick(record)}>
              智能匹配
            </a>
          ];
        }
        return [];
      },
    },
  ];

  const glassStyle = {
    background: 'rgba(255, 255, 255, 0.03)',
    backdropFilter: 'blur(20px)',
    WebkitBackdropFilter: 'blur(20px)',
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: '16px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
  };

  const statCardStyle = {
    ...glassStyle,
    padding: '20px',
  };

  return (
    <ConfigProvider
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 12,
          colorBgContainer: 'transparent',
        },
      }}
    >
      <div className="fintech-bg">
        <div className="fintech-blob blob-blue" />
        <div className="fintech-blob blob-purple" />

        <PageContainer title={<span style={{ color: '#fff', fontSize: '24px', fontWeight: 700 }}>对账中心</span>}>
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col span={6}>
              <div className="glass-card" style={{ padding: '20px' }}>
                <Statistic
                  title={<span style={{ color: 'rgba(255,255,255,0.45)' }}>总流水数</span>}
                  value={stats.total_statements}
                  prefix={<InboxOutlined style={{ color: '#1677ff' }} />}
                  valueStyle={{ color: '#fff', fontWeight: 700 }}
                />
              </div>
            </Col>
            <Col span={6}>
              <div className="glass-card" style={{ padding: '20px' }}>
                <Statistic
                  title={<span style={{ color: 'rgba(255,255,255,0.45)' }}>待对账</span>}
                  value={stats.unreconciled}
                  valueStyle={{ color: '#ff4d4f', fontWeight: 700 }}
                />
              </div>
            </Col>
            <Col span={6}>
              <div className="glass-card" style={{ padding: '20px' }}>
                <Statistic
                  title={<span style={{ color: 'rgba(255,255,255,0.45)' }}>已匹配 (待确认)</span>}
                  value={stats.matched}
                  valueStyle={{ color: '#faad14', fontWeight: 700 }}
                />
              </div>
            </Col>
            <Col span={6}>
              <div className="glass-card" style={{ padding: '20px' }}>
                <Statistic
                  title={<span style={{ color: 'rgba(255,255,255,0.45)' }}>已完成</span>}
                  value={stats.reconciled}
                  prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
                  valueStyle={{ color: '#52c41a', fontWeight: 700 }}
                />
              </div>
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col span={18}>
              <ProTable
                columns={columns}
                actionRef={actionRef}
                request={async (params = {}) => {
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
                    total: res.data.length * 10,
                  };
                }}
                rowKey="id"
                search={{ labelWidth: 'auto' }}
                className="glass-card"
                toolBarRender={() => [
                  <Button
                    key="run"
                    type="primary"
                    icon={<SyncOutlined />}
                    onClick={handleRunReconciliation}
                    style={{ borderRadius: '8px' }}
                  >
                    开始自动对账
                  </Button>,
                ]}
              />
            </Col>
            <Col span={6}>
              <Card title={<span style={{ color: '#fff' }}>导入流水</span>} className="glass-card" bodyStyle={{ padding: '24px' }}>
                <Dragger
                  name="file"
                  action="/api/v1/reconciliation/upload"
                  data={{ source_type: 'ALIPAY' }}
                  style={{ background: 'rgba(255,255,255,0.02)', border: '1px dashed rgba(255,255,255,0.2)', borderRadius: '12px' }}
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
                    <CloudUploadOutlined style={{ color: '#1677ff', fontSize: '48px' }} />
                  </p>
                  <p style={{ color: '#fff', fontSize: '16px', marginBottom: '8px' }}>点击或拖拽文件上传</p>
                  <p style={{ color: 'rgba(255,255,255,0.45)', fontSize: '12px' }}>
                    支持 CSV, Excel 格式
                  </p>
                </Dragger>
              </Card>
              <Card title={<span style={{ color: '#fff' }}>对账规则</span>} className="glass-card" style={{ marginTop: 16 }}>
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Text style={{ color: 'rgba(255,255,255,0.45)' }}>当前启用规则：</Text>
                  <Tag color="blue" style={{ borderRadius: '4px', border: 'none', background: 'rgba(22, 119, 255, 0.15)', color: '#1677ff' }}>金额容差 ±0.01</Tag>
                  <Tag color="blue" style={{ borderRadius: '4px', border: 'none', background: 'rgba(22, 119, 255, 0.15)', color: '#1677ff' }}>日期范围 ±3天</Tag>
                  <Tag color="purple" style={{ borderRadius: '4px', border: 'none', background: 'rgba(124, 58, 237, 0.15)', color: '#7c3aed' }}>AI 语义匹配</Tag>
                </Space>
              </Card>
            </Col>
          </Row>
        </PageContainer>
      </div>
    </ConfigProvider>
  );
};

export default Reconciliation;
