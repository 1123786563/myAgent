import React, { useState } from 'react';
import { Form, Input, Button, Typography, Space, message, ConfigProvider, theme } from 'antd';
import { UserOutlined, LockOutlined, ArrowRightOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const { Title, Text } = Typography;

const Login = () => {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { login } = useAuth();

  const onFinish = async (values) => {
    setLoading(true);
    try {
      const result = await login(values.email, values.password);
      if (result.success) {
        message.success('登录成功');
        navigate('/');
      } else {
        message.error(result.message || '登录失败，请检查账号密码');
      }
    } catch (error) {
      message.error('系统繁忙，请稍后再试');
    } finally {
      setLoading(false);
    }
  };

  // Glassmorphic Styles
  const glassStyle = {
    background: 'rgba(255, 255, 255, 0.05)',
    backdropFilter: 'blur(20px)',
    WebkitBackdropFilter: 'blur(20px)',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    borderRadius: '24px',
    padding: '48px 40px',
    width: '100%',
    maxWidth: '440px',
    boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
    animation: 'fadeInUp 0.8s ease-out'
  };

  const backgroundStyle = {
    position: 'relative',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    minHeight: '100vh',
    background: '#0F172A', // Deep Fintech Navy
    overflow: 'hidden'
  };

  // Dynamic mesh gradient "blobs"
  const blobStyle = {
    position: 'absolute',
    borderRadius: '50%',
    filter: 'blur(80px)',
    zIndex: 0,
    opacity: 0.6
  };

  return (
    <ConfigProvider
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#1677ff', // Trust Blue
          borderRadius: 8,
          colorBgContainer: 'rgba(255, 255, 255, 0.05)',
        },
      }}
    >
      <div style={backgroundStyle}>
        {/* Animated Background Blobs */}
        <div style={{ ...blobStyle, width: '400px', height: '400px', background: '#1e40af', top: '-10%', left: '-5%' }} />
        <div style={{ ...blobStyle, width: '350px', height: '350px', background: '#7c3aed', bottom: '-5%', right: '5%' }} />

        <style>
          {`
            @keyframes fadeInUp {
              from { opacity: 0; transform: translateY(20px); }
              to { opacity: 1; transform: translateY(0); }
            }
            .glass-input .ant-input-affix-wrapper {
              background: rgba(255, 255, 255, 0.03) !important;
              border: 1px solid rgba(255, 255, 255, 0.1) !important;
              padding: 12px 16px;
            }
            .glass-input .ant-input-affix-wrapper-focused {
              border-color: #1677ff !important;
              box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.2) !important;
            }
            .login-btn {
              height: 50px;
              font-weight: 600;
              letter-spacing: 0.5px;
              margin-top: 12px;
            }
          `}
        </style>

        <div style={glassStyle} className="glass-container">
          <div style={{ textAlign: 'center', marginBottom: '40px' }}>
            <div style={{
              width: '64px',
              height: '64px',
              background: 'linear-gradient(135deg, #1677ff 0%, #7c3aed 100%)',
              borderRadius: '16px',
              margin: '0 auto 24px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 10px 20px rgba(22, 119, 255, 0.3)'
            }}>
              <LockOutlined style={{ fontSize: '32px', color: '#fff' }} />
            </div>
            <Title level={2} style={{ margin: '0 0 8px', color: '#fff', fontWeight: 700, letterSpacing: '-0.5px' }}>
              Ledger Alpha
            </Title>
            <Text style={{ color: 'rgba(255, 255, 255, 0.45)', fontSize: '15px' }}>
              欢迎回来，请输入您的凭据以访问财务看板
            </Text>
          </div>

          <Form
            name="login"
            onFinish={onFinish}
            autoComplete="off"
            layout="vertical"
            className="glass-input"
          >
            <Form.Item
              name="email"
              rules={[
                { required: true, message: '请输入您的邮箱' },
                { type: 'email', message: '请输入有效的邮箱地址' }
              ]}
            >
              <Input
                prefix={<UserOutlined style={{ color: 'rgba(255, 255, 255, 0.25)' }} />}
                placeholder="邮箱地址"
              />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[{ required: true, message: '请输入您的密码' }]}
            >
              <Input.Password
                prefix={<LockOutlined style={{ color: 'rgba(255, 255, 255, 0.25)' }} />}
                placeholder="登录密码"
              />
            </Form.Item>

            <div style={{ marginBottom: '24px', textAlign: 'right' }}>
              <Button type="link" style={{ padding: 0, color: 'rgba(255, 255, 255, 0.45)' }}>
                忘记密码?
              </Button>
            </div>

            <Form.Item style={{ marginBottom: 0 }}>
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                block
                className="login-btn"
                icon={<ArrowRightOutlined />}
              >
                立即登录
              </Button>
            </Form.Item>
          </Form>

          <div style={{ marginTop: '32px', textAlign: 'center' }}>
            <Text style={{ color: 'rgba(255, 255, 255, 0.35)' }}>
              还没有账户? <Button type="link" style={{ padding: '0 4px', fontWeight: 600 }}>申请试用</Button>
            </Text>
          </div>
        </div>
      </div>
    </ConfigProvider>
  );
};

export default Login;
