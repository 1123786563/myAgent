import React, { useRef, useState } from 'react';
import { PageContainer, ProTable } from '@ant-design/pro-components';
import { Button, Tag, Space, Modal, Form, Input, message, Timeline, Card, ConfigProvider, theme } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined, AuditOutlined } from '@ant-design/icons';
import axios from 'axios';
import dayjs from 'dayjs';

const Workflow = () => {
  const actionRef = useRef();
  const [modalVisible, setModalVisible] = useState(false);
  const [currentTask, setCurrentTask] = useState(null);
  const [actionType, setActionType] = useState(null); // 'APPROVE' | 'REJECT'
  const [form] = Form.useForm();
  const [historyModalVisible, setHistoryModalVisible] = useState(false);
  const [historyList, setHistoryList] = useState([]);

  // 处理审批动作
  const handleAction = async (values) => {
    try {
      await axios.post('/api/v1/workflow/action', {
        instance_id: currentTask.id,
        action_type: actionType,
        comment: values.comment,
      });
      message.success('操作成功');
      setModalVisible(false);
      actionRef.current?.reload();
    } catch (error) {
      message.error('操作失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  // 打开审批弹窗
  const openApproveModal = (record, type) => {
    setCurrentTask(record);
    setActionType(type);
    form.resetFields();
    setModalVisible(true);
  };

  // 查看历史
  const viewHistory = async (record) => {
    try {
      const res = await axios.get(`/api/v1/workflow/history/${record.id}`);
      setHistoryList(res.data);
      setHistoryModalVisible(true);
    } catch (error) {
      message.error('获取历史失败');
    }
  };

  const columns = [
    {
      title: '业务类型',
      dataIndex: 'business_type',
      valueEnum: {
        INVOICE: { text: '发票验证', status: 'Processing' },
        REIMBURSEMENT: { text: '报销申请', status: 'Warning' },
        PAYMENT: { text: '付款申请', status: 'Error' },
      },
    },
    {
      title: '业务编号',
      dataIndex: 'business_id',
      copyable: true,
    },
    {
      title: '当前节点',
      dataIndex: 'current_node_name',
      render: (text) => <Tag color="blue" style={{ borderRadius: '4px', border: 'none', background: 'rgba(22, 119, 255, 0.15)', color: '#1677ff' }}>{text}</Tag>,
    },
    {
      title: '提交时间',
      dataIndex: 'created_at',
      valueType: 'dateTime',
      sorter: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      valueEnum: {
        RUNNING: { text: '审批中', status: 'Processing' },
        COMPLETED: { text: '已通过', status: 'Success' },
        REJECTED: { text: '已驳回', status: 'Error' },
      },
    },
    {
      title: '操作',
      valueType: 'option',
      render: (text, record) => [
        <a key="approve" onClick={() => openApproveModal(record, 'APPROVE')} style={{ color: '#52c41a', fontWeight: 600 }}>
          同意
        </a>,
        <a key="reject" onClick={() => openApproveModal(record, 'REJECT')} style={{ color: '#ff4d4f', fontWeight: 600 }}>
          驳回
        </a>,
        <a key="history" onClick={() => viewHistory(record)} style={{ color: '#1677ff' }}>
          轨迹
        </a>,
      ],
    },
  ];

  const glassStyle = {
    background: 'rgba(255, 255, 255, 0.03)',
    backdropFilter: 'blur(20px)',
    WebkitBackdropFilter: 'blur(20px)',
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: '16px',
  };

  return (
    <ConfigProvider
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#1677ff',
        },
      }}
    >
      <PageContainer title={<span style={{ color: '#fff', fontSize: '24px', fontWeight: 700 }}>审批中心</span>}>
        <ProTable
          headerTitle={<span style={{ color: '#fff' }}>我的待办任务</span>}
          actionRef={actionRef}
          rowKey="id"
          request={async () => {
            const res = await axios.get('/api/v1/workflow/tasks/pending');
            return {
              data: res.data,
              success: true,
              total: res.data.length,
            };
          }}
          columns={columns}
          search={false}
          style={glassStyle}
          toolBarRender={() => [
            <Button key="refresh" onClick={() => actionRef.current?.reload()} style={{ borderRadius: '8px' }}>
              刷新
            </Button>,
          ]}
        />

        {/* 审批动作弹窗 */}
        <Modal
          title={<span style={{ color: '#fff' }}>{actionType === 'APPROVE' ? '同意申请' : '驳回申请'}</span>}
          open={modalVisible}
          onCancel={() => setModalVisible(false)}
          onOk={() => form.submit()}
          okText="确认操作"
          cancelText="取消"
          okButtonProps={{ danger: actionType === 'REJECT', style: { borderRadius: '8px', height: '36px' } }}
          cancelButtonProps={{ style: { borderRadius: '8px', height: '36px' } }}
          styles={{ content: { ...glassStyle, padding: '24px' }, header: { background: 'transparent', borderBottom: '1px solid rgba(255,255,255,0.1)' } }}
        >
          <Form form={form} onFinish={handleAction} layout="vertical" style={{ marginTop: '20px' }}>
            <Form.Item
              name="comment"
              label={<span style={{ color: 'rgba(255,255,255,0.85)' }}>审批意见</span>}
              rules={[{ required: actionType === 'REJECT', message: '驳回时必须填写意见' }]}
            >
              <Input.TextArea
                rows={4}
                placeholder="请输入您的审批意见..."
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff' }}
              />
            </Form.Item>
          </Form>
        </Modal>

        {/* 历史记录弹窗 */}
        <Modal
          title={<span style={{ color: '#fff' }}>审批历史轨迹</span>}
          open={historyModalVisible}
          onCancel={() => setHistoryModalVisible(false)}
          footer={null}
          width={640}
          styles={{ content: { ...glassStyle, padding: '32px' }, header: { background: 'transparent', borderBottom: '1px solid rgba(255,255,255,0.1)' } }}
        >
          <Timeline mode="left" style={{ marginTop: '32px' }}>
            {historyList.map((item) => (
              <Timeline.Item
                key={item.id}
                label={<span style={{ color: 'rgba(255,255,255,0.45)' }}>{dayjs(item.created_at).format('YYYY-MM-DD HH:mm')}</span>}
                color={
                  item.action_type === 'APPROVE' ? '#52c41a' :
                  item.action_type === 'REJECT' ? '#ff4d4f' :
                  item.action_type === 'SUBMIT' ? '#1677ff' : '#8c8c8c'
                }
              >
                <Card
                  size="small"
                  title={<span style={{ color: '#fff' }}>{item.node_name}</span>}
                  style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', marginBottom: '8px' }}
                >
                  <p style={{ color: 'rgba(255,255,255,0.65)', margin: '4px 0' }}><strong>操作人:</strong> {item.operator_name || item.operator_id}</p>
                  <p style={{ color: 'rgba(255,255,255,0.65)', margin: '4px 0' }}><strong>动作:</strong> <Tag color={item.action_type === 'APPROVE' ? 'green' : 'red'} style={{ border: 'none' }}>{item.action_type}</Tag></p>
                  {item.comment && <p style={{ color: 'rgba(255,255,255,0.85)', marginTop: '8px', padding: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '4px' }}><strong>意见:</strong> {item.comment}</p>}
                </Card>
              </Timeline.Item>
            ))}
          </Timeline>
        </Modal>
      </PageContainer>
    </ConfigProvider>
  );
};

export default Workflow;
