# 错误熔断器集成说明

## 已实现的功能

### 1. 错误熔断 (`modules/error_circuit.py`)
- 连续错误阈值：3 次
- 最大重试次数：5 次
- 触发熔断后暂停所有任务
- 缓存失败任务信息

### 2. 用户通知 (`modules/error_notifier.py`)
- 通过 TG 机器人发送错误通知
- 包含失败任务列表和可能原因
- 提供恢复命令说明

### 3. 用户命令
在 `main.py` 中已添加以下命令处理：

| 命令 | 功能 |
|------|------|
| `/cache_status` | 查看缓存的任务状态 |
| `/resume` | 恢复所有缓存任务 |
| `/clear_cache` | 清除缓存并重置系统 |

### 4. Bot 命令菜单
已更新 Bot 命令菜单，包含新增的三个命令。

## 集成步骤

### 步骤 1：在 main.py 中初始化熔断器

在 `main()` 函数中，找到以下位置（大约 11660 行）：

```python
# 初始化 Web 任务管理器集成
try:
    from modules.web_task_manager import get_task_manager
    from modules.web_integration import init_web_integration
    from modules.task_persistence import init_persistence
    from modules.task_recovery import init_recovery

    # 初始化持久化管理器
    persistence = init_persistence("/app/db/tasks.json")
    logger.info("✅ 任务持久化已初始化")

    # 初始化 Web 任务管理器
    task_manager = get_task_manager()
    init_web_integration(bot, task_manager)
    logger.info("✅ Web 任务管理器集成已初始化")

    # 初始化恢复管理器
    recovery = init_recovery(bot)
    await recovery.start()
    logger.info("✅ 任务恢复管理器已启动")
except Exception as e:
    logger.warning(f"⚠️ Web 任务管理器集成失败：{e}")
```

在这段代码之后，添加熔断器初始化：

```python
# 初始化熔断器
try:
    from modules.error_circuit import init_circuit_breaker
    circuit = init_circuit_breaker("/app/db/circuit_cache.json")
    logger.info("✅ 错误熔断器已初始化")
except Exception as e:
    logger.warning(f"⚠️ 熔断器初始化失败：{e}")
```

### 步骤 2：在下载失败时记录错误

在 `_process_download_async` 方法中，找到下载失败的处理位置（搜索 `下载失败` 或 `error_msg`），添加：

```python
# 记录到熔断器
try:
    from modules.error_circuit import get_circuit_breaker
    from modules.error_notifier import get_error_notifier
    
    circuit = get_circuit_breaker()
    
    # 生成任务 ID
    task_id = f"tg_{chat_id}_{status_message.message_id}"
    
    # 记录错误
    triggered = circuit.record_error(
        task_id=task_id,
        url=url,
        title=url[:50],
        error_message=error_msg,
        retry_count=0,
    )
    
    # 如果触发熔断，通知用户
    if triggered:
        notifier = get_error_notifier(self)
        if not circuit.state.user_notified:
            # 发送通知
            cached_tasks = [t.to_dict() for t in circuit.get_cached_tasks()]
            await notifier.notify_circuit_break(
                user_id=chat_id,
                cached_tasks=cached_tasks,
                continuous_errors=circuit.continuous_errors,
            )
            circuit.mark_user_notified()
except Exception as e:
    logger.debug(f"熔断器记录失败：{e}")
```

### 步骤 3：在下载成功时重置熔断器

在下载成功的处理位置，添加：

```python
# 重置熔断器连续错误计数
try:
    from modules.error_circuit import get_circuit_breaker
    circuit = get_circuit_breaker()
    circuit.record_success()
except Exception as e:
    logger.debug(f"熔断器重置失败：{e}")
```

## 使用流程

1. **正常运行**：熔断器处于 `closed` 状态，下载正常进行。

2. **连续失败**：当连续 3 次下载失败时：
   - 熔断器切换到 `open` 状态
   - 暂停所有下载任务
   - 发送通知给用户

3. **用户确认**：
   - 用户收到通知消息
   - 检查网络和代理配置
   - 发送 `/resume` 命令恢复下载
   - 或发送 `/clear_cache` 清除缓存

4. **查看状态**：
   - 发送 `/cache_status` 查看缓存的任务详情
   - 发送 `/status` 查看整体下载统计

## 配置文件

熔断器状态保存在 `/app/db/circuit_cache.json`，包含：
- 熔断器状态
- 缓存的任务列表
- 暂停的任务 ID 列表
- 用户通知状态
