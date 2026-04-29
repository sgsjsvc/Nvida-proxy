import React, { useState, useEffect, useCallback } from 'react';
import { Card, Form, Select, Button, InputNumber, message, Descriptions, Tag, Table, Input } from 'antd';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import api from '../utils/api';

export default function Settings() {
  const [config, setConfig] = useState(null);
  const [form] = Form.useForm();
  const [timeoutForm] = Form.useForm();
  const [models, setModels] = useState([]);
  const [modelTotal, setModelTotal] = useState(0);
  const [loadingModels, setLoadingModels] = useState(false);
  const [searchText, setSearchText] = useState('');

  useEffect(() => {
    api.get('/config').then(({ data }) => {
      setConfig(data);
      form.setFieldsValue({ strategy: data.strategy });
      timeoutForm.setFieldsValue({ timeout: data.upstream.timeout });
    });
    loadModels();
  }, []);

  const loadModels = useCallback(async (search = '') => {
    setLoadingModels(true);
    try {
      const params = {};
      if (search) params.search = search;
      const { data } = await api.get('/models', { params });
      setModels(data.models || []);
      setModelTotal(data.total || 0);
    } catch (e) {
      console.error(e);
    }
    setLoadingModels(false);
  }, []);

  const handleSearch = (value) => {
    setSearchText(value);
    loadModels(value);
  };

  const handleStrategyChange = async (values) => {
    try {
      await api.put('/config/strategy', { strategy: values.strategy });
      message.success('策略已更新');
      setConfig(prev => ({ ...prev, strategy: values.strategy }));
    } catch (e) {
      message.error('更新失败');
    }
  };

  const handleTimeoutChange = async (values) => {
    try {
      const timeout = values.timeout;
      await api.put('/config/timeout', { timeout });
      message.success(`超时已更新为 ${timeout}s`);
      setConfig(prev => ({ ...prev, upstream: { ...prev.upstream, timeout } }));
    } catch (e) {
      message.error('更新失败');
    }
  };

  const handleFetchModels = async () => {
    setLoadingModels(true);
    try {
      const { data } = await api.post('/models/fetch');
      message.success(`已获取并保存 ${data.count} 个模型`);
      await loadModels(searchText);
    } catch (e) {
      message.error(e.response?.data?.detail || '获取模型列表失败');
    }
    setLoadingModels(false);
  };

  if (!config) return null;

  const modelColumns = [
    { title: '模型 ID', dataIndex: 'id', key: 'id', ellipsis: true },
  ];

  return (
    <div>
      <Card title="轮询策略" style={{ marginBottom: 16 }}>
        <Form form={form} layout="inline" onFinish={handleStrategyChange}>
          <Form.Item name="strategy" label="策略">
            <Select style={{ width: 220 }}>
              <Select.Option value="rpm_aware">RPM 感知（推荐）</Select.Option>
              <Select.Option value="round_robin">Round-Robin（轮询）</Select.Option>
              <Select.Option value="weighted_round_robin">加权轮询</Select.Option>
              <Select.Option value="least_used">最少使用</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit">应用</Button>
          </Form.Item>
        </Form>
      </Card>

      <Card title="当前配置" style={{ marginBottom: 16 }}>
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="上游 URL">{config.upstream.base_url}</Descriptions.Item>
          <Descriptions.Item label="API 端点">{config.upstream.endpoint}</Descriptions.Item>
          <Descriptions.Item label="超时">
          <Form form={timeoutForm} layout="inline" onFinish={handleTimeoutChange}>
            <Form.Item name="timeout" noStyle>
              <InputNumber min={0} step={60} style={{ width: 100 }} addonAfter="s" />
            </Form.Item>
            <Form.Item noStyle>
              <Button type="link" htmlType="submit" size="small">保存</Button>
            </Form.Item>
          </Form>
          <div style={{ color: '#999', fontSize: 12 }}>0 = 无超时限制</div>
        </Descriptions.Item>
          <Descriptions.Item label="RPM 限制">{config.rpm_limit} 次/分钟</Descriptions.Item>
          <Descriptions.Item label="健康检查">
            {config.health_check.enabled ? (
              <Tag color="green">已启用（{config.health_check.interval}s）</Tag>
            ) : (
              <Tag color="red">已禁用</Tag>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="最大重试">{config.retry.max_attempts} 次</Descriptions.Item>
          <Descriptions.Item label="重试间隔">{config.retry.backoff_ms}ms</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card
        title={`可用模型列表（共 ${modelTotal} 个）`}
        extra={
          <Button
            icon={<ReloadOutlined />}
            onClick={handleFetchModels}
            loading={loadingModels}
          >
            获取模型
          </Button>
        }
      >
        <Input
          placeholder="搜索模型..."
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={e => handleSearch(e.target.value)}
          allowClear
          style={{ marginBottom: 12 }}
        />
        <Table
          dataSource={models}
          columns={modelColumns}
          rowKey="id"
          size="small"
          loading={loadingModels}
          pagination={{ pageSize: 20 }}
        />
      </Card>
    </div>
  );
}
