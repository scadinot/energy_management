# Changelog

Toutes les évolutions notables de cette intégration sont consignées dans ce fichier.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [Non publié]

## [0.1.0] - 2026-11-08

Première version.

### Ajouté

- **Passage sur batterie pendant les heures pleines des jours rouges** Tempo, avec seuil 12 abaissé à la réserve et seuil 13 à réserve + écart avant l'écriture du mode.
- **Réserve de secours ajustée selon la vigilance Météo-France** : 30 % normalement, 50 % si une vigilance orange ou rouge est active sur l'un des phénomènes surveillés.
- **Charge réseau renforcée** (20 A) pendant les heures creuses qui précèdent un jour rouge, si la borne ne charge pas.
- **Réconciliation** : état voulu des quatre commandes comparé à l'état réel à chaque changement d'entrée et chaque minute ; seuls les écarts sont corrigés, sans réécriture d'une valeur en place.
- **Écritures sûres** : séquentielles, relecture jusqu'à 60 s, trois essais, ordre préservant 13 ≥ 12 + écart, mode batterie écrit seulement après relecture des deux seuils, abstention si un seuil est illisible, arrêt immédiat à la coupure du Pilotage ou du réseau.
- **Notifications d'échec** : une par épisode et par commande (notification persistante et service `notify` facultatif), effacée au succès suivant.
- **Verrou général Pilotage** (`switch`) : coupé par défaut, état conservé au redémarrage ; remise unique aux valeurs normales au passage actif vers coupé, reportée pendant une coupure réseau et conservée à un redémarrage ou un rechargement des options.
- **Mode observation** : décision calculée même Pilotage coupé.
- **Entités d'état** : Mode voulu, Raison, Réserve active, Écart.
- **Panneau latéral** « Energy Management » (`/energy-management`), en lecture seule sauf l'interrupteur Pilotage.
- **Assistant de configuration en trois étapes** et options, avec contrôles de saisie ; aucun identifiant d'entité en dur.
- Traductions française et anglaise ; CI GitHub Actions (tests, HACS, Hassfest).
