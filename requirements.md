# Claude Code API 轮询池代理系统

## 需求文档

**版本**: v1.1
**日期**: 2026-04-20
**状态**: 所有待确认事项已确认，可进入开发

---

## 1. 项目概述

### 1.1 背景
Claude Code 通过 ccswitch 工具代理到英伟达 API 官网，实现对 Claude 模型的访问。当前架构为单点代理模式，存在以下潜在问题：
- 单一 API 密钥的速率限制
- 单点故障风险
- 无法充分利用多个 API 配额

### 1.2 目标
在 ccswitch 代理层之后，增加一个 **API 轮询池（API Polling Pool）**，实现：
1. 多个英伟达 API 密钥的轮询负载均衡
2. 自动故障转移（Failover）
3. 请求速率分散，避免单密钥限流
4. 透明集成，对 Claude Code 客户端无感知

### 1.3 范围
- **包含**: API 轮询池核心功能、本地 GUI 管理界面、配置管理、健康检查、日志
- **不包含**: 远程服务器部署、用户认证系统

---

## 2. 系统架构

### 2.1 当前架构
```
Claude Code CLI
    ↓
ccswitch (代理配置)
    ↓
英伟达 API 官网 (单一密钥)
```

### 2.2 目标架构
```
Claude Code CLI
    ↓
ccswitch (代理配置，指向本地轮询池)
    ↓
API 轮询池服务 (localhost:8080)
    ├── HTTP 代理端点 (供 ccswitch 调用)
    └── GUI 管理界面 (localhost:8081)
    ↓
    ├── 英伟达 API 密钥 #1
    ├── 英伟达 API 密钥 #2
    ├── 英伟达 API 密钥 #3
    └── ... (N 个密钥)

上游目标:
  URL: https://integrate.api.nvidia.com
  Endpoint: POST /v1/chat/completions
```

---

## 3. 功能需求

### 3.1 核心功能

#### FR-001: API 密钥池管理
- 支持配置多个英伟达 API 密钥
- 支持动态添加/删除密钥（热重载）
- 每个密钥可配置权重（优先级）

#### FR-002: 请求轮询分发
- **轮询策略**（默认）：Round-Robin 均匀分发
- **加权轮询**：根据权重分配请求比例
- **最少使用**：优先选择使用次数最少的密钥
- **故障感知**：自动跳过不健康的密钥

#### FR-003: 故障转移 (Failover)
- 当某个密钥返回 429（速率限制）时，自动切换到下一个密钥
- 当某个密钥返回 401/403（认证失败）时，标记为不可用
- 支持配置重试次数（默认：3 次）

#### FR-004: 健康检查
- 定期检查每个密钥的可用性
- 检查间隔可配置（默认：60 秒）
- 自动恢复之前不可用的密钥

#### FR-005: 请求代理
- 透明代理所有请求到英伟达 API
- 保持原始请求头和请求体
- 支持流式响应（SSE）透传

### 3.2 配置管理

#### FR-006: 配置文件
支持 YAML 或 JSON 格式配置文件，包含：
- API 密钥列表
- 轮询策略选择
- 健康检查配置
- 代理监听端口
- GUI 监听端口
- 日志级别

**示例配置** (`config.yaml`):
```yaml
server:
  host: "127.0.0.1"
  proxy_port: 8080
  gui_port: 8081

upstream:
  base_url: "https://integrate.api.nvidia.com"
  endpoint: "/v1/chat/completions"
  timeout: 30

keys:
  - key: "nvapi-xxxxx1"
    weight: 1
    enabled: true
  - key: "nvapi-xxxxx2"
    weight: 2
    enabled: true
  - key: "nvapi-xxxxx3"
    weight: 1
    enabled: true

strategy: "weighted_round_robin"  # round_robin | weighted_round_robin | least_used

health_check:
  enabled: true
  interval: 60  # 秒
  endpoint: "/v1/models"

retry:
  max_attempts: 3
  backoff_ms: 1000

logging:
  level: "info"  # debug | info | warn | error
  file: "proxy.log"
```

### 3.3 GUI 管理界面

#### FR-007: 本地 Web GUI
基于浏览器的本地管理界面，提供以下功能：
- **密钥池管理**: 可视化添加/删除/启用/禁用 API 密钥
- **实时状态监控**: 显示每个密钥的健康状态、使用次数、成功/失败率
- **请求日志查看**: 实时查看请求历史，支持筛选和搜索
- **策略配置**: 在线切换轮询策略（Round-Robin / 加权 / 最少使用）
- **统计图表**: 请求量趋势、密钥使用分布、响应时间分布
- **配置编辑**: 在线编辑配置文件，支持热重载

**技术选型**:
- 后端: Python FastAPI + WebSocket（实时数据推送）
- 前端: React + Ant Design / 或 Vue + Element Plus
- 图表: ECharts / Chart.js

**GUI 页面结构**:
```
/ (Dashboard 总览)
├── /keys (密钥管理)
├── /logs (请求日志)
├── /stats (统计分析)
└── /settings (系统设置)
```

### 3.4 监控与日志

#### FR-008: 请求日志
- 记录每个请求的：时间戳、使用的密钥、响应状态码、延迟
- 支持日志轮转

#### FR-009: 统计信息
- 每个密钥的使用次数
- 每个密钥的成功/失败率
- 当前活跃密钥数量

---

## 4. 非功能需求

### 4.1 性能
- 代理延迟增加 < 10ms（不含上游响应时间）
- 支持并发请求 ≥ 100
- 内存占用 < 200MB（含 GUI 前端资源）

### 4.2 可靠性
- 单密钥故障不影响整体服务
- 支持优雅关闭（Graceful Shutdown）
- 配置错误时提供清晰的错误信息

### 4.3 安全性
- API 密钥仅存储在本地配置文件
- 不记录完整的 API 密钥到日志（仅记录前 8 位）
- 配置文件权限建议：600

### 4.4 易用性
- 提供命令行启动参数
- 支持 `--config` 指定配置文件路径
- 提供 `--validate` 验证配置文件
- 提供 `--dry-run` 模拟运行
- 启动后自动打开浏览器到 GUI 界面

---

## 5. 技术方案

### 5.1 实现语言与框架

**选定方案**: Python + FastAPI

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| **后端框架** | FastAPI | 异步高性能，原生 WebSocket 支持 |
| **HTTP 代理** | httpx | 支持异步、SSE 流式代理 |
| **前端框架** | React + Vite | 组件化开发，生态成熟 |
| **UI 组件库** | Ant Design | 丰富的管理后台组件 |
| **图表库** | ECharts | 强大的数据可视化 |
| **实时通信** | WebSocket | 日志和状态实时推送 |
| **配置解析** | PyYAML | YAML 配置文件支持 |
| **打包工具** | PyInstaller | 可选，打包为单文件可执行 |

### 5.2 依赖组件
- FastAPI + uvicorn（HTTP 服务器）
- httpx（异步 HTTP 客户端，支持 SSE）
- PyYAML（配置解析）
- WebSocket（实时数据推送）
- SQLite（轻量级本地存储，用于日志和统计）
- React + Ant Design（前端 GUI）
- ECharts（数据可视化图表）

---

## 6. 集成方式

### 6.1 与 ccswitch 集成

1. 启动 API 轮询池服务（代理监听 `localhost:8080`，GUI 监听 `localhost:8081`）
2. 修改 ccswitch 配置，将代理目标指向本地轮询池：
   ```
   ccswitch set-url http://localhost:8080
   ```
3. Claude Code 正常使用，无需任何改动
4. 浏览器访问 `http://localhost:8081` 打开管理界面

### 6.2 启动流程
```bash
# 启动轮询池（同时启动代理服务和 GUI）
python main.py --config config.yaml

# 验证代理服务
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-5-20250514","messages":[{"role":"user","content":"hello"}]}'

# 访问 GUI 管理界面
# 浏览器打开 http://localhost:8081

# 配置 ccswitch
ccswitch set-url http://localhost:8080

# 正常使用 Claude Code
claude
```

### 6.3 GUI 界面预览

```
┌─────────────────────────────────────────────────────────────┐
│  NVIDIA API Pool Manager                         [Settings] │
├──────────┬──────────────────────────────────────────────────┤
│Dashboard │  密钥池状态                                      │
│          │  ┌─────────────────────────────────────────────┐ │
│  Keys    │  │ nvapi-xxxx1  ✓ Healthy  1,234 req  0.2% err│ │
│          │  │ nvapi-xxxx2  ✓ Healthy  1,198 req  0.1% err│ │
│  Logs    │  │ nvapi-xxxx3  ⚠ 429限流    890 req  1.5% err│ │
│          │  └─────────────────────────────────────────────┘ │
│  Stats   │                                                  │
│          │  实时请求日志                                     │
│          │  ┌─────────────────────────────────────────────┐ │
│          │  │ 18:30:01 POST /v1/chat  200  1.2s  key-xxx1│ │
│          │  │ 18:30:05 POST /v1/chat  200  0.8s  key-xxx2│ │
│          │  │ 18:30:08 POST /v1/chat  429  0.3s  key-xxx3│ │
│          │  └─────────────────────────────────────────────┘ │
└──────────┴──────────────────────────────────────────────────┘
```

---

## 7. 验收标准

### 7.1 功能验收
- [ ] 配置 3 个 API 密钥，轮询池能正常分发请求
- [ ] 模拟某个密钥 429 错误，系统自动切换到其他密钥
- [ ] 健康检查能正确检测并恢复不可用密钥
- [ ] 流式响应（SSE）正常透传
- [ ] 日志正确记录请求信息

### 7.2 性能验收
- [ ] 代理延迟 < 10ms
- [ ] 并发 100 请求无错误
- [ ] 连续运行 24 小时无内存泄漏

### 7.3 集成验收
- [ ] 与 ccswitch 正常集成
- [ ] Claude Code 所有功能正常工作

---

## 8. 项目计划

### Phase 1: 核心代理（3 天）
- 基础 HTTP 代理服务器
- 密钥池管理
- Round-Robin 轮询
- 基础故障转移
- SSE 流式代理

### Phase 2: GUI 管理界面（4 天）
- Dashboard 总览页面
- 密钥管理页面（增删改查）
- 实时请求日志页面
- 统计分析页面（ECharts 图表）
- 系统设置页面

### Phase 3: 增强功能（3 天）
- 健康检查
- 多种轮询策略
- 配置热重载
- 完善日志系统
- WebSocket 实时推送

### Phase 4: 优化与打包（2 天）
- 性能优化
- 使用文档
- 打包为可执行文件

---

## 9. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 英伟达 API 变更 | 代理失效 | 版本化适配、监控告警 |
| 流式响应兼容性 | 功能受限 | 充分测试 SSE 场景 |
| 密钥泄露 | 安全风险 | 日志脱敏、文件权限 |

---

## 10. 待确认事项

1. **~~英伟达 API 的具体端点和认证方式？~~** ✅ 已确认
   - URL: `https://integrate.api.nvidia.com`
   - Endpoint: `POST /v1/chat/completions`
   - 认证: Bearer Token（`Authorization: Bearer nvapi-xxx`）

2. **~~是否需要 Web 管理界面？~~** ✅ 已确认 - 需要本地 GUI
3. **~~是否需要支持 API 密钥的自动获取/刷新？~~** ✅ 已确认 - 手动在 GUI 管理
4. **~~部署环境？~~** ✅ 已确认 - 仅本地环境

---

## 附录

### A. 参考资料
- ccswitch 工具文档
- 英伟达 API 文档：https://docs.api.nvidia.com/
- Claude Code 文档
- 英伟达 API 端点：`POST https://integrate.api.nvidia.com/v1/chat/completions`

### B. 术语表
- **ccswitch**: Claude Code 的代理配置工具
- **API 轮询池**: 多个 API 密钥的负载均衡管理
- **SSE**: Server-Sent Events，服务端推送事件
- **Failover**: 故障自动转移机制
