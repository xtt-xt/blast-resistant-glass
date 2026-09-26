# -*- coding: utf-8 -*-
"""防爆玻璃 / 钢化玻璃 · 服务端脚本

动态注册两个系列的染色配方：8 个环形玻璃 + 中心 1 个染料 → 8 个对应颜色的玻璃。

- 环形材料：同系列的基础玻璃，或同系列其它颜色的玻璃（同色环跳过）
- 染料：16 种染料；黑/蓝/棕/白额外接受墨囊、青金石、可可豆、骨粉
- 配方数量：每个系列 320 条（16 产物 × 16 环形 × 平均 1.25 种染料），两个系列共 640 条

注册时机：脚本初始化时注册，此时客户端尚未连接，配方随初始数据一起下发。
不能等玩家加入（AddServerPlayerEvent）再注册——那时服务端会在客户端还没进入世界时
推送 CraftingDataPacket，客户端会断言 "Level is not usable" 崩溃。
"""

import mod.server.extraServerApi as serverApi
from mod_log import logger

ServerSystem = serverApi.GetServerSystemCls()

# 方块系列，与 behavior_pack/netease_blocks/<系列>/ 目录同名
SERIES = ["blast_glass", "tempered_glass"]

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


class ReinforcedGlassServerSystem(ServerSystem):
    def __init__(self, namespace, systemName):
        super(ReinforcedGlassServerSystem, self).__init__(namespace, systemName)
        self.recipesRegistered = self.RegisterDyeingRecipes()
        if not self.recipesRegistered:
            # 兜底：关卡尚未就绪时，等客户端加载完成再补注册
            self.ListenForEvent(
                serverApi.GetEngineNamespace(),
                serverApi.GetEngineSystemName(),
                "ClientLoadAddonsFinishServerEvent",
                self,
                self.OnClientLoadAddonsFinish,
            )

    def OnClientLoadAddonsFinish(self, args):
        if not self.recipesRegistered:
            self.recipesRegistered = self.RegisterDyeingRecipes()

    def RegisterDyeingRecipes(self):
        # type: () -> bool
        recipeComp = serverApi.GetEngineCompFactory().CreateRecipe(serverApi.GetLevelId())
        success = 0
        total = 0
        for series in SERIES:
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
        logger.info("[reinforced_glass] 染色配方注册完成: %d/%d", success, total)
        return success == total