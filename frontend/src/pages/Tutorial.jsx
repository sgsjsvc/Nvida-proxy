import React from 'react';
import { Typography, Steps, Card, Alert, Divider } from 'antd';

const { Title, Paragraph, Text } = Typography;

export default function Tutorial() {
  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <Title level={3}>使用教程</Title>
      <Paragraph type="secondary">
        通过 API 轮询池实现多密钥负载均衡，避免单密钥限流。
      </Paragraph>

      <Alert
        message="前置要求"
        description="已安装 Python 3.10+、Node.js 18+，已获取至少一个 NVIDIA API 密钥。"
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
      />

      <Card title="快速开始" style={{ marginBottom: 24 }}>
        <Steps
          direction="vertical"
          current={-1}
          items={[
            {
              title: '配置 API 密钥',
              description: (
                <div>
                  <Paragraph>
                    编辑 <Text code>config/config.yaml</Text>，在 <Text code>keys</Text> 下添加你的 NVIDIA API 密钥：
                  </Paragraph>
                  <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 4, fontSize: 13 }}>
{`keys:
  - key: "nvapi-your-key-1"
    weight: 1
    enabled: true
  - key: "nvapi-your-key-2"
    weight: 1
    enabled: true`}
                  </pre>
                  <Paragraph style={{ marginTop: 8 }}>
                    也可在 GUI 的 <Text strong>密钥管理</Text> 页面中可视化添加。
                  </Paragraph>
                </div>
              ),
            },
            {
              title: '启动服务',
              description: (
                <div>
                  <Paragraph>
                    运行 <Text code>python main.py</Text> 启动后端服务：
                  </Paragraph>
                  <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 4, fontSize: 13 }}>
{`python main.py
# 代理服务: http://127.0.0.1:8080
# GUI 管理: http://127.0.0.1:8081`}
                  </pre>
                  <Paragraph style={{ marginTop: 8 }}>
                    前端开发模式另开终端运行 <Text code>cd frontend && npm run dev</Text>，
                    浏览器打开 <Text code>http://localhost:5173</Text>
                  </Paragraph>
                </div>
              ),
            },
            {
              title: '配置 ccswitch 代理',
              description: (
                <div>
                  <Paragraph>
                    将 Claude Code 的代理目标指向本地轮询池：
                  </Paragraph>
                  <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 4, fontSize: 13 }}>
{`ccswitch set-url http://localhost:8080`}
                  </pre>
                  <Paragraph style={{ marginTop: 8 }}>
                    之后正常运行 <Text code>claude</Text> 即可，所有请求会通过轮询池分发到多个密钥。
                  </Paragraph>
                </div>
              ),
            },
            {
              title: '获取可用模型',
              description: (
                <Paragraph>
                  在 <Text strong>系统设置</Text> 页面点击 <Text strong>获取模型</Text> 按钮，
                  从 NVIDIA API 拉取可用模型列表。模型数据会持久化保存，支持模糊搜索。
                </Paragraph>
              ),
            },
            {
              title: '测试 API 调用',
              description: (
                <Paragraph>
                  在 <Text strong>聊天测试</Text> 页面选择模型，输入消息即可测试 API 调用。
                  下拉框支持搜索已获取的模型。
                </Paragraph>
              ),
            },
          ]}
        />
      </Card>

      <Card title="功能说明" style={{ marginBottom: 24 }}>
        <Title level={5}>RPM 感知策略（推荐）</Title>
        <Paragraph>
          每个 API 密钥有 40 rpm 的速率限制。系统会实时跟踪每个密钥的请求数，
          当某个密钥接近限制时自动切换到剩余空间更大的密钥，避免触发 429 错误。
        </Paragraph>

        <Divider />

        <Title level={5}>故障转移</Title>
        <Paragraph>
          当某个密钥返回 429（限流）或 401/403（认证失败）时，系统会自动重试其他可用密钥。
          最大重试次数可在配置中设置。
        </Paragraph>

        <Divider />

        <Title level={5}>健康检查</Title>
        <Paragraph>
          定期检查每个密钥的可用性，自动恢复之前不可用的密钥。
          检查间隔可在 <Text code>config.yaml</Text> 中配置。
        </Paragraph>
      </Card>

      <Card title="配置说明">
        <pre style={{ background: '#f5f5f5', padding: 16, borderRadius: 4, fontSize: 13 }}>
{`server:
  host: "127.0.0.1"      # 监听地址
  proxy_port: 8080        # 代理端口（ccswitch 指向这里）
  gui_port: 8081          # GUI 管理端口

upstream:
  base_url: "https://integrate.api.nvidia.com"
  endpoint: "/v1/chat/completions"
  timeout: 30              # 请求超时（秒）

strategy: "rpm_aware"      # 轮询策略
rpm_limit: 40              # 每个密钥每分钟最大请求数

health_check:
  enabled: true
  interval: 60             # 健康检查间隔（秒）

retry:
  max_attempts: 3          # 最大重试次数
  backoff_ms: 1000         # 重试间隔（毫秒）`}
        </pre>
      </Card>
    </div>
  );
}
