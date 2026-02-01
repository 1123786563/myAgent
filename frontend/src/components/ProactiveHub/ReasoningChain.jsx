import React from 'react';
import { Card, Steps, Tag, Typography, Progress, Empty, Space, Divider } from 'antd';
import {
  RobotOutlined,
  ThunderboltOutlined,
  SearchOutlined,
  CheckCircleOutlined,
  InfoCircleOutlined
} from '@ant-design/icons';

const { Text, Title, Paragraph } = Typography;

/**
 * ReasoningChain Component
 * Visualizes the AI's Chain of Thought (CoT) for accounting classification.
 *
 * @param {Object} log - The inference log from the Transaction or ProposeEntry
 * @param {boolean} loading - Loading state
 */
const ReasoningChain = ({ log, loading }) => {
  if (!log && !loading) {
    return (
      <Card title="AI 记账助理" size="small">
        <Empty description="选择一条分录查看 AI 推理逻辑" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    );
  }

  const cot = log?.cot_trace || [];
  const confidence = (log?.confidence || 0) * 100;

  const getStepIcon = (step) => {
    switch (step) {
      case 'INPUT_ANALYSIS': return <SearchOutlined />;
      case 'ROUTING': return <ThunderboltOutlined />;
      case 'RULE_MATCH': return <CheckCircleOutlined />;
      default: return <InfoCircleOutlined />;
    }
  };

  const getStepTitle = (step) => {
    switch (step) {
      case 'INPUT_ANALYSIS': return '特征分析';
      case 'ROUTING': return '路由决策';
      case 'RULE_MATCH': return '规则匹配';
      case 'DIMENSION_EXTRACTION': return '维度提取';
      case 'CONFIDENCE_SCORING': return '置信度评分';
      default: return step;
    }
  };

  return (
    <Card
      title={
        <Space>
          <RobotOutlined style={{ color: '#1890ff' }} />
          <span>AI 决策内幕</span>
        </Space>
      }
      size="small"
      loading={loading}
    >
      <div style={{ marginBottom: 16 }}>
        <Text type="secondary">置信度</Text>
        <Progress
          percent={Math.round(confidence)}
          status={confidence > 80 ? 'success' : 'normal'}
          strokeColor={confidence > 80 ? '#52c41a' : '#1890ff'}
        />
      </div>

      <Divider style={{ margin: '12px 0' }} />

      <Title level={5}>推理链 (CoT)</Title>
      <Steps
        direction="vertical"
        size="small"
        current={cot.length}
        items={cot.map((item, index) => ({
          title: getStepTitle(item.step),
          description: (
            <div style={{ fontSize: '12px' }}>
              {item.details && <Paragraph ellipsis={{ rows: 2 }}>{item.details}</Paragraph>}
              {item.result && <Tag color="blue">{item.result}</Tag>}
              {item.rule_id && <Text code>Rule: {item.rule_id}</Text>}
              {item.match_type && <Tag color="cyan">{item.match_type}</Tag>}
              {item.dims && Object.keys(item.dims).length > 0 && (
                <div style={{ marginTop: 4 }}>
                  {Object.entries(item.dims).map(([k, v]) => (
                    <Tag key={k} style={{ fontSize: '10px' }}>{k}: {v}</Tag>
                  ))}
                </div>
              )}
            </div>
          ),
          icon: getStepIcon(item.step),
        }))}
      />

      <Divider style={{ margin: '12px 0' }} />

      <div style={{ fontSize: '12px', color: '#999' }}>
        <InfoCircleOutlined /> AI 引擎: {log?.engine || 'L1-Moltbot'}
      </div>
    </Card>
  );
};

export default ReasoningChain;
