import React from 'react';
import {
  PageContainer,
  ProForm,
  ProFormList,
  ProFormText,
  ProFormDigit,
  ProFormSelect,
  ProFormDatePicker,
} from '@ant-design/pro-components';
import { Card, Row, Col, Statistic, message, Divider } from 'antd';
import { SaveOutlined } from '@ant-design/icons';
import request from '../../utils/request';

const VoucherEntry = () => {
  const [form] = ProForm.useForm();

  const handleFinish = async (values) => {
    // 借贷平衡逻辑校验
    const items = values.items || [];
    const totalDebit = items.reduce((sum, item) => sum + (item.debit || 0), 0);
    const totalCredit = items.reduce((sum, item) => sum + (item.credit || 0), 0);

    if (Math.abs(totalDebit - totalCredit) > 0.001) {
      message.error(`借贷不平衡！当前借方合计: ${totalDebit.toFixed(2)}, 贷方合计: ${totalCredit.toFixed(2)}`);
      return false;
    }

    try {
      await request.post('/accounting/vouchers', values);
      message.success('凭证录入成功');
      form.resetFields();
    } catch (error) {
      // 错误已在拦截器处理
    }
  };

  return (
    <PageContainer title="记账凭证录入">
      <ProForm
        form={form}
        onFinish={handleFinish}
        initialValues={{
          voucher_date: new Date(),
          items: [{}, {}], // 初始两行
        }}
        submitter={{
          render: (props, doms) => (
            <div style={{ textAlign: 'right', marginTop: 24 }}>
              {doms}
            </div>
          ),
          searchConfig: {
            submitText: '提交凭证',
          },
          resetButtonProps: {
            style: { display: 'none' },
          },
        }}
      >
        <Card title="基础信息" style={{ marginBottom: 24 }}>
          <Row gutter={16}>
            <Col span={8}>
              <ProFormDatePicker
                name="voucher_date"
                label="凭证日期"
                rules={[{ required: true }]}
                width="100%"
              />
            </Col>
            <Col span={16}>
              <ProFormText
                name="description"
                label="总备注"
                placeholder="请输入该笔凭证的总体说明"
              />
            </Col>
          </Row>
        </Card>

        <Card title="分录明细">
          <ProFormList
            name="items"
            initialValue={[{}, {}]}
            creatorButtonProps={{
              creatorButtonText: '添加分录',
            }}
            min={2}
          >
            <Row gutter={16} align="middle">
              <Col span={6}>
                <ProFormSelect
                  name="account_code"
                  label="会计科目"
                  showSearch
                  request={async () => {
                    const data = await request.get('/accounting/accounts');
                    return data.map(item => ({
                      label: `${item.code} ${item.name}`,
                      value: item.code,
                    }));
                  }}
                  rules={[{ required: true }]}
                />
              </Col>
              <Col span={6}>
                <ProFormText name="abstract" label="摘要" />
              </Col>
              <Col span={6}>
                <ProFormDigit
                  name="debit"
                  label="借方金额"
                  min={0}
                  precision={2}
                  fieldProps={{ style: { width: '100%' } }}
                />
              </Col>
              <Col span={6}>
                <ProFormDigit
                  name="credit"
                  label="贷方金额"
                  min={0}
                  precision={2}
                  fieldProps={{ style: { width: '100%' } }}
                />
              </Col>
            </Row>
          </ProFormList>
        </Card>
      </ProForm>
    </PageContainer>
  );
};

export default VoucherEntry;
