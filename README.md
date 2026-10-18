# Données externes

Deux familles de données externes, conformément au §8 du cahier de spécification (version B) :

1. **Variables explicatives candidates pour la prévision de la demande (§11.1)** : météo et épidémies. Elles sont
   intégrées **uniquement** au jeu ML de prévision (pas au Data Warehouse) et ne sont conservées que si elles améliorent
   réellement le modèle — mesure faite sur la **période réelle** uniquement.
2. **Données synthétiques** : prolongation de l'export réel (7 mois) jusqu'à 2 ans d'historique, rangée à part.

Le calendrier français (jours fériés) n'est pas une source externe : il est calculé dans `dim_temps`. Les vacances
scolaires ne sont pas retenues.

| Fichier / dossier | Source | Contenu | Granularité | Jointure |
|---|---|---|---|---|
| `meteo_paris_open-meteo.json` | [Open-Meteo](https://open-meteo.com/) (API archive, licence CC BY 4.0) | Température moy./min./max., pluie, ensoleillement, rayonnement — Paris, 01/09/2024 → 29/09/2026 | Jour | Date |
| `sentinelles_inc-3-PAY.csv` | [Réseau Sentinelles](https://www.sentiweb.fr/) (Inserm, Sorbonne Université) | Syndromes grippaux | Semaine ISO, France | Semaine ISO |
| `sentinelles_inc-25-PAY.csv` | Réseau Sentinelles | Infections respiratoires aiguës (IRA) | Semaine ISO | Semaine ISO |
| `sentinelles_inc-6-PAY.csv` | Réseau Sentinelles | Diarrhée aiguë (gastro-entérite) | Semaine ISO | Semaine ISO |
| `sentinelles_inc-7-PAY.csv` | Réseau Sentinelles | Varicelle | Semaine ISO | Semaine ISO |
| [`donnees_synthetiques/`](donnees_synthetiques/) | `generate_external_data.py` (branche `main`) | Suite simulée de l'export : ventes, lignes, paiements, trésorerie, caisses, mouvements de stock, stock final — 01/05/2025 → 29/09/2026 | Mêmes fichiers et formats que l'export | Identifiants continuant ceux de l'export |

- Météo et Sentinelles sont téléchargées par `build_dataset.py` si absentes (la météo est retéléchargée si elle ne couvre
  pas toute la période). Seule la valeur `inc100` (taux d'incidence pour 100 000 habitants) des fichiers Sentinelles est utilisée.
- **Délimitation réel / synthétique : par la date** — réel jusqu'au 30/04/2025 inclus, synthétique à partir du 01/05/2025.
  Les hypothèses de génération (dont des effets météo et épidémiques) sont listées dans
  [`donnees_synthetiques/README.md`](donnees_synthetiques/README.md) : ce sont des hypothèses, pas des découvertes.

Retour à la vue d'ensemble : branche [`main`](../../tree/main).
