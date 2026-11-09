# Energy Management

Intégration personnalisée Home Assistant (HACS) qui pilote une installation de stockage domestique selon le tarif EDF **Tempo**, avec deux objectifs d'égale importance :

- **secours** : garder une réserve d'énergie pour une coupure réseau ;
- **économie** : alimenter la maison sur batterie pendant les heures pleines des **jours rouges**, seul cas rentable (écart d'environ 0,44 €/kWh contre environ 0,01 €/kWh un jour blanc).

Installation de référence : deux onduleurs Growatt SPF 6000 ES Plus en parallèle, deux packs LiFePO4 Docan (environ 650 Ah, 33 kWh), réglages accessibles par les entités de l'ESP Growatt existant.

L'intégration ne connaît **aucun identifiant d'entité en dur** : toutes les sources et toutes les commandes sont choisies dans l'assistant de configuration.

## Avertissement : liaison N-PE, mesure à faire avant d'activer le Pilotage

La sortie des onduleurs est en neutre isolé, avec une liaison N-PE établie par un contacteur dont la bobine est alimentée par **la présence du réseau**. Si l'onduleur coupe aussi le neutre en fonctionnement sur batterie (constaté sur un SPF 5000 ES), alors en mode SBU **réseau présent** — exactement la situation créée par cette intégration les jours rouges — la sortie est en neutre flottant et **les différentiels 30 mA ne protègent plus les personnes**.

C'est pourquoi l'interrupteur **Pilotage** est **coupé par défaut**. Avant de l'activer :

1. mesurer la **tension N-PE en sortie**, onduleurs en SBU, réseau présent ;
2. si nécessaire, reprendre la commande du contacteur (elle devrait suivre « onduleur sur batterie » et non « réseau présent »).

Tant que cette mesure n'est pas faite, laisser le Pilotage coupé : l'intégration calcule et affiche ce qu'elle ferait, sans rien écrire.

## Table des matières

- [Fonctionnement](#fonctionnement)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entités créées](#entités-créées)
- [Panneau latéral](#panneau-latéral)
- [Sécurités et gestion des erreurs](#sécurités-et-gestion-des-erreurs)
- [Mise en service](#mise-en-service)
- [Points ouverts hors logiciel](#points-ouverts-hors-logiciel)
- [Tests](#tests)
- [Roadmap et changelog](#roadmap-et-changelog)
- [Licence](#licence)

## Fonctionnement

### Principe : réconciliation

À chaque changement d'une des entrées (couleurs Tempo, heures creuses, vigilance, SOC, borne, présence réseau) et **toutes les minutes**, l'intégration calcule l'**état voulu** des quatre commandes (mode de sortie, seuil 12, seuil 13, courant de charge réseau), le compare à leur état réel et ne corrige que les écarts. Après un redémarrage de Home Assistant, elle se recale sans dépendre d'un horaire manqué.

Les quatre commandes sont **lues, jamais écoutées** : un changement de leur valeur n'est pris en compte qu'à la vérification suivante (au plus une minute) ou au prochain changement d'une entrée. Sinon chaque relecture après écriture relancerait un calcul.

### Définitions

- **Heures creuses** : l'entité « heures creuses » choisie (22 h à 6 h).
- **Jour rouge** : couleur du jour Tempo égale à « Rouge ». Le jour Tempo va de 6 h à 6 h.
- **Lendemain rouge** : couleur du prochain jour Tempo égale à « Rouge ». Entre 22 h et 6 h, elle doit désigner le jour qui commence à 6 h (à vérifier, voir la [roadmap](ROADMAP.md)).
- **Vigilance active** : niveau orange ou rouge sur l'un des phénomènes choisis dans l'entité de vigilance Météo-France. Phénomènes par défaut : vent violent, orages, neige-verglas, grand froid, pluie-inondation.
- **Borne en charge** : puissance de la borne au-dessus du seuil (500 W par défaut).

### Table de décision

La décision est calculée **que le Pilotage soit actif ou non** : l'interrupteur ne fait que suspendre les écritures. Pilotage coupé, Mode voulu, Raison et Écart montrent donc ce que l'intégration ferait, ce qui sert la période d'observation.

| Situation (évaluée dans cet ordre) | Mode | Seuil 12 | Seuil 13 | Charge réseau |
|---|---|---|---|---|
| Réseau absent | *aucune écriture, état voulu inchangé* | | | |
| Jour rouge et hors heures creuses | **batterie** | **réserve** | réserve + écart | normal |
| Heures creuses et lendemain rouge | réseau | normal | normal | **renforcé** si la borne ne charge pas, sinon normal |
| Tous les autres cas | réseau | normal | normal | normal |

- **Réserve** = réserve normale (30 %), ou réserve sous vigilance (50 %) si une vigilance est active.
- **Écart** = 5 points par défaut : le seuil 13 reste toujours au moins 5 points au-dessus du seuil 12.
- **Valeurs normales** : seuil 12 = 50 %, seuil 13 = 95 %, charge réseau = 15 A.
- **Charge renforcée** = 20 A.
- Toutes ces valeurs sont réglables dans les options.

### Conséquences voulues

- **Matin d'un jour rouge** : le seuil 13 est abaissé **avant** le passage en mode batterie. Sans cela, un onduleur en SBU ne repart sur batterie qu'au-dessus de 95 %.
- **Réserve atteinte** : c'est l'onduleur qui repasse seul sur le réseau grâce au seuil 12. La réserve tient même si Home Assistant est arrêté.
- **Vigilance qui apparaît en cours de journée** : le seuil 12 monte à 50 % ; si la batterie est déjà en dessous, l'onduleur repasse aussitôt sur le réseau.
- **Coupure réseau** : les onduleurs basculent seuls sur batterie quel que soit le mode, jusqu'au seuil de coupure (réglage 21, non piloté).
- **Borne qui démarre en pleine nuit** : la charge réseau redescend à la valeur normale à la vérification suivante.

## Installation

Version minimale de Home Assistant : **2026.3.0** (voir `hacs.json`).

### Via HACS (recommandé)

1. Dans HACS, menu ⋮ → **Dépôts personnalisés**, ajouter le dépôt de l'intégration avec la catégorie **Intégration**.
2. Rechercher **Energy Management** dans HACS et l'installer.
3. Redémarrer Home Assistant.
4. **Paramètres → Appareils et services → Ajouter une intégration → Energy Management**.

### Installation manuelle

1. Copier le dossier `custom_components/energy_management` dans le dossier `custom_components` de votre configuration Home Assistant.
2. Redémarrer Home Assistant, puis ajouter l'intégration comme ci-dessus.

Une seule instance est possible (`single_config_entry`).

### Désinstallation

Avant de supprimer l'intégration, couper le Pilotage et attendre la fin de la remise aux valeurs normales : la pastille « Remise en attente » a disparu du panneau (attribut `remise_en_attente` du Pilotage à faux). L'entité Écart ne convient pas : elle compare l'état réel à la décision, pas aux valeurs normales. Une fois l'intégration supprimée, plus rien ne remet les onduleurs en mode réseau.

## Configuration

À l'installation, assistant en trois étapes. Ensuite, **Configurer** ouvre un **menu de configuration** : Sources, Commandes de l'onduleur, Valeurs et réglages, puis **Valider et enregistrer**. Chaque page revient au menu ; rien n'est enregistré avant « Valider et enregistrer ». À l'enregistrement, les valeurs sont revérifiées : si un changement de commandes les a rendues fausses (par exemple une valeur « réseau » absente du nouveau `select`), la page Valeurs s'affiche avec l'erreur, et l'enregistrement se fait dès qu'elle est corrigée.

| Étape | Champ | Type | Exemple (installation de référence) |
|---|---|---|---|
| 1. Sources | Couleur du jour Tempo | `sensor` | `sensor.rte_tempo_couleur_actuelle` |
| | Couleur du prochain jour | `sensor` | `sensor.rte_tempo_prochaine_couleur` |
| | Heures creuses | `binary_sensor` | `binary_sensor.rte_tempo_heures_creuses` |
| | Vigilance météo | `sensor` | `sensor.76_weather_alert` |
| | Phénomènes surveillés | liste | 5 phénomènes (voir plus haut) |
| | SOC de la batterie | `sensor` (%) | SOC système Docan |
| | Puissance de la borne | `sensor` (W) | `sensor.shelly_em_2_channel_1_power` |
| | Présence réseau (facultatif) | `binary_sensor` | *Grid Available* de l'onduleur 1 |
| 2. Commandes | Mode de sortie | `select` | priorité de sortie de l'onduleur 1 |
| | Seuil 12 (retour au réseau) | `number` | *Battery Low to Utility SOC* |
| | Seuil 13 (retour sur batterie) | `number` | *Utility Back to Battery SOC* |
| | Charge réseau | `number` | *AC Charge Current (AC1)* |
| 3. Valeurs | Valeur « réseau » / « batterie » du mode de sortie | options du select | UTI / SBU |
| | Réserve normale / sous vigilance | % | 30 / 50 |
| | Écart 12 → 13 | points | 5 |
| | Seuils normaux 12 / 13 | % | 50 / 95 |
| | Charge normale / renforcée | A | 15 / 20 |
| | Seuil « borne en charge » | W | 500 |
| | Service de notification (facultatif, proposé seulement s'il existe un service `notify`) | service `notify` | à choisir |

Notes :

- Les valeurs « réseau » et « batterie » se choisissent à l'étape 3, car leurs choix dépendent du `select` retenu à l'étape 2.
- **Service de notification** : dans les options, s'il n'existe plus aucun service `notify` au moment de les modifier, le champ n'est pas proposé et la cible déjà enregistrée est conservée.
- **Présence réseau** : facultative. Non configurée, le réseau est supposé présent. Configurée, seul l'état `on` compte comme présent. `off` est une coupure réseau ; un capteur absent, `unknown` ou `unavailable` est signalé à part (« Capteur réseau indisponible ») et traité de la même façon : aucune écriture.
- Contrôles de saisie : réserve sous vigilance ≥ réserve normale ; seuil 13 normal ≥ seuil 12 normal + écart ; valeurs dans les bornes des entités `number` choisies ; valeurs « réseau » et « batterie » présentes dans les options du `select` et différentes entre elles.

## Entités créées

| Entité | Type | Rôle |
|---|---|---|
| Pilotage | `switch` | Verrou général. Coupé par défaut, état conservé au redémarrage. Attributs : `remise_en_attente` (remise aux valeurs normales pas terminée) et `commandes_a_remettre` (commandes encore à remettre). |
| Mode voulu | `sensor` (enum) | Réseau, batterie (jour rouge), charge renforcée, coupure réseau, capteur réseau indisponible |
| Raison | `sensor` | Texte, par exemple « Jour rouge, réserve 50 % (vigilance vent orange) » |
| Réserve active | `sensor` (%) | 30 ou 50 selon la vigilance |
| Écart | `binary_sensor` | Allumé si l'état réel diffère de l'état voulu ; attributs : commandes en écart. Pilotage coupé, il montre ce que l'intégration ferait. |

L'entité Écart se met à jour à la vérification suivante (une minute au plus) ou à tout changement d'une entrée.

## Panneau latéral

Entrée **Energy Management** dans la barre latérale (icône `mdi:home-battery`, adresse `/energy-management`).

| Bloc | Contenu |
|---|---|
| En-tête | Interrupteur Pilotage, avec confirmation au basculement ; indicateur Écart ; pastille « Remise en attente » suivie des commandes encore à remettre, tant que la remise aux valeurs normales n'est pas terminée |
| Aujourd'hui / demain | Couleurs Tempo, heures creuses, vigilance du jour |
| Batterie | SOC, réserve active, présence du réseau |
| Décision | Mode voulu et raison |
| Onduleurs | Pour chaque commande : valeur voulue face à valeur réelle |

Le panneau est en lecture seule, sauf l'interrupteur Pilotage.

## Sécurités et gestion des erreurs

### Verrou Pilotage

Pilotage coupé, l'intégration calcule et affiche, mais n'écrit rien. Pour régler les onduleurs à la main, on coupe le Pilotage.

**Remise aux valeurs normales** (mode réseau, seuils normaux, charge normale) :

- elle a lieu **une seule fois**, uniquement quand on passe le Pilotage de actif à coupé ; jamais à l'installation, jamais à un redémarrage avec le Pilotage déjà coupé ;
- demandée pendant une coupure réseau ou capteur de présence indisponible, elle **attend le retour du réseau** ;
- elle est **suivie commande par commande** : chaque commande relue à sa valeur normale sort de la remise, et seules les commandes restantes sont encore écrites ; la remise est **terminée quand les quatre commandes en sont sorties** ;
- une commande **déjà remise puis réglée à la main n'est plus réécrite** par la remise, même si une autre commande reste en attente ;
- une commande indisponible (donc non écrite) ou en échec **reste en attente** sans faire réécrire les commandes déjà remises ; elle est retentée à chaque vérification, et le panneau la nomme (pastille « Remise en attente ») ;
- si un seul des deux seuils reste à remettre et que l'écrire violerait seuil 13 ≥ seuil 12 + écart (l'autre seuil ayant été réglé à la main), il n'est pas écrit et reste en attente ;
- une remise pas encore faite **survit à un redémarrage de Home Assistant ou à un rechargement des options** (conservée dans les données de restauration de l'interrupteur) ;
- si le Pilotage est réactivé entre-temps, la remise est annulée.

Avant de supprimer l'intégration, couper le Pilotage et attendre la fin de la remise aux valeurs normales : la pastille « Remise en attente » a disparu du panneau (attribut `remise_en_attente` du Pilotage à faux). L'entité Écart ne convient pas : elle compare l'état réel à la décision, pas aux valeurs normales. Une fois l'intégration supprimée, plus rien ne remet les onduleurs en mode réseau.

### Démarrage de Home Assistant

Tant que Home Assistant n'a pas fini de démarrer, l'intégration calcule et affiche mais **n'écrit rien** (ni réconciliation, ni remise) : la couleur Tempo peut ne pas être encore chargée alors que l'onduleur se lit déjà, ce qui ferait repasser un jour rouge en mode réseau puis en batterie. Le premier calcul avec écritures a lieu dès la fin du démarrage.

### Donnée indisponible ou inconnue : choix prudent

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

### Écritures

- **Séquentielles** : une écriture, puis attente de la relecture de l'entité (jusqu'à 60 s) avant la suivante, avec trois essais. Deux écritures trop rapprochées avaient fait perdre une valeur à l'ESP. Un appel de service sans réponse au bout de 60 s compte aussi comme un essai raté.
- **Ordre imposé** :
  - vers le mode batterie : seuil 12, seuil 13, puis mode ;
  - vers le mode réseau : mode, seuil 13, puis seuil 12 ;
  - charge réseau : indépendante, après les seuils.
- **Invariant** : à aucun moment le seuil 13 n'est inférieur au seuil 12 + écart. Quand les seuils baissent, le 12 est écrit en premier ; quand ils montent, le 13. Exemple du matin rouge : 50 / 95 → 30 / 95 → 30 / 35, puis passage en batterie.
- **Seuil illisible** : si l'un des deux seuils (12 ou 13) ne peut pas être lu, **aucun seuil n'est écrit et le mode batterie n'est pas engagé** : la valeur réelle de l'onduleur étant inconnue, seule l'abstention garantit 13 ≥ 12 + écart. Le retour au mode réseau reste toujours permis.
- **Le mode batterie n'est écrit qu'après relecture des deux seuils** à leur valeur voulue.
- **Pas de réécriture** d'une valeur déjà en place (environ six écritures par jour rouge, zéro les autres jours), ce qui limite l'usure de la mémoire des onduleurs.
- **Échec** : la séquence s'arrête au premier échec ; Écart s'allume, une notification persistante est créée et le service de notification choisi est appelé s'il y en a un. La séquence est retentée à la vérification suivante (chaque minute). **Une seule notification par épisode et par commande**, effacée au succès suivant.
- **Arrêt immédiat** : les écritures s'arrêtent avant l'essai suivant quand le Pilotage est coupé ou quand la présence réseau passe à `off` ou indisponible pendant une séquence.
- **Une seule réconciliation à la fois** : une vérification qui tombe pendant une séquence est ignorée.

## Mise en service

1. Installer et configurer avec le Pilotage coupé.
2. Observer quelques jours : Mode voulu, Raison et Écart doivent correspondre aux journées réelles (au moins une nuit et une journée).
3. Faire la mesure N-PE décrite en tête de ce document et, si nécessaire, reprendre la commande du contacteur.
4. Activer le Pilotage. Vérifier le premier jour rouge sur l'historique : passage en mode batterie à 6 h, réserve tenue, retour au réseau à 22 h.

## Points ouverts hors logiciel

- **Mesure N-PE** : bloquante pour l'activation du Pilotage.
- **Courant maximal du bypass** de chaque onduleur : toute la maison y passe en mode réseau.
- **Pointe au-delà de 12 kW** possible sur batterie (induction, four et sèche-linge ensemble).

## Tests

Les tests ne tournent pas sous Windows natif (Home Assistant importe `fcntl`). Les lancer sous Linux ou WSL, dans un environnement Python 3.14 :

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
python -m pytest --cov=custom_components.energy_management --cov-report=term-missing
```

La CI GitHub Actions (tests, validation HACS, Hassfest) tourne sous Linux avec Python 3.14.

## Roadmap et changelog

- [ROADMAP.md](ROADMAP.md)
- [CHANGELOG.md](CHANGELOG.md)

Le dépôt GitHub (documentation et suivi des anomalies) est à venir : les liens du manifeste ne seront valides qu'à sa création.

## Licence

Voir le fichier [LICENSE](LICENSE).
