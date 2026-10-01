# 服务端 API 详解

> 覆盖本模组的**自定义指令**（服务端设置读写）与**设置事件**。本模组不提供客户端指令。
> 指令定义文件位于 `behavior_pack/netease_commands/`，处理逻辑位于
> `behavior_pack/Script_NeteaseModY4HZxOgU/modServer.py`。

## 功能概述

本模组的染色配方由**服务端**在世界加载时按开关注册，因此所有设置项都是**服务端全局设置**：

- 存储于存档（ExtraData，键 `ReinforcedGlassSettings`），重进世界保留；
- 仅**管理员（操作员/自定义权限档，`GetPlayerOperation() >= 2`）**可读写；
- 配方开关的改动**需重启世界生效**（配方仅在加载时注册一次，无运行时移除接口）。

设置项既可在**游戏内指令**中读写，也可在 **CardRegistry 前置模组的设置界面**中操作
（暂停菜单 → 模组设置 → 防爆玻璃），两者读写的是同一份服务端权威数据。

## 指令定义

| 指令 | 说明 | 权限等级 |
|------|------|----------|
| `reinforced_glass_set` | 修改服务端设置项 | `game_directors` |
| `reinforced_glass_get` | 查询服务端设置项 | `game_directors` |
| `reinforced_glass_reset` | 重置服务端设置项 | `game_directors` |
| `reinforced_glass_list` | 列出全部设置键及当前值 | `game_directors` |

> 所有指令均**仅作用于服务端设置**，不存在 `_client_` 后缀的客户端指令。
> 指令在代码层校验管理员权限：带触发者（玩家）时非管理员一律拒绝；
> 命令方块/控制台无触发者，不做该校验。

## 参数

### 通用参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| 键 | str | 设置键，形如 `reinforced_glass.server.<中间卡片id>.<设置项>` |
| 值 | str | 设置值，本模组设置项均为开关，取 `true` / `false`（亦接受 `1/0`、`on/off`、`yes/no`） |
| 目标 | target | 明细回显目标，默认 `@s`（仅影响回显，不影响写入结果） |
| 页码 | int | `reinforced_glass_list` 的页码，默认 `1` |

### reinforced_glass_set

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| 键 | str | `""` | 待修改的设置键 |
| 值 | str | `""` | 目标值（`true` / `false`） |
| 目标 | target | `@s` | 回显目标 |

### reinforced_glass_get

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| 键 | str | `""` | 待查询的设置键 |
| 目标 | target | `@s` | 回显目标 |

### reinforced_glass_reset

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| 键 | str | `""` | 设置键**或分组前缀**：`server` / `server.<中间卡片id>` / 完整设置键 |
| 目标 | target | `@s` | 回显目标 |

### reinforced_glass_list

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| 页码 | int | `1` | 每页 10 条 |
| 目标 | target | `@s` | 回显目标 |

## 使用示例

```text
# 列出全部设置键及当前值
/reinforced_glass_list

# 关闭防爆玻璃的染色配方（重启世界后生效）
/reinforced_glass_set reinforced_glass.server.rg_recipe.enable_recipe_blast_glass false

# 查询某个设置项
/reinforced_glass_get reinforced_glass.server.rg_recipe.enable_recipe_blast_glass

# 重置整个「配方」分组为默认值（两个系列恢复开启）
/reinforced_glass_reset reinforced_glass.server.rg_recipe

# 重置全部服务端设置
/reinforced_glass_reset reinforced_glass.server

# 把明细回显给指定玩家（不影响写入结果，写入始终是全局的）
/reinforced_glass_list 1 @a
```

## 设置键表

键前缀固定为 `reinforced_glass.`，中间卡片 id 与设置界面中的分组一一对应。

| 完整键 | 默认值 | 说明 |
|--------|--------|------|
| `reinforced_glass.server.rg_recipe.enable_recipe_blast_glass` | `true` | 开启防爆玻璃染色配方 |
| `reinforced_glass.server.rg_recipe.enable_recipe_tempered_glass` | `true` | 开启钢化玻璃染色配方 |
| `reinforced_glass.server.rg_debug.debug_mode` | `false` | 在控制台输出服务端调试日志 |

## 处理流程

1. `ReinforcedGlassServerSystem` 监听引擎事件 `CustomCommandTriggerServerEvent`。
2. 指令名不在本模组指令表中 → **静默返回**（多模组共存约定，不设置任何返回字段）。
3. 解析参数（按 `name` 匹配：键 / 值 / 目标 / 页码）。
4. **鉴权**：有触发者（玩家）时，`GetPlayerOperation() < 2` 直接返回
   `commands.reinforced_glass.no_permission`；命令方块/控制台无触发者，不做该校验。
5. 键前缀不以 `reinforced_glass.` 开头 → 静默返回。
6. 按动作执行：`set` / `get` / `reset` / `list`，写入后持久化并向**全服广播**同步事件
   （命令路径同时向目标玩家发送 tellraw 明细；无玩家时输出到服务端日志）。

### 返回消息键

| 消息键 | 触发时机 |
|--------|----------|
| `commands.reinforced_glass.set.ok` | 设置写入成功 |
| `commands.reinforced_glass.get.ok` | 查询成功 |
| `commands.reinforced_glass.reset.ok` | 重置成功 |
| `commands.reinforced_glass.list.ok` | 列表输出成功 |
| `commands.reinforced_glass.unknown_key` | 键或前缀不存在 |
| `commands.reinforced_glass.bad_value` | 值格式不合法 |
| `commands.reinforced_glass.no_permission` | 非管理员调用 |

> 消息文案定义在资源包 `texts/zh_CN.lang`、`texts/zh_TW.lang`、`texts/en_US.lang`。

## 事件

自定义事件用于「设置界面 ↔ 服务端」互通，外部模组一般无需监听。

| 事件名 | 方向 | 数据 | 说明 |
|--------|------|------|------|
| `Script_NeteaseModY4HZxOgU_RequestSetting` | 客户端 → 服务端 | `{playerId}` | 客户端请求当前权威设置与自身 OP 状态 |
| `Script_NeteaseModY4HZxOgU_SettingChange` | 客户端 → 服务端 | `{playerId, key, value}` | 设置界面开关变更，服务端鉴权后写入 |
| `Script_NeteaseModY4HZxOgU_SettingSync` | 服务端 → 客户端 | `{values, is_op}` | 下发权威设置值与该玩家的 OP 状态（用于锁定 UI） |

服务端系统名：`Script_NeteaseModY4HZxOgU` / `ReinforcedGlassServerSystem`
客户端系统名：`ReinforcedGlassClient` / `ReinforcedGlassClientSystem`

## 与前置模组（CardRegistry）的关系

- 设置界面由前置模组提供，本模组在 `UiInitFinished` 中**延迟导入**并注册卡片；
  前置未安装时整体跳过，指令与配方功能不受影响。
- 指令路径**不依赖前置**，可在未安装前置的环境下正常使用。
- 非管理员在设置界面中的开关会显示为锁定状态，无法切换。