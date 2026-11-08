# Energy Management — conception de la version 0.1.0

*Date : 08/11/2026. Statut : conception validée section par section en conversation,
en attente de relecture du document.*

## 1. Objectif

Extension Home Assistant `energy_management` (« Energy Management ») qui pilote une
installation de stockage domestique selon le tarif EDF **Tempo**, avec deux objectifs
d'égale importance :

- **secours** : garder une réserve d'énergie pour une coupure réseau ;
- **économie** : alimenter la maison sur batterie pendant les heures pleines des jours
  rouges, seul cas rentable (écart ~0,44 €/kWh contre ~0,01 €/kWh un jour blanc).

Installation de référence : deux onduleurs Growatt SPF 6000 ES Plus en parallèle,
deux packs LiFePO4 Docan (~650 Ah, ~33 kWh), réglages accessibles par les entités de
l'ESP Growatt existant. Toute la maison sauf la piscine et la borne de recharge est
câblée derrière les onduleurs (chantier électrique conduit séparément).

L'extension ne connaît **aucun identifiant d'entité en dur** : toutes les sources et
commandes sont choisies dans l'assistant de configuration, comme pour `pool_control`.

## 2. Prérequis bloquant : liaison N-PE

La sortie des onduleurs est en neutre isolé, avec une liaison N-PE établie par un
contacteur dont la bobine est alimentée par **la présence du réseau**. Si l'onduleur
coupe aussi le neutre en fonctionnement sur batterie (constaté sur un SPF 5000 ES),
alors en mode SBU **réseau présent** — exactement la situation créée par cette
extension les jours rouges — la sortie est en neutre flottant et les différentiels
30 mA ne protègent plus les personnes.

Conséquences pour la conception :

- l'interrupteur **Pilotage** est coupé par défaut ;
- le README place cet avertissement en tête, avec la mesure à faire : tension N-PE en
  sortie, onduleurs en SBU, réseau présent ;
- le pilotage n'est activé qu'après cette mesure, et éventuellement la reprise de la
  commande du contacteur (qui devrait suivre « onduleur sur batterie »).

## 3. Périmètre

**Version 0.1.0 :**

- passage sur batterie pendant les heures pleines des jours rouges ;
- réserve de secours ajustée selon la vigilance Météo-France ;
- charge renforcée la nuit qui précède un jour rouge, si la borne ne charge pas ;
- verrou général et mode observation ;
- entités d'état et panneau latéral.

**Hors périmètre (pistes pour `ROADMAP.md`) :** production solaire, pilotage de la
borne ou de la piscine, historique et calcul des économies, recharge complète
périodique pour recaler les compteurs de batterie, réglages modifiables depuis le
panneau.

## 4. Comportement

### 4.1 Principe : réconciliation

À chaque changement d'une entrée, et toutes les minutes, l'extension calcule l'**état
voulu** des quatre commandes (mode de sortie, seuil 12, seuil 13, courant de charge
réseau), le compare à leur état réel et ne corrige que les écarts. Après un
redémarrage de Home Assistant, elle se recale sans dépendre d'un horaire manqué.

### 4.2 Définitions

- **Heures creuses** : l'entité « heures creuses » choisie (`binary_sensor.rte_tempo_heures_creuses`
  chez nous, de 22 h à 6 h).
- **Jour rouge** : couleur du jour Tempo (`sensor.rte_tempo_couleur_actuelle`) égale à
  « Rouge ». Le jour Tempo va de 6 h à 6 h ; la couleur du jour bascule à 6 h.
- **Lendemain rouge** : couleur du prochain jour Tempo (`sensor.rte_tempo_prochaine_couleur`)
  égale à « Rouge ». Entre 22 h et 6 h, elle doit désigner le jour qui commence à 6 h :
  **à vérifier** pendant l'observation, notamment après minuit. Si l'intégration
  bascule à minuit, seule la charge renforcée de 0 h à 6 h est touchée.
- **Vigilance active** : niveau orange ou rouge, sur l'un des phénomènes choisis, dans
  l'entité de vigilance (`sensor.76_weather_alert`, qui expose un attribut par
  phénomène). Phénomènes par défaut : vent violent, orages, neige-verglas, grand froid,
  pluie-inondation.
- **Borne en charge** : puissance de la borne au-dessus du seuil (500 W par défaut).

### 4.3 Table de décision

La décision est calculée **que le Pilotage soit actif ou non** : l'interrupteur ne fait
que suspendre les écritures (§ 8.1). Pilotage coupé, Mode voulu, Raison et Écart
montrent donc ce que l'extension ferait, ce qui sert la période d'observation (§ 11).

| Situation (évaluée dans cet ordre) | Mode | Seuil 12 | Seuil 13 | Charge réseau |
|---|---|---|---|---|
| Réseau absent | *aucune écriture, état voulu inchangé* | | | |
| Jour rouge et hors heures creuses | **batterie** | **réserve** | réserve + écart | normal |
| Heures creuses et lendemain rouge | réseau | normal | normal | **renforcé** si la borne ne charge pas, sinon normal |
| Tous les autres cas | réseau | normal | normal | normal |

- **Réserve** = réserve normale (30 %), ou réserve sous vigilance (50 %) si une
  vigilance est active.
- **Écart** = 5 points par défaut : le seuil 13 reste toujours au moins 5 points
  au-dessus du seuil 12.
- **Valeurs normales** : seuil 12 = 50 %, seuil 13 = 95 %, charge réseau = 15 A.
- **Charge renforcée** = 20 A.
- Toutes ces valeurs sont réglables dans les options.

### 4.4 Conséquences voulues

- **Matin d'un jour rouge** : le seuil 13 est abaissé **avant** le passage en mode
  batterie. Sans cela, un onduleur en SBU ne repart sur batterie qu'au-dessus de
  95 % (constaté le 03/10/2026).
- **Réserve atteinte** : c'est l'onduleur qui repasse seul sur le réseau grâce au
  seuil 12. La réserve tient même si Home Assistant est arrêté.
- **Vigilance qui apparaît en cours de journée** : le seuil 12 monte à 50 % ; si la
  batterie est déjà en dessous, l'onduleur repasse aussitôt sur le réseau.
- **Coupure réseau** : les onduleurs basculent seuls sur batterie quel que soit le
  mode, jusqu'au seuil de coupure (réglage 21, non piloté).
- **Borne qui démarre en pleine nuit** : la charge réseau redescend à la valeur
  normale à la vérification suivante.

## 5. Configuration

Assistant en trois étapes, toutes modifiables ensuite dans les options. Une seule
instance (`single_config_entry`).

| Étape | Champ | Type | Valeur chez nous |
|---|---|---|---|
| 1. Sources | Couleur du jour Tempo | `sensor` (enum) | `sensor.rte_tempo_couleur_actuelle` |
| | Couleur du prochain jour | `sensor` (enum) | `sensor.rte_tempo_prochaine_couleur` |
| | Heures creuses | `binary_sensor` | `binary_sensor.rte_tempo_heures_creuses` |
| | Vigilance météo | `sensor` | `sensor.76_weather_alert` |
| | Phénomènes surveillés | liste | 5 phénomènes (§ 4.2) |
| | SOC de la batterie | `sensor` (%) | SOC système Docan |
| | Puissance de la borne | `sensor` (W) | `sensor.shelly_em_2_channel_1_power` |
| | Présence réseau (facultatif) | `binary_sensor` | *Grid Available* Ond1 |
| 2. Commandes | Mode de sortie | `select` | priorité de sortie Ond1 |
| | Valeur « réseau » / « batterie » | options du select | UTI / SBU |
| | Seuil 12 (retour au réseau) | `number` | *Battery Low to Utility SOC* Ond1 |
| | Seuil 13 (retour sur batterie) | `number` | *Utility Back to Battery SOC* Ond1 |
| | Charge réseau | `number` | *AC Charge Current (AC1)* Ond1 |
| 3. Valeurs | Réserve normale / sous vigilance | % | 30 / 50 |
| | Écart 12 → 13 | points | 5 |
| | Seuils normaux 12 / 13 | % | 50 / 95 |
| | Charge normale / renforcée | A | 15 / 20 |
| | Seuil « borne en charge » | W | 500 |
| | Service de notification (facultatif) | service `notify` | à choisir |

Contrôles de saisie : réserve sous vigilance ≥ réserve normale ; seuil 13 normal ≥
seuil 12 normal + écart ; valeurs dans les bornes des entités `number` choisies ;
valeurs « réseau » et « batterie » présentes dans les options du `select`.

## 6. Entités créées

| Entité | Type | Rôle |
|---|---|---|
| Pilotage | `switch` | Verrou général. Coupé par défaut, état conservé au redémarrage. |
| Mode voulu | `sensor` (enum) | réseau, batterie (jour rouge), charge renforcée, coupure réseau |
| Raison | `sensor` | Texte, par exemple « Jour rouge, réserve 50 % (vigilance vent orange) » |
| Réserve active | `sensor` (%) | 30 ou 50 selon la vigilance |
| Écart | `binary_sensor` | Allumé si l'état réel diffère de l'état voulu ; attributs : commandes en écart. Pilotage coupé, il montre ce que l'extension ferait. |

## 7. Panneau latéral

Entrée « Energy Management » dans la barre latérale, icône `mdi:home-battery`, adresse
`/energy-management`. Même mécanisme que `pool_control` : `frontend.py` sert le fichier
JavaScript et déclare le panneau (`panel_custom`) ; le composant lit `hass.states` et
appelle `hass.callService`.

| Bloc | Contenu |
|---|---|
| En-tête | Interrupteur Pilotage, avec confirmation au basculement ; indicateur Écart |
| Aujourd'hui / demain | Couleurs Tempo, heures creuses, vigilance du jour |
| Batterie | SOC, réserve active, présence du réseau |
| Décision | Mode voulu et raison |
| Onduleurs | Pour chaque commande : valeur voulue face à valeur réelle |

Le panneau est en lecture seule, sauf l'interrupteur Pilotage. Les blocs sont
indépendants pour en ajouter plus tard sans refonte.

## 8. Sécurités et gestion des erreurs

### 8.1 Verrou

Pilotage coupé, l'extension calcule et affiche, mais n'écrit rien. À la coupure du
Pilotage, elle remet **une fois** les valeurs normales (mode réseau, 50 / 95, 15 A),
puis n'écrit plus. Pour régler les onduleurs à la main, on coupe le Pilotage.

### 8.2 Donnée indisponible ou inconnue : choix prudent

| Donnée | Comportement |
|---|---|
| Couleur du jour | Considéré comme non rouge |
| Couleur du prochain jour | Pas de charge renforcée |
| Heures creuses | Pas de mode batterie, pas de charge renforcée |
| Vigilance | Considérée comme active (réserve sous vigilance) |
| SOC | Pas de passage en mode batterie ; retour au réseau si déjà en mode batterie |
| Puissance de la borne | Considérée comme en charge (charge normale) |
| Présence réseau = absent | Aucune écriture |
| Commande indisponible | Pas d'écriture sur cette commande ; Écart allumé |

### 8.3 Écritures

- **Séquentielles** : une écriture, puis attente de la relecture de l'entité (jusqu'à
  60 s) avant la suivante. Constaté le 09/10/2026 : deux écritures à 2 s d'intervalle
  en avaient perdu une.
- **Ordre imposé** :
  - vers le mode batterie : seuil 12, seuil 13, puis mode ;
  - vers le mode réseau : mode, seuil 13, puis seuil 12 ;
  - charge réseau : indépendante, après les seuils.
- **Invariant** : à aucun moment le seuil 13 n'est inférieur au seuil 12 + écart.
  Règle générale, valable aussi quand une vigilance apparaît en cours de journée :
  quand les seuils baissent, le 12 est écrit en premier ; quand ils montent, le 13.
  Exemple du matin rouge : 50 / 95 → 30 / 95 → 30 / 35, puis passage en batterie.
- **Pas de réécriture** d'une valeur déjà en place, ce qui limite l'usure de la
  mémoire des onduleurs (environ six écritures par jour rouge, zéro les autres jours).
- **Échec** : trois essais. Si la relecture diffère encore, Écart s'allume, une
  notification persistante est créée, et le service de notification choisi est
  appelé s'il y en a un. La commande est retentée à la vérification suivante.
- **Une seule réconciliation à la fois** : une vérification qui tombe pendant une
  séquence d'écritures est ignorée.

## 9. Architecture

| Fichier | Rôle | Dépend de |
|---|---|---|
| `decision.py` | Calcule l'état voulu et sa raison à partir des entrées et des réglages | rien (Python pur) |
| `inputs.py` | Lit les entités et applique le § 8.2 ; produit les entrées de `decision.py` | `hass.states` |
| `reconciler.py` | Compare, ordonne, écrit, relit, retente ; verrou ; gel en coupure | services `select` / `number` |
| `__init__.py` | Cycle de vie, écoute des entrées, minuteur d'une minute | les trois précédents |
| `config_flow.py`, `options_flow.py` | Assistant et options, contrôles du § 5 | |
| `switch.py`, `sensor.py`, `binary_sensor.py` | Entités du § 6 | état partagé de l'instance |
| `frontend.py`, `frontend/energy_management_panel.js` | Panneau du § 7 | |
| `const.py`, `strings.json`, `translations/fr.json`, `translations/en.json` | Constantes et textes | |

Fichiers du dépôt, comme pour `pool_control` et `shutters_management` :
`manifest.json` (domaine `energy_management`, `config_flow`, `single_config_entry`,
`iot_class: calculated`, dépendances `http`, `frontend`, `panel_custom`, version 0.1.0),
`hacs.json`, `README.md`, `CHANGELOG.md`, `ROADMAP.md`, `LICENSE`, `pytest.ini`,
`requirements_test.txt`, workflows GitHub (tests, HACS, Hassfest).

## 10. Tests

Outillage : `pytest`, `pytest-asyncio`, `pytest-homeassistant-custom-component`.

- **`decision.py`** : table de cas couvrant les couleurs, les bascules d'heures creuses,
  la vigilance (par phénomène et par niveau), la borne au seuil, chaque donnée
  indisponible, le verrou et la coupure réseau.
- **`reconciler.py`** : entités simulées. Ordre des écritures dans les deux sens ;
  invariant 12/13 à chaque étape ; attente de la relecture ; trois essais puis Écart et
  notification ; aucune réécriture d'une valeur en place ; gel en coupure ; remise aux
  valeurs normales une seule fois à la coupure du verrou ; une seule réconciliation à
  la fois.
- **Configuration** : création, options, chaque contrôle de saisie.
- **Entités et panneau** : entités créées et leurs états ; panneau enregistré.
- **CI GitHub** : tests, HACS, Hassfest.

## 11. Mise en service

1. Installer et configurer avec le Pilotage coupé.
2. Observer quelques jours : Mode voulu, Raison et Écart doivent correspondre aux
   journées réelles (au moins une nuit et une journée).
3. Faire la mesure N-PE du § 2 et, si nécessaire, reprendre la commande du contacteur.
4. Activer le Pilotage. Vérifier le premier jour rouge sur l'historique : passage en
   mode batterie à 6 h, réserve tenue, retour au réseau à 22 h.

## 12. Points ouverts hors logiciel

- Mesure N-PE (§ 2) : bloquante pour l'activation.
- Courant maximal du bypass de chaque onduleur : toute la maison y passe en mode réseau.
- Pointe au-delà de 12 kW possible sur batterie (induction, four et sèche-linge
  ensemble).
