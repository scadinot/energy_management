// Banc d'essai Node du panneau : DOM minimal, hass simulé.
// Lancé par tests/test_panel_js.py ; affiche un objet JSON sur la sortie standard.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

// --- DOM minimal ------------------------------------------------------------
class FakeRoot {
  constructor() { this.els = {}; this._html = ''; }
  set innerHTML(v) { this._html = v; this.els = {}; }
  get innerHTML() { return this._html; }
  addEventListener() {}
  getElementById(id) {
    if (!this.els[id]) this.els[id] = { innerHTML: '' };
    return this.els[id];
  }
}
class FakeHTMLElement {
  attachShadow() { this.shadowRoot = new FakeRoot(); return this.shadowRoot; }
  toggleAttribute() {}
}
const registry = {};
globalThis.HTMLElement = FakeHTMLElement;
// Comme un navigateur : une seconde définition du même nom est refusée
globalThis.customElements = {
  get: (name) => registry[name],
  define: (name, cls) => {
    if (registry[name]) throw new Error(`"${name}" has already been used with this registry`);
    registry[name] = cls;
  },
};
globalThis.window = globalThis;
globalThis.confirm = () => true;

const src = fs.readFileSync(
  path.join(__dirname, '..', 'custom_components', 'energy_management', 'frontend', 'energy_management_panel.js'),
  'utf8',
);
vm.runInThisContext(src);
const Panel = registry['energy-management-panel'];

// Nouvelle version chargée dans la même page (onglet resté ouvert pendant
// une mise à jour) : pas d'erreur, la première définition est conservée.
let reloadError = null;
try {
  vm.runInThisContext(`(() => {\n${src}\n})();`);
} catch (e) {
  reloadError = String(e);
}

// --- Données ------------------------------------------------------------------
const st = (state, attributes = {}) => ({ state, attributes });
const own = (prefix) => ({
  [`switch.${prefix}pilotage`]: st('on', { remise_en_attente: false, commandes_a_remettre: [] }),
  [`sensor.${prefix}mode_voulu`]: st('reseau', { mode: 'grid', seuil_12: 50, seuil_13: 95, charge: 15 }),
  [`sensor.${prefix}raison`]: st('Fonctionnement normal'),
  [`sensor.${prefix}reserve_active`]: st('30'),
  [`binary_sensor.${prefix}ecart`]: st('on', { commandes: ['Seuil 12'] }),
});
const registryOf = (prefix, platform = 'energy_management') => {
  const keys = { pilotage: 'switch', mode_voulu: 'sensor', raison: 'sensor', reserve_active: 'sensor', ecart: 'binary_sensor' };
  const out = {};
  for (const [key, domain] of Object.entries(keys)) {
    const id = `${domain}.${prefix}${key}`;
    out[id] = { entity_id: id, platform, translation_key: key };
  }
  return out;
};
const sources = {
  'select.mode': st('UTI (Utility First)'),
  'number.low': st('40.0'),
  'number.high': st('95.0'),
  'number.charge': st('15.0'),
};
// Configuration figée à l'enregistrement : anciens identifiants
const config = {
  pilotage_entity: 'switch.energy_management_pilotage',
  mode_voulu_entity: 'sensor.energy_management_mode_voulu',
  raison_entity: 'sensor.energy_management_raison',
  reserve_active_entity: 'sensor.energy_management_reserve_active',
  ecart_entity: 'binary_sensor.energy_management_ecart',
  mode_select: 'select.mode', low_threshold: 'number.low', high_threshold: 'number.high', charge_current: 'number.charge',
  option_grid: 'UTI (Utility First)', option_battery: 'SBU (Solar-Battery-Utility)',
};

function render(hass, cfg = config) {
  const el = new Panel();
  el.panel = { config: cfg };
  el.hass = hass;
  return el;
}
function snapshot(el) {
  const r = el.shadowRoot;
  return {
    header: r.getElementById('header').innerHTML,
    days: r.getElementById('days').innerHTML,
    battery: r.getElementById('battery').innerHTML,
    decision: r.getElementById('decision').innerHTML,
    inverters: r.getElementById('inverters').innerHTML,
  };
}

const result = {};
result.reload = { error: reloadError, sameClass: registry['energy-management-panel'] === Panel };

// 1. Entités renommées (pièce « Sous-sol ») : retrouvées par hass.entities,
//    malgré un leurre d'une autre intégration avec la même clé de traduction.
const decoy = { 'switch.autre_pilotage': { entity_id: 'switch.autre_pilotage', platform: 'autre', translation_key: 'pilotage' } };
const renamed = {
  states: { ...sources, ...own('sous_sol_energy_management_'), 'switch.autre_pilotage': st('off') },
  entities: { ...decoy, ...registryOf('sous_sol_energy_management_') },
};
const el1 = render(renamed);
result.renamed = snapshot(el1);

// 2. Sans hass.entities : repli sur les identifiants de la configuration.
const el2 = render({ states: { ...sources, ...own('energy_management_') } });
result.fallback = snapshot(el2);

// 3. Renommage après le premier rendu : le nouvel objet hass.entities est relu.
const el3 = render({ states: { ...sources, ...own('energy_management_') }, entities: registryOf('energy_management_') });
el3.hass = {
  states: { ...sources, ...own('cave_energy_management_') },
  entities: registryOf('cave_energy_management_'),
};
result.renamedLater = snapshot(el3);

// 4. Ni hass.entities utile ni configuration valide : affichage « — ».
const el4 = render({ states: { ...sources, ...own('sous_sol_energy_management_') }, entities: {} });
result.lost = snapshot(el4);

// 5. Présence réseau : vraie coupure et capteur illisible affichés différemment.
const gridCfg = { ...config, grid_presence: 'binary_sensor.grid' };
const gridCase = (gridState, mode) => {
  const states = { ...sources, ...own('energy_management_') };
  if (gridState !== undefined) states['binary_sensor.grid'] = st(gridState);
  if (mode) states['sensor.energy_management_mode_voulu'] = st(mode, { mode: null });
  return snapshot(render({ states }, gridCfg));
};
result.grid = {
  on: gridCase('on'),
  off: gridCase('off', 'coupure_reseau'),
  unavailable: gridCase('unavailable', 'capteur_reseau_indisponible'),
  missing: gridCase(undefined, 'capteur_reseau_indisponible'),
  notConfigured: snapshot(render({ states: { ...sources, ...own('energy_management_') } })),
};

// 6. Formats : valeurs réelles brutes de l'onduleur (« 50.0 ») et SOC décimal,
//    heures pleines.
const fmtCfg = { ...config, soc: 'sensor.soc', off_peak: 'binary_sensor.hc' };
result.formats = snapshot(render({
  states: {
    ...sources,
    ...own('energy_management_'),
    'number.low': st('50.0'),
    'number.high': st('95.0'),
    'number.charge': st('15.0'),
    'sensor.soc': st('99.8'),
    'binary_sensor.hc': st('off'),
  },
}, fmtCfg));

process.stdout.write(JSON.stringify(result));
