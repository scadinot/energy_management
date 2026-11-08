/**
 * Energy Management — panneau latéral pour Home Assistant
 *
 * Web Component vanilla JS, sans build ni dépendance.
 * Lecture seule (hass.states), sauf l'interrupteur Pilotage.
 * Les identifiants d'entités viennent de panel.config (voir frontend.py).
 */

const TEMPO_COLORS = {
  Bleu: { bg: '#1e63c8', fg: '#ffffff' },
  Blanc: { bg: '#f4f4f4', fg: '#222222' },
  Rouge: { bg: '#d32f2f', fg: '#ffffff' },
};

const MODE_LABELS = {
  reseau: 'Réseau',
  batterie: 'Batterie',
  charge_renforcee: 'Charge renforcée',
  coupure_reseau: 'Coupure réseau',
};

// Repli si la conf du panneau ne fournit pas active_levels
const ACTIVE_LEVELS = ['Orange', 'Rouge'];

// Clés de la conf pour lesquelles le panneau lit l'entité de commande
const COMMANDS = [
  { label: 'Mode de sortie', key: 'mode_select', kind: 'mode' },
  { label: 'Seuil 12', key: 'low_threshold', kind: 'number', want: 'seuil_12', unit: '%' },
  { label: 'Seuil 13', key: 'high_threshold', kind: 'number', want: 'seuil_13', unit: '%' },
  { label: 'Charge réseau', key: 'charge_current', kind: 'number', want: 'charge', unit: 'A' },
];

class EnergyManagementPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._rendered = false;
    this._cfg = {};
    this._last = {};
    this._narrow = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._rendered) {
      this._cfg = this._panelConfig();
      this._renderShell();
      this._rendered = true;
    }
    this._update();
  }

  get hass() { return this._hass; }
  set panel(v) {
    this._panel = v;
    this._cfg = this._panelConfig();
    if (this._rendered) { this._last = {}; this._update(); }
  }
  _panelConfig() { return (this._panel && this._panel.config) || {}; }
  get panel() { return this._panel; }
  set narrow(v) { this._narrow = v; this.toggleAttribute('narrow', !!v); }
  set route(v) { this._route = v; }

  /* ---------------------------------------------------------------- données */

  _state(id) {
    if (!id || !this._hass || !this._hass.states[id]) return null;
    return this._hass.states[id];
  }

  _text(id, fallback = '') {
    const s = this._state(id);
    return s ? s.state : fallback;
  }

  _known(id) {
    const t = this._text(id);
    return t !== '' && t !== 'unknown' && t !== 'unavailable';
  }

  _attrs(id) {
    const s = this._state(id);
    return (s && s.attributes) || {};
  }

  _lang() {
    return (this._hass && ((this._hass.locale && this._hass.locale.language) || this._hass.language)) || 'fr';
  }

  _num(id) {
    const v = parseFloat(this._text(id));
    return isNaN(v) ? null : v;
  }

  _esc(v) {
    return String(v === null || v === undefined ? '' : v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  _fmtState(id) {
    const s = this._state(id);
    if (!s) return '—';
    if (typeof this._hass.formatEntityState === 'function') {
      try { return this._hass.formatEntityState(s); } catch (e) { /* repli ci-dessous */ }
    }
    return MODE_LABELS[s.state] || s.state;
  }

  /* ----------------------------------------------------------------- rendu */

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; padding: 16px; box-sizing: border-box;
          color: var(--primary-text-color); background: var(--primary-background-color);
          font-family: var(--paper-font-body1_-_font-family, inherit); }
        .wrap { max-width: 960px; margin: 0 auto; display: grid; gap: 16px; }
        .card { background: var(--card-background-color); border-radius: var(--ha-card-border-radius, 12px);
          padding: 16px; box-shadow: var(--ha-card-box-shadow, none);
          border: 1px solid var(--divider-color); }
        h1 { margin: 0; font-size: 1.4em; font-weight: 500; }
        h2 { margin: 0 0 12px; font-size: 1.1em; font-weight: 500; }
        .row { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; justify-content: space-between; }
        .grid2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
        :host([narrow]) .grid2 { grid-template-columns: 1fr; }
        .muted { color: var(--secondary-text-color); }
        .badge { display: inline-block; padding: 4px 12px; border-radius: 16px; font-size: 0.9em;
          background: var(--secondary-background-color); color: var(--primary-text-color); }
        .badge.ok { background: var(--success-color); color: #fff; }
        .badge.err { background: var(--error-color); color: #fff; }
        .badge.warn { background: var(--warning-color); color: #fff; }
        .tempo { display: inline-block; min-width: 72px; text-align: center; padding: 6px 14px;
          border-radius: 8px; font-weight: 600; border: 1px solid var(--divider-color); }
        .kv { display: flex; justify-content: space-between; padding: 6px 0;
          border-bottom: 1px solid var(--divider-color); }
        .kv:last-child { border-bottom: none; }
        .big { font-size: 1.8em; font-weight: 500; }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--divider-color); }
        th { color: var(--secondary-text-color); font-weight: 500; }
        td.diff { color: var(--error-color); font-weight: 600; }
        td.same { color: var(--success-color); }
        label.toggle { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; }
      </style>
      <div class="wrap">
        <div class="card" id="header"></div>
        <div class="card" id="days"></div>
        <div class="grid2">
          <div class="card" id="battery"></div>
          <div class="card" id="decision"></div>
        </div>
        <div class="card" id="inverters"></div>
      </div>`;
    this._root = this.shadowRoot;
    // Délégation : un seul écouteur pour l'interrupteur Pilotage
    this._root.addEventListener('change', (ev) => {
      const t = ev.target;
      if (t && t.id === 'pilotage-toggle') this._onPilotage(t);
    });
  }

  _update() {
    if (!this._rendered) return;
    this._renderHeader();
    this._renderDays();
    this._renderBattery();
    this._renderDecision();
    this._renderInverters();
  }

  _set(id, html) {
    const el = this._root.getElementById(id);
    // Comparaison avec le dernier html écrit : innerHTML est resérialisé par le navigateur
    if (el && this._last[id] !== html) { this._last[id] = html; el.innerHTML = html; }
  }

  _renderHeader() {
    const c = this._cfg;
    const on = this._text(c.pilotage_entity) === 'on';
    const available = this._state(c.pilotage_entity) !== null;
    const ecartOn = this._text(c.ecart_entity) === 'on';
    const commandes = this._attrs(c.ecart_entity).commandes || [];
    const ecart = ecartOn
      ? `<span class="badge err">Écart : ${this._esc(commandes.join(', '))}</span>`
      : '<span class="badge ok">Aucun écart</span>';
    this._set('header', `
      <div class="row">
        <h1>Energy Management</h1>
        <div class="row">
          ${ecart}
          <label class="toggle">
            <input type="checkbox" id="pilotage-toggle" ${on ? 'checked' : ''} ${available ? '' : 'disabled'}>
            <span>Pilotage ${on ? 'actif' : 'coupé'}</span>
          </label>
        </div>
      </div>`);
  }

  _onPilotage(input) {
    const id = this._cfg.pilotage_entity;
    const on = input.checked;
    const message = on
      ? 'Activer le Pilotage ? Energy Management pourra écrire sur l\'onduleur.'
      : 'Couper le Pilotage ? Les réglages de l\'onduleur seront remis aux valeurs normales.';
    if (!id || !window.confirm(message)) {
      // Annulation : on restaure l'état réel de l'entité
      input.checked = this._text(id) === 'on';
      return;
    }
    this._hass.callService("switch", on ? "turn_on" : "turn_off", { entity_id: id });
  }

  _tempoCell(id) {
    const value = this._text(id, '');
    if (!this._known(id)) return '<span class="tempo muted">—</span>';
    const col = TEMPO_COLORS[value] || { bg: 'var(--secondary-background-color)', fg: 'var(--primary-text-color)' };
    return `<span class="tempo" style="background:${col.bg};color:${col.fg}">${this._esc(value)}</span>`;
  }

  _vigilance() {
    const id = this._cfg.vigilance;
    if (!this._state(id)) return '<span class="badge">Non configurée</span>';
    const attrs = this._attrs(id);
    const phenomena = Array.isArray(this._cfg.phenomena) ? this._cfg.phenomena : [];
    const levels = Array.isArray(this._cfg.active_levels) ? this._cfg.active_levels : ACTIVE_LEVELS;
    const active = phenomena.filter((p) => levels.includes(attrs[p]));
    if (!active.length) return '<span class="badge ok">Aucune vigilance</span>';
    const red = active.some((p) => attrs[p] === 'Rouge');
    return `<span class="badge ${red ? 'err' : 'warn'}">${this._esc(active.map((p) => `${p} (${attrs[p]})`).join(', '))}</span>`;
  }

  _renderDays() {
    const c = this._cfg;
    const offPeak = this._state(c.off_peak)
      ? (this._text(c.off_peak) === 'on'
        ? '<span class="badge ok">Heures creuses</span>'
        : '<span class="badge">Heures pleines</span>')
      : '<span class="badge muted">Non configurées</span>';
    this._set('days', `
      <h2>Aujourd'hui / demain</h2>
      <div class="grid2">
        <div><div class="muted">Aujourd'hui</div>${this._tempoCell(c.color_today)}</div>
        <div><div class="muted">Demain</div>${this._tempoCell(c.color_tomorrow)}</div>
      </div>
      <div class="kv"><span>Heures creuses</span><span>${offPeak}</span></div>
      <div class="kv"><span>Vigilance</span><span>${this._vigilance()}</span></div>`);
  }

  _renderBattery() {
    const c = this._cfg;
    const soc = this._num(c.soc);
    const reserve = this._num(c.reserve_active_entity);
    let grid;
    if (!c.grid_presence || !this._state(c.grid_presence)) {
      grid = '<span class="badge">Non configurée</span>';
    } else {
      grid = this._text(c.grid_presence) === 'on'
        ? '<span class="badge ok">Présent</span>'
        : '<span class="badge err">Absent</span>';
    }
    this._set('battery', `
      <h2>Batterie</h2>
      <div class="big">${soc === null ? '—' : `${soc.toLocaleString(this._lang(), { maximumFractionDigits: 1 })} %`}</div>
      <div class="kv"><span>Réserve active</span><span>${reserve === null ? '—' : `${reserve} %`}</span></div>
      <div class="kv"><span>Réseau</span><span>${grid}</span></div>`);
  }

  _renderDecision() {
    const c = this._cfg;
    const raw = this._text(c.mode_voulu_entity);
    const label = this._known(c.mode_voulu_entity) ? this._fmtState(c.mode_voulu_entity) : '—';
    const raison = this._known(c.raison_entity) ? this._text(c.raison_entity) : '—';
    this._set('decision', `
      <h2>Décision</h2>
      <div class="big" title="${this._esc(raw)}">${this._esc(label)}</div>
      <div class="muted">${this._esc(raison)}</div>`);
  }

  _wanted(cmd, attrs) {
    if (cmd.kind === 'mode') {
      if (attrs.mode === 'grid') return this._cfg.option_grid;
      if (attrs.mode === 'battery') return this._cfg.option_battery;
      return null;
    }
    const v = attrs[cmd.want];
    return v === undefined || v === null ? null : v;
  }

  _renderInverters() {
    const c = this._cfg;
    const attrs = this._attrs(c.mode_voulu_entity);
    const rows = COMMANDS.map((cmd) => {
      const id = c[cmd.key];
      const want = this._wanted(cmd, attrs);
      const hasActual = this._known(id);
      const actual = hasActual ? this._text(id) : null;
      let same = null;
      if (want !== null && actual !== null) {
        same = cmd.kind === 'mode'
          ? actual === want
          : Math.abs(parseFloat(actual) - parseFloat(want)) < 0.5;
      }
      const fmt = (v) => (v === null ? '—' : this._esc(cmd.unit ? `${v} ${cmd.unit}` : v));
      const cls = same === null ? '' : (same ? 'same' : 'diff');
      return `<tr><td>${cmd.label}</td><td>${fmt(want)}</td><td class="${cls}">${fmt(actual)}</td></tr>`;
    }).join('');
    this._set('inverters', `
      <h2>Onduleurs</h2>
      <table>
        <thead><tr><th>Commande</th><th>Voulu</th><th>Réel</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`);
  }
}

customElements.define("energy-management-panel", EnergyManagementPanel);
