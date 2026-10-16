import * as m from 'mithril';
import Component from './Component';
import defaultSettings from './App.json';

export default class App extends Component {
  constructor({ host, port, settings } = {}) {
    super();

    this.game = null;

    // The view's own settings. Settings from the server (the config file and
    // live changes from the control panel) always apply on top of these.
    this._baseSettings = Object.assign({}, this.defaultSettings(), settings || {});
    this.settings = Object.assign({}, this._baseSettings);

    this.host = host || 'localhost';
    this.port = port || '8124';

    this._ws = null;
    this._wsReconnectDelay = 5000;
  }

  defaultSettings() {
    // Subclasses extend this, so don't hand out the shared object
    return Object.assign({}, defaultSettings);
  }

  boot() {
    window.addEventListener('beforeunload', e => this._ws && this._ws.close(1000));
    window.addEventListener('resize', () => this.fitToWindow());
    window.addEventListener('load', () => this.fitToWindow());
    this.connect();

    this.applySettings();
    m.mount(document.getElementById('app'), this);
  }

  applySettings() {
    document.getElementById('app').style.visibility = this.settings.showOverlay ? '' : 'hidden';
    this.fitToWindow();
  }

  // The views are laid out for a 1920x1080 (16:9) or 1440x1080 (4:3)
  // source. Keep that fixed layout and scale it to fit any other window
  // size, so it lines up the same way everywhere.
  fitToWindow() {
    const stage = document.getElementById('app');
    const ratio = window.innerWidth / window.innerHeight;
    const is4x3 = ratio < (4 / 3 + 16 / 9) / 2;
    const width = is4x3 ? 1440 : 1920;
    const height = 1080;

    document.documentElement.classList.toggle('App--4x3', is4x3);

    // A hidden window (e.g. an OBS source that isn't visible yet) has no
    // size; leave the layout unscaled until the next resize.
    if (!this.settings.scaleToWindow || !window.innerWidth || !window.innerHeight) {
      stage.style.transform = '';
      return;
    }

    const scale = Math.min(window.innerWidth / width, window.innerHeight / height);
    const offsetX = (window.innerWidth - width * scale) / 2;

    stage.style.transform = `translate(${offsetX}px, 0) scale(${scale})`;
  }

  // Keep reconnecting for as long as the page is open: an OBS source can
  // stay open for days while the server is stopped and started again.
  connect() {
    const ws = new WebSocket(`ws://${this.host}:${this.port}/`);

    ws.onmessage = this.onmessage.bind(this);
    ws.onclose = e => {
      // Don't keep showing the last state of a server that is gone
      if (this.game !== null) {
        this.game = null;
        m.redraw();
      }

      if (e.code !== 1000) {
        setTimeout(() => this.connect(), this._wsReconnectDelay);
      }
    };

    this._ws = ws;
  }

  onmessage(event) {
    const data = JSON.parse(event.data);

    switch (data.type) {
      case 'state':
        this.game = data.content;
        break;

      case 'settings':
        // The server sends the full set of overrides, so a setting it no
        // longer has goes back to the view's own value.
        this.settings = Object.assign({}, this._baseSettings, data.content || {});
        this.applySettings();
        break;
    }

    m.redraw();
  }
}
