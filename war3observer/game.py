import ctypes
import ctypes.wintypes as wt
import logging
import struct
import sys

from construct import Struct
from war3structs.observer import ObserverGame, ObserverPlayer

SHARED_MEMORY_NAME = "War3StatsObserverSharedMemory"

# Number of player slots we scan. ObserverFile reserves 28, but the game
# itself is limited to 24 players.
MAX_PLAYERS = 24

FILE_MAP_WRITE = 0x2
FILE_MAP_READ = 0x4

# Byte offsets inside the shared memory file (ObserverFile)
VERSION_OFFSET = 0
GAME_OFFSET = 4
REFRESH_RATE_OFFSET = GAME_OFFSET  # first field of ObserverGame
PLAYERS_OFFSET = GAME_OFFSET + ObserverGame.sizeof()

# Leading fields of ObserverPlayer up to and including `type`. Used to cheaply
# tell whether a slot is occupied without parsing the multi-MB player struct.
_PlayerHeader = Struct(*ObserverPlayer.subcons[:7])


class _MemoryBasicInformation(ctypes.Structure):
  _fields_ = [
    ("BaseAddress", ctypes.c_void_p),
    ("AllocationBase", ctypes.c_void_p),
    ("AllocationProtect", wt.DWORD),
    ("PartitionId", wt.WORD),
    ("RegionSize", ctypes.c_size_t),
    ("State", wt.DWORD),
    ("Protect", wt.DWORD),
    ("Type", wt.DWORD),
  ]


_kernel32 = None


def _get_kernel32():
  global _kernel32
  if _kernel32 is None:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenFileMappingW.restype = wt.HANDLE
    k32.OpenFileMappingW.argtypes = [wt.DWORD, wt.BOOL, wt.LPCWSTR]
    k32.MapViewOfFile.restype = ctypes.c_void_p
    k32.MapViewOfFile.argtypes = [wt.HANDLE, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_size_t]
    k32.VirtualQuery.restype = ctypes.c_size_t
    k32.VirtualQuery.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MemoryBasicInformation), ctypes.c_size_t]
    k32.UnmapViewOfFile.restype = wt.BOOL
    k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    k32.CloseHandle.restype = wt.BOOL
    k32.CloseHandle.argtypes = [wt.HANDLE]
    _kernel32 = k32
  return _kernel32


class SharedMemoryError(Exception):
  pass


class SharedMemoryView():
  """SharedMemoryView class

  Opens the existing named file mapping with OpenFileMappingW and maps it
  once. Unlike mmap.mmap(-1, ..., tagname), this never creates the mapping
  if the game did not. Raises SharedMemoryError if it cannot be opened.
  """

  def __init__(self, name):
    if sys.platform != "win32":
      raise SharedMemoryError("The observer API is only available on Windows")

    k32 = _get_kernel32()

    self._handle = k32.OpenFileMappingW(FILE_MAP_READ | FILE_MAP_WRITE, False, name)
    if not self._handle:
      raise SharedMemoryError(
        "Observer API shared memory '%s' not found: Warcraft III only creates it "
        "while a replay is playing or a game is being observed (error %d)"
        % (name, ctypes.get_last_error()))

    self._view = k32.MapViewOfFile(self._handle, FILE_MAP_READ | FILE_MAP_WRITE, 0, 0, 0)
    if not self._view:
      error = ctypes.get_last_error()
      self._release_handle()
      raise SharedMemoryError(
        "Unable to map Observer API shared memory '%s' (error %d)" % (name, error))

    mbi = _MemoryBasicInformation()
    if not k32.VirtualQuery(self._view, ctypes.byref(mbi), ctypes.sizeof(mbi)):
      error = ctypes.get_last_error()
      self.close()
      raise SharedMemoryError(
        "Unable to query Observer API shared memory '%s' (error %d)" % (name, error))
    self.size = mbi.RegionSize

  def read(self, offset, size):
    if offset < 0 or offset + size > self.size:
      raise SharedMemoryError("Read of %d bytes at offset %d is outside the shared memory (%d bytes)" % (size, offset, self.size))
    return ctypes.string_at(self._view + offset, size)

  def write(self, offset, data):
    if offset < 0 or offset + len(data) > self.size:
      raise SharedMemoryError("Write of %d bytes at offset %d is outside the shared memory (%d bytes)" % (len(data), offset, self.size))
    ctypes.memmove(self._view + offset, data, len(data))

  def _release_handle(self):
    if self._handle:
      _get_kernel32().CloseHandle(self._handle)
      self._handle = None

  def close(self):
    if self._view:
      _get_kernel32().UnmapViewOfFile(self._view)
      self._view = None
    self._release_handle()


class Game():
  """Game class

  A game updates the state from the observer API.
  """

  _refresh_rate = 2000
  _game_size = ObserverGame.sizeof()
  _player_size = ObserverPlayer.sizeof()

  def __init__(self):
    self._shm = None
    self._slots = []  # byte offsets of the occupied player slots
    self._last_error = None
    self._was_available = False

    self.state = dict(game=dict(is_in_game=False), players=[])

  def _unavailable(self, error):
    # The server logs availability changes; keep this at debug level and
    # only when the reason changes, update() is polled continuously.
    if error != self._last_error:
      logging.debug(error)
      self._last_error = error

    self.state = dict(game=dict(is_in_game=False, api_available=False, error=error), players=[])
    return self.state

  def _attach(self):
    """Open the shared memory. Returns an error message, or None on success."""

    try:
      shm = SharedMemoryView(SHARED_MEMORY_NAME)
    except SharedMemoryError as e:
      return str(e)

    version = struct.unpack("<I", shm.read(VERSION_OFFSET, 4))[0]

    required = PLAYERS_OFFSET + MAX_PLAYERS * self._player_size
    if shm.size < required:
      shm.close()
      return (
        "Observer API shared memory is smaller than expected (%d < %d bytes), "
        "the layout may have changed (version %d)" % (shm.size, required, version))

    if not self._was_available:
      logging.info("Attached to the observer API (version %d, %d bytes)", version, shm.size)
    self._was_available = True

    # The game only starts updating the file once the refresh rate is set.
    refresh_rate = struct.unpack("<I", shm.read(REFRESH_RATE_OFFSET, 4))[0]
    if refresh_rate != self._refresh_rate:
      shm.write(REFRESH_RATE_OFFSET, struct.pack("<I", self._refresh_rate))

    self._shm = shm
    return None

  def _get_game_state(self):
    parsed = ObserverGame.parse(self._shm.read(GAME_OFFSET, self._game_size))
    del parsed._io

    parsed['api_available'] = True
    parsed['version'] = struct.unpack("<I", self._shm.read(VERSION_OFFSET, 4))[0]

    return parsed

  def _get_player_state(self, offset):
    player = ObserverPlayer.parse(self._shm.read(offset, self._player_size))

    # We can do some light processing here. For now, just delete the _io
    # garbage from construct as well as the counts which we don't need.
    del player._io
    del player.heroes_count
    del player.buildings_on_map_count
    del player.upgrades_completed_count
    del player.units_on_map_count
    del player.researches_in_progress_count

    for hero in player.heroes:
      del hero._io
      del hero.abilities_count
      del hero.inventory_count

      for ability in hero.abilities:
        del ability._io

      for item in hero.inventory:
        del item._io

    for building in player.buildings_on_map:
      del building._io

    for upgrade in player.upgrades_completed:
      del upgrade._io

    for unit in player.units_on_map:
      del unit._io

    for research in player.researches_in_progress:
      del research._io

    return player

  def _find_players(self, count):
    slots = []

    for i in range(MAX_PLAYERS):
      offset = PLAYERS_OFFSET + self._player_size * i
      header = _PlayerHeader.parse(self._shm.read(offset, _PlayerHeader.sizeof()))
      if header.type == "PLAYER" or header.type == "COMPUTER":
        slots.append(offset)
        if len(slots) >= count:
          self._slots = slots
          return

    raise Exception("Attempted to find %s players but found only %s" % (count, len(slots)))

  def close(self):
    """Close the game's file handles and clear the state"""

    self.state = dict(game=dict(is_in_game=False), players=[])
    self._slots = []
    self._last_error = None
    self._was_available = False
    self._detach()

  def _detach(self):
    if self._shm is not None:
      self._shm.close()
      self._shm = None

  def update(self):
    """Update the game state"""

    # The mapping is opened for each update and closed right after. Holding
    # it open would keep it alive after the game drops it (closing the game
    # or leaving a replay), and we would keep serving that stale state.
    error = self._attach()
    if error is not None:
      self._was_available = False
      return self._unavailable(error)
    self._last_error = None

    try:
      return self._read_state()
    finally:
      self._detach()

  def _read_state(self):
    game_state = self._get_game_state()

    if not game_state['is_in_game']:
      self.state = dict(game=game_state, players=[])
      return self.state

    # If in the previous state we were not in a game, or there is a
    # mismatch of players, then we will search for players again. The
    # former is only needed for platforms such as Netease, where e.g.
    # if two players are playing in a 4-player map (TM, TR) there can
    # exist a gap (empty player) between the two.
    if not self.state['game']['is_in_game'] or len(self._slots) != game_state['players_count']:
      self._find_players(game_state['players_count'])

    player_states = []
    for offset in self._slots:
      player_states.append(self._get_player_state(offset))

    self.state = dict(game=game_state, players=player_states)
    return self.state
