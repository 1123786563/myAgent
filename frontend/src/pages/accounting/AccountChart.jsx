import React, { useRef, useState } from 'react';
import { PageContainer, ProTable, ModalForm, ProFormText, ProFormSelect, ProFormCheckbox, ProFormTextArea } from '@ant-design/pro-components';
import { Tag, Button, Space, message, Modal } from 'antd';
import { PlusOutlined, ApartmentOutlined, EditOutlined, PlusSquareOutlined } from '@ant-design/icons';
import request from '../../utils/request';

const AccountChart = () => {
  const actionRef = useRef();
  const [createModalVisible, handleModalVisible] = useState(false);
  const [currentRow, setCurrentRow] = useState();

  const auxiliaryOptions = [
    { label: '部门', value: 'DEPARTMENT' },
    { label: '项目', value: 'PROJECT' },
    { label: '客户', value: 'CUSTOMER' },
    { label: '供应商', value: 'SUPPLIER' },
    { label: '员工', value: 'EMPLOYEE' },
  ];

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
      dataIndex: 'type',
      valueEnum: {
        ASSET: { text: '资产', status: 'Processing' },
        LIABILITY: { text: '负债', status: 'Error' },
        EQUITY: { text: '权益', status: 'Warning' },
        REVENUE: { text: '收入', status: 'Success' },
        EXPENSE: { text: '费用', status: 'Default' },
      },
    },
    {
      title: '辅助核算',
      dataIndex: 'auxiliary_types',
      render: (_, record) => {
        if (!record.enable_auxiliary || !record.auxiliary_types) return '-';
        return (
          <Space size={[0, 4]} wrap>
            {record.auxiliary_types.split(',').map(type => (
              <Tag color="blue" key={type}>
                {auxiliaryOptions.find(opt => opt.value === type)?.label || type}
              </Tag>
            ))}
          </Space>
        );
      },
    },
    {
      title: '末级',
      dataIndex: 'is_leaf',
      width: 80,
      align: 'center',
      render: (leaf) => (leaf ? <Tag color="cyan">是</Tag> : <Tag>否</Tag>),
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
      width: 150,
      render: (_, record) => [
        <a key="add" onClick={() => {
          setCurrentRow({ parent_code: record.code, account_type: record.type, balance_direction: record.direction });
          handleModalVisible(true);
        }}>
          <PlusSquareOutlined /> 下级
        </a>,
        <a key="edit" onClick={() => {
          message.info('详情编辑功能开发中，请使用“新建”覆盖或直接通过 API 调整');
        }}>
          编辑
        </a>,
      ],
    },
  ];

  const handleAdd = async (fields) => {
    const hide = message.loading('正在正在添加...');
    try {
      await request.post('/accounting/accounts', {
        ...fields,
        auxiliary_types: fields.auxiliary_types?.join(','),
        enable_auxiliary: !!fields.auxiliary_types?.length,
        // 默认方向跟随类型，简单处理
        balance_direction: fields.account_type === 'ASSET' || fields.account_type === 'EXPENSE' ? 'DEBIT' : 'CREDIT',
      });
      hide();
      message.success('添加成功');
      return true;
    } catch (error) {
      hide();
      return false;
    }
  };

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
          <Button key="init" icon={<ApartmentOutlined />} onClick={async () => {
            Modal.confirm({
              title: '确认初始化',
              content: '系统将按照中国会计准则初始化标准科目表，是否继续？',
              onOk: async () => {
                await request.post('/accounting/accounts/init-standard');
                message.success('初始化成功');
                actionRef.current?.reload();
              }
            });
          }}>
            初始化标准科目
          </Button>,
          <Button key="add" type="primary" icon={<PlusOutlined />} onClick={() => {
            setCurrentRow(undefined);
            handleModalVisible(true);
          }}>
            新建科目
          </Button>,
        ]}
        expandable={{
          childrenColumnName: 'children',
        }}
      />

      <ModalForm
        title={currentRow?.parent_code ? `添加 [${currentRow.parent_code}] 的下级科目` : '新建一级科目'}
        width="520px"
        visible={createModalVisible}
        onVisibleChange={handleModalVisible}
        onFinish={async (value) => {
          const success = await handleAdd({ ...value, parent_code: currentRow?.parent_code });
          if (success) {
            handleModalVisible(false);
            if (actionRef.current) {
              actionRef.current.reload();
            }
          }
        }}
        initialValues={currentRow}
      >
        <ProFormText
          rules={[{ required: true, message: '请输入科目编码' }]}
          width="md"
          name="code"
          label="科目编码"
          placeholder="例如: 1002.01"
        />
        <ProFormText
          rules={[{ required: true, message: '请输入科目名称' }]}
          width="md"
          name="name"
          label="科目名称"
        />
        <ProFormSelect
          name="account_type"
          label="科目类型"
          width="md"
          options={[
            { label: '资产', value: 'ASSET' },
            { label: '负债', value: 'LIABILITY' },
            { label: '权益', value: 'EQUITY' },
            { label: '收入', value: 'REVENUE' },
            { label: '费用', value: 'EXPENSE' },
          ]}
          rules={[{ required: true }]}
          disabled={!!currentRow?.parent_code}
        />
        <ProFormCheckbox.Group
          name="auxiliary_types"
          label="辅助核算维度"
          options={auxiliaryOptions}
        />
        <ProFormTextArea name="description" label="备注说明" />
      </ModalForm>
    </PageContainer>
  );
};

export default AccountChart;
