import React, { useState, useEffect } from 'react';
import { PageContainer, StatisticCard } from '@ant-design/pro-components';
import { Row, Col, Card, List, Typography, Space, Badge, message } from 'antd';
import {
  LineChartOutlined,
  AccountBookOutlined,
  TransactionOutlined,
  SafetyOutlined
} from '@ant-design/icons';
import { Line } from '@ant-design/plots';
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
  const [chartData, setChartData] = useState([]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        // Fetch metrics
        const metricsRes = await request.get('/ui/dashboard/metrics');
        // Fetch chart data
        const chartRes = await request.get('/ui/dashboard/chart');
        
        setData({
          metrics: metricsRes.metrics || { balance: 0, pending_vouchers: 0, matched_invoices: 0, health_score: 0 },
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
        
        setChartData(chartRes.data || []);
      } catch (error) {
        console.error("Dashboard fetch error", error);
        message.error("获取看板数据失败");
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const chartConfig = {
    data: chartData,
    xField: 'date',
    yField: 'value',
    seriesField: 'category',
    smooth: true,
    animation: {
      appear: {
        animation: 'path-in',
        duration: 1000,
      },
    },
    color: ['#1890ff', '#52c41a'],
    area: {
      style: {
        fill: 'l(270) 0:#ffffff 0.5:#1890ff 1:#1890ff',
        fillOpacity: 0.1,
      },
    },
    legend: {
      position: 'top-right',
    },
    point: {
      size: 4,
      shape: 'circle',
      style: {
        fill: '#fff',
        stroke: '#1890ff',
        lineWidth: 2,
      },
    },
    tooltip: {
      showMarkers: true,
    },
    interactions: [{ type: 'element-active' }],
  };

  const cardStyle = {
    borderRadius: '8px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.05)',
    transition: 'all 0.3s cubic-bezier(0.645, 0.045, 0.355, 1)',
    cursor: 'pointer',
  };

  return (
    <PageContainer
      title="财务智能看板"
      content="基于 AI 洞察的实时财务健康监控与自动化建议"
    >
      <Row gutter={[24, 24]}>
        <Col span={18}>
          <StatisticCard.Group direction="row" gutter={16}>
            <StatisticCard
              statistic={{
                title: '账户总余额',
                value: data.metrics.balance,
                precision: 2,
                suffix: 'CNY',
                icon: (
                  <div style={{ background: '#e6f7ff', padding: '8px', borderRadius: '50%', display: 'flex' }}>
                    <AccountBookOutlined style={{ color: '#1890ff', fontSize: '24px' }} />
                  </div>
                ),
              }}
              hoverable
              style={cardStyle}
            />
            <StatisticCard
              statistic={{
                title: '待过账凭证',
                value: data.metrics.pending_vouchers,
                icon: (
                  <div style={{ background: '#fff7e6', padding: '8px', borderRadius: '50%', display: 'flex' }}>
                    <TransactionOutlined style={{ color: '#faad14', fontSize: '24px' }} />
                  </div>
                ),
              }}
              hoverable
              style={cardStyle}
            />
            <StatisticCard
              statistic={{
                title: '已勾稽发票',
                value: data.metrics.matched_invoices,
                icon: (
                  <div style={{ background: '#f6ffed', padding: '8px', borderRadius: '50%', display: 'flex' }}>
                    <SafetyOutlined style={{ color: '#52c41a', fontSize: '24px' }} />
                  </div>
                ),
              }}
              hoverable
              style={cardStyle}
            />
            <StatisticCard
              statistic={{
                title: '合规健康分',
                value: data.metrics.health_score,
                suffix: '/ 100',
                icon: (
                  <div style={{ background: '#f9f0ff', padding: '8px', borderRadius: '50%', display: 'flex' }}>
                    <LineChartOutlined style={{ color: '#722ed1', fontSize: '24px' }} />
                  </div>
                ),
              }}
              hoverable
              style={cardStyle}
            />
          </StatisticCard.Group>

          <Card
            title="收支趋势 (最近 14 天)"
            style={{ ...cardStyle, marginTop: 24 }}
            bodyStyle={{ padding: '24px' }}
          >
             {chartData.length > 0 ? (
               <Line {...chartConfig} style={{ height: 320 }} />
             ) : (
               <div style={{ textAlign: 'center', padding: '100px 0', color: '#bfbfbf' }}>
                 暂无趋势数据，等待交易产生...
               </div>
             )}
          </Card>
        </Col>

        <Col span={6}>
          <Card
            title={
              <Space>
                <Badge status="processing" color="#1890ff" />
                <span style={{ fontWeight: 600 }}>智能助理洞察</span>
              </Space>
            }
            bodyStyle={{ padding: '16px' }}
            style={cardStyle}
          >
            {data.actions.length > 0 ? (
              data.actions.map(action => (
                <ActionCard
                  key={action.id}
                  title={action.title}
                  description={action.description}
                  type={action.type}
                  date={action.date}
                  onAction={() => message.info('正在导航至相关业务模块...')}
                />
              ))
            ) : (
              <div style={{ textAlign: 'center', color: '#bfbfbf', padding: '20px 0' }}>
                目前没有需要处理的建议
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
};

export default Dashboard;
