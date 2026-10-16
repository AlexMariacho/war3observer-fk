"""Fake Warcraft III observer API for development and testing.

Creates the named shared memory 'War3StatsObserverSharedMemory' the way the
game does and fills it with a small in-game state:
  - player 1 (slot 0):  HUMAN with an Archmage (Hamg)
  - player 2 (slot 23): UNDEAD with a Forsaken Paladin (Npal), exercising the
    24th player slot
The game time advances every second. Run it, then start the server (or use
war3observer.game.Game directly) in another process:

  python tools/fake_observer_api.py [--seconds N]

Runs until Ctrl+C, or for N seconds. Needs war3structs installed. Windows only.
The refresh_rate field is left untouched so you can see whether the server
wrote it. Dev/testing tool only.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import struct
import time

from war3structs.observer import ObserverFile, ObserverGame, ObserverPlayer

NAME = "War3StatsObserverSharedMemory"
FILE_MAP_ALL_ACCESS = 0xF001F
PAGE_READWRITE = 0x4
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

VERSION = 0
GAME_OFFSET = 4
PLAYERS_OFFSET = GAME_OFFSET + ObserverGame.sizeof()
PLAYER_SIZE = ObserverPlayer.sizeof()
LAST_SLOT = 23

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateFileMappingW.restype = wt.HANDLE
k32.CreateFileMappingW.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.DWORD, wt.LPCWSTR]
k32.MapViewOfFile.restype = ctypes.c_void_p
k32.MapViewOfFile.argtypes = [wt.HANDLE, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_size_t]
k32.UnmapViewOfFile.restype = wt.BOOL
k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
k32.CloseHandle.restype = wt.BOOL
k32.CloseHandle.argtypes = [wt.HANDLE]


def hero_ability(id, level, is_hero_ability, cooldown=0.0):
  return dict(
    id=id, cooldown_time=10.0, cooldown=cooldown, level=level, art="",
    is_hero_ability=is_hero_ability, damage_dealt=0, damage_healed=0)


def hero_item(id, slot, charges=0):
  return dict(id=id, slot=slot, charges=charges, art="")


def hero(id, class_, abilities, items, level=5):
  return dict(
    id=id, **{"class": class_}, art="", level=level, experience=1200,
    experience_max=2000, hitpoints=650, hitpoints_max=720, mana=200,
    mana_max=300, damage_dealt=1000, damage_received=500, damage_self=0,
    index=0, damage_healed=0, deaths_count=0, kills_count=12, kills_self=0,
    kills_heroes=1, kills_buildings=0, time_alive=300000,
    abilities_count=len(abilities), abilities=abilities,
    inventory_count=len(items), inventory=items)


def player(name, race, id, team_index, team_color, heroes):
  return dict(
    name=name, race_preference=race, race=race, id=id,
    team_index=team_index, team_color=team_color, type="PLAYER", handicap=100,
    game_result="IN_PROGRESS", slot_state="PLAYING", ai_difficulty="NORMAL",
    apm=120, apm_realtime=150, gold=1234, gold_mined=5000, gold_taxed=0,
    gold_tax=0, lumber=567, lumber_harvested=2000, lumber_taxed=0,
    lumber_tax=0, food_max=60, food=42,
    heroes_count=len(heroes), heroes=heroes,
    buildings_on_map_count=0, buildings_on_map=[],
    upgrades_completed_count=0, upgrades_completed=[],
    units_on_map_count=0, units_on_map=[],
    researches_in_progress_count=0, researches_in_progress=[])


def game_bytes(game_time):
  return ObserverGame.build(dict(
    refresh_rate=0, is_in_game=True, game_time=game_time, players_count=2,
    game_name="Fake observer API game", map_name="Maps\\Fake\\(2)FakeMap.w3x"))


def main():
  parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
  parser.add_argument("--seconds", type=float, default=None, help="exit after N seconds")
  args = parser.parse_args()

  size = ObserverFile.sizeof()
  handle = k32.CreateFileMappingW(INVALID_HANDLE_VALUE, None, PAGE_READWRITE, size >> 32, size & 0xFFFFFFFF, NAME)
  if not handle:
    raise ctypes.WinError(ctypes.get_last_error())
  view = k32.MapViewOfFile(handle, FILE_MAP_ALL_ACCESS, 0, 0, 0)
  if not view:
    raise ctypes.WinError(ctypes.get_last_error())

  try:
    ctypes.memmove(view + 0, struct.pack("<I", VERSION), 4)

    archmage = hero("Hamg", "Archmage", [
      hero_ability("AHwe", 1, True),
      hero_ability("AHab", 1, True),
      hero_ability("AHbz", 1, True),
      hero_ability("AHmt", 1, True),
    ], [hero_item("bspd", 0), hero_item("ckng", 1)])

    paladin = hero("Npal", "Forsaken Paladin", [
      hero_ability("AHcr", 2, True),
      hero_ability("ANcp", 1, True),
      hero_ability("AHpa", 1, True),
      hero_ability("AHcl", 1, True),
      hero_ability("AIat", 1, False),
    ], [hero_item("bspd", 0), hero_item("ckng", 1), hero_item("eshc", 2, charges=3)])

    slots = [
      (0, player("Fake Human", "HUMAN", 0, 0, 0, [archmage])),
      (LAST_SLOT, player("Fake Undead", "UNDEAD", 1, 1, 1, [paladin])),
    ]
    for slot, p in slots:
      data = ObserverPlayer.build(p)
      assert len(data) == PLAYER_SIZE, (len(data), PLAYER_SIZE)
      ctypes.memmove(view + PLAYERS_OFFSET + slot * PLAYER_SIZE, data, PLAYER_SIZE)

    print("Fake observer API running (shared memory %d bytes). Ctrl+C to stop." % size, flush=True)

    start = time.time()
    while args.seconds is None or time.time() - start < args.seconds:
      data = game_bytes(int((time.time() - start) * 1000))
      # Preserve refresh_rate (first field) as written by the server.
      ctypes.memmove(view + GAME_OFFSET + 4, data[4:], len(data) - 4)
      time.sleep(1)
  except KeyboardInterrupt:
    pass
  finally:
    k32.UnmapViewOfFile(view)
    k32.CloseHandle(handle)


if __name__ == "__main__":
  main()
