import asyncio
import websockets
import json
import logging

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
        try:
          state = self.game.update()
          self.log_api_availability(state)
        except Exception:
          logging.exception('An error occurred while updating the game state')
          state = None

        await websocket.send(self.state_event(state))
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

        if action == 'setClientSettings':
          websockets.broadcast(
            list(self._clients),
            self.settings_event(data.get('content')))
    except websockets.exceptions.ConnectionClosed:
      pass

  async def connect_client(self, websocket):
    logging.debug('observer - Client connected')

    self._clients.add(websocket)
    tasks = []

    try:
      # Begin by sending the client settings once
      await websocket.send(self.settings_event(self.config['clientSettings']))

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
