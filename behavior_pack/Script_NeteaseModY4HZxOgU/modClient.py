# -*- coding: utf-8 -*-
"""防爆玻璃 / 钢化玻璃 · 客户端脚本

接入 CardRegistry 前置模组（命名空间 Script_NeteaseMod9sPMlz0K），在其设置界面中
注册"防爆玻璃"主卡片，以及"配方"与"调试"两个中间卡片：

- 配方：开启防爆玻璃染色配方 / 开启钢化玻璃染色配方
- 调试：模组调试 / 允许命令方块修改设置

这些设置均为**服务端全局设置**（染色配方由服务端在世界加载时按开关注册），
仅 OP 可改，改动需重启世界生效。前置未安装时整体跳过，不影响模组本体功能。
"""

import mod.client.extraClientApi as clientApi

ClientSystem = clientApi.GetClientSystemCls()

engineNamespace = clientApi.GetEngineNamespace()
engineSystemName = clientApi.GetEngineSystemName()

# ==================== 前置(CardRegistry)相关常量 ====================
MAIN_CARD_ID = "reinforced_glass"
MAIN_CARD_NAME = "防爆玻璃"
MAIN_CARD_ICON = "textures/reinforced_glass"
SUB_KEY = "server"

# 中间卡片：(id, 名称, 图标)，id 须与 modServer.py 中的分组一致
MIDDLE_CARDS = [
    ("rg_recipe", "配方", "textures/ui/icon/general-icon"),
    ("rg_debug", "调试", "textures/ui/icon/debug"),
]

# 设置项：(中间卡片id, item_id, 小标题, 描述, 默认值)
SETTING_ITEMS = [
    ("rg_recipe", "enable_recipe_blast_glass", "防爆玻璃",
     "关闭后不再注册该系列的染色配方，改动需重启世界生效", True),
    ("rg_recipe", "enable_recipe_tempered_glass", "钢化玻璃",
     "关闭后不再注册该系列的染色配方，改动需重启世界生效", True),
    ("rg_debug", "debug_mode", "模组调试",
     "在控制台输出服务端调试日志（默认关闭）", False),
]

# 各中间卡片的说明文字
MIDDLE_NOTES = {
    "rg_recipe": "两个玻璃系列的染色配方在世界加载时按开关注册，关闭后对应配方不可用",
    "rg_debug": "调试日志与自定义指令相关设置，仅管理员（操作员）可修改",
}

# ==================== 与服务端系统互通的约定 ====================
SERVER_NAMESPACE = "Script_NeteaseModY4HZxOgU"
SERVER_SYSTEM = "ReinforcedGlassServerSystem"
# 客户端 -> 服务端：修改设置 / 请求当前设置
SETTING_CHANGE_EVENT = "Script_NeteaseModY4HZxOgU_SettingChange"
REQUEST_SETTING_EVENT = "Script_NeteaseModY4HZxOgU_RequestSetting"
# 服务端 -> 客户端：下发权威设置与自身 OP 状态
SETTING_SYNC_EVENT = "Script_NeteaseModY4HZxOgU_SettingSync"


class ReinforcedGlassClientSystem(ClientSystem):
    def __init__(self, namespace, systemName):
        ClientSystem.__init__(self, namespace, systemName)
        # 前置 CardRegistryApi 中的 API 引用（延迟导入成功后赋值）
        self._register_main = None
        self._register_middle = None
        self._create_content = None
        self._get_item = None
        self._set_value = None
        self._set_locked = None
        self._clear_locked = None
        self._ready = False
        self._pending_sync = None  # 缓存先于注册到达的服务端设置
        self._poll_counter = 0     # 权限轮询计数（约 3 秒一次）
        self._POLL_TICKS = 60      # 20 tick/s × 3s

        self.ListenForEvent(engineNamespace, engineSystemName,
                            "UiInitFinished", self, self.OnUiInitFinished)
        # 每次推入界面（含前置设置界面）时重新请求权威值，刷新开关显示与锁定
        self.ListenForEvent(engineNamespace, engineSystemName,
                            "PushScreenEvent", self, self.OnPushScreen)
        self.ListenForEvent(SERVER_NAMESPACE, SERVER_SYSTEM,
                            SETTING_SYNC_EVENT, self, self.OnSettingSync)

    # ==================== 前置设置界面注册 ====================

    def OnUiInitFinished(self, args):
        if not clientApi.GetLocalPlayerId():
            return
        # 延迟导入前置 CardRegistryApi，避免多 Addon 加载顺序导致的 ImportError
        try:
            from Script_NeteaseMod9sPMlz0K.CardRegistryApi import (
                RegisterMainCard, RegisterMiddleCard, CreateContentInst,
                GetContentItem, SetSettingValue, SetLocked,
            )
            from Script_NeteaseMod9sPMlz0K.SettingState import ClearSettingLocked
            self._register_main = RegisterMainCard
            self._register_middle = RegisterMiddleCard
            self._create_content = CreateContentInst
            self._get_item = GetContentItem
            self._set_value = SetSettingValue
            self._set_locked = SetLocked
            self._clear_locked = ClearSettingLocked
        except ImportError:
            print "==== [防爆玻璃] 前置模组(CardRegistry)未安装，跳过设置界面注册 ===="
            return

        if not self._ready:
            self._RegisterCards()
            self._ready = True
            # 注册后立即全部锁定（fail-closed），等服务端下发 OP 状态后再为管理员解锁
            self._LockAll(True)

        # 服务端为设置源头：UI 就绪后请求一次权威值与自身 OP 状态
        self.RequestSettings()
        # 处理先于注册到达的服务端设置
        if self._pending_sync is not None:
            self.OnSettingSync(self._pending_sync)
            self._pending_sync = None

    def OnPushScreen(self, args):
        """界面入栈时重新请求权威值（前置设置界面打开时刷新开关与锁定）。"""
        if args.get("screenDef") != "setting.main":
            return
        self.RequestSettings()

    def Update(self):
        """约每 3 秒重新请求一次权威值：兜底初始同步丢失，并跟随 OP 状态变化刷新锁定。"""
        if not self._ready:
            return
        self._poll_counter += 1
        if self._poll_counter < self._POLL_TICKS:
            return
        self._poll_counter = 0
        self.RequestSettings()

    def _RegisterCards(self):
        self._register_main(MAIN_CARD_ID, MAIN_CARD_NAME, MAIN_CARD_ICON)
        insts = {}
        for card_id, name, icon in MIDDLE_CARDS:
            self._register_middle(MAIN_CARD_ID, SUB_KEY, card_id, name, icon)
            insts[card_id] = self._create_content(MAIN_CARD_ID, SUB_KEY, card_id)
        for card_id, note in MIDDLE_NOTES.items():
            insts[card_id].AddText(card_id + "_note", "", note)
        for mid, item_id, litle, desc, default in SETTING_ITEMS:
            # 注册时一律先锁定（fail-closed），等服务端下发 OP 状态后再为管理员解锁
            insts[mid].AddSwitch(item_id, desc, litle=litle, default_value=default,
                                 locked=True, on_toggle=self.OnSettingToggle)

    # ==================== 设置读写 ====================

    def OnSettingToggle(self, screenNode, item_id, state):
        """开关回调：交由服务端鉴权并持久化（服务端随后回发权威值）。"""
        playerId = clientApi.GetLocalPlayerId()
        if not playerId:
            return
        self.NotifyToServer(SETTING_CHANGE_EVENT, {
            "playerId": playerId,
            "key": item_id,
            "value": bool(state),
        })

    def RequestSettings(self):
        playerId = clientApi.GetLocalPlayerId()
        if not playerId:
            return
        self.NotifyToServer(REQUEST_SETTING_EVENT, {"playerId": playerId})

    def OnSettingSync(self, args):
        """服务端下发权威设置：刷新开关显示值，并按 OP 状态决定是否锁定。"""
        if not self._ready:
            self._pending_sync = args
            return
        values = args.get("values") or {}
        is_op = bool(args.get("is_op", False))
        for mid, item_id, _litle, _desc, default in SETTING_ITEMS:
            value = bool(values.get(item_id, default))
            self._set_value(MAIN_CARD_ID, SUB_KEY, mid, item_id, value)
            self._ApplyItemLock(mid, item_id, not is_op)

    def _LockAll(self, locked):
        """锁定/解锁全部服务端设置项（fail-closed 兜底）。"""
        for mid, item_id, _litle, _desc, _default in SETTING_ITEMS:
            self._ApplyItemLock(mid, item_id, locked)

    def _ApplyItemLock(self, mid, item_id, locked):
        """按服务端 OP 状态实时决定锁定，覆盖全部服务端设置项。

        仅调前置的 SetLocked 不足以鉴权：它只更新「当前正在显示的分组」的数据层，
        且分组重建时会优先读取持久化的 ::locked（房主曾解锁会被保存成过期解锁态）。
        故这里三步都做：写数据层、清除持久化锁定、刷新当前 UI。
        """
        try:
            item = self._get_item(MAIN_CARD_ID, SUB_KEY, mid, item_id)
            if item is not None and hasattr(item, "SetLocked"):
                item.SetLocked(locked)
        except Exception:
            pass
        try:
            self._clear_locked(MAIN_CARD_ID, SUB_KEY, mid, item_id)
        except Exception:
            pass
        try:
            self._set_locked(item_id, locked)
        except Exception:
            pass