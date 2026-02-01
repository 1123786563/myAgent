import React, { useState, useEffect } from 'react';
import { PageContainer, StatisticCard } from '@ant-design/pro-components';
import { Row, Col, Card, Typography, Space, Badge, message, ConfigProvider, theme } from 'antd';
import {
  LineChartOutlined,
  AccountBookOutlined,
  TransactionOutlined,
  SafetyOutlined
} from '@ant-design/icons';
import { Line } from '@ant-design/plots';
import ActionCard from '../../components/ProactiveHub/ActionCard';
import request from '../../utils/request';

const { Title, Text } = Typography;

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
        const metricsRes = await request.get('/ui/dashboard/metrics');
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
    theme: 'dark',
    animation: {
      appear: {
        animation: 'path-in',
        duration: 1000,
      },
    },
    color: ['#1677ff', '#7c3aed'],
    lineStyle: {
      lineWidth: 3,
      shadowColor: 'rgba(22, 119, 255, 0.5)',
      shadowBlur: 10,
    },
    area: {
      style: {
        fill: 'l(270) 0:rgba(22, 119, 255, 0) 1:rgba(22, 119, 255, 0.2)',
      },
    },
    xAxis: {
      label: { style: { fill: 'rgba(255,255,255,0.45)' } },
      line: { style: { stroke: 'rgba(255,255,255,0.1)' } },
    },
    yAxis: {
      label: { style: { fill: 'rgba(255,255,255,0.45)' } },
      grid: { line: { style: { stroke: 'rgba(255,255,255,0.05)', lineDash: [4, 4] } } },
    },
    legend: {
      position: 'top-right',
      itemName: { style: { fill: 'rgba(255,255,255,0.65)' } },
    },
    point: {
      size: 4,
      shape: 'circle',
      style: {
        fill: '#0F172A',
        stroke: '#1677ff',
        lineWidth: 2,
      },
    },
    tooltip: {
      showMarkers: true,
      domStyles: {
        'g2-tooltip': {
          background: 'rgba(15, 23, 42, 0.9)',
          backdropFilter: 'blur(10px)',
          border: '1px solid rgba(255,255,255,0.1)',
          boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)',
          color: '#fff'
        }
      }
    },
    interactions: [{ type: 'element-active' }],
  };

  const glassStyle = {
    background: 'rgba(255, 255, 255, 0.03)',
    backdropFilter: 'blur(20px)',
    WebkitBackdropFilter: 'blur(20px)',
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: '16px',
    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
  };

  const backgroundStyle = {
    position: 'relative',
    minHeight: '100vh',
    background: '#0F172A',
    padding: '24px',
    overflow: 'hidden'
  };

  const blobStyle = {
    position: 'absolute',
    borderRadius: '50%',
    filter: 'blur(100px)',
    zIndex: 0,
    opacity: 0.4
  };

  return (
    <ConfigProvider
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 12,
          colorBgContainer: 'transparent',
        },
      }}
    >
      <div className="fintech-bg">
        {/* Animated Background Blobs */}
        <div className="fintech-blob blob-blue" />
        <div className="fintech-blob blob-purple" />

        <PageContainer
          title={<span style={{ color: '#fff', fontSize: '24px', fontWeight: 700 }}>财务智能看板</span>}
          content={<span style={{ color: 'rgba(255,255,255,0.45)' }}>基于 AI 洞察的实时财务健康监控与自动化建议</span>}
          style={{ position: 'relative', zIndex: 1 }}
        >
          <Row gutter={[24, 24]}>
            <Col span={18}>
              <StatisticCard.Group direction="row" gutter={16} style={{ background: 'transparent' }}>
                <StatisticCard
                  statistic={{
                    title: <span style={{ color: 'rgba(255,255,255,0.65)' }}>账户总余额</span>,
                    value: data.metrics.balance,
                    precision: 2,
                    suffix: <span style={{ color: 'rgba(255,255,255,0.45)', fontSize: '14px' }}>CNY</span>,
                    icon: (
                      <div className="metric-icon-wrapper" style={{ background: 'rgba(22, 119, 255, 0.15)' }}>
                        <AccountBookOutlined style={{ color: '#1677ff', fontSize: '24px' }} />
                      </div>
                    ),
                  }}
                  className="glass-card"
                />
                <StatisticCard
                  statistic={{
                    title: <span style={{ color: 'rgba(255,255,255,0.65)' }}>待过账凭证</span>,
                    value: data.metrics.pending_vouchers,
                    icon: (
                      <div className="metric-icon-wrapper" style={{ background: 'rgba(250, 173, 20, 0.15)' }}>
                        <TransactionOutlined style={{ color: '#faad14', fontSize: '24px' }} />
                      </div>
                    ),
                  }}
                  className="glass-card"
                />
                <StatisticCard
                  statistic={{
                    title: <span style={{ color: 'rgba(255,255,255,0.65)' }}>已勾稽发票</span>,
                    value: data.metrics.matched_invoices,
                    icon: (
                      <div className="metric-icon-wrapper" style={{ background: 'rgba(82, 196, 26, 0.15)' }}>
                        <SafetyOutlined style={{ color: '#52c41a', fontSize: '24px' }} />
                      </div>
                    ),
                  }}
                  className="glass-card"
                />
                <StatisticCard
                  statistic={{
                    title: <span style={{ color: 'rgba(255,255,255,0.65)' }}>合规健康分</span>,
                    value: data.metrics.health_score,
                    suffix: <span style={{ color: 'rgba(255,255,255,0.45)', fontSize: '14px' }}>/ 100</span>,
                    icon: (
                      <div className="metric-icon-wrapper" style={{ background: 'rgba(124, 58, 237, 0.15)' }}>
                        <LineChartOutlined style={{ color: '#7c3aed', fontSize: '24px' }} />
                      </div>
                    ),
                  }}
                  className="glass-card"
                />
              </StatisticCard.Group>

              <Card
                title={<span style={{ color: '#fff', fontWeight: 600 }}>收支趋势 (最近 14 天)</span>}
                className="glass-card"
                style={{ marginTop: 24 }}
                bodyStyle={{ padding: '24px' }}
              >
                {chartData.length > 0 ? (
                  <Line {...chartConfig} style={{ height: 320 }} />
                ) : (
                  <div style={{ textAlign: 'center', padding: '100px 0', color: 'rgba(255,255,255,0.25)' }}>
                    暂无趋势数据，等待交易产生...
                  </div>
                )}
              </Card>
            </Col>

            <Col span={6}>
              <Card
                title={
                  <Space>
                    <Badge status="processing" color="#1677ff" />
                    <span style={{ fontWeight: 600, color: '#fff' }}>智能助理洞察</span>
                  </Space>
                }
                bodyStyle={{ padding: '16px' }}
                className="glass-card"
              >
                {data.actions.length > 0 ? (
                  data.actions.map(action => (
                    <div key={action.id} style={{ marginBottom: '16px' }}>
                       <ActionCard
                        title={action.title}
                        description={action.description}
                        type={action.type}
                        date={action.date}
                        onAction={() => message.info('正在导航至相关业务模块...')}
                      />
                    </div>
                  ))
                ) : (
                  <div style={{ textAlign: 'center', color: 'rgba(255,255,255,0.25)', padding: '20px 0' }}>
                    目前没有需要处理的建议
                  </div>
                )}
              </Card>
            </Col>
          </Row>
        </PageContainer>
      </div>
    </ConfigProvider>
  );
};

export default Dashboard;
