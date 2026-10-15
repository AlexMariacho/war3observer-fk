"""Probe the Warcraft III observer shared memory without creating it.

Run while Warcraft III is open and a replay/observed game is running:
  python probe_observer_api.py

Unlike mmap.mmap(-1, ..., tagname) (which silently CREATES an empty
mapping when the game does not provide one), this uses OpenFileMappingW,
so "not found" really means the game did not create it.
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

NAME = "War3StatsObserverSharedMemory"
FILE_MAP_READ, FILE_MAP_WRITE = 0x4, 0x2

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenFileMappingW.restype = wt.HANDLE
k32.OpenFileMappingW.argtypes = [wt.DWORD, wt.BOOL, wt.LPCWSTR]
k32.MapViewOfFile.restype = ctypes.c_void_p
k32.MapViewOfFile.argtypes = [wt.HANDLE, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_size_t]


class MBI(ctypes.Structure):
  _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
              ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD),
              ("RegionSize", ctypes.c_size_t), ("State", wt.DWORD),
              ("Protect", wt.DWORD), ("Type", wt.DWORD)]


h = k32.OpenFileMappingW(FILE_MAP_READ | FILE_MAP_WRITE, False, NAME)
if not h:
  print("NOT FOUND: game did not create %r (err %d)" % (NAME, ctypes.get_last_error()))
  print("-> either WC3 is not running, or 3.x removed/renamed the observer API.")
  sys.exit(1)

view = k32.MapViewOfFile(h, FILE_MAP_READ | FILE_MAP_WRITE, 0, 0, 0)
mbi = MBI()
k32.VirtualQuery(ctypes.c_void_p(view), ctypes.byref(mbi), ctypes.sizeof(mbi))
size = mbi.RegionSize
raw = ctypes.string_at(view, size)
print("FOUND mapping, view size = %d bytes" % size)

version, refresh = struct.unpack_from("<II", raw, 0)
print("version field = %d, refresh_rate = %d" % (version, refresh))
if refresh == 0:
  # Same as war3observer does on startup: ask the game to start writing.
  ctypes.memmove(view + 4, struct.pack("<I", 2000), 4)
  print("refresh_rate was 0 -> wrote 2000; re-run in a few seconds.")

try:
  from war3structs.observer import ObserverGame, ObserverPlayer, ObserverFile
except ImportError:
  print("war3structs not installed; raw header only:", raw[:64].hex())
  sys.exit(0)

print("expected sizes: game=%d player=%d file=%d" % (
  ObserverGame.sizeof(), ObserverPlayer.sizeof(), ObserverFile.sizeof()))
if size < ObserverFile.sizeof():
  print("WARNING: mapping is smaller than the 1.32 ObserverFile layout -> layout changed")

game = ObserverGame.parse(raw[4:])
print("is_in_game=%s game_time=%dms players_count=%d map=%r" % (
  game.is_in_game, game.game_time, game.players_count, game.map_name))

base = 4 + ObserverGame.sizeof()
for i in range(28):
  off = base + i * ObserverPlayer.sizeof()
  if off + ObserverPlayer.sizeof() > size:
    print("slot %d: beyond mapping end" % i)
    break
  try:
    p = ObserverPlayer.parse(raw[off:])
  except Exception as e:
    print("slot %d: PARSE ERROR %s" % (i, e))
    continue
  if str(p.type) in ("PLAYER", "COMPUTER"):
    print("slot %2d: %-20r race=%-8s team=%d color=%d gold=%d lumber=%d food=%d/%d heroes=%d apm=%d" % (
      i, p.name, p.race, p.team_index, p.team_color, p.gold, p.lumber,
      p.food, p.food_max, len(p.heroes), p.apm))
    for hero in p.heroes:
      print("         hero %s lvl %d hp %d/%d abilities=%s items=%s" % (
        hero.id, hero.level, hero.hitpoints, hero.hitpoints_max,
        [a.id for a in hero.abilities], [it.id for it in hero.inventory]))
