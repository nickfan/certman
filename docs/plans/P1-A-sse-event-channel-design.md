# P1-A: Subscribe 升级为 SSE/WebSocket 事件通道

**设计版本**: v1.0  
**设计日期**: 2026-03-28  
**目标版本**: certman v0.1.1  

---

## 1. 架构设计概览

### 1.1 升级目标

将现有的 HTTP 长轮询 (`/api/v1/node-agent/subscribe`) 升级为 SSE (Server-Sent Events) 实时推送，同时保持向后兼容的三层回退链：

```
SSE (推荐) → Subscribe (长轮询) → Poll (短轮询)
```

### 1.2 关键约束

- **向后兼容**: 现有 poll/subscribe 端点必须保留
- **认证一致性**: 使用相同的 Ed25519 签名机制
- **最小依赖**: 优先使用现有库（httpx、pydantic），避免引入新依赖
- **跨平台**: Windows 和 Linux 兼容
- **横向扩展**: 单进程内多连接管理，为未来分布式部署预留接口

---

## 2. SSE 路由设计

### 2.1 端点定义

```
GET /api/v1/node-agent/events
```

**认证方式**: Query Parameters（与 bundle download 一致）

```
?node_id=<node-id>
&timestamp=<unix-timestamp>
&nonce=<uuid>
&signature=<ed25519-signature>
```

**签名 Payload**:
```python
# 空 payload（与 poll 一致）
signature = sign_message(
    private_key,
    node_id=node_id,
    timestamp=timestamp,
    nonce=nonce,
    payload=b""
)
```

### 2.2 响应格式

**Content-Type**: `text/event-stream`  
**Cache-Control**: `no-cache`  
**Connection**: `keep-alive`  

#### 事件类型

1. **连接确认事件**（立即发送）
```
event: connected
data: {"node_id": "node-a", "server_time": 1711584000}

```

2. **心跳事件**（每 15 秒）
```
: keepalive-1711584015

```

3. **任务分配事件**（有任务时）
```
event: assignment
data: {"assignments": [{"job_id": "job-123", "bundle_url": "...", "bundle_token": "..."}]}

```

4. **错误事件**（认证失败、节点禁用等）
```
event: error
data: {"code": "AUTH_NODE_DISABLED", "message": "node is disabled", "reconnect": false}

```

### 2.3 连接管理

**客户端重连策略**:
- `retry: 3000` (SSE 标准报头，建议客户端 3 秒后重连)
- 客户端实现指数退避：3s, 6s, 12s, 24s, 30s (上限)
- 加入 jitter (±20%) 避免雷鸣羊群效应

**服务端连接池**:
- 每个节点最多保持 1 个活跃 SSE 连接
- 新连接到来时关闭旧连接（避免僵尸连接）
- 连接超时：60 分钟（通过心跳检测客户端活跃性）

---

## 3. 服务端事件队列与连接管理

### 3.1 架构图

```
┌─────────────────────────────────────────────────────────┐
│  FastAPI Application                                    │
│                                                          │
│  ┌────────────────────┐      ┌─────────────────────┐   │
│  │ POST /jobs         │      │ GET /events         │   │
│  │ (创建任务)          │      │ (SSE 连接)          │   │
│  └─────────┬──────────┘      └──────────┬──────────┘   │
│            │                            │              │
│            v                            v              │
│  ┌──────────────────────────────────────────────────┐  │
│  │   SSEEventBus (增强版)                           │  │
│  │                                                   │  │
│  │  ┌─────────────────────────────────────────────┐ │  │
│  │  │ Connection Pool: Dict[node_id, SSEClient]   │ │  │
│  │  └─────────────────────────────────────────────┘ │  │
│  │                                                   │  │
│  │  ┌─────────────────────────────────────────────┐ │  │
│  │  │ Event Queue: asyncio.Queue (per connection) │ │  │
│  │  └─────────────────────────────────────────────┘ │  │
│  │                                                   │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 3.2 数据结构

```python
# certman/node_agent/sse_event_bus.py

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Optional
from uuid import uuid4


@dataclass
class SSEEvent:
    """SSE 事件数据结构"""
    event: str  # connected, assignment, error, ping
    data: str   # JSON 字符串
    id: Optional[str] = None
    retry: Optional[int] = None  # 毫秒


@dataclass
class SSEClient:
    """单个 SSE 连接的管理器"""
    node_id: str
    queue: asyncio.Queue[SSEEvent | None]  # None 表示关闭连接
    connected_at: float
    last_activity: float
    
    def send_event(self, event: SSEEvent) -> None:
        """非阻塞地发送事件（如果队列满则丢弃旧事件）"""
        try:
            self.queue.put_nowait(event)
            self.last_activity = time.time()
        except asyncio.QueueFull:
            # 队列满时丢弃最旧的事件，保留最新的
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(event)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass
    
    def close(self) -> None:
        """关闭连接（发送终止信号）"""
        try:
            self.queue.put_nowait(None)
        except asyncio.QueueFull:
            pass


class SSEEventBus:
    """
    SSE 事件总线，管理所有 node-agent SSE 连接。
    
    设计原则：
    1. 每个 node_id 最多 1 个活跃连接（新连接会关闭旧连接）
    2. 使用 asyncio.Queue 实现异步消息传递
    3. 连接池自动清理过期连接（60 分钟无活动）
    """
    
    def __init__(self, max_queue_size: int = 100):
        self._clients: Dict[str, SSEClient] = {}
        self._lock = asyncio.Lock()
        self._max_queue_size = max_queue_size
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def register_client(self, node_id: str) -> SSEClient:
        """
        注册新的 SSE 客户端连接。
        
        如果该 node_id 已有连接，则关闭旧连接。
        """
        async with self._lock:
            # 关闭旧连接
            if node_id in self._clients:
                old_client = self._clients[node_id]
                old_client.close()
            
            # 创建新连接
            client = SSEClient(
                node_id=node_id,
                queue=asyncio.Queue(maxsize=self._max_queue_size),
                connected_at=time.time(),
                last_activity=time.time(),
            )
            self._clients[node_id] = client
            
            # 启动清理任务（如果尚未启动）
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            
            return client
    
    async def unregister_client(self, node_id: str) -> None:
        """移除客户端连接"""
        async with self._lock:
            if node_id in self._clients:
                del self._clients[node_id]
    
    async def notify_assignments_updated(self, node_ids: Optional[list[str]] = None) -> int:
        """
        通知节点有新的任务分配。
        
        Args:
            node_ids: 指定节点列表（None 表示广播给所有连接）
        
        Returns:
            通知的客户端数量
        """
        event = SSEEvent(
            event="assignment",
            data='{"refresh": true}',  # 客户端收到后应立即调用 poll
            id=uuid4().hex,
        )
        
        async with self._lock:
            if node_ids is None:
                targets = list(self._clients.values())
            else:
                targets = [self._clients[nid] for nid in node_ids if nid in self._clients]
            
            for client in targets:
                client.send_event(event)
            
            return len(targets)
    
    async def _cleanup_loop(self) -> None:
        """后台任务：定期清理过期连接"""
        while True:
            await asyncio.sleep(60)  # 每分钟检查一次
            
            now = time.time()
            timeout_seconds = 3600  # 60 分钟
            
            async with self._lock:
                expired = [
                    node_id
                    for node_id, client in self._clients.items()
                    if now - client.last_activity > timeout_seconds
                ]
                
                for node_id in expired:
                    client = self._clients[node_id]
                    client.close()
                    del self._clients[node_id]


# 全局单例
sse_event_bus = SSEEventBus()
```

### 3.3 集成点修改

**在 `certman/services/job_service.py` 中通知事件总线**:

```python
# 在 create_job() 或 assign_job_to_node() 后添加
from certman.node_agent.sse_event_bus import sse_event_bus

async def create_job(...):
    # ... 创建任务的现有逻辑 ...
    
    # 通知 SSE 订阅者
    if job.node_id:
        await sse_event_bus.notify_assignments_updated([job.node_id])
    else:
        # 未分配节点时广播给所有节点
        await sse_event_bus.notify_assignments_updated()
    
    return job
```

**注意**: 需要确保 FastAPI 应用使用 `asyncio` 运行（已默认支持）。

---

## 4. API 路由实现

### 4.1 SSE 端点实现

在 `certman/api/routes/node_agent.py` 中添加：

```python
from fastapi import Response
from fastapi.responses import StreamingResponse
from certman.node_agent.sse_event_bus import sse_event_bus, SSEEvent
import json

@router.get(
    "/events",
    summary="Subscribe to real-time events (SSE)",
    description="Establish a Server-Sent Events connection for real-time job assignment notifications.",
    response_class=StreamingResponse,
)
async def sse_events(
    request: Request,
    node_id: str = Query(..., description="Node identifier"),
    timestamp: int = Query(..., description="Unix timestamp in seconds"),
    nonce: str = Query(..., description="Single-use nonce for replay protection"),
    signature: str = Query(..., description="Ed25519 signature over node_id/timestamp/nonce"),
) -> StreamingResponse:
    """
    SSE 实时事件流端点。
    
    认证方式与 bundle download 一致（query params + signature）。
    
    事件类型：
    - connected: 连接建立确认
    - assignment: 有新任务分配（客户端应调用 poll 获取详情）
    - error: 错误通知（含 reconnect: false 表示不应重连）
    - 心跳: 注释行（: keepalive-<timestamp>）
    
    响应格式遵循 SSE 标准：
    - event: <type>
    - data: <json>
    - id: <event-id>
    - retry: <milliseconds>
    """
    runtime = request.app.state.runtime
    
    # 1. 认证验证（与 poll 一致）
    try:
        node = _get_active_node(runtime, node_id)
        public_key = serialization.load_pem_public_key(node.public_key_pem.encode("utf-8"))
        verify_message(
            public_key,
            signature,
            node_id=node_id,
            timestamp=timestamp,
            nonce=nonce,
            payload=b"",
        )
    except (HTTPException, SecurityError) as exc:
        # 认证失败时返回 401 错误
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_INVALID_SIGNATURE", "message": str(exc)}
        ) from exc
    
    # 2. 防重放攻击（存储 nonce）
    _store_nonce_or_conflict(runtime, node_id, nonce)
    _touch_node_last_seen(runtime, node_id)
    
    # 3. 注册 SSE 客户端
    client = await sse_event_bus.register_client(node_id)
    
    # 4. 生成 SSE 流
    async def event_stream():
        try:
            # 发送连接确认
            yield _format_sse_event(SSEEvent(
                event="connected",
                data=json.dumps({
                    "node_id": node_id,
                    "server_time": int(time.time()),
                }),
                retry=3000,  # 建议客户端 3 秒后重连
            ))
            
            # 发送初始心跳
            last_heartbeat = time.time()
            heartbeat_interval = 15  # 秒
            
            # 主循环：从队列中读取事件
            while True:
                # 计算下次心跳时间
                now = time.time()
                next_heartbeat = last_heartbeat + heartbeat_interval
                timeout = max(0.1, next_heartbeat - now)
                
                try:
                    # 等待事件（带超时）
                    event = await asyncio.wait_for(
                        client.queue.get(),
                        timeout=timeout
                    )
                    
                    # None 表示连接关闭
                    if event is None:
                        break
                    
                    # 发送事件
                    yield _format_sse_event(event)
                    
                except asyncio.TimeoutError:
                    # 超时时发送心跳
                    yield f": keepalive-{int(time.time())}\n\n"
                    last_heartbeat = time.time()
        
        finally:
            # 清理连接
            await sse_event_bus.unregister_client(node_id)
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )


def _format_sse_event(event: SSEEvent) -> str:
    """格式化 SSE 事件为标准文本格式"""
    lines = []
    
    if event.retry is not None:
        lines.append(f"retry: {event.retry}")
    
    if event.id is not None:
        lines.append(f"id: {event.id}")
    
    if event.event:
        lines.append(f"event: {event.event}")
    
    if event.data:
        # 支持多行 data（SSE 标准）
        for line in event.data.split("\n"):
            lines.append(f"data: {line}")
    
    lines.append("")  # 空行表示事件结束
    return "\n".join(lines) + "\n"
```

---

## 5. 客户端 SSE 实现

### 5.1 配置扩展

在 `certman/config.py` 中扩展 `ControlPlaneConfig`:

```python
class ControlPlaneConfig(BaseModel):
    endpoint: str
    poll_interval_seconds: int = 30
    
    # 长轮询配置（向后兼容）
    prefer_subscribe: bool = False
    subscribe_wait_seconds: int = 25
    
    # SSE 配置（新增）
    prefer_sse: bool = False  # 默认关闭，保持向后兼容
    sse_reconnect_min_seconds: int = 3  # 最小重连间隔
    sse_reconnect_max_seconds: int = 30  # 最大重连间隔
    sse_heartbeat_timeout_seconds: int = 60  # 心跳超时（超过此时间未收到任何数据则断开）
```

### 5.2 SSE 客户端实现

在 `certman/node_agent/sse_client.py` 新建文件：

```python
from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Callable, Optional
from uuid import uuid4

import httpx

from certman.security.identity import load_ed25519_private_key
from certman.security.signing import sign_message


@dataclass
class SSEMessage:
    """SSE 消息解析结果"""
    event: str
    data: str
    id: Optional[str] = None
    retry: Optional[int] = None


class SSEClient:
    """
    SSE 客户端，支持自动重连和回退策略。
    
    重连策略：指数退避 + jitter
    - 初始延迟: 3 秒
    - 最大延迟: 30 秒
    - Jitter: ±20%
    """
    
    def __init__(
        self,
        *,
        endpoint: str,
        node_id: str,
        private_key_path: Path,
        reconnect_min_seconds: int = 3,
        reconnect_max_seconds: int = 30,
        heartbeat_timeout_seconds: int = 60,
        on_assignment: Optional[Callable[[], None]] = None,
    ):
        self._endpoint = endpoint
        self._node_id = node_id
        self._private_key_path = private_key_path
        self._reconnect_min = reconnect_min_seconds
        self._reconnect_max = reconnect_max_seconds
        self._heartbeat_timeout = heartbeat_timeout_seconds
        self._on_assignment = on_assignment
        
        self._reconnect_delay = reconnect_min_seconds
        self._running = False
    
    async def connect_and_listen(self) -> None:
        """
        建立 SSE 连接并监听事件。
        
        此方法会持续运行，直到外部调用 stop()。
        连接断开时自动重连（指数退避）。
        """
        self._running = True
        
        while self._running:
            try:
                await self._connect_once()
                # 连接成功后重置延迟
                self._reconnect_delay = self._reconnect_min
            except Exception as exc:
                # 连接失败，计算重连延迟
                jitter = random.uniform(-0.2, 0.2)  # ±20%
                delay = self._reconnect_delay * (1 + jitter)
                
                if self._running:
                    await asyncio.sleep(delay)
                    
                    # 指数退避（限制上限）
                    self._reconnect_delay = min(
                        self._reconnect_delay * 2,
                        self._reconnect_max
                    )
    
    async def _connect_once(self) -> None:
        """单次 SSE 连接生命周期"""
        # 生成签名
        timestamp = int(datetime.now(timezone.utc).timestamp())
        nonce = uuid4().hex
        private_key = load_ed25519_private_key(self._private_key_path)
        signature = sign_message(
            private_key,
            node_id=self._node_id,
            timestamp=timestamp,
            nonce=nonce,
            payload=b"",
        )
        
        # 构建 URL
        url = f"{self._endpoint.rstrip('/')}/api/v1/node-agent/events"
        params = {
            "node_id": self._node_id,
            "timestamp": timestamp,
            "nonce": nonce,
            "signature": signature,
        }
        
        # 建立连接
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", url, params=params) as response:
                if response.status_code != 200:
                    raise ValueError(f"SSE connection failed: {response.status_code}")
                
                # 读取事件流
                last_data_time = time.time()
                async for message in self._parse_sse_stream(response.aiter_lines()):
                    last_data_time = time.time()
                    
                    # 处理事件
                    await self._handle_message(message)
                    
                    # 检查心跳超时
                    if time.time() - last_data_time > self._heartbeat_timeout:
                        raise TimeoutError("SSE heartbeat timeout")
    
    async def _parse_sse_stream(self, lines: AsyncIterator[str]) -> AsyncIterator[SSEMessage]:
        """解析 SSE 流为消息对象"""
        event = "message"
        data_lines = []
        msg_id = None
        retry = None
        
        async for line in lines:
            line = line.rstrip("\n\r")
            
            # 注释行（心跳）
            if line.startswith(":"):
                continue
            
            # 空行表示消息结束
            if not line:
                if data_lines:
                    yield SSEMessage(
                        event=event,
                        data="\n".join(data_lines),
                        id=msg_id,
                        retry=retry,
                    )
                
                # 重置状态
                event = "message"
                data_lines = []
                msg_id = None
                retry = None
                continue
            
            # 解析字段
            if ":" in line:
                field, _, value = line.partition(":")
                value = value.lstrip(" ")
                
                if field == "event":
                    event = value
                elif field == "data":
                    data_lines.append(value)
                elif field == "id":
                    msg_id = value
                elif field == "retry":
                    try:
                        retry = int(value)
                    except ValueError:
                        pass
    
    async def _handle_message(self, message: SSEMessage) -> None:
        """处理 SSE 消息"""
        if message.event == "connected":
            # 连接确认
            pass
        
        elif message.event == "assignment":
            # 有新任务分配
            if self._on_assignment:
                self._on_assignment()
        
        elif message.event == "error":
            # 错误事件
            try:
                error_data = json.loads(message.data)
                if not error_data.get("reconnect", True):
                    # 服务端要求不要重连（如节点被禁用）
                    self.stop()
            except (json.JSONDecodeError, KeyError):
                pass
    
    def stop(self) -> None:
        """停止 SSE 连接"""
        self._running = False
```

### 5.3 集成到 NodePoller

修改 `certman/node_agent/poller.py`:

```python
class NodePoller:
    def __init__(self, ..., prefer_sse: bool = False, sse_config: dict | None = None):
        # ... 现有字段 ...
        self._prefer_sse = prefer_sse
        self._sse_config = sse_config or {}
        self._sse_client: Optional[SSEClient] = None
        self._sse_task: Optional[asyncio.Task] = None
        self._assignment_event = asyncio.Event()
    
    async def start_sse_listener(self) -> None:
        """启动 SSE 监听器（后台任务）"""
        if not self._prefer_sse or self._private_key_path is None:
            return
        
        self._sse_client = SSEClient(
            endpoint=self._endpoint,
            node_id=self._node_id,
            private_key_path=self._private_key_path,
            reconnect_min_seconds=self._sse_config.get("reconnect_min_seconds", 3),
            reconnect_max_seconds=self._sse_config.get("reconnect_max_seconds", 30),
            heartbeat_timeout_seconds=self._sse_config.get("heartbeat_timeout_seconds", 60),
            on_assignment=self._on_sse_assignment,
        )
        
        self._sse_task = asyncio.create_task(self._sse_client.connect_and_listen())
    
    def _on_sse_assignment(self) -> None:
        """SSE 任务通知回调"""
        self._assignment_event.set()
    
    async def poll_async(self) -> list[dict]:
        """异步轮询（SSE 模式下等待事件或超时）"""
        if self._prefer_sse and self._sse_client:
            # 等待 SSE 通知或超时
            try:
                await asyncio.wait_for(
                    self._assignment_event.wait(),
                    timeout=30.0  # 超时后也轮询一次
                )
                self._assignment_event.clear()
            except asyncio.TimeoutError:
                pass
        
        # 执行实际轮询（poll 或 subscribe）
        return self.poll()  # 调用现有的同步 poll 方法
    
    def stop_sse_listener(self) -> None:
        """停止 SSE 监听器"""
        if self._sse_client:
            self._sse_client.stop()
        
        if self._sse_task:
            self._sse_task.cancel()
```

### 5.4 修改 agent.py

在 `certman/node_agent/agent.py` 中使用新的 prefer_sse 配置：

```python
poller = NodePoller(
    # ... 现有参数 ...
    prefer_subscribe=runtime.config.control_plane.prefer_subscribe,
    subscribe_wait_seconds=runtime.config.control_plane.subscribe_wait_seconds,
    # 新增
    prefer_sse=runtime.config.control_plane.prefer_sse,
    sse_config={
        "reconnect_min_seconds": runtime.config.control_plane.sse_reconnect_min_seconds,
        "reconnect_max_seconds": runtime.config.control_plane.sse_reconnect_max_seconds,
        "heartbeat_timeout_seconds": runtime.config.control_plane.sse_heartbeat_timeout_seconds,
    },
)

# 在 loop 模式下启动 SSE
if not once:
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(poller.start_sse_listener())
    
    # 使用异步轮询
    async def async_loop():
        while True:
            assignments = await poller.poll_async()
            # ... 处理逻辑 ...
    
    try:
        loop.run_until_complete(async_loop())
    finally:
        poller.stop_sse_listener()
        loop.close()
```

---

## 6. 回退策略

### 6.1 三层回退链

```python
# 伪代码
async def poll_with_fallback(poller: NodePoller) -> list[dict]:
    """带回退的轮询逻辑"""
    
    # 第一层：SSE（如果启用）
    if poller.prefer_sse:
        try:
            await poller.sse_client.connect_and_listen()
            # SSE 连接成功后会通过事件通知
            # 此处等待事件或超时
            await asyncio.wait_for(poller.assignment_event.wait(), timeout=30.0)
            poller.assignment_event.clear()
        except Exception:
            # SSE 失败，回退到 subscribe
            pass
    
    # 第二层：Subscribe（长轮询）
    if poller.prefer_subscribe:
        assignments = poller._subscribe(payload)
        if assignments is not None:  # 404 表示不支持 subscribe
            return assignments
    
    # 第三层：Poll（短轮询）
    return poller._poll(payload)
```

### 6.2 配置示例

```toml
# 推荐配置（SSE 优先）
[control_plane]
endpoint = "http://certman-server:8000"
prefer_sse = true
prefer_subscribe = true  # 作为回退
poll_interval_seconds = 30

# 保守配置（仅长轮询）
[control_plane]
endpoint = "http://certman-server:8000"
prefer_sse = false
prefer_subscribe = true
subscribe_wait_seconds = 25

# 最小配置（仅短轮询）
[control_plane]
endpoint = "http://certman-server:8000"
prefer_sse = false
prefer_subscribe = false
poll_interval_seconds = 10
```

---

## 7. 集成测试策略

### 7.1 单元测试

**测试 SSEEventBus**:

```python
# tests/test_sse_event_bus.py

import asyncio
import pytest
from certman.node_agent.sse_event_bus import SSEEventBus, SSEEvent

@pytest.mark.asyncio
async def test_register_client():
    bus = SSEEventBus()
    client = await bus.register_client("node-a")
    assert client.node_id == "node-a"
    assert client.queue.qsize() == 0

@pytest.mark.asyncio
async def test_replace_existing_connection():
    bus = SSEEventBus()
    client1 = await bus.register_client("node-a")
    client2 = await bus.register_client("node-a")
    
    # 旧连接应该收到关闭信号
    event = await client1.queue.get()
    assert event is None
    
    # 新连接正常
    assert client2.queue.qsize() == 0

@pytest.mark.asyncio
async def test_notify_assignments():
    bus = SSEEventBus()
    client_a = await bus.register_client("node-a")
    client_b = await bus.register_client("node-b")
    
    # 定向通知
    count = await bus.notify_assignments_updated(["node-a"])
    assert count == 1
    
    event = await asyncio.wait_for(client_a.queue.get(), timeout=1.0)
    assert event.event == "assignment"
    
    # node-b 不应收到通知
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(client_b.queue.get(), timeout=0.1)
    
    # 广播通知
    count = await bus.notify_assignments_updated()
    assert count == 2
```

**测试 SSE 客户端解析**:

```python
# tests/test_sse_client.py

import pytest
from certman.node_agent.sse_client import SSEClient, SSEMessage

@pytest.mark.asyncio
async def test_parse_sse_message():
    lines = [
        "event: connected",
        "data: {\"node_id\": \"node-a\"}",
        "",
    ]
    
    async def line_generator():
        for line in lines:
            yield line
    
    client = SSEClient(
        endpoint="http://localhost:8000",
        node_id="node-a",
        private_key_path=Path("test.pem"),
    )
    
    messages = [msg async for msg in client._parse_sse_stream(line_generator())]
    assert len(messages) == 1
    assert messages[0].event == "connected"
    assert messages[0].data == '{"node_id": "node-a"}'
```

### 7.2 集成测试

**Mock SSE 服务端**:

```python
# tests/test_sse_integration.py

import asyncio
from fastapi.testclient import TestClient
from certman.main import app

def test_sse_endpoint_authentication():
    """测试 SSE 端点的认证机制"""
    client = TestClient(app)
    
    # 无签名 -> 401
    response = client.get("/api/v1/node-agent/events?node_id=node-a")
    assert response.status_code == 422  # 缺少必需参数
    
    # 错误签名 -> 401
    response = client.get(
        "/api/v1/node-agent/events",
        params={
            "node_id": "node-a",
            "timestamp": 1234567890,
            "nonce": "test",
            "signature": "invalid",
        }
    )
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_sse_event_flow():
    """测试完整的 SSE 事件流"""
    # 1. 建立 SSE 连接（后台任务）
    # 2. 创建任务
    # 3. 验证客户端收到 assignment 事件
    # 4. 调用 poll 获取任务详情
    # 5. 关闭连接
    pass  # 详细实现略
```

### 7.3 性能测试

```python
# tests/test_sse_performance.py

@pytest.mark.asyncio
async def test_concurrent_connections():
    """测试同时 100 个 SSE 连接的性能"""
    bus = SSEEventBus()
    
    # 注册 100 个客户端
    clients = [
        await bus.register_client(f"node-{i}")
        for i in range(100)
    ]
    
    # 广播通知
    start = time.time()
    await bus.notify_assignments_updated()
    duration = time.time() - start
    
    # 通知应在 100ms 内完成
    assert duration < 0.1
    
    # 验证每个客户端都收到通知
    for client in clients:
        event = await asyncio.wait_for(client.queue.get(), timeout=1.0)
        assert event.event == "assignment"
```

---

## 8. 部署与运维

### 8.1 配置迁移

**迁移路径**（分阶段启用）:

1. **阶段 1**: 部署服务端 SSE 端点（`prefer_sse=false`，仅提供能力）
2. **阶段 2**: 小范围试点（少量节点设置 `prefer_sse=true`）
3. **阶段 3**: 全量启用（所有节点 `prefer_sse=true`）
4. **未来**: 移除 poll 端点支持（破坏性变更，需要 major 版本升级）

### 8.2 监控指标

**服务端指标**:
- `certman_sse_connections_total{node_id}`: 当前 SSE 连接数
- `certman_sse_events_sent_total{event_type}`: 发送的事件计数
- `certman_sse_connection_duration_seconds`: 连接持续时间

**客户端指标**:
- `certman_agent_sse_reconnects_total`: 重连次数
- `certman_agent_sse_events_received_total{event_type}`: 收到的事件计数
- `certman_agent_poll_latency_seconds{method}`: 轮询延迟（sse/subscribe/poll）

### 8.3 故障处理

**常见问题**:

1. **连接频繁断开**
   - 检查网络稳定性 & 防火墙超时设置
   - 增加心跳频率（降低 `heartbeat_interval`）
   - 检查 nginx/LB 是否有缓冲配置（`X-Accel-Buffering: no`）

2. **节点收不到事件**
   - 检查服务端 `notify_assignments_updated` 是否正确调用
   - 验证 `node_id` 匹配
   - 检查客户端是否正常连接（查看 `connected` 事件）

3. **内存泄漏**
   - 确保 `unregister_client` 正确调用
   - 检查队列是否无限增长（限制 `max_queue_size`）
   - 启用清理任务（`_cleanup_loop`）

---

## 9. 依赖清单

**新增依赖**: 无（使用现有库）

**现有依赖**:
- `httpx >= 0.27.0` (已有，用于 SSE 客户端 streaming)
- `fastapi >= 0.115.0` (已有，用于 StreamingResponse)
- `asyncio` (Python 标准库)

**可选依赖**（未来优化）:
- `sse-starlette` - 社区维护的 SSE 工具库（如果需要更丰富的功能）
- `websockets` - 如果未来升级到 WebSocket（双向通信）

---

## 10. 后续优化方向

### 10.1 分布式部署支持

当前设计基于单进程内存队列，未来可扩展：

1. **Redis Pub/Sub**
   ```python
   # 服务端发布事件到 Redis
   await redis.publish(f"certman:events:{node_id}", json.dumps(event))
   
   # SSE 端点订阅 Redis 频道
   async for message in redis.subscribe(f"certman:events:{node_id}"):
       yield _format_sse_event(message)
   ```

2. **消息队列**（RabbitMQ/Kafka）
   - 适用于高吞吐场景（>1000 节点）
   - 支持事件持久化和重放

### 10.2 WebSocket 升级

SSE 是单向推送，未来可升级为 WebSocket 支持双向通信：

```python
@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await websocket.accept()
    
    # 双向通信：服务端推送 + 客户端发送心跳
    async def send_loop():
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    
    async def recv_loop():
        while True:
            data = await websocket.receive_json()
            # 处理客户端消息（如心跳确认）
    
    await asyncio.gather(send_loop(), recv_loop())
```

### 10.3 事件过滤与订阅

允许节点订阅特定类型的事件：

```
GET /api/v1/node-agent/events?node_id=...&events=assignment,update
```

---

## 11. 检查清单

### 11.1 服务端实现

- [ ] `certman/node_agent/sse_event_bus.py` - SSE 事件总线
- [ ] `certman/api/routes/node_agent.py` - `/events` 端点
- [ ] `certman/services/job_service.py` - 集成事件通知
- [ ] `certman/config.py` - 新增 SSE 配置字段

### 11.2 客户端实现

- [ ] `certman/node_agent/sse_client.py` - SSE 客户端
- [ ] `certman/node_agent/poller.py` - 集成 SSE 和回退逻辑
- [ ] `certman/node_agent/agent.py` - 使用新配置

### 11.3 测试

- [ ] `tests/test_sse_event_bus.py` - 事件总线单元测试
- [ ] `tests/test_sse_client.py` - SSE 客户端单元测试
- [ ] `tests/test_sse_integration.py` - 端到端集成测试
- [ ] `tests/test_sse_performance.py` - 性能和并发测试

### 11.4 文档

- [ ] `docs/en/api-access.md` - 更新 API 文档
- [ ] `docs/zh-CN/api-access.md` - 中文 API 文档
- [ ] `docs/en/quickguide-layered.md` - 更新快速指南
- [ ] `docs/zh-CN/quickguide-layered.md` - 中文快速指南
- [ ] `README.md` - 更新功能列表

### 11.5 部署

- [ ] 更新 `docker-compose.yml` 示例配置
- [ ] 更新 K8s 部署 YAML
- [ ] 更新迁移指南（v0.1.0 → v0.1.1）

---

## 12. 时间估算

| 任务 | 工时估算 | 优先级 |
|------|----------|--------|
| 服务端事件总线实现 | 4h | P1 |
| SSE 路由端点实现 | 3h | P1 |
| SSE 客户端实现 | 5h | P1 |
| Poller 集成与回退逻辑 | 3h | P1 |
| 单元测试 | 4h | P1 |
| 集成测试 | 3h | P1 |
| 文档更新 | 2h | P2 |
| 性能测试与调优 | 2h | P2 |
| **总计** | **26h** | - |

---

## 13. 风险与限制

### 13.1 已知限制

1. **单进程部署限制**
   - 当前设计基于内存队列，多实例部署时需要引入 Redis/MQ
   - 解决方案：文档中明确说明，未来版本提供分布式支持

2. **连接数限制**
   - FastAPI/uvicorn 默认最大并发连接数（可通过 `--limit-concurrency` 调整）
   - 建议：单实例支持 <1000 SSE 连接（足够大部分场景）

3. **网络环境限制**
   - 部分企业防火墙/代理可能限制 SSE 长连接
   - 缓解：提供回退到 subscribe/poll 的能力

### 13.2 潜在风险

1. **异步编程复杂度**
   - 引入 asyncio 可能增加代码复杂度
   - 缓解：保持同步 API 向后兼容，asyncio 仅在 SSE 部分使用

2. **测试覆盖不足**
   - SSE 流式响应较难测试
   - 缓解：使用 `httpx.AsyncClient` 进行端到端测试

---

## 附录

### A. 相关标准

- [Server-Sent Events (SSE) - W3C Specification](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [WHATWG Fetch API - Streaming](https://fetch.spec.whatwg.org/#concept-body-consume-body)

### B. 参考实现

- FastAPI SSE: https://github.com/sysid/sse-starlette
- MDN SSE Guide: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events

### C. 配置示例

见 `docs/en/cookbook-sse.md` （后续创建）

---

**设计审查**: [待填写]  
**实现负责人**: [待分配]  
**预计发布版本**: v0.1.1  
**设计状态**: ✅ 已完成
