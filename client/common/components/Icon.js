import * as m from 'mithril';
import Component from '../Component';

// Neutral dark square, used when no icon set has the requested id
const PLACEHOLDER = 'data:image/svg+xml,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
  + '<rect width="64" height="64" fill="#1a1a1a"/>'
  + '<rect x="1.5" y="1.5" width="61" height="61" fill="none" stroke="#555" stroke-width="3"/>'
  + '<text x="32" y="43" font-family="sans-serif" font-size="32" text-anchor="middle" fill="#777">?</text>'
  + '</svg>'
);

function getIconUrls(id) {
  const root = app.settings.iconRoot;
  const urls = [`${root}${id}.jpg`];

  for (const fallbackRoot of app.settings.iconFallbackRoots || []) {
    const url = `${fallbackRoot}${id}.jpg`;

    if (fallbackRoot !== root && !urls.includes(url)) {
      urls.push(url);
    }
  }

  urls.push(PLACEHOLDER);

  return urls;
}

export default class Icon extends Component {
  onerror(id, e) {
    // A failed image is not a reason to redraw
    e.redraw = false;

    const img = e.target;
    const urls = getIconUrls(id);
    const next = (parseInt(img.dataset.iconAttempt, 10) || 0) + 1;

    // The placeholder is the last candidate, never retry past it
    if (next >= urls.length) {
      return;
    }

    img.dataset.iconAttempt = next;
    img.src = urls[next];

    if (next === urls.length - 1) {
      img.classList.add('Icon--missing');
    }
  }

  // Start over when the icon this element shows changes
  resetIfChanged(vnode) {
    const key = `${app.settings.iconRoot}${vnode.attrs.id}`;

    if (vnode.dom.dataset.iconKey !== key) {
      vnode.dom.dataset.iconKey = key;
      vnode.dom.dataset.iconAttempt = 0;
      vnode.dom.classList.remove('Icon--missing');
    }
  }

  oncreate(vnode) {
    this.resetIfChanged(vnode);
  }

  onupdate(vnode) {
    this.resetIfChanged(vnode);
  }

  view(vnode) {
    const { id, ...attrs } = vnode.attrs;

    return <img src={getIconUrls(id)[0]} onerror={e => this.onerror(id, e)} {...attrs} />;
  }
}
