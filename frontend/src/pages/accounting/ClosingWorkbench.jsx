import React, { useState } from 'react';
import { PageContainer, ProCard } from '@ant-design/pro-components';
import { Steps, Button, Result, Space, Alert, message, Card, Statistic, Row, Col, Divider, Modal, ConfigProvider, theme } from 'antd';
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
      // Error handled by interceptor
    }
    setLoading(false);
  };

  const handleFinalClose = async () => {
    setLoading(true);
    try {
      await request.post('/accounting/periods/close', { year: period.year, month: period.month });
      setCurrentStep(4);
    } catch (e) {
      // Error handled by interceptor
    }
    setLoading(false);
  };

  const glassCardStyle = {
    background: 'rgba(255, 255, 255, 0.03)',
    backdropFilter: 'blur(20px)',
    WebkitBackdropFilter: 'blur(20px)',
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: '24px',
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.2)',
    padding: '40px',
    width: '100%',
    maxWidth: '800px',
    margin: '0 auto'
  };

  const renderContent = () => {
    const commonResultProps = {
      style: { color: '#fff' }
    };

    if (currentStep === 0) {
      return (
        <div style={glassCardStyle}>
          <Result
            icon={<FileTextOutlined style={{ color: '#1677ff', fontSize: '64px' }} />}
            title={<span style={{ color: '#fff' }}>第一步：凭证完整性检查</span>}
            subTitle={<span style={{ color: 'rgba(255,255,255,0.45)' }}>系统将检查 {period.year}年{period.month}月 是否存在草稿或待审批凭证</span>}
            extra={[
              <Button type="primary" key="check" onClick={handleIntegrityCheck} loading={loading} size="large" style={{ borderRadius: '8px', height: '48px', padding: '0 32px' }}>
                开始检查
              </Button>,
            ]}
          >
            {checkResult?.status === 'error' && (
              <Alert
                message={<span style={{ color: '#ff4d4f' }}>{checkResult.message}</span>}
                type="error"
                showIcon
                style={{ marginTop: 24, background: 'rgba(255, 77, 79, 0.1)', border: '1px solid rgba(255, 77, 79, 0.2)' }}
              />
            )}
          </Result>
        </div>
      );
    }

    if (currentStep === 1) {
      return (
        <div style={glassCardStyle}>
          <Result
            icon={<SafetyCertificateOutlined style={{ color: '#52c41a', fontSize: '64px' }} />}
            title={<span style={{ color: '#fff' }}>第二步：试算平衡校验</span>}
            subTitle={<span style={{ color: 'rgba(255,255,255,0.45)' }}>在关账前，必须确保资产 = 负债 + 所有者权益</span>}
            extra={[
              <Button type="primary" key="balance" onClick={handleTrialBalance} loading={loading} size="large" style={{ borderRadius: '8px', height: '48px', padding: '0 32px' }}>
                执行试算平衡
              </Button>,
            ]}
          />
        </div>
      );
    }

    if (currentStep === 2) {
      return (
        <div style={glassCardStyle}>
          <Result
            icon={<LoadingOutlined style={{ color: '#7c3aed', fontSize: '64px' }} />}
            title={<span style={{ color: '#fff' }}>第三步：损益结转</span>}
            subTitle={<span style={{ color: 'rgba(255,255,255,0.45)' }}>由 AI 自动扫描所有收入与费用科目，一键结转至本年利润</span>}
            extra={[
              <Button type="primary" key="transfer" onClick={handlePLTransfer} loading={loading} size="large" style={{ borderRadius: '8px', height: '48px', padding: '0 32px' }}>
                一键生成结转凭证
              </Button>,
            ]}
          />
        </div>
      );
    }

    if (currentStep === 3) {
      return (
        <div style={glassCardStyle}>
          <Result
            status="warning"
            title={<span style={{ color: '#fff' }}>最后一步：正式锁定期间</span>}
            subTitle={<span style={{ color: 'rgba(255,255,255,0.45)' }}>关账后将禁止在该期间录入任何新凭证，请确保所有核算已完成</span>}
            extra={[
              <Button type="primary" danger key="close" onClick={handleFinalClose} loading={loading} size="large" style={{ borderRadius: '8px', height: '48px', padding: '0 32px' }}>
                确认关账
              </Button>,
            ]}
          />
        </div>
      );
    }

    if (currentStep === 4) {
      return (
        <div style={glassCardStyle}>
          <Result
            status="success"
            title={<span style={{ color: '#fff' }}>{period.year}年{period.month}月 结账成功</span>}
            subTitle={<span style={{ color: 'rgba(255,255,255,0.45)' }}>期间已锁定，您可以开始下一期间的操作或导出报表</span>}
            extra={[
              <Button key="next" size="large" style={{ borderRadius: '8px', height: '48px' }}>进入下个期间</Button>,
              <Button key="report" type="primary" size="large" style={{ borderRadius: '8px', height: '48px' }}>查看资产负债表</Button>,
            ]}
          />
        </div>
      );
    }
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
      <PageContainer title={<span style={{ color: '#fff', fontSize: '24px', fontWeight: 700 }}>期末结账工作台</span>}>
        <ProCard style={{ background: 'transparent', border: 'none' }}>
          <Steps
            current={currentStep}
            items={steps}
            style={{ padding: '24px 48px', marginBottom: '48px' }}
          />
          <div style={{ minHeight: 500, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {renderContent()}
          </div>
        </ProCard>
      </PageContainer>

      <style>
        {`
          .ant-steps-item-title {
            color: rgba(255, 255, 255, 0.85) !important;
            font-weight: 600 !important;
          }
          .ant-steps-item-description {
            color: rgba(255, 255, 255, 0.45) !important;
          }
          .ant-steps-item-process .ant-steps-item-icon {
            background: #1677ff !important;
            border-color: #1677ff !important;
          }
          .ant-steps-item-finish .ant-steps-item-icon {
            border-color: #52c41a !important;
          }
          .ant-steps-item-finish .ant-steps-item-icon > .ant-steps-icon {
            color: #52c41a !important;
          }
          .ant-steps-item-finish > .ant-steps-item-container > .ant-steps-item-content > .ant-steps-item-title::after {
            background-color: #52c41a !important;
          }
        `}
      </style>
    </ConfigProvider>
  );
};

export default ClosingWorkbench;
