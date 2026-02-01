import React, { useState } from 'react';
import { PageContainer, ProCard, ProTable } from '@ant-design/pro-components';
import { Steps, Button, Result, Space, Alert, message, Card, Statistic, Row, Col, Divider, Modal } from 'antd';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
  ArrowRightOutlined,
  SafetyCertificateOutlined,
  FileTextOutlined
} from '@ant-design/icons';
import request from '../../utils/request';

const ClosingWorkbench = () => {
  const [currentStep, setCurrentStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [period, setPeriod] = useState({ year: new Date().getFullYear(), month: new Date().getMonth() + 1 });
  const [checkResult, setCheckResult] = useState(null);

  const steps = [
    { title: '凭证完整性检查', description: '检查所有凭证是否已过账' },
    { title: '试算平衡', description: '确保借贷双方余额一致' },
    { title: '损益结转', description: '自动生成损益冲平凭证' },
    { title: '正式关账', description: '锁定期间，归档数据' },
  ];

  const handleIntegrityCheck = async () => {
    setLoading(true);
    try {
      // 模拟前端检查逻辑（实际调用后端验证接口）
      const res = await request.get('/accounting/vouchers', { params: { year: period.year, month: period.month, status: 'DRAFT' } });
      if (res.total > 0) {
        setCheckResult({
          status: 'error',
          message: `发现 ${res.total} 笔未过账凭证，请先完成过账。`,
          details: res.items
        });
      } else {
        setCheckResult({ status: 'success', message: '凭证完整性检查通过，所有单据已过账。' });
        setCurrentStep(1);
      }
    } catch (e) {
      message.error('检查失败');
    }
    setLoading(false);
  };

  const handleTrialBalance = async () => {
    setLoading(true);
    try {
      const data = await request.get('/accounting/reports/trial-balance', { params: { year: period.year, month: period.month } });
      const lastRow = data[data.length - 1];
      if (lastRow.is_balanced) {
        message.success('试算平衡！');
        setCurrentStep(2);
      } else {
        Modal.error({ title: '试算不平衡', content: '当前期间借贷金额不一致，请核对账目。' });
      }
    } catch (e) {
      message.error('获取试算平衡表失败');
    }
    setLoading(false);
  };

  const handlePLTransfer = async () => {
    setLoading(true);
    try {
      const res = await request.post('/accounting/periods/generate-pl-transfer', { year: period.year, month: period.month });
      message.success(`结转凭证生成成功：No.${res.voucher_number}`);
      setCurrentStep(3);
    } catch (e) {
      // 错误已处理
    }
    setLoading(false);
  };

  const handleFinalClose = async () => {
    setLoading(true);
    try {
      await request.post('/accounting/periods/close', { year: period.year, month: period.month });
      setCurrentStep(4);
    } catch (e) {
      // 错误已处理
    }
    setLoading(false);
  };

  const renderContent = () => {
    if (currentStep === 0) {
      return (
        <Result
          icon={<FileTextOutlined />}
          title="第一步：凭证完整性检查"
          subTitle={`系统将检查 ${period.year}年${period.month}月 是否存在草稿或待审批凭证`}
          extra={[
            <Button type="primary" key="check" onClick={handleIntegrityCheck} loading={loading}>
              开始检查
            </Button>,
          ]}
        >
          {checkResult?.status === 'error' && (
            <Alert message={checkResult.message} type="error" showIcon style={{ marginTop: 16 }} />
          )}
        </Result>
      );
    }

    if (currentStep === 1) {
      return (
        <Result
          icon={<SafetyCertificateOutlined style={{ color: '#52c41a' }} />}
          title="第二步：试算平衡校验"
          subTitle="在关账前，必须确保资产 = 负债 + 所有者权益"
          extra={[
            <Button type="primary" key="balance" onClick={handleTrialBalance} loading={loading}>
              执行试算平衡
            </Button>,
          ]}
        />
      );
    }

    if (currentStep === 2) {
      return (
        <Result
          icon={<LoadingOutlined />}
          title="第三步：损益结转"
          subTitle="由 AI 自动扫描所有收入与费用科目，一键结转至本年利润"
          extra={[
            <Button type="primary" key="transfer" onClick={handlePLTransfer} loading={loading}>
              一键生成结转凭证
            </Button>,
          ]}
        />
      );
    }

    if (currentStep === 3) {
      return (
        <Result
          status="warning"
          title="最后一步：正式锁定期间"
          subTitle="关账后将禁止在该期间录入任何新凭证，请确保所有核算已完成"
          extra={[
            <Button type="primary" danger key="close" onClick={handleFinalClose} loading={loading}>
              确认关账
            </Button>,
          ]}
        />
      );
    }

    if (currentStep === 4) {
      return (
        <Result
          status="success"
          title={`${period.year}年${period.month}月 结账成功`}
          subTitle="期间已锁定，您可以开始下一期间的操作或导出报表"
          extra={[
            <Button key="next">进入下个期间</Button>,
            <Button key="report" type="primary">查看资产负债表</Button>,
          ]}
        />
      );
    }
  };

  return (
    <PageContainer title="期末结账工作台">
      <ProCard>
        <Steps
          current={currentStep}
          items={steps}
          style={{ padding: '24px 48px' }}
        />
        <Divider />
        <div style={{ minHeight: 400, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {renderContent()}
        </div>
      </ProCard>
    </PageContainer>
  );
};

export default ClosingWorkbench;
