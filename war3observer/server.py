import asyncio
import websockets
import json
import logging
import os
import time

from . import __version__
from .game import Game

class Server():
  @staticmethod
  def setdefaults(config):
    config.setdefault('loggingLevel', logging.INFO)
    config.setdefault('host', 'localhost')
    config.setdefault('port', 8124)
    config.setdefault('clientSettings', {})

    return config

  def __init__(self, config):
    self._clients = set()
    self.config = Server.setdefaults(config)

    logging.basicConfig(
      level=self.config['loggingLevel'],
      format='%(levelname)s: %(message)s')

    self.game = Game()
    self._api_error = None
    self._state = None
    self._state_time = 0

    # Settings changed live (e.g. from the control panel) on top of each
    # view's own defaults. Every client gets the full set, so a client that
    # (re)connects later, or a key that is reset, ends up the same everywhere.
    self._client_settings = dict(self.config['clientSettings'] or {})

  def serve(self):
    logging.info('observer %s' % __version__)
    logging.debug('observer - Starting with config %s' % self.config)

    try:
      asyncio.run(self._serve())
    except KeyboardInterrupt:
      logging.info('observer - Stopping')
    finally:
      self.game.close()

  async def _serve(self):
    async with websockets.serve(self.connect_client, self.config['host'], self.config['port']):
      await asyncio.Future()

  def state_event(self, state):
    return json.dumps({ 'type': 'state', 'content': state }, default=lambda o: None)

  def settings_event(self, settings):
    return json.dumps({ 'type': 'settings', 'content': settings })

  def get_state(self):
    # Every client polls, share one update between them
    if self._state is not None and time.monotonic() - self._state_time < 1:
      return self._state

    try:
      state = self.game.update()
      self.log_api_availability(state)
    except Exception:
      logging.exception('An error occurred while updating the game state')
      state = None

    self._state = state
    self._state_time = time.monotonic()
    return state

  def update_client_settings(self, changes, reset=False):
    if reset:
      self._client_settings = {}

    for key, value in (changes or {}).items():
      # null resets a setting to the view's own default
      if value is None:
        self._client_settings.pop(key, None)
      else:
        self._client_settings[key] = value

    self.save_client_settings()
    websockets.broadcast(list(self._clients), self.settings_event(self._client_settings))

  def save_client_settings(self):
    """Keep live changes across restarts by writing them to the config file"""

    path = self.config.get('config')
    if not path:
      return

    try:
      config = {}
      if os.path.isfile(path):
        with open(path, 'r', encoding='utf-8') as fh:
          config = json.load(fh)

      config['clientSettings'] = self._client_settings

      with open(path + '.tmp', 'w', encoding='utf-8') as fh:
        json.dump(config, fh, indent=2, ensure_ascii=False)
      os.replace(path + '.tmp', path)
    except (OSError, ValueError):
      logging.exception('observer - Could not save the client settings to %s' % path)

  def log_api_availability(self, state):
    # Only log when the availability (or the reason for it) changes
    game = state.get('game') if isinstance(state, dict) else None
    if not isinstance(game, dict):
      return

    error = game.get('error') if game.get('api_available') is False else None

    if error != self._api_error:
      if error:
        logging.warning('observer - Observer API unavailable: %s' % error)
      else:
        logging.info('observer - Observer API available')

      self._api_error = error

  async def send_state_to_client(self, websocket):
    try:
      while True:
        await websocket.send(self.state_event(self.get_state()))
        await asyncio.sleep(2)
    except websockets.exceptions.ConnectionClosed:
      pass

  async def receive_client_messages(self, websocket):
    try:
      async for message in websocket:
        try:
          data = json.loads(message)
          action = data['action']
        except (ValueError, KeyError, TypeError):
          logging.debug('observer - Ignoring malformed message %r' % (message,))
          continue

        content = data.get('content')

        if action == 'setClientSettings' and isinstance(content, dict):
          self.update_client_settings(content)
        elif action == 'resetClientSettings':
          self.update_client_settings(None, reset=True)
    except websockets.exceptions.ConnectionClosed:
      pass

  async def connect_client(self, websocket):
    logging.debug('observer - Client connected')

    self._clients.add(websocket)
    tasks = []

    try:
      # Begin by sending the client settings once
      await websocket.send(self.settings_event(self._client_settings))

      # Send an updated state periodically and check for messages
      tasks = [
        asyncio.create_task(self.send_state_to_client(websocket)),
        asyncio.create_task(self.receive_client_messages(websocket))
      ]

      # Whichever ends first (typically the client disconnecting) ends the other
      await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except websockets.exceptions.ConnectionClosed:
      pass
    finally:
      logging.debug('observer - Client closed')

      self._clients.discard(websocket)

      # Stop sending the state and receiving messages
      for task in tasks:
        task.cancel()

      if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

      # Close the game if this was the last client
      if not self._clients:
        logging.debug('observer - Was last client, closing game')

        self.game.close()
        self._state = None
