import './ControlPanel.scss';
import * as m from 'mithril';
import Component from '../common/Component';

const ON_OFF = [[true, 'On'], [false, 'Off']];

// Settings the panel can change, shown in groups. Each one can also be set
// back to the view's own default.
const GROUPS = [
  {
    title: 'Visibility',
    settings: [
      { key: 'showOverlay', label: 'Whole overlay', options: [[true, 'Shown'], [false, 'Hidden']] },
      { key: 'showResources', label: 'Resource bar', options: ON_OFF },
      { key: 'showHeroes', label: 'Heroes', options: ON_OFF }
    ]
  },
  {
    title: 'Look',
    settings: [
      { key: 'iconRoot', label: 'Icons', options: [['icons/', 'Classic'], ['icons/hd/', 'Reforged'], ['icons/de/', 'Definitive']] },
      { key: 'hudType', label: 'Resource bar style', options: [['auto', 'By race'], ['human', 'Human'], ['orc', 'Orc'], ['nightelf', 'Night Elf'], ['undead', 'Undead'], ['forsaken', 'Forsaken']] },
      { key: 'reversePlayerOrder', label: 'Swap sides', options: ON_OFF },
      { key: 'useTeamColors', label: 'Team colors for names', options: ON_OFF },
      { key: 'scaleToWindow', label: 'Scale to window', options: ON_OFF }
    ]
  },
  {
    title: 'Heroes',
    settings: [
      { key: 'showHeroStatus', label: 'Health and mana', options: ON_OFF },
      { key: 'showHeroStatusExperience', label: 'Experience bar', options: ON_OFF },
      { key: 'showHeroAbilities', label: 'Abilities', options: ON_OFF },
      { key: 'showHeroItems', label: 'Items', options: ON_OFF },
      { key: 'heroLevelPrecision', label: 'Level', options: [[0, '3'], [1, '3.1'], [2, '3.14']] },
      { key: 'heroAbilityFilter', label: 'Which abilities', options: [['flag', 'Learned'], ['id', 'By id'], ['auto', 'Auto']] }
    ]
  }
];

function formatTime(ms) {
  const seconds = Math.floor(ms / 1000);
  const pad = n => (n < 10 ? '0' : '') + n;

  return `${Math.floor(seconds / 60)}:${pad(seconds % 60)}`;
}

function mapName(path) {
  return (path || '').split(/[\\/]/).pop().replace(/\.w3[mx]$/i, '');
}

export default class ControlPanelApp extends Component {
  constructor({ host, port } = {}) {
    super();

    this.host = host || 'localhost';
    this.port = port || '8124';

    this.connected = false;
    this.settings = {};
    this.state = undefined;

    this._ws = null;
  }

  boot() {
    window.addEventListener('beforeunload', () => this._ws && this._ws.close(1000));
    this.connect();

    m.mount(document.getElementById('app'), this);
  }

  connect() {
    const ws = new WebSocket(`ws://${this.host}:${this.port}/`);

    ws.onopen = () => {
      this.connected = true;
      m.redraw();
    };

    ws.onmessage = event => {
      const data = JSON.parse(event.data);

      if (data.type === 'settings') {
        this.settings = data.content || {};
      } else if (data.type === 'state') {
        this.state = data.content;
      }

      m.redraw();
    };

    ws.onclose = e => {
      this.connected = false;
      this.state = undefined;
      m.redraw();

      if (e.code !== 1000) {
        setTimeout(() => this.connect(), 2000);
      }
    };

    this._ws = ws;
  }

  send(action, content) {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify({ action, content }));
    }
  }

  // null tells the server to drop the setting, so each view uses its own
  set(key, value) {
    this.send('setClientSettings', { [key]: value });
  }

  reset() {
    this.send('resetClientSettings');
  }

  viewStatus() {
    if (!this.connected) {
      return [
        <span class="ControlPanel-dot ControlPanel-dot--off" />,
        'Not connected to the server. Is run.bat running?'
      ];
    }

    const game = this.state && this.state.game;

    if (!game) {
      return [<span class="ControlPanel-dot ControlPanel-dot--wait" />, 'Connected, waiting for data...'];
    }

    if (game.api_available === false) {
      return [<span class="ControlPanel-dot ControlPanel-dot--wait" />, 'Connected. Open a replay or observe a game in Warcraft III.'];
    }

    if (!game.is_in_game) {
      return [<span class="ControlPanel-dot ControlPanel-dot--wait" />, 'Connected. Waiting for the game to start...'];
    }

    const players = this.state.players.map(player => player.name).join(' vs ');

    return [
      <span class="ControlPanel-dot ControlPanel-dot--on" />,
      <b>{mapName(game.map_name)}</b>,
      ` ${formatTime(game.game_time)} · ${players}`
    ];
  }

  viewSetting({ key, label, options }) {
    const overridden = Object.prototype.hasOwnProperty.call(this.settings, key);
    const current = this.settings[key];

    const button = (text, active, onclick, extraClass = '') => (
      <button
        class={`ControlPanel-option ${extraClass} ${active ? 'is-active' : ''}`}
        disabled={!this.connected}
        onclick={onclick}>
        {text}
      </button>
    );

    return (
      <div class="ControlPanel-setting">
        <div class="ControlPanel-label">{label}</div>
        <div class="ControlPanel-options">
          {button('Default', !overridden, () => this.set(key, null), 'ControlPanel-option--default')}
          {options.map(([value, text]) => button(text, overridden && current === value, () => this.set(key, value)))}
        </div>
      </div>
    );
  }

  view() {
    return (
      <div class="ControlPanel">
        <div class="ControlPanel-header">
          <h1>war3observer</h1>
          <button class="ControlPanel-reset" disabled={!this.connected} onclick={() => this.reset()}>
            Reset all
          </button>
        </div>

        <div class="ControlPanel-status">{this.viewStatus()}</div>

        {GROUPS.map(group => (
          <section class="ControlPanel-group">
            <h2>{group.title}</h2>
            {group.settings.map(setting => this.viewSetting(setting))}
          </section>
        ))}

        <p class="ControlPanel-hint">
          Changes apply to every open overlay right away and are saved in
          war3observer.config.json. "Default" uses each overlay page's own value.
        </p>
      </div>
    );
  }
}
