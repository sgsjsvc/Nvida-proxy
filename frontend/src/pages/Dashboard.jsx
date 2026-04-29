import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Tag, Table, Progress } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import api from '../utils/api';

export default function Dashboard({ keys, stats }) {
  const poolStats = stats?.pool || stats || {};
  const [tokenTotals, setTokenTotals] = useState({});
  const [tokenByModel, setTokenByModel] = useState([]);
  const [tokenHourly, setTokenHourly] = useState([]);

  const fetchTokenStats = async () => {
    try {
      const { data } = await api.get('/stats');
      if (data.token) {
        setTokenTotals(data.token.totals || {});
        setTokenByModel(data.token.by_model || []);
        setTokenHourly(data.token.hourly || []);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchTokenStats();
    const interval = setInterval(fetchTokenStats, 10000);
    return () => clearInterval(interval);
  }, []);

  const keyColumns = [
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
          healthy: { color: 'green', icon: <CheckCircleOutlined />, text: '正常' },
          rate_limited: { color: 'orange', icon: <ClockCircleOutlined />, text: '限流' },
          auth_failed: { color: 'red', icon: <CloseCircleOutlined />, text: '认证失败' },
          disabled: { color: 'default', text: '已禁用' },
        };
        const s = map[status] || { color: 'default', text: status };
        return <Tag color={s.color}>{s.icon} {s.text}</Tag>;
      },
    },
    {
      title: '权重',
      dataIndex: 'weight',
      key: 'weight',
    },
    {
      title: '请求数',
      dataIndex: 'use_count',
      key: 'use_count',
      sorter: (a, b) => a.use_count - b.use_count,
    },
    {
      title: 'RPM',
      key: 'rpm',
      render: (_, record) => {
        const pct = record.rpm_limit > 0 ? Math.round((record.current_rpm / record.rpm_limit) * 100) : 0;
        return (
          <Progress
            percent={pct}
            size="small"
            status={pct >= 90 ? 'exception' : pct >= 70 ? 'normal' : 'success'}
            format={() => `${record.current_rpm}/${record.rpm_limit}`}
          />
        );
      },
    },
    {
      title: '成功率',
      key: 'success_rate',
      render: (_, record) => {
        const total = record.use_count;
        if (total === 0) return '-';
        const rate = ((record.success_count / total) * 100).toFixed(1);
        return (
          <Progress
            percent={parseFloat(rate)}
            size="small"
            status={rate < 90 ? 'exception' : 'success'}
          />
        );
      },
    },
    {
      title: '错误率',
      dataIndex: 'error_rate',
      key: 'error_rate',
      render: (rate) => `${rate}%`,
      sorter: (a, b) => a.error_rate - b.error_rate,
    },
    {
      title: '最后使用',
      dataIndex: 'last_used',
      key: 'last_used',
      render: (t) => t ? new Date(t * 1000).toLocaleTimeString() : '-',
    },
  ];

  const tokenByModelOption = {
    title: { text: 'Token 用量（按模型）', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      data: tokenByModel.slice(0, 10).map(d => ({
        name: d.model.split('/').pop(),
        value: d.total_tokens,
      })),
    }],
  };

  const tokenHourlyOption = {
    title: { text: 'Token 用量趋势（24h）', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    legend: { data: ['Prompt', 'Completion'], bottom: 0 },
    xAxis: {
      type: 'category',
      data: tokenHourly.map(d => {
        const date = new Date(d.hour_ts * 1000);
        return `${date.getHours()}:00`;
      }),
    },
    yAxis: { type: 'value', name: 'Tokens' },
    series: [
      { name: 'Prompt', type: 'bar', stack: 'total', data: tokenHourly.map(d => d.prompt_tokens || 0) },
      { name: 'Completion', type: 'bar', stack: 'total', data: tokenHourly.map(d => d.completion_tokens || 0) },
    ],
  };

  return (
    <div>
      {/* Pool stats */}
      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Card><Statistic title="总密钥数" value={poolStats.total_keys || 0} /></Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="可用密钥" value={poolStats.available_keys || 0} styles={{ content: { color: '#3f8600' } }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="总请求数" value={poolStats.total_requests || 0} /></Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="当前策略" value={
              poolStats.strategy === 'rpm_aware' ? 'RPM感知' :
              poolStats.strategy === 'round_robin' ? '轮询' :
              poolStats.strategy === 'weighted_round_robin' ? '加权轮询' :
              poolStats.strategy === 'least_used' ? '最少使用' : poolStats.strategy
            } />
          </Card>
        </Col>
      </Row>

      {/* Token stats */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={6}>
          <Card><Statistic title="总 Token 消耗" value={tokenTotals.total_tokens || 0} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="Prompt Tokens" value={tokenTotals.total_prompt || 0} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="Completion Tokens" value={tokenTotals.total_completion || 0} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="Token 请求次数" value={tokenTotals.total_requests || 0} /></Card>
        </Col>
      </Row>

      {/* Token charts */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card>
            {tokenByModel.length > 0 ? (
              <ReactECharts option={tokenByModelOption} style={{ height: 260 }} />
            ) : <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>暂无数据</div>}
          </Card>
        </Col>
        <Col span={12}>
          <Card>
            {tokenHourly.length > 0 ? (
              <ReactECharts option={tokenHourlyOption} style={{ height: 260 }} />
            ) : <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>暂无数据</div>}
          </Card>
        </Col>
      </Row>

      {/* Key table */}
      <Card title="密钥池状态" style={{ marginTop: 16 }}>
        <Table dataSource={keys} columns={keyColumns} rowKey="full_key" pagination={false} size="small" />
      </Card>
    </div>
  );
}
