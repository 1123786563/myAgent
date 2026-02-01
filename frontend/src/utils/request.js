import axios from 'axios';
import { message, notification } from 'antd';

// 创建 axios 实例
const request = axios.create({
  baseURL: '/api/v1',
  timeout: 10000,
});

// 请求拦截器
request.interceptors.request.use(
  (config) => {
    // 从本地存储获取租户 ID (后续由 TenantContext 管理)
    const tenantId = localStorage.getItem('tenant_id');
    if (tenantId) {
      config.headers['X-Tenant-Id'] = tenantId;
    }

    // 注入 Auth Token
    const token = localStorage.getItem('token');
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }

    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
request.interceptors.response.use(
  (response) => {
    return response.data;
  },
  (error) => {
    const { response } = error;

    if (response) {
      const { status, data } = response;
      const errorMessage = data?.detail || data?.message || '未知错误';

      switch (status) {
        case 401:
          message.error('登录已过期，请重新登录');
          localStorage.removeItem('token');
          localStorage.removeItem('refresh_token');
          localStorage.removeItem('user_info');
          window.location.href = '/login';
          break;
        case 403:
          notification.error({
            message: '无权操作',
            description: '您没有执行该操作的权限，请联系管理员。',
          });
          break;
        case 400:
          message.warning(errorMessage);
          break;
        case 500:
          notification.error({
            message: '系统异常',
            description: '服务器发生错误，请稍后再试。',
          });
          break;
        default:
          message.error(errorMessage);
      }
    } else {
      message.error('网络连接异常，请检查网络设置');
    }

    return Promise.reject(error);
  }
);

export default request;
