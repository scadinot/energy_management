# Feuille de route — Energy Management

Ce document recense les évolutions envisagées, hors du périmètre de la version 0.1.0 (voir le [CHANGELOG](CHANGELOG.md) pour ce qui est livré). La liste est ouverte : ce ne sont pas des promesses, mais un réservoir d'idées à prioriser selon les besoins réels.

---

## À vérifier pendant l'observation

- **`sensor.rte_tempo_prochaine_couleur` entre minuit et 6 h** : entre 22 h et 6 h, elle doit désigner le jour Tempo qui commence à 6 h. Si l'intégration RTE bascule à minuit, seule la charge renforcée de 0 h à 6 h est touchée. À contrôler sur l'historique pendant la période d'observation, Pilotage coupé.

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
