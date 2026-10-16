## Summary

war3observer is a tool that keeps a local webpage updated with data from the Warcraft III observer API. This can be used for streaming tools such as OBS to render the data on stream.

It runs a local websocket server which sends a message with the entire state periodically. It uses [war3structs](https://github.com/sides/war3structs) to parse the state from the memory mapped file. A web client written in [mithril.js](https://github.com/MithrilJS/mithril.js/) is included to render the state.

![screenshot example](/screenshots/replay-example.jpg)


## Quick start (Warcraft III 3.0, Forsaken Kingdom)

You need Windows, [Python 3](https://www.python.org/), [Node.js](https://nodejs.org/), git and Warcraft III.

**1. Start war3observer.** Double-click `run.bat`. It sets everything up, builds the overlay, takes the icons from your game and starts the server. Keep its window open while you stream. It also opens the control panel in your browser.

**2. Set up OBS.** In your scene add:
- `Game Capture` for Warcraft III;
- a `Browser` source **above it**: tick `Local file`, pick `client\dist\de-1v1-overview.html`, size 1920x1080.

If the overlay does not change after an update, click `Refresh cache of current page` on the browser source.

**3. Open a replay in Warcraft III** (or observe a game). The game only shares its data while a replay plays or a game is observed, so the overlay is empty in the menus.

**4. Hide the game's own panels.** The overlay shows resources and heroes itself, so turn the game's panels off with these keys while the replay plays:

| Key | Panel |
| --- | --- |
| `A` | all panels at once |
| `H` | heroes (top left) |
| `T` | statistics (top right) |
| `Q` | production / units (bottom) |
| `S` | selection |
| `M` | minimap |
| `D` | day/night clock (the overlay's top bar is made to sit around it) |
| `R` | replay controls (speed, vision) |
| `C` | small panel with buttons for all of the above |

A good start: press `A` to hide everything, then `D` to bring the clock back. You can change the keys in `Options > Hotkeys > Observer Commands`. The option `Advanced Observer Mode` switches between these new panels and the classic replay interface.

**5. Change the overlay live** in the control panel (`client\dist\control-panel.html`): show or hide the resource bar, heroes or the whole overlay, switch icons (Classic, Reforged, Definitive), the resource bar style (by race, Human, Orc, Night Elf, Undead, Forsaken), swap the players' sides, hero health/mana, experience, abilities, items and level. Changes show up on stream right away and are kept for next time. `Default` puts a setting back, `Reset all` puts all of them back. To have the panel inside OBS: `View > Docks > Custom Browser Docks` with the URL `run.bat` prints.

Other overlay pages in `client\dist`: `sd-*` (classic icons), `hd-*` (Reforged icons), `*-flipped` (players swapped), `*-replay-*` (resource bar style follows the race), `*-teams-overview` (team games).


## Usage

- [Download the latest release](https://github.com/sides/war3observer/releases)
- Extract it somewhere
- In OBS, add a browser source to your scene, tick `Local file` and select any of the `.html` files in the `client` folder you extracted
- Set the width and height to 1920x1080 for 16:9, 1440x1080 for 4:3, scale it in OBS as needed
- For best performance (optional):
  - Use existing sources between scenes (one file = one source)
  - To avoid them running in the background regardless of whether you're using them or not, keep the sources in a separate scene collection OR enable `Shutdown source when not visible` on them
- Now you can run `war3observer.exe` whenever you want the overlay to start updating

The included views come in three flavours, depending on which icon set they use:

- `sd-*`: classic Warcraft III icons (`icons/`)
- `hd-*`: Warcraft III: Reforged icons (`icons/hd/`)
- `de-*`: Definitive Edition icons (`icons/de/`), the new art that comes with the Forsaken Kingdom update (patch 3.0)

Pick the one that matches what the game you are observing is showing. Icons that are missing from the chosen set fall back to the other sets in `iconFallbackRoots` (see below) and finally to a neutral placeholder (`Icon--missing` CSS class), instead of a broken image.

If the overlay does not update:

- Make sure a replay is playing or a game is being observed. Warcraft III only shares its data then
- Refresh the browser cache in OBS (`Refresh cache of current page` on the source)


### Updating

To update to the latest version you can download the latest release and extract the contents to wherever you have the previous version installed (replacing files). If you are using the included client you will have to clear the browser cache in OBS as well.


### Advanced usage

For advanced options you can create a file called `war3observer.config.json` in the same directory as `war3observer.exe`. Example config file:

```json
{
  "port": 8657,
  "clientSettings": {
    "useTeamColors": true,
    "showHeroItems": false,
    "reversePlayerOrder": true
  }
}
```

`war3observer.exe` also comes with some command-line options, run it with `--help` for details.

Some of the client settings you can put in `clientSettings`:

| Setting | Default | Description |
| --- | --- | --- |
| `showOverlay` / `showResources` / `showHeroes` | `true` | Show the whole overlay / the resource bar / the heroes |
| `hudType` | `"human"` (`"auto"` in the `*-replay-*` views) | Style of the top resource panel: `"human"`, `"orc"`, `"nightelf"`, `"undead"`, `"forsaken"` (the Forsaken Kingdom HUD) or `"auto"` (follows the first player's race). There is no Forsaken race, so `"forsaken"` has to be set explicitly |
| `scaleToWindow` | `true` | Keep the fixed 1920x1080 layout (1440x1080 when the window is closer to 4:3) and scale it to fit the window, so the overlay lines up at any size. At exactly 1920x1080 or 1440x1080 nothing is scaled |
| `iconRoot` | depends on the view | Folder (relative to the view) to load icons from, e.g. `"icons/de/"` |
| `iconFallbackRoots` | `["icons/"]` | Folders to try, in order, when an icon is not found in `iconRoot`. The classic set has the widest coverage |
| `heroAbilityFilter` | `"id"` | How to pick which of a hero's abilities are shown: `"id"` filters by ability id (hero abilities start with `AH`, `AO`, `AE`, `AU` or `AN`), `"flag"` uses the observer API's `is_hero_ability` flag, `"auto"` uses the flag if the hero has any flagged ability and the id otherwise |


#### Controlling the overlay

Open `client/control-panel.html` (in the release: `client\control-panel.html` next to the overlay pages) in a browser to change the overlay while it is running: show or hide the resource bar, heroes or the whole overlay, switch the icon set and resource bar style, swap sides, and so on. Every open overlay updates right away, and the changes are saved to `war3observer.config.json`, so they survive a restart of the server or a refresh of the OBS source. "Default" on a setting goes back to each overlay page's own value. In OBS you can keep the panel in a dock: `View > Docks > Custom Browser Docks`, with the panel's `file:///` URL.

Other programs can do the same. Send a JSON message to the server with top-level `action` as `"setClientSettings"` and `content` as an object of settings to change (a `null` value resets that setting), or `action` as `"resetClientSettings"` to reset all of them. All listening clients will update accordingly.


## Development

On Windows, `run.bat` does all of the steps below in one go and reports each one: it checks the tools, creates `.venv` and installs the Python dependencies, builds the client, extracts icons (again only when the game build changes, and not while the game is running, since it locks its files), stops a server left over from a previous run, and starts the server, opening the control panel in the browser. Set `WC3_DIR` if Warcraft III is not installed in the default location of the script. Options: `fake` (also start `tools\fake_observer_api.py`), `rebuild` (reinstall dependencies and re-extract icons), `noopen` (don't open the control panel), `view <name>` (overlay page it suggests for OBS, default `de-1v1-overview`).

To do it by hand:

- Have [Python 3](https://www.python.org/), [node](https://nodejs.org/en/), and Warcraft III installed
- `git clone https://github.com/sides/war3observer.git`
- `cd war3observer`
- `pip install -r requirements.txt -r requirements-dev.txt`
- `python -m war3observer` to start the server
- `cd client`
- `npm install`
- `npm run start` to watch for changes and build the client (rerun this whenever a new view is added)
- `mkdir dist\icons`
- `python ..\tools\extract_icons.py <wc3 installation dir> .\dist\icons` if you want to include icons (the classic icons go in `dist\icons`, the `hd` and `de` sets in the `hd` and `de` subfolders it creates itself)
- `python ..\tools\fake_observer_api.py` fakes the game's observer API so you can develop without running Warcraft III (Windows only, start it before `python -m war3observer`)


### Making custom views

If you're interested in making personalized views and you want to make use of the included client's environment, you can use the `war3observer-client-tools` package on npm instead of cloning the repo.

> Note: If you only need to edit a view's settings and/or add custom CSS, you can just copy+paste one of the included views and edit its HTML. Add custom CSS in `<style>` tags or link to one; change `app.settings` before the call to `app.boot()`.

Create a directory for your project that contains these files:

**package.json**

```json
{
  "private": true,
  "scripts": {
    "start": "webpack -d --watch",
    "build": "webpack -p"
  }
}
```

**webpack.config.js**

```js
const config = require('war3observer-client-tools');

module.exports = config;
```

**views/\<your view\>/app.js**

```js
import App from 'war3observer-client-tools/common/App';

const app = new App();

export { app };
```

Now you can `npm install --save-dev war3observer-client-tools` and `npm run build` and it will create your view in `dist`.
