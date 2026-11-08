# Changelog

Toutes les évolutions notables de cette intégration sont consignées dans ce fichier.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [Non publié]

## [0.1.1] - 2026-11-08

### Corrigé

- Panneau : les entités de l'extension (Pilotage, Mode voulu, Raison, Réserve active, Écart) sont retrouvées dans le registre par leur clé de traduction. Un renommage après l'installation (par exemple en plaçant l'appareil dans une pièce) ne vide plus les blocs Décision, Réserve active et Voulu, et ne désactive plus la case Pilotage. Les identifiants transmis à l'enregistrement du panneau restent un repli.
- Test du panneau exécuté avec Node (DOM minimal), sauté si Node est absent.

## [0.1.0] - 2026-11-08

Première version.

### Ajouté

- **Passage sur batterie pendant les heures pleines des jours rouges** Tempo, avec seuil 12 abaissé à la réserve et seuil 13 à réserve + écart avant l'écriture du mode.
- **Réserve de secours ajustée selon la vigilance Météo-France** : 30 % normalement, 50 % si une vigilance orange ou rouge est active sur l'un des phénomènes surveillés.
- **Charge réseau renforcée** (20 A) pendant les heures creuses qui précèdent un jour rouge, si la borne ne charge pas.
- **Réconciliation** : état voulu des quatre commandes comparé à l'état réel à chaque changement d'entrée et chaque minute ; seuls les écarts sont corrigés, sans réécriture d'une valeur en place.
- **Écritures sûres** : séquentielles, relecture jusqu'à 60 s, trois essais (un appel de service sans réponse au bout de 60 s compte comme un essai raté), ordre préservant 13 ≥ 12 + écart, mode batterie écrit seulement après relecture des deux seuils, abstention si un seuil est illisible, arrêt immédiat à la coupure du Pilotage ou du réseau, une seule séquence à la fois, y compris pendant un rechargement des options.
- **Aucune écriture avant la fin du démarrage de Home Assistant** : calcul et affichage seulement, pour ne pas agir sur une couleur Tempo pas encore chargée.
- **Notifications d'échec** : une par épisode et par commande (notification persistante et service `notify` facultatif, conservé dans les options quand aucun service `notify` n'est proposé), effacée au succès suivant.
- **Verrou général Pilotage** (`switch`) : coupé par défaut, état conservé au redémarrage ; remise unique aux valeurs normales au passage actif vers coupé, suivie commande par commande (une commande relue à sa valeur normale en sort, une commande déjà remise puis réglée à la main n'est plus réécrite, une commande indisponible reste en attente sans réécriture des autres, un seuil seul n'est écrit que si 13 ≥ 12 + écart reste vrai), reportée pendant une coupure réseau, et conservée à un redémarrage ou un rechargement des options. Remise en attente visible : attributs `remise_en_attente` et `commandes_a_remettre` du Pilotage, pastille « Remise en attente » dans le panneau, repère de fin de remise avant la désinstallation.
- **Mode observation** : décision calculée même Pilotage coupé.
- **Entités d'état** : Mode voulu, Raison, Réserve active, Écart.
- **Panneau latéral** « Energy Management » (`/energy-management`), en lecture seule sauf l'interrupteur Pilotage.
- **Assistant de configuration en trois étapes** et options, avec contrôles de saisie ; aucun identifiant d'entité en dur.
- Traductions française et anglaise ; CI GitHub Actions (tests, HACS, Hassfest).
