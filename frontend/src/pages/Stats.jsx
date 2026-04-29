import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Spin } from 'antd';
import ReactECharts from 'echarts-for-react';
import api from '../utils/api';

export default function Stats({ stats }) {
  const [hourlyData, setHourlyData] = useState([]);
  const [keyUsage, setKeyUsage] = useState([]);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const { data } = await api.get('/stats');
        setHourlyData(data.hourly || []);
        setKeyUsage(data.key_usage || []);
      } catch (e) {
        console.error(e);
      }
    };
    fetchStats();
    const timer = setInterval(fetchStats, 30000);
    return () => clearInterval(timer);
  }, []);

  const hourlyOption = {
    title: { text: '24 小时请求趋势', left: 'center' },
    tooltip: { trigger: 'axis' },
    legend: { data: ['总请求', '成功', '限流'], bottom: 0 },
    xAxis: {
      type: 'category',
      data: hourlyData.map(d => {
        const date = new Date(d.hour_ts * 1000);
        return `${date.getHours()}:00`;
      }),
    },
    yAxis: { type: 'value' },
    series: [
      {
        name: '总请求',
        type: 'line',
        data: hourlyData.map(d => d.total),
        smooth: true,
      },
      {
        name: '成功',
        type: 'line',
        data: hourlyData.map(d => d.success),
        smooth: true,
        itemStyle: { color: '#52c41a' },
      },
      {
        name: '限流',
        type: 'line',
        data: hourlyData.map(d => d.rate_limited),
        smooth: true,
        itemStyle: { color: '#faad14' },
      },
    ],
  };

  const keyUsageOption = {
    title: { text: '密钥使用分布', left: 'center' },
    tooltip: { trigger: 'item' },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        data: keyUsage.map(d => ({
          name: d.masked_key,
          value: d.total,
        })),
      },
    ],
  };

  const errorRateOption = {
    title: { text: '密钥平均响应时间', left: 'center' },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: keyUsage.map(d => d.masked_key),
    },
    yAxis: { type: 'value', name: '秒' },
    series: [
      {
        type: 'bar',
        data: keyUsage.map(d => d.avg_elapsed ? d.avg_elapsed.toFixed(3) : 0),
        itemStyle: { color: '#1890ff' },
      },
    ],
  };

  if (!stats) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <div>
      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card>
            <ReactECharts option={hourlyOption} style={{ height: 300 }} />
          </Card>
        </Col>
        <Col span={12}>
          <Card>
            <ReactECharts option={keyUsageOption} style={{ height: 300 }} />
          </Card>
        </Col>
        <Col span={12}>
          <Card>
            <ReactECharts option={errorRateOption} style={{ height: 300 }} />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
