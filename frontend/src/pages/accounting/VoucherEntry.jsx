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
    <div className="fintech-bg">
      <div className="fintech-blob blob-blue" />
      <div className="fintech-blob blob-purple" />
      
      <PageContainer title={<span style={{ color: '#fff' }}>记账凭证录入</span>}>
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
            <Card title={<span style={{ color: '#fff' }}>AI 辅助录入</span>} style={{ marginBottom: 24 }} size="small" className="glass-card" extra={<RobotOutlined style={{ color: '#1890ff' }} />}>
              <div style={{ display: 'flex', gap: '8px' }}>
                <ProFormText
                  fieldProps={{
                    prefix: <RobotOutlined style={{ color: '#1890ff' }} />,
                    onPressEnter: (e) => {
                      const text = e.target.value;
                      if (!text) return;
                      // Mock AI parsing logic
                      message.loading('AI 正在分析语义...', 1).then(() => {
                        if (text.includes('支付宝') && text.includes('500')) {
                          const items = form.getFieldValue('items') || [];
                          // Update first item (Debit)
                          items[0] = { ...items[0], account_code: '1002', abstract: text, debit: 500 };
                          // Update second item (Credit)
                          items[1] = { ...items[1], account_code: '6001', abstract: text, credit: 500 };
                          form.setFieldsValue({ items });
                          message.success('AI 已自动生成分录，请核对');
                        } else {
                          message.warning('未能完全识别，请手动补充');
                        }
                      });
                    },
                    style: { background: 'rgba(255,255,255,0.05)', border: 'none', color: '#fff' }
                  }}
                  name="ai_input"
                  placeholder="试试输入: “收到支付宝转账500元餐费” (按回车触发)"
                  noStyle
                />
              </div>
            </Card>

            <Card title={<span style={{ color: '#fff' }}>基础信息</span>} style={{ marginBottom: 24 }} size="small" className="glass-card">
              <Row gutter={16}>
                <Col span={8}>
                  <ProFormDatePicker
                    name="voucher_date"
                    label={<span style={{ color: 'rgba(255,255,255,0.85)' }}>凭证日期</span>}
                    rules={[{ required: true }]}
                    width="100%"
                    fieldProps={{ style: { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff' } }}
                  />
                </Col>
                <Col span={16}>
                  <ProFormText
                    name="description"
                    label={<span style={{ color: 'rgba(255,255,255,0.85)' }}>总备注</span>}
                    placeholder="请输入该笔凭证的总体说明"
                    fieldProps={{ style: { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff' } }}
                  />
                </Col>
              </Row>
            </Card>

            <Card title={<span style={{ color: '#fff' }}>分录明细</span>} size="small" className="glass-card">
              <ProFormList
                name="items"
                initialValue={[{}, {}]}
                creatorButtonProps={{
                  creatorButtonText: '添加分录',
                  style: { color: '#1677ff', borderColor: '#1677ff', background: 'transparent' }
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
                      border: activeItemIndex === index ? '1px solid #1677ff' : '1px solid rgba(255,255,255,0.1)',
                      borderRadius: '8px',
                      background: activeItemIndex === index ? 'rgba(22, 119, 255, 0.05)' : 'rgba(255,255,255,0.02)',
                      transition: 'all 0.3s'
                    }}
                  >
                    <Row gutter={16} align="middle">
                      <Col span={6}>
                        <ProFormSelect
                          name="account_code"
                          label={<span style={{ color: 'rgba(255,255,255,0.65)' }}>会计科目</span>}
                          showSearch
                          options={Object.values(accounts).map(acc => ({
                            label: `${acc.code} ${acc.name}`,
                            value: acc.code,
                            disabled: !acc.is_leaf
                          }))}
                          rules={[{ required: true }]}
                          fieldProps={{ 
                            style: { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff' },
                            popupClassName: 'glass-dropdown'
                          }}
                        />
                      </Col>
                      <Col span={6}>
                        <ProFormText 
                          name="abstract" 
                          label={<span style={{ color: 'rgba(255,255,255,0.65)' }}>摘要</span>}
                          fieldProps={{ style: { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff' } }}
                        />
                      </Col>
                      <Col span={6}>
                        <ProFormDigit
                          name="debit"
                          label={<span style={{ color: 'rgba(255,255,255,0.65)' }}>借方金额</span>}
                          min={0}
                          precision={2}
                          fieldProps={{ style: { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', width: '100%' } }}
                        />
                      </Col>
                      <Col span={6}>
                        <ProFormDigit
                          name="credit"
                          label={<span style={{ color: 'rgba(255,255,255,0.65)' }}>贷方金额</span>}
                          min={0}
                          precision={2}
                          fieldProps={{ style: { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', width: '100%' } }}
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
                          <div style={{ marginTop: 12, padding: '12px', background: 'rgba(255,255,255,0.02)', borderRadius: '4px', border: '1px dashed rgba(255,255,255,0.1)' }}>
                            <Space size="middle" wrap>
                              <Text type="secondary" style={{ fontSize: '12px', color: 'rgba(255,255,255,0.45)' }}>辅助核算:</Text>
                              {dims.includes('DEPARTMENT') && (
                                <ProFormSelect
                                  name="department"
                                  label={<span style={{ color: 'rgba(255,255,255,0.65)' }}>部门</span>}
                                  width="sm"
                                  options={[
                                    { label: '财务部', value: 'DEPT_FIN' },
                                    { label: '研发部', value: 'DEPT_RD' },
                                    { label: '销售部', value: 'DEPT_SALES' },
                                  ]}
                                  rules={[{ required: true }]}
                                  fieldProps={{ style: { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff' } }}
                                />
                              )}
                              {dims.includes('PROJECT') && (
                                <ProFormSelect
                                  name="project"
                                  label={<span style={{ color: 'rgba(255,255,255,0.65)' }}>项目</span>}
                                  width="sm"
                                  options={[
                                    { label: 'LedgerAlpha 研发', value: 'PROJ_LA' },
                                    { label: '市场推广 2024', value: 'PROJ_MKT' },
                                  ]}
                                  rules={[{ required: true }]}
                                  fieldProps={{ style: { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff' } }}
                                />
                              )}
                              {(dims.includes('CUSTOMER') || dims.includes('SUPPLIER')) && (
                                <ProFormText
                                  name={dims.includes('CUSTOMER') ? 'customer' : 'supplier'}
                                  label={dims.includes('CUSTOMER') ? <span style={{ color: 'rgba(255,255,255,0.65)' }}>客户</span> : <span style={{ color: 'rgba(255,255,255,0.65)' }}>供应商</span>}
                                  width="sm"
                                  rules={[{ required: true }]}
                                  fieldProps={{ style: { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff' } }}
                                />
                              )}
                              {dims.includes('EMPLOYEE') && (
                                <ProFormText
                                  name="employee"
                                  label={<span style={{ color: 'rgba(255,255,255,0.65)' }}>员工</span>}
                                  width="sm"
                                  fieldProps={{ style: { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff' } }}
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
          <div style={{ position: 'sticky', top: 24 }}>
            <ReasoningChain
              log={form.getFieldValue(['items', activeItemIndex])?.inference_log}
              loading={false}
            />
            <Card title={<span style={{ color: '#fff' }}>快捷提示</span>} size="small" style={{ marginTop: 16 }} className="glass-card">
              <Space direction="vertical">
                <Text type="secondary" style={{ fontSize: '12px', color: 'rgba(255,255,255,0.45)' }}>
                  <Badge status="processing" color="#1677ff" /> 选中分录行可查看 AI 建议详情
                </Text>
                <Text type="secondary" style={{ fontSize: '12px', color: 'rgba(255,255,255,0.45)' }}>
                  <Badge status="success" color="#52c41a" /> 辅助核算维度将自动保存至项目标签
                </Text>
              </Space>
            </Card>
          </div>
        </Col>
      </Row>
      </PageContainer>
    </div>
  );
};

export default VoucherEntry;
