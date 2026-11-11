# Feuille de route — Energy Management

Ce document recense les évolutions envisagées au-delà de la version 0.1.6 (voir le [CHANGELOG](CHANGELOG.md) pour ce qui est livré). La liste est ouverte : ce ne sont pas des promesses, mais un réservoir d'idées à prioriser selon les besoins réels.

---

## État au 11/11/2026

- **Version 0.1.6** installée sur le serveur.
- **Période d'observation** commencée le 08/11 avec la 0.1.1, **Pilotage coupé** : la décision est calculée et affichée, rien n'est écrit sur les onduleurs.
- **Résultat à ce jour** : décision « réseau » et aucun écart. Les valeurs réelles des onduleurs (UTI, seuils 50 % et 95 %, charge 15 A) sont égales aux valeurs normales.
- **Activation du Pilotage** : bloquée par les points ouverts hors logiciel ci-dessous.

## À vérifier pendant l'observation

- **`sensor.rte_tempo_prochaine_couleur` entre minuit et 6 h** : entre 22 h et 6 h, elle doit désigner le jour Tempo qui commence à 6 h. Si l'intégration RTE bascule à minuit, seule la charge renforcée de 0 h à 6 h est touchée.
  - **Pas encore vérifiable** : du 08/11 au 11/11, tous les jours étaient bleus. Il faut une veille de jour rouge pour voir si la couleur change à minuit.
  - **Déjà constaté** : chaque matin, l'entité est `unavailable` de 6 h jusque vers 7 h, le temps que RTE publie la couleur du lendemain. C'est sans effet sur la décision : un lendemain inconnu est traité comme non rouge, et la charge renforcée ne joue qu'en heures creuses, qui finissent à 6 h.
- **Présence réseau lue « absent »** pendant 30 s le 10/11 à 20 h 00. Le capteur Growatt était lisible, il a bien indiqué une absence ; la décision est passée par « Coupure réseau », sans écriture. Reste à savoir s'il s'agit d'une vraie micro-coupure ou d'une fausse lecture de l'onduleur. Si l'événement se répète, le confronter à un autre témoin de présence réseau (compteur, prise connectée côté réseau).
- **Capteur réseau illisible aux redémarrages** : à chaque démarrage de Home Assistant, le capteur Growatt est illisible environ une seconde. La décision passe par « Capteur réseau indisponible », sans écriture, puis revient à « réseau ». C'est le comportement attendu depuis la 0.1.2 ; rien à faire.

## Pistes hors périmètre

| Piste | Motivation |
|---|---|
| Production solaire | Tenir compte de la production pour décider du mode et de la réserve. |
| Pilotage de la borne de recharge ou de la piscine | Décaler ces charges hors de la maison câblée derrière les onduleurs. |
| Historique et calcul des économies | Chiffrer le gain des jours rouges. |
| Recharge complète périodique | Recaler les compteurs de batterie. |
| Réglages modifiables depuis le panneau | Aujourd'hui, les valeurs se changent dans les options de l'intégration. |

## Points ouverts hors logiciel

- **Mesure N-PE** : bloquante pour l'activation du Pilotage (voir le README).
- **Courant maximal du bypass** de chaque onduleur : toute la maison y passe en mode réseau.
- **Pointe au-delà de 12 kW** possible sur batterie (induction, four et sèche-linge ensemble).
