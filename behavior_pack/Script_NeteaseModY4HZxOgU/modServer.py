# -*- coding: utf-8 -*-
"""防爆玻璃 / 钢化玻璃 · 服务端脚本

动态注册两个系列的染色配方：8 个环形玻璃 + 中心 1 个染料 → 8 个对应颜色的玻璃。

- 环形材料：同系列的基础玻璃，或同系列其它颜色的玻璃（同色环跳过）
- 染料：16 种染料；黑/蓝/棕/白额外接受墨囊、青金石、可可豆、骨粉
- 配方数量：每个系列 320 条（16 产物 × 16 环形 × 平均 1.25 种染料），两个系列共 640 条

注册时机：脚本初始化时注册，此时客户端尚未连接，配方随初始数据一起下发。
不能等玩家加入（AddServerPlayerEvent）再注册——那时服务端会在客户端还没进入世界时
推送 CraftingDataPacket，客户端会断言 "Level is not usable" 崩溃。

两个系列各有独立的开关（服务端全局设置，仅 OP 可改，改动需重启世界生效），关闭后
该系列不再注册染色配方。开关由客户端脚本（modClient.py）接入 CardRegistry 前置后展示。
"""

import mod.server.extraServerApi as serverApi

ServerSystem = serverApi.GetServerSystemCls()

engineNamespace = serverApi.GetEngineNamespace()
engineSystemName = serverApi.GetEngineSystemName()

# 方块系列，与 behavior_pack/netease_blocks/<系列>/ 目录同名
SERIES = ["blast_glass", "tempered_glass"]

# ==================== 设置项定义（服务端全局） ====================
MAIN_CARD_ID = "reinforced_glass"
# 中间卡片 id（须与 modClient.py 一致）
MID_RECIPE = "rg_recipe"
MID_DEBUG = "rg_debug"

# 系列 -> 染色配方开关名；关闭后该系列不再注册染色配方，改动需重启世界生效
SERIES_SETTING_KEYS = {
    "blast_glass": "enable_recipe_blast_glass",
    "tempered_glass": "enable_recipe_tempered_glass",
}

# 设置键表：schema 键（server.<中间卡片id>.<设置项>）-> 默认值
# 本模组设置项均为开关（bool）
SETTING_VALUE_SCHEMA = {
    "server.%s.enable_recipe_blast_glass" % MID_RECIPE: True,
    "server.%s.enable_recipe_tempered_glass" % MID_RECIPE: True,
    "server.%s.debug_mode" % MID_DEBUG: False,
}
DEFAULT_SETTINGS = dict((k.split(".")[-1], v) for k, v in SETTING_VALUE_SCHEMA.items())

# 各分组的设置键（用于按前缀重置）
GROUP_DEFAULT_KEYS = {
    MID_RECIPE: [k.split(".")[-1] for k in sorted(SETTING_VALUE_SCHEMA)
                 if k.startswith("server.%s." % MID_RECIPE)],
    MID_DEBUG: [k.split(".")[-1] for k in sorted(SETTING_VALUE_SCHEMA)
                if k.startswith("server.%s." % MID_DEBUG)],
}

# 服务端权威设置存储键（存档 ExtraData）
SETTINGS_STORE_KEY = "ReinforcedGlassSettings"
# 指令键前缀：完整键形如 reinforced_glass.server.<中间卡片id>.<设置项>
FULL_KEY_PREFIX = MAIN_CARD_ID + "."

# 与客户端（modClient.py）约定的事件名
CLIENT_NAMESPACE = "ReinforcedGlassClient"
CLIENT_SYSTEM = "ReinforcedGlassClientSystem"
SETTING_CHANGE_EVENT = "Script_NeteaseModY4HZxOgU_SettingChange"
REQUEST_SETTING_EVENT = "Script_NeteaseModY4HZxOgU_RequestSetting"
SETTING_SYNC_EVENT = "Script_NeteaseModY4HZxOgU_SettingSync"

# 颜色标识 -> 可用染料列表（第一个为主染料，其余为等价替代品）
COLOR_DYES = [
    ("black", ["minecraft:black_dye", "minecraft:ink_sac"]),
    ("blue", ["minecraft:blue_dye", "minecraft:lapis_lazuli"]),
    ("brown", ["minecraft:brown_dye", "minecraft:cocoa_beans"]),
    ("cyan", ["minecraft:cyan_dye"]),
    ("gray", ["minecraft:gray_dye"]),
    ("green", ["minecraft:green_dye"]),
    ("light_blue", ["minecraft:light_blue_dye"]),
    ("lime", ["minecraft:lime_dye"]),
    ("magenta", ["minecraft:magenta_dye"]),
    ("orange", ["minecraft:orange_dye"]),
    ("pink", ["minecraft:pink_dye"]),
    ("purple", ["minecraft:purple_dye"]),
    ("red", ["minecraft:red_dye"]),
    ("silver", ["minecraft:light_gray_dye"]),
    ("white", ["minecraft:white_dye", "minecraft:bone_meal"]),
    ("yellow", ["minecraft:yellow_dye"]),
]


def glass_id(series, color=None):
    # type: (str, str) -> str
    """color 为 None 时取该系列的基础玻璃"""
    if color is None:
        return "reinforced_glass:%s" % series
    return "reinforced_glass:%s_%s" % (color, series)


def build_dyeing_recipe(series, out_color, ring_color, dye_item):
    # type: (str, str, str, str) -> dict
    ring_label = ring_color if ring_color else series
    return {
        "minecraft:recipe_shaped": {
            "description": {
                "identifier": "reinforced_glass:%s_%s_from_%s_%s"
                % (series, out_color, ring_label, dye_item.split(":")[1])
            },
            "tags": ["crafting_table"],
            "pattern": ["III", "IEI", "III"],
            "key": {
                "I": {"item": glass_id(series, ring_color), "data": 0},
                "E": {"item": dye_item, "data": 0},
            },
            "result": {"item": glass_id(series, out_color), "data": 0, "count": 8},
        }
    }


def _CoerceBool(value):
    # type: (object) -> bool or None
    """把指令/设置界面传入的值解析为 bool；无法识别返回 None。"""
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("true", "1", "on", "yes", "t"):
        return True
    if s in ("false", "0", "off", "no", "f"):
        return False
    return None


class ReinforcedGlassServerSystem(ServerSystem):
    def __init__(self, namespace, systemName):
        super(ReinforcedGlassServerSystem, self).__init__(namespace, systemName)
        # 服务端权威设置：需先于配方注册读取，关闭的系列不注册
        self.settings = self.LoadSettings()
        self.recipesRegistered = self.RegisterDyeingRecipes()
        if not self.recipesRegistered:
            # 兜底：关卡尚未就绪时，等客户端加载完成再补注册
            self.ListenForEvent(
                engineNamespace,
                engineSystemName,
                "ClientLoadAddonsFinishServerEvent",
                self,
                self.OnClientLoadAddonsFinish,
            )
        # 客户端（modClient.py）读写设置项
        self.ListenForEvent(CLIENT_NAMESPACE, CLIENT_SYSTEM,
                            SETTING_CHANGE_EVENT, self, self.OnSettingChange)
        self.ListenForEvent(CLIENT_NAMESPACE, CLIENT_SYSTEM,
                            REQUEST_SETTING_EVENT, self, self.OnRequestSetting)
        # 自定义指令：读写服务端设置（不依赖前置，支持命令方块）
        self.ListenForEvent(engineNamespace, engineSystemName,
                            "CustomCommandTriggerServerEvent", self, self.OnCustomCommand)

    def OnClientLoadAddonsFinish(self, args):
        if not self.recipesRegistered:
            self.recipesRegistered = self.RegisterDyeingRecipes()

    def _DebugPrint(self, message):
        """调试日志：仅当 debug_mode 开启时输出到服务端控制台。"""
        if self.settings.get("debug_mode", False):
            print "[reinforced_glass调试] " + message

    # ==================== 设置项：持久化 / 鉴权 / 同步 ====================

    def _GetExtraDataComp(self):
        levelId = serverApi.GetLevelId()
        if levelId is None:
            return None
        try:
            return serverApi.GetEngineCompFactory().CreateExtraData(levelId)
        except Exception:
            return None

    def LoadSettings(self):
        # type: () -> dict
        """读取存档中的服务端设置；无存档值时使用默认值。"""
        settings = dict(DEFAULT_SETTINGS)
        extraComp = self._GetExtraDataComp()
        if extraComp:
            try:
                saved = extraComp.GetExtraData(SETTINGS_STORE_KEY)
                if isinstance(saved, dict):
                    for key in settings:
                        if isinstance(saved.get(key), bool):
                            settings[key] = saved[key]
            except Exception:
                pass
        return settings

    def SaveSettings(self):
        extraComp = self._GetExtraDataComp()
        if extraComp:
            try:
                extraComp.SetExtraData(SETTINGS_STORE_KEY, self.settings)
                extraComp.SaveExtraData()
            except Exception:
                pass

    def IsOperator(self, playerId):
        """权限档 >= 2（操作员/自定义）视为管理员。"""
        if not playerId:
            return False
        try:
            playerComp = serverApi.GetEngineCompFactory().CreatePlayer(playerId)
            return playerComp.GetPlayerOperation() >= 2
        except Exception:
            return False

    def SyncSettingToPlayer(self, playerId):
        """向单个玩家下发权威开关值 + 其自身 OP 状态（用于 UI 锁定）。"""
        if not playerId:
            return
        self.NotifyToClient(playerId, SETTING_SYNC_EVENT, {
            "values": self.settings,
            "is_op": self.IsOperator(playerId),
        })

    def BroadcastSetting(self):
        for pid in serverApi.GetPlayerList():
            self.SyncSettingToPlayer(pid)

    def OnRequestSetting(self, args):
        self.SyncSettingToPlayer(args.get("playerId"))

    def OnSettingChange(self, args):
        """前置设置界面开关回调：仅 OP 可改，改后持久化并广播全服。"""
        playerId = args.get("playerId")
        key = args.get("key")
        if key not in DEFAULT_SETTINGS:
            return
        if not self.IsOperator(playerId):
            # 非 OP 修改被忽略，回发权威值以纠正其 UI
            self.SyncSettingToPlayer(playerId)
            return
        ok, _value = self.ApplySetting(key, args.get("value"), source="setting_ui")
        if ok:
            self.BroadcastSetting()

    def ApplySetting(self, item, value, source="command"):
        """单一写入入口：按设置项名写入服务端存储。返回 (是否成功, 规范值/失败原因)。"""
        if item not in DEFAULT_SETTINGS:
            return False, "unknown"
        parsed = _CoerceBool(value)
        if parsed is None:
            return False, "bad_bool"
        self.settings[item] = parsed
        self.SaveSettings()
        self._DebugPrint("设置由%s更新：%s = %s" % (source, item, parsed))
        return True, parsed

    # ==================== 自定义指令（服务端设置，仅管理员） ====================

    LIST_PAGE_SIZE = 10  # reinforced_glass_list 每页条数

    def OnCustomCommand(self, args):
        """处理 /reinforced_glass_set|get|reset|list 自定义指令。

        非本模组指令一律静默返回（多模组共存约定）。
        """
        action = self.COMMAND_ACTIONS.get(args.get("command"))
        if action is None:
            return
        argMap = {}
        for a in args.get("args", []) or []:
            if isinstance(a, dict):
                argMap[a.get("name")] = a.get("value")
        origin = args.get("origin") or {}
        playerId = origin.get("entityId")

        # 服务端设置：全部动作（含查询）均需管理员；命令方块/控制台无触发者，不做校验
        if playerId and not self.IsOperator(playerId):
            args["return_failed"] = True
            args["return_msg_key"] = "commands.reinforced_glass.no_permission"
            return

        targets = self._CommandTargets(playerId, argMap.get("目标"))

        if action == "list":
            self._Echo(targets, self._BuildSettingList(argMap))
            args["return_msg_key"] = "commands.reinforced_glass.list.ok"
            return

        fullKey = str(argMap.get("键", "") or "")
        if not fullKey.startswith(FULL_KEY_PREFIX):
            return  # 静默：非本模组设置键
        rest = fullKey[len(FULL_KEY_PREFIX):]  # server.<中间卡片id>.<设置项>

        if action == "set":
            item = self._ItemOfKey(rest)
            if item is None:
                args["return_failed"] = True
                args["return_msg_key"] = "commands.reinforced_glass.unknown_key"
                return
            ok, res = self.ApplySetting(item, argMap.get("值"), source="command")
            if not ok:
                args["return_failed"] = True
                args["return_msg_key"] = "commands.reinforced_glass.bad_value"
                self._Echo(targets, "[防爆玻璃] 值格式不合法：%s 需要 true/false" % item)
                return
            self.BroadcastSetting()
            self._Echo(targets, "[防爆玻璃] %s = %s" % (fullKey, res))
            args["return_msg_key"] = "commands.reinforced_glass.set.ok"
            return

        if action == "get":
            item = self._ItemOfKey(rest)
            if item is None:
                args["return_failed"] = True
                args["return_msg_key"] = "commands.reinforced_glass.unknown_key"
                return
            self._Echo(targets,
                       "[防爆玻璃] %s = %s" % (fullKey, self.settings.get(item)))
            args["return_msg_key"] = "commands.reinforced_glass.get.ok"
            return

        if action == "reset":
            items = self._ItemsOfPrefix(rest)
            if not items:
                args["return_failed"] = True
                args["return_msg_key"] = "commands.reinforced_glass.unknown_key"
                return
            for item in items:
                self.ApplySetting(item, SETTING_VALUE_SCHEMA[self._SchemaKey(item)],
                                  source="command_reset")
            self.BroadcastSetting()
            self._Echo(targets, "[防爆玻璃] 已重置 %d 项" % len(items))
            args["return_msg_key"] = "commands.reinforced_glass.reset.ok"
            return

    # 指令名 -> 动作
    COMMAND_ACTIONS = {
        "reinforced_glass_set": "set",
        "reinforced_glass_get": "get",
        "reinforced_glass_reset": "reset",
        "reinforced_glass_list": "list",
    }

    def _SchemaKey(self, item):
        """设置项名 -> schema 键（server.<中间卡片id>.<设置项>）。"""
        for key in SETTING_VALUE_SCHEMA:
            if key.split(".")[-1] == item:
                return key
        return None

    def _ItemOfKey(self, rest):
        """完整键去掉前缀后的 rest（server.<中间卡片id>.<设置项>）-> 设置项名；不合法返回 None。"""
        if rest not in SETTING_VALUE_SCHEMA:
            return None
        return rest.split(".")[-1]

    def _ItemsOfPrefix(self, rest):
        """按前缀取设置项名列表：支持 server / server.<中间卡片id> / 完整 schema 键。"""
        if rest in SETTING_VALUE_SCHEMA:
            return [rest.split(".")[-1]]
        matched = [k.split(".")[-1] for k in sorted(SETTING_VALUE_SCHEMA)
                   if k.startswith(rest + ".")]
        return matched

    def _BuildSettingList(self, argMap):
        """列出全部设置键与当前值（分页）。"""
        items = sorted("%s%s = %s" % (FULL_KEY_PREFIX, k, self.settings.get(k.split(".")[-1]))
                       for k in SETTING_VALUE_SCHEMA)
        try:
            page = int(argMap.get("页码") or 1)
        except Exception:
            page = 1
        total = len(items)
        maxPage = max(1, (total + self.LIST_PAGE_SIZE - 1) / self.LIST_PAGE_SIZE)
        page = max(1, min(page, maxPage))
        pageItems = items[(page - 1) * self.LIST_PAGE_SIZE: page * self.LIST_PAGE_SIZE]
        lines = ["[防爆玻璃] 服务端设置（共 %d 项）" % total]
        lines.extend(pageItems)
        lines.append("── 第 %d/%d 页 ──" % (page, maxPage))
        return "\n".join(lines)

    def _CommandTargets(self, playerId, rawTarget):
        """指令回显目标：显式指定的目标优先，否则为触发者本人（命令方块下为空）。"""
        if rawTarget:
            if isinstance(rawTarget, (list, tuple)):
                return tuple(rawTarget)
            return (rawTarget,)
        return (playerId,) if playerId else ()

    def _Echo(self, targetIds, text):
        """玩家走 tellraw；命令方块/控制台（无玩家）写服务端日志。"""
        if not targetIds:
            print "[reinforced_glass] 指令明细: " + text
            return
        for pid in targetIds:
            self._SendTellraw(pid, text)

    def _SendTellraw(self, playerId, text):
        try:
            import json as _json
            # ensure_ascii=True：Py2.7 下输出 \uXXXX 保证 SetCommand 行为稳定
            payload = _json.dumps({"rawtext": [{"text": text}]}, ensure_ascii=True)
        except Exception:
            payload = '{"rawtext":[{"text":"%s"}]}' % text.replace("\\", "\\\\").replace("\"", "\\\"")
        try:
            cmdComp = serverApi.GetEngineCompFactory().CreateCommand(playerId)
            return bool(cmdComp.SetCommand("/tellraw @s %s" % payload))
        except Exception as e:
            print "[reinforced_glass] tellraw 失败: %s" % str(e)
            return False

    def RegisterDyeingRecipes(self):
        # type: () -> bool
        recipeComp = serverApi.GetEngineCompFactory().CreateRecipe(serverApi.GetLevelId())
        success = 0
        total = 0
        for series in SERIES:
            if not self.settings.get(SERIES_SETTING_KEYS[series], True):
                continue
            # 环形材料 = 该系列的基础玻璃 + 除产物本色外的其它颜色
            ring_colors = [None] + [color for color, _ in COLOR_DYES if color]
            for out_color, dyes in COLOR_DYES:
                for ring_color in ring_colors:
                    if ring_color == out_color:
                        continue
                    for dye_item in dyes:
                        total += 1
                        recipe = build_dyeing_recipe(series, out_color, ring_color, dye_item)
                        if recipeComp.AddRecipe(recipe):
                            success += 1
        self._DebugPrint("染色配方注册完成: %d/%d（已关闭的系列已跳过）" % (success, total))
        return success == total