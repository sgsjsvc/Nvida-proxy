import React, { useState } from 'react';
import { Layout, Menu, Tag, Spin } from 'antd';
import {
  DashboardOutlined,
  KeyOutlined,
  MessageOutlined,
  FileTextOutlined,
  BarChartOutlined,
  SettingOutlined,
  BookOutlined,
  WifiOutlined,
} from '@ant-design/icons';
import Dashboard from './pages/Dashboard';
import KeyManager from './pages/KeyManager';
import ChatTest from './pages/ChatTest';
import RequestLogs from './pages/RequestLogs';
import Stats from './pages/Stats';
import Settings from './pages/Settings';
import Tutorial from './pages/Tutorial';
import { useWebSocket } from './hooks/useWebSocket';

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: 'dashboard', icon: <DashboardOutlined />, label: '总览' },
  { key: 'keys', icon: <KeyOutlined />, label: '密钥管理' },
  { key: 'chat', icon: <MessageOutlined />, label: '聊天测试' },
  { key: 'logs', icon: <FileTextOutlined />, label: '请求日志' },
  { key: 'stats', icon: <BarChartOutlined />, label: '统计分析' },
  { key: 'settings', icon: <SettingOutlined />, label: '系统设置' },
  { key: 'tutorial', icon: <BookOutlined />, label: '使用教程' },
];

function App() {
  const [selectedKey, setSelectedKey] = useState('dashboard');
  const { keys, stats, logs, connected } = useWebSocket();

  const renderContent = () => {
    switch (selectedKey) {
      case 'dashboard':
        return <Dashboard keys={keys} stats={stats} />;
      case 'keys':
        return <KeyManager keys={keys} />;
      case 'chat':
        return <ChatTest keys={keys} />;
      case 'logs':
        return <RequestLogs wsLogs={logs} />;
      case 'stats':
        return <Stats stats={stats} />;
      case 'settings':
        return <Settings />;
      case 'tutorial':
        return <Tutorial />;
      default:
        return <Dashboard keys={keys} stats={stats} />;
    }
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="dark" width={180}>
        <div style={{ color: '#fff', textAlign: 'center', padding: '16px', fontSize: 16, fontWeight: 'bold' }}>
          API Pool
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => setSelectedKey(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 18, fontWeight: 500 }}>NVIDIA API 轮询池管理</span>
          <Tag
            icon={<WifiOutlined />}
            color={connected ? 'green' : 'red'}
          >
            {connected ? '已连接' : '未连接'}
          </Tag>
        </Header>
        <Content style={{ margin: 16, padding: 16, background: '#fff', borderRadius: 8 }}>
          {!connected && keys.length === 0 ? (
            <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
          ) : (
            renderContent()
          )}
        </Content>
      </Layout>
    </Layout>
  );
}

export default App;
