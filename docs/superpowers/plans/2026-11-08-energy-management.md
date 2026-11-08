# Energy Management 0.1.0 — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** extension Home Assistant `energy_management` qui calcule l'état voulu des onduleurs selon Tempo et la vigilance, l'affiche, et ne l'écrit que si le Pilotage est actif.

**Architecture :** une fonction pure (`decision.py`) calcule l'état voulu à partir d'entrées déjà nettoyées (`inputs.py`) ; une fonction pure (`plan_writes`) ordonne les écritures ; un exécuteur asynchrone (`Reconciler`) écrit, relit et retente ; un objet d'instance (`EnergyManager`, `manager.py`) relie le tout aux écoutes d'état, au minuteur d'une minute, aux entités et au panneau.

**Tech Stack :** Python 3.14, Home Assistant 2026.10, `pytest-homeassistant-custom-component` 0.13.375, Web Component JavaScript sans build.

**Spec :** `docs/superpowers/specs/2026-11-08-energy-management-design.md` (à lire en entier avant la tâche 1).

## Contraintes globales

- **Aucune écriture sur l'installation réelle.** Pendant toute la réalisation, ne jamais appeler `ha_call_service`, `ha_set_entity`, `ha_bulk_control` ni aucun outil MCP d'écriture sur une entité Growatt ou Docan. Les tests utilisent `MockConfigEntry` et des entités simulées par `hass.states.async_set`.
- **Aucun identifiant d'entité en dur** dans `custom_components/` (spec § 1). Les identifiants réels ne vivent que dans `tests/const.py`.
- Domaine `energy_management`, nom « Energy Management », version `0.1.0`, `single_config_entry: true`, `iot_class: calculated`, dépendances `http`, `frontend`, `panel_custom`, `codeowners: ["@scadinot"]`.
- Pilotage **coupé par défaut**, état conservé au redémarrage.
- Valeurs par défaut (spec § 4.3) : réserve 30 %, réserve sous vigilance 50 %, écart 5 points, seuils normaux 50 / 95 %, charge normale 15 A, charge renforcée 20 A, seuil borne 500 W.
- Phénomènes par défaut, noms exacts des attributs de l'entité de vigilance : `"Vent violent"`, `"Orages"`, `"Neige-verglas"`, `"Grand-froid"`, `"Pluie-inondation"`. Niveaux actifs : `"Orange"`, `"Rouge"`.
- Couleur rouge : état exactement `"Rouge"` ; `"Bleu"`, `"Blanc"`, `"inconnu"`, `unknown`, `unavailable` ne sont pas rouges.
- Comparaison d'une valeur `number` relue : égale si `abs(réel - voulu) < 0.5` (`NUMBER_TOLERANCE`).
- Relecture attendue au plus 60 s (`READBACK_TIMEOUT`), trois essais par commande (`WRITE_ATTEMPTS`).
- Code commenté en français, docstrings en français ; README, CHANGELOG, ROADMAP en français.
- Commits en français, au format du dépôt (`feat: …`, `docs: …`, `test: …`), terminés par la ligne `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Tests : `.venv\Scripts\python.exe -m pytest` depuis la racine du dépôt (PowerShell).

## Décisions prises par ce plan (la spec ne les tranche pas)

1. **Remise aux valeurs normales** : seulement au passage Pilotage actif → coupé. Jamais à l'installation, jamais au redémarrage avec un état restauré « coupé ».
2. **Remise demandée pendant une coupure réseau** : elle reste en attente et part au retour du réseau, sauf si le Pilotage a été réactivé entre-temps.
3. **Vers le mode batterie** : le mode n'est écrit qu'après relecture des deux seuils à leur valeur voulue. Si un seuil échoue ou est indisponible, le mode n'est pas écrit. **Vers le mode réseau** : le mode est écrit en premier, sans condition.
4. **Ordre des seuils** : on choisit l'ordre dont l'état intermédiaire respecte `13 ≥ 12 + écart` ; si les deux le respectent, ou aucun, on applique la règle de la spec (13 d'abord s'il monte, sinon 12 d'abord).
5. **Notification d'échec** : une par épisode et par commande. Elle est effacée au premier succès suivant.
6. **Présence réseau** : non configurée = présente ; configurée = présente seulement si l'état vaut `on` (`off`, `unknown`, `unavailable` = absente). La fausse coupure de 3 à 8 s au démarrage de l'ESP ne fait que geler les écritures.
7. **Déclencheurs** : changement d'état d'une entrée (les 8 sources), changement du Pilotage, minuteur d'une minute. Les quatre commandes sont lues, jamais écoutées (sinon chaque relecture relancerait un calcul).
8. **Pilotage coupé pendant une séquence** : la séquence s'arrête avant l'écriture suivante.
9. **Écarts de forme assumés par rapport à la spec** : les valeurs « réseau » / « batterie » du select passent à l'étape 3 de l'assistant (leurs choix dépendent du select retenu à l'étape 2) ; l'objet d'instance vit dans `manager.py` et non dans `__init__.py`.

## Points de vigilance (Review Focus)

1. **Pilotage coupé au milieu d'un matin rouge** (12 écrit, 13 en attente) → aucune écriture après la coupure en dehors de la remise normale. Test : tâche 7, `test_pilotage_off_interrompt_sequence`.
2. **Redémarrage de HA avec le Pilotage restauré coupé** → zéro appel de service. Test : tâche 7, `test_redemarrage_pilotage_coupe_aucune_ecriture`.
3. **ESP Growatt hors ligne ou seuil jamais relu un matin rouge** → SBU jamais écrit, une seule notification en cinq minutes. Test : tâche 5, `test_echec_seuil_bloque_mode_et_notifie_une_fois`.
4. **Seuils réglés à la main hors invariant** (par exemple 50 / 50) → ordre choisi selon la décision 4, sans exception. Test : tâche 4, `test_seuils_hors_invariant`.
5. **Présence réseau qui passe `off` ou indisponible pendant une remise demandée** → la remise attend le retour du réseau. Test : tâche 7, `test_remise_reportee_pendant_coupure`.

---

## Fichiers

```
custom_components/energy_management/
  __init__.py          cycle de vie : crée le manager, plateformes, panneau
  manifest.json
  const.py             clés de configuration, défauts, constantes
  decision.py          Inputs, Settings, Targets, Decision, decide()  (pur)
  inputs.py            read_inputs(), settings_from_conf()
  reconciler.py        Actual, Write, read_actual(), plan_writes(), gaps(), Reconciler
  manager.py           EnergyManager : écoutes, minuteur, verrou, remise
  config_flow.py       assistant 3 étapes, OptionsFlow, validate_values()
  switch.py sensor.py binary_sensor.py
  frontend.py
  frontend/energy_management_panel.js
  strings.json  translations/fr.json  translations/en.json
tests/
  __init__.py conftest.py const.py
  test_manifest.py test_decision.py test_inputs.py test_plan_writes.py
  test_reconciler.py test_config_flow.py test_manager.py test_entities.py
  test_frontend.py
.github/workflows/tests.yaml  "Validate HACS.yaml"  "Validate Hassfest.yaml"
hacs.json pytest.ini requirements_test.txt LICENSE .gitignore .gitattributes
README.md CHANGELOG.md ROADMAP.md
```

---

### Tâche 1 : squelette du dépôt et environnement de test

**Fichiers :**
- Créer : `custom_components/energy_management/manifest.json`, `const.py`, `__init__.py` (vide pour l'instant, docstring seule), `hacs.json`, `pytest.ini`, `requirements_test.txt`, `LICENSE`, `.gitignore`, `.gitattributes`, les trois workflows, `tests/__init__.py`, `tests/conftest.py`, `tests/const.py`
- Test : `tests/test_manifest.py`

**Interfaces :**
- Produit (`const.py`) : `DOMAIN = "energy_management"` ; clés étape 1 `CONF_COLOR_TODAY = "color_today"`, `CONF_COLOR_TOMORROW = "color_tomorrow"`, `CONF_OFF_PEAK = "off_peak"`, `CONF_VIGILANCE = "vigilance"`, `CONF_PHENOMENA = "phenomena"`, `CONF_SOC = "soc"`, `CONF_EV_POWER = "ev_power"`, `CONF_GRID = "grid_presence"` ; étape 2 `CONF_MODE_SELECT = "mode_select"`, `CONF_LOW = "low_threshold"`, `CONF_HIGH = "high_threshold"`, `CONF_CHARGE = "charge_current"` ; étape 3 `CONF_OPTION_GRID = "option_grid"`, `CONF_OPTION_BATTERY = "option_battery"`, `CONF_RESERVE_NORMAL`, `CONF_RESERVE_VIGILANCE`, `CONF_GAP`, `CONF_LOW_NORMAL`, `CONF_HIGH_NORMAL`, `CONF_CHARGE_NORMAL`, `CONF_CHARGE_BOOST`, `CONF_EV_THRESHOLD`, `CONF_NOTIFY` (valeur = nom de la clé en minuscules) ; `DEFAULTS: dict[str, Any]` avec les valeurs des contraintes globales ; `DEFAULT_PHENOMENA: list[str]` (les 5) ; `KNOWN_PHENOMENA: list[str]` (les 5 + `"Inondation"`, `"Vagues-submersion"`, `"Canicule"`, `"Avalanches"`) ; `ACTIVE_LEVELS = ("Orange", "Rouge")` ; `RED = "Rouge"` ; `NUMBER_TOLERANCE = 0.5` ; `READBACK_TIMEOUT = 60` ; `WRITE_ATTEMPTS = 3` ; `UPDATE_INTERVAL = timedelta(minutes=1)` ; `signal_update(entry_id: str) -> str` (renvoie `f"{DOMAIN}_update_{entry_id}"`).
- Produit (`tests/const.py`) : les identifiants réels relevés le 08/11/2026 — `sensor.rte_tempo_couleur_actuelle`, `sensor.rte_tempo_prochaine_couleur`, `binary_sensor.rte_tempo_heures_creuses`, `sensor.76_weather_alert`, `sensor.sous_sol_docan_docan_soc_systeme`, `sensor.shelly_em_2_channel_1_power`, `binary_sensor.sous_sol_growatt_growatt_grid_available_ond1`, `select.sous_sol_growatt_growatt_output_priority_ond1`, `number.sous_sol_growatt_growatt_battery_low_to_utility_soc_setting_ond1`, `number.solaire_growatt_growatt_utility_back_to_battery_soc_setting_ond1`, `number.sous_sol_growatt_growatt_ac_charge_current_setting_ac1_ond1` ; `UTI = "UTI (Utility First)"`, `SBU = "SBU (Solar-Battery-Utility)"`, `SELECT_OPTIONS` (les quatre options réelles : SBU, `"SOL (Solar First)"`, UTI, `"SUB (Solar-Utility-Battery)"`) ; bornes `LOW_BOUNDS = (6, 95)`, `HIGH_BOUNDS = (10, 100)`, `CHARGE_BOUNDS = (0, 80)` ; `MOCK_CONF: dict` (configuration complète avec les défauts).
- Produit (`tests/conftest.py`) : fixture autouse `auto_enable_custom_integrations` ; fixture `base_states(hass)` qui pose une journée bleue normale (couleurs `"Bleu"`, heures creuses `off`, vigilance `"Vert"` avec les 7 attributs réels, SOC `"97.7"`, borne `"38"`, réseau `on`, select `UTI` avec `options=SELECT_OPTIONS`, seuils `50` / `95`, charge `15`, chaque `number` avec ses attributs `min` / `max` / `step: 1`) ; fixture `fake_inverter(hass)` qui enregistre `select.select_option` et `number.set_value`, recopie la valeur écrite dans l'état de l'entité, garde la liste `calls: list[tuple[str, Any]]` et un ensemble `deaf: set[str]` d'entités qui ignorent les écritures et un dictionnaire `delay: dict[str, float]` (secondes avant que l'état relu soit posé, par `async_call_later`) ; fixture `mock_entry()` → `MockConfigEntry(domain=DOMAIN, data=MOCK_CONF, unique_id=DOMAIN, version=1)`.

- [ ] **Étape 1 : créer l'environnement**

Run : `py -3.14 -m venv .venv` puis `.venv\Scripts\python.exe -m pip install -r requirements_test.txt`
`requirements_test.txt` : `pytest-homeassistant-custom-component==0.13.375`, `pytest-cov>=5.0` (ne pas épingler `homeassistant` séparément).
Expected : installation sans erreur, `homeassistant` 2026.10.x installé.

- [ ] **Étape 2 : écrire le test qui échoue**

```python
def test_manifest():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["domain"] == "energy_management"
    assert data["name"] == "Energy Management"
    assert data["version"] == "0.1.0"
    assert data["single_config_entry"] is True
    assert data["config_flow"] is True
    assert data["iot_class"] == "calculated"
    assert set(data["dependencies"]) == {"http", "frontend", "panel_custom"}

def test_defaults():
    assert DEFAULTS[CONF_RESERVE_NORMAL] == 30 and DEFAULTS[CONF_RESERVE_VIGILANCE] == 50
    assert DEFAULTS[CONF_GAP] == 5
    assert (DEFAULTS[CONF_LOW_NORMAL], DEFAULTS[CONF_HIGH_NORMAL]) == (50, 95)
    assert (DEFAULTS[CONF_CHARGE_NORMAL], DEFAULTS[CONF_CHARGE_BOOST]) == (15, 20)
    assert DEFAULTS[CONF_EV_THRESHOLD] == 500
    assert DEFAULT_PHENOMENA == ["Vent violent", "Orages", "Neige-verglas", "Grand-froid", "Pluie-inondation"]
```

- [ ] **Étape 3 : lancer, vérifier l'échec**

Run : `.venv\Scripts\python.exe -m pytest tests/test_manifest.py -v` — Expected : FAIL (fichiers absents).

- [ ] **Étape 4 : écrire les fichiers**

Recopier les conventions des voisins (`D:\sources\Home Assistant\HA Integration\shutters_management` pour `hacs.json`, workflows et `pyproject`/`pytest.ini` ; `pool_control` pour `LICENSE`, `.gitignore`, `.gitattributes`). `hacs.json` : `"name": "Energy Management"`, `"homeassistant": "2026.3.0"`. Workflow de tests : Python **3.14** (HA 2026.10 exige 3.14.2), sans l'étape « markers » de `pool_control`. `.gitignore` ajoute `.venv/`. `pytest.ini` : `testpaths = tests`, `asyncio_mode = auto`, `addopts = -ra`.

- [ ] **Étape 5 : lancer, vérifier le succès** — Run : même commande — Expected : 2 passed.

- [ ] **Étape 6 : commit** — `git add -A` puis `git commit -m "feat: squelette de l'extension et environnement de test"`

---

### Tâche 2 : décision (`decision.py`)

**Fichiers :** Créer `custom_components/energy_management/decision.py` — Test `tests/test_decision.py`

**Interfaces :**
- Consomme : rien (Python pur, n'importe pas Home Assistant).
- Produit :

```python
MODE_GRID = "grid"; MODE_BATTERY = "battery"
STATE_GRID = "reseau"; STATE_BATTERY = "batterie"
STATE_BOOST = "charge_renforcee"; STATE_OUTAGE = "coupure_reseau"
STATES = [STATE_GRID, STATE_BATTERY, STATE_BOOST, STATE_OUTAGE]

@dataclass(frozen=True)
class Inputs:
    grid_present: bool
    today_red: bool
    tomorrow_red: bool
    off_peak: bool | None              # None = inconnu
    vigilance: tuple[tuple[str, str], ...]   # (phénomène, niveau) actifs
    vigilance_unknown: bool
    soc: float | None
    ev_charging: bool

@dataclass(frozen=True)
class Settings:
    reserve_normal: int; reserve_vigilance: int; gap: int
    low_normal: int; high_normal: int
    charge_normal: int; charge_boost: int

@dataclass(frozen=True)
class Targets:
    mode: str; low: float; high: float; charge: float

@dataclass(frozen=True)
class Decision:
    state: str; reason: str; reserve: int; targets: Targets | None

def normal_targets(settings: Settings) -> Targets
def decide(inputs: Inputs, settings: Settings, previous: Targets | None = None) -> Decision
```

Règles (spec § 4.3 et § 8.2, évaluées dans cet ordre) :
- réserve = `reserve_vigilance` si `vigilance` non vide ou `vigilance_unknown`, sinon `reserve_normal` ; calculée dans tous les cas.
- `grid_present` faux → `STATE_OUTAGE`, `targets = previous`, raison `"Réseau absent, aucune écriture"`.
- `today_red` et `off_peak is False` : si `soc is None` → `STATE_GRID`, cibles normales, raison `"Jour rouge, SOC inconnu : réseau"` ; sinon `STATE_BATTERY`, `Targets(MODE_BATTERY, réserve, réserve + gap, charge_normal)`, raison `"Jour rouge, réserve {réserve} %"` suivie de `" (vigilance {phénomène} {niveau})"` en minuscules, plusieurs phénomènes séparés par `", "`, ou `" (vigilance inconnue)"`.
- `off_peak is True` et `tomorrow_red` : si `ev_charging` → `STATE_GRID`, cibles normales, raison `"Lendemain rouge, borne en charge : charge normale"` ; sinon `STATE_BOOST`, cibles normales avec `charge = charge_boost`, raison `"Lendemain rouge : charge renforcée {charge_boost} A"`.
- `off_peak is None` → `STATE_GRID`, cibles normales, raison `"Heures creuses inconnues : réseau"`.
- sinon `STATE_GRID`, cibles normales, raison `"Fonctionnement normal"`.

- [ ] **Étape 1 : écrire les tests qui échouent**

Une fabrique `make_inputs(**overrides)` (défauts : réseau présent, rien de rouge, `off_peak=False`, aucune vigilance, `soc=80.0`, borne à l'arrêt) et `SETTINGS = Settings(30, 50, 5, 50, 95, 15, 20)`.

```python
def test_jour_normal():          # targets == Targets("grid", 50, 95, 15), state "reseau"
def test_jour_rouge_hp():        # today_red, off_peak False → Targets("battery", 30, 35, 15), state "batterie", reason "Jour rouge, réserve 30 %"
def test_jour_rouge_vigilance(): # vigilance=(("Vent violent", "Orange"),) → Targets("battery", 50, 55, 15), reason "Jour rouge, réserve 50 % (vigilance vent violent orange)"
def test_jour_rouge_deux_vigilances():  # reason se termine par "(vigilance vent violent orange, orages rouge)"
def test_jour_rouge_vigilance_inconnue(): # vigilance_unknown → réserve 50, reason finit par "(vigilance inconnue)"
def test_jour_rouge_heures_creuses():     # today_red, off_peak True, tomorrow non rouge → normal
def test_jour_rouge_soc_inconnu():        # soc None → state "reseau", Targets("grid", 50, 95, 15)
def test_jour_rouge_hc_inconnues():       # off_peak None → normal, reason "Heures creuses inconnues : réseau"
def test_veille_rouge_hc():               # off_peak True, tomorrow_red → state "charge_renforcee", charge 20
def test_veille_rouge_borne_en_charge():  # + ev_charging → state "reseau", charge 15
def test_veille_rouge_hors_hc():          # off_peak False, tomorrow_red → normal
def test_rouge_aujourdhui_et_demain_nuit(): # today_red, tomorrow_red, off_peak True → charge_renforcee
def test_coupure_garde_cibles_precedentes():  # grid_present False, previous=X → targets is X, state "coupure_reseau"
def test_coupure_sans_precedent():        # previous None → targets None
def test_reserve_toujours_calculee():     # journée bleue avec vigilance → decision.reserve == 50
```

- [ ] **Étape 2 : lancer, vérifier l'échec** — Run : `.venv\Scripts\python.exe -m pytest tests/test_decision.py -v` — Expected : FAIL (module absent).
- [ ] **Étape 3 : écrire `decision.py`** selon les règles ci-dessus.
- [ ] **Étape 4 : lancer, vérifier le succès** — Expected : 15 passed.
- [ ] **Étape 5 : commit** — `feat: calcul de l'état voulu`

---

### Tâche 3 : lecture des entrées (`inputs.py`)

**Fichiers :** Créer `custom_components/energy_management/inputs.py` — Test `tests/test_inputs.py`

**Interfaces :**
- Consomme : `Inputs`, `Settings` (tâche 2) ; constantes de `const.py`.
- Produit :

```python
def read_inputs(hass: HomeAssistant, conf: Mapping[str, Any]) -> Inputs
def settings_from_conf(conf: Mapping[str, Any]) -> Settings   # valeurs absentes → DEFAULTS
def input_entities(conf: Mapping[str, Any]) -> list[str]      # les sources configurées, sans None
```

Règles (spec § 8.2) : couleur rouge ⇔ état `== RED` ; heures creuses `on` → True, `off` → False, autre ou absente → None ; vigilance absente, `unknown` ou `unavailable` → `vigilance_unknown=True` ; sinon un phénomène configuré est actif si son attribut est dans `ACTIVE_LEVELS`, un attribut manquant est ignoré ; SOC = `float(état)` si convertible et dans 0–100, sinon None ; borne en charge si l'état n'est pas convertible ou si `float(état) > seuil` (strictement) ; présence réseau selon la décision 6.

- [ ] **Étape 1 : écrire les tests qui échouent** (avec `hass` et `base_states`)

```python
async def test_journee_bleue(hass, base_states):   # read_inputs → today_red False, off_peak False, vigilance (), soc 97.7, ev_charging False, grid_present True
async def test_rouge(hass, base_states):           # couleur "Rouge" → today_red True
@pytest.mark.parametrize("etat", ["Bleu", "Blanc", "inconnu", "unknown", "unavailable"])
async def test_couleur_non_rouge(hass, base_states, etat):   # today_red False
async def test_entite_couleur_absente(hass, base_states):    # hass.states.async_remove → today_red False
async def test_heures_creuses_indisponibles(hass, base_states):  # off_peak is None
async def test_vigilance_orange(hass, base_states):  # attribut "Vent violent": "Orange" → vigilance == (("Vent violent", "Orange"),)
async def test_vigilance_jaune_ignoree(hass, base_states):  # "Orages": "Jaune" → ()
async def test_vigilance_phenomene_non_surveille(hass, base_states):  # "Vagues-submersion": "Rouge" → ()
async def test_vigilance_indisponible(hass, base_states):  # vigilance_unknown True
@pytest.mark.parametrize("etat", ["unknown", "unavailable", "abc", "-5", "120"])
async def test_soc_invalide(hass, base_states, etat):  # soc is None
@pytest.mark.parametrize("etat,attendu", [("500", False), ("500.1", True), ("unavailable", True)])
async def test_borne(hass, base_states, etat, attendu):
@pytest.mark.parametrize("etat,attendu", [("on", True), ("off", False), ("unavailable", False), ("unknown", False)])
async def test_presence_reseau(hass, base_states, etat, attendu):
async def test_presence_reseau_non_configuree(hass, base_states):  # conf sans CONF_GRID → True
def test_settings_from_conf():  # MOCK_CONF → Settings(30, 50, 5, 50, 95, 15, 20) ; conf vide → mêmes valeurs
def test_input_entities():      # 8 entités avec MOCK_CONF, 7 sans CONF_GRID
```

- [ ] **Étape 2 : lancer, vérifier l'échec** — `pytest tests/test_inputs.py -v` — FAIL.
- [ ] **Étape 3 : écrire `inputs.py`.**
- [ ] **Étape 4 : lancer, vérifier le succès.**
- [ ] **Étape 5 : commit** — `feat: lecture prudente des entrées`

---

### Tâche 4 : ordre des écritures (`plan_writes`)

**Fichiers :** Créer `custom_components/energy_management/reconciler.py` (partie pure) — Test `tests/test_plan_writes.py`

**Interfaces :**
- Consomme : `Targets`, `MODE_GRID`, `MODE_BATTERY` (tâche 2) ; `NUMBER_TOLERANCE`.
- Produit :

```python
CMD_MODE = "mode"; CMD_LOW = "low"; CMD_HIGH = "high"; CMD_CHARGE = "charge"
COMMANDS = (CMD_MODE, CMD_LOW, CMD_HIGH, CMD_CHARGE)

@dataclass(frozen=True)
class Actual:
    mode: str | None     # MODE_GRID, MODE_BATTERY, autre option brute, ou None si indisponible
    low: float | None; high: float | None; charge: float | None

@dataclass(frozen=True)
class Write:
    command: str; value: str | float     # value = MODE_* pour CMD_MODE

def same(actual: float | None, wanted: float) -> bool
def plan_writes(actual: Actual, desired: Targets, gap: float) -> list[Write]
def compute_gaps(actual: Actual, desired: Targets) -> list[str]   # commandes en écart ou indisponibles, dans l'ordre de COMMANDS
```

Règles : rien pour une commande déjà en place (`same`) ou indisponible (None). Seuils ordonnés selon la décision 4. Vers la batterie : seuils, puis mode ; mode omis si `low` ou `high` est None. Vers le réseau : mode, puis seuils. Mode inchangé : seuils seuls. Charge toujours en dernier.

- [ ] **Étape 1 : écrire les tests qui échouent**

Une aide `apply(actual, writes)` rejoue les écritures et renvoie la liste des couples (12, 13) intermédiaires.

```python
def test_matin_rouge():   # Actual("grid", 50, 95, 15) → Targets("battery", 30, 35, 15) : [low 30, high 35, mode battery] ; intermédiaires (30,95), (30,35)
def test_soir_rouge():    # Actual("battery", 30, 35, 15) → normal : [mode grid, high 95, low 50] ; intermédiaires (30,95), (50,95)
def test_vigilance_en_journee():  # Actual("battery", 30, 35, 15) → Targets("battery", 50, 55, 15) : [high 55, low 50]
def test_vigilance_levee():       # (50,55) → (30,35) : [low 30, high 35]
def test_invariant_a_chaque_etape():  # pour toutes les paires (départ, arrivée) dans {(50,95),(30,35),(50,55),(30,95)} : chaque intermédiaire vérifie 13 >= 12 + 5
def test_seuils_hors_invariant():     # Actual("grid", 50, 50, 15) → Targets("battery", 30, 35, 15) : [low 30, high 35, mode] sans exception
def test_rien_a_ecrire():         # Actual == cibles → []
def test_tolerance():             # Actual("grid", 50.3, 94.6, 15.0) → []
def test_charge_en_dernier():     # Actual("grid", 50, 95, 15) → boost 20 : [charge 20] ; avec seuils à changer, charge reste dernière
def test_seuil_indisponible_bloque_batterie():  # Actual("grid", None, 95, 15) → batterie : [high 35] seulement, pas de mode
def test_mode_indisponible():     # Actual(None, 50, 95, 15) → batterie : [low 30, high 35]
def test_mode_inconnu():          # Actual("SOL (Solar First)", 50, 95, 15) → normal : [mode grid]
def test_compute_gaps():          # Actual("grid", None, 95, 20) vs normal → ["low", "charge"]
```

- [ ] **Étape 2 : lancer, vérifier l'échec.**
- [ ] **Étape 3 : écrire la partie pure de `reconciler.py`.**
- [ ] **Étape 4 : lancer, vérifier le succès.**
- [ ] **Étape 5 : commit** — `feat: ordre des écritures et invariant des seuils`

---

### Tâche 5 : exécuteur des écritures (`Reconciler`)

**Fichiers :** Modifier `custom_components/energy_management/reconciler.py` — Test `tests/test_reconciler.py`

**Interfaces :**
- Consomme : `plan_writes`, `Write`, `Actual` (tâche 4) ; `fake_inverter`, `base_states` (tâche 1).
- Produit :

```python
def read_actual(hass: HomeAssistant, conf: Mapping[str, Any]) -> Actual
    # select : CONF_OPTION_GRID → MODE_GRID, CONF_OPTION_BATTERY → MODE_BATTERY, autre option → brute, unknown/unavailable/absent → None
    # number : float(état) ou None

class Reconciler:
    def __init__(self, hass: HomeAssistant, conf: Mapping[str, Any]) -> None
    @property
    def busy(self) -> bool
    async def async_apply(self, desired: Targets, gap: float,
                          should_continue: Callable[[], bool] = lambda: True) -> bool
        # True si toutes les écritures planifiées ont été relues ; ne fait rien et renvoie False si busy
```

Comportement : verrou `asyncio.Lock`, une séquence à la fois (`busy`). Pour chaque `Write`, vérifier `should_continue()` avant d'écrire. Une écriture = `select.select_option` (`option` = `CONF_OPTION_GRID` / `CONF_OPTION_BATTERY`) ou `number.set_value` (`value`), `blocking=True`, puis attente que l'état relu soit égal (`same` pour les nombres) au plus `READBACK_TIMEOUT` s, avec `async_track_state_change_event` et un `asyncio.Event` ; contrôler l'état courant avant d'attendre. Jusqu'à `WRITE_ATTEMPTS` essais ; une exception du service compte comme un essai raté. Échec : arrêter la séquence (décision 3), créer la notification persistante `notification_id=f"{DOMAIN}_echec_{command}"`, titre `"Energy Management"`, message nommant la commande, l'entité et la valeur voulue ; appeler `notify.<service>` si `CONF_NOTIFY` est renseigné. Une seule notification par épisode (décision 5) : mémoriser les commandes en échec, effacer (`persistent_notification.async_dismiss`) au premier succès.

- [ ] **Étape 1 : écrire les tests qui échouent** (`monkeypatch` de `reconciler.READBACK_TIMEOUT` à 0.05)

```python
async def test_matin_rouge_ordre_des_appels(hass, base_states, fake_inverter):
    # async_apply(Targets("battery", 30, 35, 15), 5) → True
    # fake_inverter.calls == [(LOW, 30), (HIGH, 35), (SELECT, SBU)]
async def test_soir_rouge_ordre_des_appels(...):      # [(SELECT, UTI), (HIGH, 95), (LOW, 50)]
async def test_aucune_reecriture(...):                # cibles déjà en place → calls == []
async def test_attend_la_relecture(...):              # delay[LOW] = 0.02 → l'écriture du 13 part après la relecture du 12
async def test_trois_essais(...):                     # LOW dans deaf → 3 appels sur LOW, résultat False
async def test_echec_seuil_bloque_mode_et_notifie_une_fois(hass, base_states, fake_inverter):
    # LOW sourd ; 5 appels successifs d'async_apply → aucun appel sur SELECT,
    # une seule notification persistante "energy_management_echec_low"
async def test_succes_efface_la_notification(...):    # LOW sourd puis entendu → notification retirée
async def test_service_notify_appele(...):            # CONF_NOTIFY = "notify.test" (service simulé) → appelé une fois par épisode
async def test_une_sequence_a_la_fois(...):           # deux async_apply lancés ensemble → le second renvoie False sans appel
async def test_should_continue(...):                  # should_continue passe à False après la 1re écriture → une seule écriture
async def test_exception_du_service(...):             # le service lève HomeAssistantError → compte comme essai raté
def test_read_actual(hass, base_states):              # Actual("grid", 50.0, 95.0, 15.0) ; select "SOL (Solar First)" → mode brut ; number unavailable → None
```

- [ ] **Étape 2 : lancer, vérifier l'échec.**
- [ ] **Étape 3 : écrire `read_actual` et `Reconciler`.**
- [ ] **Étape 4 : lancer, vérifier le succès.** — Run : `pytest tests/test_reconciler.py tests/test_plan_writes.py -v`
- [ ] **Étape 5 : commit** — `feat: écritures séquentielles avec relecture et essais`

---

### Tâche 6 : assistant de configuration et options

**Fichiers :** Créer `config_flow.py`, `strings.json`, `translations/fr.json`, `translations/en.json` — Test `tests/test_config_flow.py`

**Interfaces :**
- Consomme : constantes de `const.py`.
- Produit :

```python
class EnergyManagementConfigFlow(ConfigFlow, domain=DOMAIN):  # VERSION = 1
    async def async_step_user(self, user_input=None)      # étape 1 « sources »
    async def async_step_commands(self, user_input=None)  # étape 2
    async def async_step_values(self, user_input=None)    # étape 3, puis async_create_entry(title="Energy Management", data=...)
    @staticmethod
    def async_get_options_flow(entry) -> EnergyManagementOptionsFlow

class EnergyManagementOptionsFlow(OptionsFlow):  # mêmes trois étapes : init, commands, values ; préremplies avec {**data, **options} ; enregistre le tout dans options

def validate_values(hass: HomeAssistant, conf: Mapping[str, Any]) -> dict[str, str]   # {champ: clé d'erreur}
```

Sélecteurs : étape 1 `EntitySelector` (`sensor` pour couleurs, vigilance, SOC, borne ; `binary_sensor` pour heures creuses et présence réseau, celle-ci facultative), `SelectSelector` multiple pour `CONF_PHENOMENA` (options `KNOWN_PHENOMENA`, `custom_value=True`, défaut `DEFAULT_PHENOMENA`). Étape 2 : `select` pour le mode, `number` pour les trois seuils. Étape 3 : `SelectSelector` pour `CONF_OPTION_GRID` / `CONF_OPTION_BATTERY` construits avec les `options` du select choisi (présélection : l'option qui commence par `"UTI"` / `"SBU"`, sinon la première), `NumberSelector` pour les valeurs, `SelectSelector` facultatif pour `CONF_NOTIFY` listant `notify.<service>` de `hass.services.async_services_for_domain("notify")`.

Contrôles (`validate_values`, spec § 5) : `reserve_vigilance < reserve_normal` → `reserve_order` sur `CONF_RESERVE_VIGILANCE` ; `high_normal < low_normal + gap` → `gap_order` sur `CONF_HIGH_NORMAL` ; `option_grid == option_battery` → `same_option` sur `CONF_OPTION_BATTERY` ; option absente des options du select → `option_missing` ; bornes lues dans les attributs `min` / `max` de chaque `number` (contrôle sauté si l'entité ou ses attributs manquent), erreur `out_of_bounds` sur le champ fautif : seuil 12 pour `reserve_normal`, `reserve_vigilance`, `low_normal` ; seuil 13 pour `reserve_normal + gap`, `reserve_vigilance + gap`, `high_normal` (erreur portée par la réserve ou par `CONF_GAP`) ; charge pour `charge_normal`, `charge_boost`.

Textes : `strings.json` et `translations/en.json` identiques, en anglais ; `translations/fr.json` en français, avec les intitulés de la spec § 5 et la mise en garde N-PE en description de l'étape 1 (« Le Pilotage reste coupé tant que la liaison N-PE n'a pas été mesurée. »). Les mêmes fichiers portent les noms d'entités (`entity.switch.pilotage.name` = « Pilotage », `entity.sensor.mode_voulu.name` = « Mode voulu » et ses quatre états, `entity.sensor.raison.name` = « Raison », `entity.sensor.reserve_active.name` = « Réserve active », `entity.binary_sensor.ecart.name` = « Écart »).

- [ ] **Étape 1 : écrire les tests qui échouent**

```python
async def test_parcours_complet(hass, base_states):
    # user → commands → values avec les valeurs de MOCK_CONF → CREATE_ENTRY, data == MOCK_CONF
async def test_options_de_l_etape_3(hass, base_states):
    # le schéma de values propose SELECT_OPTIONS, défauts UTI et SBU
async def test_une_seule_instance(hass, base_states, mock_entry):  # 2e flux → abort "single_instance_allowed"
@pytest.mark.parametrize("champ,valeur,erreur", [
    (CONF_RESERVE_VIGILANCE, 20, "reserve_order"),
    (CONF_HIGH_NORMAL, 54, "gap_order"),
    (CONF_LOW_NORMAL, 96, "out_of_bounds"),
    (CONF_RESERVE_NORMAL, 3, "out_of_bounds"),
    (CONF_CHARGE_BOOST, 90, "out_of_bounds"),
    (CONF_OPTION_BATTERY, UTI, "same_option"),
])
async def test_controles(hass, base_states, champ, valeur, erreur):  # formulaire values réaffiché avec errors == {champ: erreur}
async def test_bornes_ignorees_si_entite_absente(hass, base_states):  # number retiré → pas d'out_of_bounds
async def test_options_flow(hass, base_states, mock_entry):  # init → commands → values, charge renforcée 18 → entry.options[CONF_CHARGE_BOOST] == 18
async def test_traductions_coherentes():  # mêmes clés dans strings.json, en.json, fr.json
```

- [ ] **Étape 2 : lancer, vérifier l'échec.**
- [ ] **Étape 3 : écrire `config_flow.py` et les trois fichiers de textes.** `__init__.py` reçoit `async_setup_entry` / `async_unload_entry` minimaux renvoyant True (complétés en tâche 7).
- [ ] **Étape 4 : lancer, vérifier le succès.**
- [ ] **Étape 5 : commit** — `feat: assistant de configuration et options`

---

### Tâche 7 : manager, cycle de vie et interrupteur Pilotage

**Fichiers :** Créer `manager.py`, `switch.py` ; modifier `__init__.py` — Test `tests/test_manager.py`

**Interfaces :**
- Consomme : `read_inputs`, `settings_from_conf`, `input_entities` (tâche 3) ; `decide`, `normal_targets` (tâche 2) ; `read_actual`, `compute_gaps`, `Reconciler` (tâches 4-5) ; `signal_update`.
- Produit :

```python
class EnergyManager:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None
    conf: dict[str, Any]              # {**entry.data, **entry.options}
    settings: Settings
    pilotage: bool                    # False au départ
    decision: Decision | None
    gaps: list[str]
    reset_pending: bool
    async def async_start(self) -> None   # écoutes (décision 7), minuteur UPDATE_INTERVAL, premier calcul
    async def async_stop(self) -> None
    async def async_refresh(self) -> None
    async def async_set_pilotage(self, on: bool, *, restored: bool = False) -> None
```

`async_refresh` : lire les entrées, `decide(inputs, settings, previous=dernières cibles)`, calculer `self.gaps = compute_gaps(...)` si des cibles existent, envoyer `signal_update(entry_id)`. Puis, si le réseau est présent (état différent de `STATE_OUTAGE`) : si `reset_pending` et Pilotage coupé → `async_apply(normal_targets)` et `reset_pending = False` en cas de succès ; sinon si Pilotage actif → `async_apply(decision.targets, gap, should_continue=lambda: self.pilotage)`. Recalculer les écarts et renvoyer le signal après une séquence.
`async_set_pilotage(False)` d'un état actif, sans `restored` → `reset_pending = True` (décision 1) ; `async_set_pilotage(True)` → `reset_pending = False`. Puis `async_refresh`.

`switch.py` : `PilotageSwitch(SwitchEntity, RestoreEntity)`, `translation_key="pilotage"`, `unique_id=f"{entry_id}_pilotage"`, `has_entity_name=True`, appareil « Energy Management » (`identifiers={(DOMAIN, entry_id)}`). À l'ajout : état restauré `on` → `async_set_pilotage(True, restored=True)` ; sinon rien.
`__init__.py` : `PLATFORMS = ["switch"]` (la tâche 8 ajoute `sensor` et `binary_sensor`), manager dans `entry.runtime_data`, `async_start` après les plateformes, `async_stop` au déchargement, rechargement de l'entrée à la mise à jour des options.

- [ ] **Étape 1 : écrire les tests qui échouent** (avec `async_fire_time_changed` et `mock_restore_cache`)

```python
async def test_pilotage_coupe_aucune_ecriture(hass, base_states, fake_inverter, mock_entry):
    # couleur "Rouge" → manager.decision.state == "batterie", manager.gaps == ["mode", "low", "high"], calls == []
async def test_pilotage_actif_matin_rouge(...):  # switch on, couleur Rouge → calls == [(LOW,30),(HIGH,35),(SELECT,SBU)]
async def test_minuteur(...):                    # Pilotage actif, état réel modifié à la main (seuil 12 à 40) → corrigé après +61 s
async def test_commandes_non_ecoutees(...):      # changer l'état d'un number ne déclenche aucun calcul avant le minuteur
async def test_coupure_pilotage_remet_les_normales(...):  # jour rouge en SBU 30/35, switch off → calls se terminent par [(SELECT,UTI),(HIGH,95),(LOW,50)], puis plus rien après +61 s
async def test_redemarrage_pilotage_coupe_aucune_ecriture(...):  # restore cache "off", seuils réels à 30/35 → calls == [] après +120 s
async def test_redemarrage_pilotage_actif(...):  # restore cache "on" → Pilotage actif, réconciliation faite
async def test_reseau_absent_gel(...):           # Pilotage actif, réseau off, couleur Rouge → calls == [], state "coupure_reseau"
async def test_remise_reportee_pendant_coupure(...):  # Pilotage actif en SBU, réseau off, switch off → calls == [] ; réseau on → remise aux normales
async def test_pilotage_off_interrompt_sequence(...):  # delay[HIGH] = 0.5 (READBACK_TIMEOUT monkeypatché à 1) ; switch off pendant l'attente → aucune écriture SBU
async def test_dechargement(...):                # async_unload → plus aucun calcul au minuteur
```

- [ ] **Étape 2 : lancer, vérifier l'échec.**
- [ ] **Étape 3 : écrire `manager.py`, `switch.py`, compléter `__init__.py`.**
- [ ] **Étape 4 : lancer, vérifier le succès.** — Run : `pytest -v` (toute la suite).
- [ ] **Étape 5 : commit** — `feat: manager, cycle de vie et interrupteur Pilotage`

---

### Tâche 8 : capteurs Mode voulu, Raison, Réserve active, Écart

**Fichiers :** Créer `sensor.py`, `binary_sensor.py` ; modifier `__init__.py` (plateformes) — Test `tests/test_entities.py`

**Interfaces :**
- Consomme : `EnergyManager.decision`, `.gaps`, `signal_update` (tâche 7) ; `STATES` (tâche 2) ; `COMMANDS` (tâche 4).
- Produit (identifiants uniques `f"{entry_id}_{clé}"`, `has_entity_name=True`, même appareil que le switch) :
  - `mode_voulu` : `SensorDeviceClass.ENUM`, `options=STATES`, attributs `mode`, `seuil_12`, `seuil_13`, `charge` (cibles, None si aucune) ;
  - `raison` : texte (`decision.reason`) ;
  - `reserve_active` : unité `%`, valeur `decision.reserve` ;
  - `ecart` : `BinarySensorDeviceClass.PROBLEM`, allumé si `gaps` non vide, attribut `commandes` = libellés français dans l'ordre de `COMMANDS` : `"Mode de sortie"`, `"Seuil 12"`, `"Seuil 13"`, `"Charge réseau"`.
  - Toutes s'abonnent à `signal_update(entry_id)` via `async_dispatcher_connect`.

- [ ] **Étape 1 : écrire les tests qui échouent**

```python
async def test_entites_creees(hass, base_states, mock_entry):  # 5 entités enregistrées pour l'entrée, par unique_id
async def test_journee_normale(...):   # mode_voulu "reseau", raison "Fonctionnement normal", reserve_active "30", ecart off
async def test_jour_rouge_pilotage_coupe(...):  # mode_voulu "batterie", attributs seuil_12 30, seuil_13 35 ; ecart on, commandes ["Mode de sortie", "Seuil 12", "Seuil 13"]
async def test_vigilance(...):         # attribut "Vent violent" à "Orange" → reserve_active "50"
async def test_commande_indisponible(...):  # charge unavailable → ecart on, commandes ["Charge réseau"]
```

- [ ] **Étape 2 : lancer, vérifier l'échec.**
- [ ] **Étape 3 : écrire `sensor.py`, `binary_sensor.py`, ajouter les plateformes.**
- [ ] **Étape 4 : lancer, vérifier le succès** (toute la suite).
- [ ] **Étape 5 : commit** — `feat: entités d'état`

---

### Tâche 9 : panneau latéral

**Fichiers :** Créer `frontend.py`, `frontend/energy_management_panel.js` ; modifier `__init__.py` — Test `tests/test_frontend.py`

**Interfaces :**
- Consomme : registre d'entités, `entry.runtime_data`, conf.
- Produit :

```python
PANEL_URL_PATH = "energy-management"; PANEL_TITLE = "Energy Management"
PANEL_ICON = "mdi:home-battery"; PANEL_NAME = "energy-management-panel"
STATIC_PATH = "/energy_management_static"; JS_FILENAME = "energy_management_panel.js"
async def async_register_panel(hass: HomeAssistant, entry: ConfigEntry) -> None
async def async_unregister_panel(hass: HomeAssistant) -> None
```

Même mécanique que `pool_control/custom_components/pool_control/frontend.py` (chemin statique servi une fois, `panel_custom.async_register_panel`, `require_admin=False`, `embed_iframe=False`, enregistrement idempotent), sans le multi-instance. `config` transmis au panneau : identifiants des cinq entités créées, retrouvés par `er.async_get(hass).async_get_entity_id(domaine, DOMAIN, unique_id)` (ne jamais deviner les slugs, ils dépendent de la langue), plus les sources et commandes de la conf sous leurs clés `CONF_*`. Enregistré après `async_start`, retiré au déchargement.

Le JS reprend le squelette de `pool_control_panel.js` lignes 23-62 : `class EnergyManagementPanel extends HTMLElement`, shadow DOM, `set hass` (rendu au premier passage, `this.panel.config`), `set panel`, `set narrow`, `customElements.define("energy-management-panel", …)`. Cinq blocs indépendants (spec § 7), chacun une méthode `_render<Bloc>()` : en-tête (Pilotage avec `confirm()` en français avant `hass.callService("switch", "turn_on" | "turn_off", { entity_id })`, pastille Écart) ; aujourd'hui / demain ; batterie ; décision ; onduleurs (tableau commande / voulu / réel, voulu lu dans les attributs de Mode voulu). Couleurs par les variables CSS de HA. Aucun autre appel de service.

- [ ] **Étape 1 : écrire les tests qui échouent**

```python
async def test_panneau_enregistre(hass, base_states, mock_entry):
    # avec patch de panel_custom.async_register_panel : appelé une fois, frontend_url_path "energy-management",
    # webcomponent_name "energy-management-panel", sidebar_icon "mdi:home-battery",
    # config["pilotage_entity"] == id réel du switch dans le registre, config[CONF_MODE_SELECT] == SELECT
async def test_panneau_retire_au_dechargement(...):  # frontend.async_remove_panel appelé avec "energy-management"
def test_fichier_js_present():  # le fichier existe et contient 'customElements.define("energy-management-panel"'
def test_js_un_seul_service():  # le JS ne contient qu'un callService, sur le domaine "switch"
```

- [ ] **Étape 2 : lancer, vérifier l'échec.**
- [ ] **Étape 3 : écrire `frontend.py` et le panneau, brancher dans `__init__.py`.**
- [ ] **Étape 4 : lancer, vérifier le succès** (toute la suite).
- [ ] **Étape 5 : contrôle visuel facultatif** sur une instance Home Assistant de développement **seulement** si l'utilisateur en fournit une ; jamais sur le serveur de production 192.168.0.169.
- [ ] **Étape 6 : commit** — `feat: panneau latéral`

---

### Tâche 10 : documentation et vérification finale

**Fichiers :** Créer `README.md`, `CHANGELOG.md`, `ROADMAP.md`

- [ ] **Étape 1 : `README.md`**, en français, sur le modèle de `shutters_management/README.md` : en tête, l'avertissement N-PE de la spec § 2 avec la mesure à faire ; puis fonctionnement (table de décision § 4.3), installation HACS (dépôt personnalisé), configuration (table § 5), entités (§ 6), panneau (§ 7), sécurités (§ 8), mise en service (§ 11), points ouverts (§ 12).
- [ ] **Étape 2 : `CHANGELOG.md`** : entrée `## [0.1.0] - 2026-11-08` listant les fonctions du périmètre (spec § 3).
- [ ] **Étape 3 : `ROADMAP.md`** : les pistes hors périmètre de la spec § 3, plus la vérification de `sensor.rte_tempo_prochaine_couleur` entre minuit et 6 h.
- [ ] **Étape 4 : vérification complète** — Run : `.venv\Scripts\python.exe -m pytest --cov=custom_components.energy_management --cov-report=term-missing` — Expected : tout passe ; `decision.py` et `reconciler.py` couverts à 100 %.
- [ ] **Étape 5 : contrôle des identifiants en dur** — Run : `git grep -n "sous_sol_\|solaire_growatt\|rte_tempo\|76_weather\|shelly_em" -- custom_components` — Expected : aucune ligne.
- [ ] **Étape 6 : commit** — `docs: README, CHANGELOG et ROADMAP de la version 0.1.0`
