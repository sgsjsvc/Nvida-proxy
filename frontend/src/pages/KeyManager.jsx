import React, { useState } from 'react';
import { Table, Button, Tag, Modal, Form, Input, InputNumber, Switch, Space, message, Popconfirm, Progress } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import api from '../utils/api';

function keyId(fullKey) {
  return encodeURIComponent(fullKey);
}

export default function KeyManager({ keys }) {
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const handleAdd = async (values) => {
    try {
      await api.post('/keys', values);
      message.success('密钥已添加');
      setModalOpen(false);
      form.resetFields();
    } catch (e) {
      message.error(e.response?.data?.detail || '添加失败');
    }
  };

  const handleDelete = async (fullKey) => {
    try {
      await api.delete(`/keys/${keyId(fullKey)}`);
      message.success('密钥已删除');
    } catch (e) {
      message.error('删除失败');
    }
  };

  const handleToggle = async (fullKey, enabled) => {
    try {
      await api.patch(`/keys/${keyId(fullKey)}`, { enabled });
      message.success(enabled ? '已启用' : '已禁用');
    } catch (e) {
      message.error('操作失败');
    }
  };

  const handleReset = async (fullKey) => {
    try {
      await api.post(`/keys/${keyId(fullKey)}/reset`);
      message.success('密钥已重置');
    } catch (e) {
      message.error('重置失败');
    }
  };

  const columns = [
    {
      title: '密钥',
      dataIndex: 'key',
      key: 'key',
      render: (k, record) => <code title={record.full_key}>{k}</code>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status) => {
        const map = {
          healthy: { color: 'green', text: '正常' },
          rate_limited: { color: 'orange', text: '限流' },
          auth_failed: { color: 'red', text: '认证失败' },
          disabled: { color: 'default', text: '已禁用' },
        };
        const s = map[status] || { color: 'default', text: status };
        return <Tag color={s.color}>{s.text}</Tag>;
      },
    },
    {
      title: '权重',
      dataIndex: 'weight',
      key: 'weight',
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled, record) => (
        <Switch
          checked={enabled}
          onChange={(checked) => handleToggle(record.full_key, checked)}
        />
      ),
    },
    {
      title: '请求数',
      dataIndex: 'use_count',
      key: 'use_count',
      sorter: (a, b) => a.use_count - b.use_count,
    },
    {
      title: '成功/失败',
      key: 'sf',
      render: (_, r) => `${r.success_count} / ${r.fail_count}`,
    },
    {
      title: '错误率',
      dataIndex: 'error_rate',
      key: 'error_rate',
      render: (rate) => (
        <Progress
          percent={rate}
          size="small"
          status={rate > 10 ? 'exception' : 'normal'}
          format={(p) => `${p}%`}
        />
      ),
      sorter: (a, b) => a.error_rate - b.error_rate,
    },
    {
      title: '最后错误',
      dataIndex: 'last_error',
      key: 'last_error',
      render: (e) => e || '-',
      ellipsis: true,
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => handleReset(record.full_key)}>
            重置
          </Button>
          <Popconfirm
            title="确定删除此密钥？"
            onConfirm={() => handleDelete(record.full_key)}
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          添加密钥
        </Button>
      </div>

      <Table dataSource={keys} columns={columns} rowKey="full_key" size="small" />

      <Modal
        title="添加 API 密钥"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} layout="vertical" onFinish={handleAdd}>
          <Form.Item
            name="key"
            label="API 密钥"
            rules={[{ required: true, message: '请输入 API 密钥' }]}
          >
            <Input placeholder="nvapi-xxxxx" />
          </Form.Item>
          <Form.Item name="weight" label="权重" initialValue={1}>
            <InputNumber min={1} max={10} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
