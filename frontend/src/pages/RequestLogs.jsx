import React, { useState, useEffect } from 'react';
import { Table, Tag, Select, InputNumber, Space, Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import api from '../utils/api';

export default function RequestLogs({ wsLogs }) {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [statusFilter, setStatusFilter] = useState(null);

  const fetchLogs = async (p = page, ps = pageSize) => {
    setLoading(true);
    try {
      const params = { limit: ps, offset: (p - 1) * ps };
      if (statusFilter) params.status = statusFilter;
      const { data } = await api.get('/logs', { params });
      setLogs(data.logs);
      setTotal(data.total);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchLogs();
  }, [page, pageSize, statusFilter]);

  useEffect(() => {
    if (wsLogs.length > 0) {
      setLogs(prev => {
        const newLogs = wsLogs.filter(
          wl => !prev.some(p => p.timestamp === wl.timestamp && p.key === wl.key)
        );
        return [...newLogs, ...prev].slice(0, pageSize);
      });
      setTotal(prev => prev + wsLogs.length);
    }
  }, [wsLogs]);

  const resultColor = {
    success: 'green',
    stream_done: 'green',
    rate_limited: 'orange',
    auth_failed: 'red',
    error: 'red',
    timeout: 'volcano',
  };

  const resultText = {
    success: '成功',
    stream_done: '流式完成',
    rate_limited: '限流',
    auth_failed: '认证失败',
    error: '错误',
    timeout: '超时',
  };

  const columns = [
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      render: (t) => dayjs(t * 1000).format('HH:mm:ss'),
      width: 90,
    },
    {
      title: '方法',
      dataIndex: 'method',
      key: 'method',
      width: 70,
    },
    {
      title: '状态码',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (s) => s > 0 ? <Tag color={s === 200 ? 'green' : 'red'}>{s}</Tag> : '-',
    },
    {
      title: '耗时',
      dataIndex: 'elapsed',
      key: 'elapsed',
      width: 80,
      render: (t) => `${t}s`,
    },
    {
      title: '密钥',
      dataIndex: 'masked_key',
      key: 'masked_key',
      width: 120,
    },
    {
      title: '模型',
      dataIndex: 'model',
      key: 'model',
      width: 200,
      ellipsis: true,
      render: (m) => m && m !== 'unknown' ? <code>{m}</code> : '-',
    },
    {
      title: '结果',
      dataIndex: 'result',
      key: 'result',
      width: 100,
      render: (r) => <Tag color={resultColor[r]}>{resultText[r] || r}</Tag>,
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Select
          placeholder="筛选状态"
          allowClear
          style={{ width: 150 }}
          onChange={(v) => { setStatusFilter(v); setPage(1); }}
          options={[
            { label: '成功', value: 200 },
            { label: '限流', value: 429 },
            { label: '认证失败', value: 401 },
          ]}
        />
        <Button icon={<ReloadOutlined />} onClick={() => fetchLogs()}>
          刷新
        </Button>
      </Space>

      <Table
        dataSource={logs}
        columns={columns}
        rowKey={(r) => `${r.timestamp}-${r.masked_key}`}
        loading={loading}
        size="small"
        pagination={{
          current: page,
          pageSize,
          total,
          onChange: (p, ps) => { setPage(p); setPageSize(ps); },
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
        }}
      />
    </div>
  );
}
