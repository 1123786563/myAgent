import React, { useState, useEffect } from 'react';
import { PageContainer, StatisticCard } from '@ant-design/pro-components';
import { Row, Col, Card, List, Typography, Space, Badge } from 'antd';
import {
  LineChartOutlined,
  AccountBookOutlined,
  TransactionOutlined,
  SafetyOutlined
} from '@ant-design/icons';
import ActionCard from '../../components/ProactiveHub/ActionCard';
import request from '../../utils/request';

const { Title } = Typography;
const { Statistic, Divider } = StatisticCard;

const Dashboard = () => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    metrics: { balance: 0, pending_vouchers: 0, matched_invoices: 0, health_score: 0 },
    actions: []
  });

  useEffect(() => {
    // 模拟获取看板数据
    const fetchData = async () => {
      setLoading(false);
      // 这里的 mock 数据反映了系统目前的业务深度
      setData({
        metrics: { balance: 1258400.50, pending_vouchers: 12, matched_invoices: 45, health_score: 98 },
        actions: [
          {
            id: 1,
            title: '对账差异提醒',
            description: '发现在“支付宝”流水中有一笔 500.00 元的款项未找到对应的记账凭证，建议核对。',
            type: 'WARNING',
            date: '10分钟前'
          },
          {
            id: 2,
            title: '发票自动勾稽完成',
            description: '系统已自动为 24 张进项发票匹配了银行流水，请进入工作台进行最终确认。',
            type: 'SUCCESS',
            date: '1小时前'
          }
        ]
      });
    };
    fetchData();
  }, []);

  return (
    <PageContainer title="财务智能看板">
      <Row gutter={16}>
        <Col span={18}>
          <StatisticCard.Group direction="row">
            <StatisticCard
              statistic={{
                title: '账户总余额',
                value: data.metrics.balance,
                precision: 2,
                suffix: 'CNY',
                icon: <AccountBookOutlined style={{ color: '#1890ff', fontSize: '32px' }} />,
              }}
            />
            <Divider type="vertical" />
            <StatisticCard
              statistic={{
                title: '待过账凭证',
                value: data.metrics.pending_vouchers,
                icon: <TransactionOutlined style={{ color: '#faad14', fontSize: '32px' }} />,
              }}
            />
            <Divider type="vertical" />
            <StatisticCard
              statistic={{
                title: '已勾稽发票',
                value: data.metrics.matched_invoices,
                icon: <SafetyOutlined style={{ color: '#52c41a', fontSize: '32px' }} />,
              }}
            />
            <Divider type="vertical" />
            <StatisticCard
              statistic={{
                title: '合规健康分',
                value: data.metrics.health_score,
                suffix: '/ 100',
                icon: <LineChartOutlined style={{ color: '#722ed1', fontSize: '32px' }} />,
              }}
            />
          </StatisticCard.Group>

          <Card title="收支趋势 (核心图表占位)" style={{ marginTop: 24, height: 400 }}>
            <div style={{ textAlign: 'center', paddingTop: 100, color: '#999' }}>
              [此处集成 @ant-design/plots 动态图表]
            </div>
          </Card>
        </Col>

        <Col span={6}>
          <Card
            title={
              <Space>
                <Badge dot color="blue" />
                <span>智能助理洞察</span>
              </Space>
            }
            bodyStyle={{ padding: '12px' }}
          >
            {data.actions.map(action => (
              <ActionCard
                key={action.id}
                title={action.title}
                description={action.description}
                type={action.type}
                date={action.date}
                onAction={() => message.info('正在导航至相关业务模块...')}
              />
            ))}
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
};

export default Dashboard;
