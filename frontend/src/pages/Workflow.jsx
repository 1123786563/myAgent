import React, { useRef, useState } from 'react';
import { PageContainer, ProTable } from '@ant-design/pro-components';
import { Button, Tag, Space, Modal, Form, Input, message, Tabs, Timeline, Card } from 'antd';
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
      render: (text) => <Tag color="blue">{text}</Tag>,
    },
    {
      title: '提交人ID',
      dataIndex: 'submitter_id',
      valueType: 'digit',
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
        <a key="approve" onClick={() => openApproveModal(record, 'APPROVE')} style={{ color: '#52c41a' }}>
          同意
        </a>,
        <a key="reject" onClick={() => openApproveModal(record, 'REJECT')} style={{ color: '#f5222d' }}>
          驳回
        </a>,
        <a key="history" onClick={() => viewHistory(record)}>
          历史
        </a>,
      ],
    },
  ];

  return (
    <PageContainer title="审批中心">
      <ProTable
        headerTitle="我的待办任务"
        actionRef={actionRef}
        rowKey="id"
        request={async (params) => {
          const res = await axios.get('/api/v1/workflow/tasks/pending');
          return {
            data: res.data,
            success: true,
            total: res.data.length,
          };
        }}
        columns={columns}
        search={false}
        toolBarRender={() => [
          <Button key="refresh" onClick={() => actionRef.current?.reload()}>
            刷新
          </Button>,
        ]}
      />

      {/* 审批动作弹窗 */}
      <Modal
        title={actionType === 'APPROVE' ? '同意申请' : '驳回申请'}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        okText="确认"
        cancelText="取消"
        okButtonProps={{ danger: actionType === 'REJECT' }}
      >
        <Form form={form} onFinish={handleAction} layout="vertical">
          <Form.Item
            name="comment"
            label="审批意见"
            rules={[{ required: actionType === 'REJECT', message: '驳回时必须填写意见' }]}
          >
            <Input.TextArea rows={4} placeholder="请输入您的审批意见..." />
          </Form.Item>
        </Form>
      </Modal>

      {/* 历史记录弹窗 */}
      <Modal
        title="审批历史轨迹"
        open={historyModalVisible}
        onCancel={() => setHistoryModalVisible(false)}
        footer={null}
        width={600}
      >
        <Timeline mode="left">
          {historyList.map((item) => (
            <Timeline.Item
              key={item.id}
              label={dayjs(item.created_at).format('YYYY-MM-DD HH:mm')}
              color={
                item.action_type === 'APPROVE' ? 'green' :
                item.action_type === 'REJECT' ? 'red' :
                item.action_type === 'SUBMIT' ? 'blue' : 'gray'
              }
            >
              <Card size="small" title={item.node_name}>
                <p><strong>操作人:</strong> {item.operator_name || item.operator_id}</p>
                <p><strong>动作:</strong> <Tag>{item.action_type}</Tag></p>
                {item.comment && <p><strong>意见:</strong> {item.comment}</p>}
              </Card>
            </Timeline.Item>
          ))}
        </Timeline>
      </Modal>
    </PageContainer>
  );
};

export default Workflow;
