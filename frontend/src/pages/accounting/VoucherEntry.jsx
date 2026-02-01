import React, { useState, useEffect } from 'react';
import {
  PageContainer,
  ProForm,
  ProFormList,
  ProFormText,
  ProFormDigit,
  ProFormSelect,
  ProFormDatePicker,
  ProFormDependency,
} from '@ant-design/pro-components';
import { Card, Row, Col, Statistic, message, Divider, Space, Typography, Badge } from 'antd';
import { SaveOutlined, RobotOutlined } from '@ant-design/icons';
import request from '../../utils/request';
import ReasoningChain from '../../components/ProactiveHub/ReasoningChain';

const { Text } = Typography;

const VoucherEntry = () => {
  const [form] = ProForm.useForm();
  const [accounts, setAccounts] = useState({});
  const [activeItemIndex, setActiveItemIndex] = useState(0);

  // 加载科目元数据用于动态联动
  useEffect(() => {
    const fetchAccounts = async () => {
      const data = await request.get('/accounting/accounts');
      const map = {};
      data.forEach(acc => {
        map[acc.code] = acc;
      });
      setAccounts(map);
    };
    fetchAccounts();
  }, []);

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
      <Row gutter={16}>
        <Col span={18}>
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
            <Card title="基础信息" style={{ marginBottom: 24 }} size="small">
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

            <Card title="分录明细" size="small">
              <ProFormList
                name="items"
                initialValue={[{}, {}]}
                creatorButtonProps={{
                  creatorButtonText: '添加分录',
                }}
                min={2}
                onAfterAdd={(index) => setActiveItemIndex(index)}
              >
                {(meta, index) => (
                  <div
                    key={meta.key}
                    onClick={() => setActiveItemIndex(index)}
                    style={{
                      padding: '16px',
                      marginBottom: '16px',
                      border: activeItemIndex === index ? '1px solid #1890ff' : '1px solid #f0f0f0',
                      borderRadius: '4px',
                      background: activeItemIndex === index ? '#f0faff' : 'inherit'
                    }}
                  >
                    <Row gutter={16} align="middle">
                      <Col span={6}>
                        <ProFormSelect
                          name="account_code"
                          label="会计科目"
                          showSearch
                          options={Object.values(accounts).map(acc => ({
                            label: `${acc.code} ${acc.name}`,
                            value: acc.code,
                            disabled: !acc.is_leaf
                          }))}
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

                    {/* 辅助核算动态维度 */}
                    <ProFormDependency name={['account_code']}>
                      {({ account_code }) => {
                        const accConfig = accounts[account_code];
                        if (!accConfig || !accConfig.enable_auxiliary) return null;

                        const dims = accConfig.auxiliary_types?.split(',') || [];
                        return (
                          <div style={{ marginTop: 12, padding: '12px', background: '#fafafa', borderRadius: '4px' }}>
                            <Space size="middle" wrap>
                              <Text type="secondary" style={{ fontSize: '12px' }}>辅助核算:</Text>
                              {dims.includes('DEPARTMENT') && (
                                <ProFormSelect
                                  name="department"
                                  label="部门"
                                  width="sm"
                                  options={[
                                    { label: '财务部', value: 'DEPT_FIN' },
                                    { label: '研发部', value: 'DEPT_RD' },
                                    { label: '销售部', value: 'DEPT_SALES' },
                                  ]}
                                  rules={[{ required: true }]}
                                />
                              )}
                              {dims.includes('PROJECT') && (
                                <ProFormSelect
                                  name="project"
                                  label="项目"
                                  width="sm"
                                  options={[
                                    { label: 'LedgerAlpha 研发', value: 'PROJ_LA' },
                                    { label: '市场推广 2024', value: 'PROJ_MKT' },
                                  ]}
                                  rules={[{ required: true }]}
                                />
                              )}
                              {(dims.includes('CUSTOMER') || dims.includes('SUPPLIER')) && (
                                <ProFormText
                                  name={dims.includes('CUSTOMER') ? 'customer' : 'supplier'}
                                  label={dims.includes('CUSTOMER') ? '客户' : '供应商'}
                                  width="sm"
                                  rules={[{ required: true }]}
                                />
                              )}
                              {dims.includes('EMPLOYEE') && (
                                <ProFormText
                                  name="employee"
                                  label="员工"
                                  width="sm"
                                />
                              )}
                            </Space>
                          </div>
                        );
                      }}
                    </ProFormDependency>
                  </div>
                )}
              </ProFormList>
            </Card>
          </ProForm>
        </Col>

        <Col span={6}>
          <div style={{ position: 'sticky', top: 0 }}>
            <ReasoningChain
              log={form.getFieldValue(['items', activeItemIndex])?.inference_log}
              loading={false}
            />
            <Card title="快捷提示" size="small" style={{ marginTop: 16 }}>
              <Space direction="vertical">
                <Text type="secondary" style={{ fontSize: '12px' }}>
                  <Badge status="processing" /> 选中分录行可查看 AI 建议详情
                </Text>
                <Text type="secondary" style={{ fontSize: '12px' }}>
                  <Badge status="success" /> 辅助核算维度将自动保存至项目标签
                </Text>
              </Space>
            </Card>
          </div>
        </Col>
      </Row>
    </PageContainer>
  );
};

export default VoucherEntry;
