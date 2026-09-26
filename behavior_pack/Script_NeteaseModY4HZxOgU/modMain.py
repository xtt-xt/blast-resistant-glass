# -*- coding: utf-8 -*-

from mod.common.mod import Mod  # type: ignore
import mod.server.extraServerApi as serverApi


@Mod.Binding(name="Script_NeteaseModY4HZxOgU", version="0.0.1")
class Script_NeteaseModY4HZxOgU(object):

    def __init__(self):
        pass

    @Mod.InitServer()
    def Script_NeteaseModY4HZxOgUServerInit(self):
        serverApi.RegisterSystem(
            "Script_NeteaseModY4HZxOgU",
            "ReinforcedGlassServerSystem",
            "Script_NeteaseModY4HZxOgU.modServer.ReinforcedGlassServerSystem"
        )

    @Mod.DestroyServer()
    def Script_NeteaseModY4HZxOgUServerDestroy(self):
        pass

    @Mod.InitClient()
    def Script_NeteaseModY4HZxOgUClientInit(self):
        pass

    @Mod.DestroyClient()
    def Script_NeteaseModY4HZxOgUClientDestroy(self):
        pass
