import React from 'react';
import { Card, Button, Tag, Space, Typography } from 'antd';
import {
  BellOutlined,
  ArrowRightOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined
} from '@ant-design/icons';

const { Text, Paragraph } = Typography;

const ActionCard = ({ title, description, type, actionText, onAction, date, onViewReasoning }) => {
  const getIcon = () => {
    switch (type) {
      case 'WARNING': return <ExclamationCircleOutlined style={{ color: '#faad14' }} />;
      case 'SUCCESS': return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
      default: return <BellOutlined style={{ color: '#1890ff' }} />;
    }
  };

  return (
    <Card
      size="small"
      style={{ marginBottom: 16, borderLeft: `4px solid ${type === 'WARNING' ? '#faad14' : '#1890ff'}` }}
      title={
        <Space>
          {getIcon()}
          <span>{title}</span>
        </Space>
      }
      extra={<Text type="secondary" style={{ fontSize: '12px' }}>{date}</Text>}
    >
      <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 12 }}>
        {description}
      </Paragraph>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
        {onViewReasoning && (
          <Button size="small" type="text" onClick={onViewReasoning} icon={<RobotOutlined />}>
            AI分析
          </Button>
        )}
        <Button size="small" type="link" onClick={onAction} icon={<ArrowRightOutlined />}>
          {actionText || '去处理'}
        </Button>
      </div>
    </Card>
  );
};

export default ActionCard;
