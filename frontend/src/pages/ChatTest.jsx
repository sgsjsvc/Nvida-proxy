import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Card, Input, Button, Select, InputNumber, Space, Typography, Tag, Spin } from 'antd';
import { SendOutlined } from '@ant-design/icons';
import api from '../utils/api';

const { TextArea } = Input;
const { Text } = Typography;

export default function ChatTest({ keys }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [model, setModel] = useState('');
  const [maxTokens, setMaxTokens] = useState(256);
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [modelOptions, setModelOptions] = useState([]);
  const [modelSearch, setModelSearch] = useState('');
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load models from DB on mount
  useEffect(() => {
    loadModels('');
  }, []);

  const loadModels = useCallback(async (search) => {
    try {
      const params = {};
      if (search) params.search = search;
      const { data } = await api.get('/models', { params });
      const opts = (data.models || []).map(m => ({ value: m.id, label: m.id }));
      setModelOptions(opts);
      // Auto-select first model if none selected
      if (!model && opts.length > 0) {
        setModel(opts[0].value);
      }
    } catch (e) {
      console.error(e);
    }
  }, [model]);

  const handleModelSearch = useCallback((value) => {
    setModelSearch(value);
    loadModels(value);
  }, [loadModels]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMsg = { role: 'user', content: input.trim() };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');
    setLoading(true);
    setStreaming(true);

    try {
      const { data } = await api.post('/chat', {
        model,
        messages: newMessages.map(m => ({ role: m.role, content: m.content })),
        max_tokens: maxTokens,
        stream: false,
      });

      const choice = data?.choices?.[0];
      if (choice) {
        const assistantMsg = {
          role: 'assistant',
          content: choice.message?.content || '[empty response]',
        };
        setMessages(prev => [...prev, assistantMsg]);
      } else {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: `[Unexpected response format] ${JSON.stringify(data).slice(0, 200)}`,
        }]);
      }
    } catch (e) {
      const errContent = e.response?.data?.detail
        || e.response?.data?.error
        || e.message;
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `[Error] ${errContent}`,
      }]);
    } finally {
      setLoading(false);
      setStreaming(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const availableKeys = keys?.filter(k => k.available) || [];

  return (
    <div style={{ display: 'flex', gap: 16, height: 'calc(100vh - 180px)' }}>
      {/* Chat area */}
      <Card
        style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
        styles={{ body: { flex: 1, display: 'flex', flexDirection: 'column', padding: 16 } }}
      >
        <div style={{
          flex: 1,
          overflow: 'auto',
          marginBottom: 16,
          padding: 8,
          background: '#fafafa',
          borderRadius: 8,
        }}>
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', color: '#999', marginTop: 40 }}>
              <Text type="secondary">输入消息开始测试 API 调用</Text>
            </div>
          )}
          {messages.map((msg, i) => (
            <div
              key={i}
              style={{
                marginBottom: 12,
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
              }}
            >
              <div style={{
                maxWidth: '80%',
                padding: '8px 12px',
                borderRadius: 8,
                background: msg.role === 'user' ? '#1677ff' : '#f0f0f0',
                color: msg.role === 'user' ? '#fff' : '#333',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}>
                {msg.content}
              </div>
            </div>
          ))}
          {streaming && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Spin size="small" />
              <Text type="secondary">正在生成...</Text>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <Space.Compact style={{ width: '100%' }}>
          <TextArea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
            autoSize={{ minRows: 1, maxRows: 4 }}
            disabled={loading}
            style={{ flex: 1 }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={loading}
            disabled={!input.trim()}
          >
            发送
          </Button>
        </Space.Compact>
      </Card>

      {/* Settings sidebar */}
      <Card title="测试参数" style={{ width: 280 }}>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Text strong>模型</Text>
            <Select
              showSearch
              value={model}
              onChange={setModel}
              onSearch={handleModelSearch}
              filterOption={false}
              options={modelOptions}
              style={{ width: '100%', marginTop: 4 }}
              disabled={loading}
              placeholder="搜索并选择模型..."
              notFoundContent={modelSearch ? '无匹配模型' : '请先在系统设置中获取模型'}
            />
          </div>
          <div>
            <Text strong>Max Tokens</Text>
            <InputNumber
              value={maxTokens}
              onChange={setMaxTokens}
              min={1}
              max={4096}
              style={{ width: '100%', marginTop: 4 }}
              disabled={loading}
            />
          </div>
          <div>
            <Text strong>可用密钥</Text>
            <div style={{ marginTop: 4 }}>
              {availableKeys.length === 0 ? (
                <Tag color="red">无可用密钥</Tag>
              ) : (
                availableKeys.map(k => (
                  <div key={k.full_key} style={{ marginBottom: 4 }}>
                    <Tag color={k.rpm_available ? 'green' : 'orange'}>
                      {k.key} ({k.current_rpm}/{k.rpm_limit} rpm)
                    </Tag>
                  </div>
                ))
              )}
            </div>
          </div>
          <Button
            onClick={() => setMessages([])}
            disabled={messages.length === 0}
            block
          >
            清空对话
          </Button>
        </Space>
      </Card>
    </div>
  );
}
