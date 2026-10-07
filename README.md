# Données externes

Téléchargées automatiquement par `build_dataset.py` (branche `main`) puis intégrées à `dim_temps` et aux jeux de
prévision ML (§8 et §11.1 du cahier de spécification).

| Fichier | Source | Contenu | Granularité | Jointure |
|---|---|---|---|---|
| `meteo_paris_open-meteo.json` | [Open-Meteo](https://open-meteo.com/) (API archive, licence CC BY 4.0) | Température moy./min./max., pluie, ensoleillement, rayonnement — Paris, 01/09/2024 → 31/12/2025 | Jour | `DateKey` |
| `sentinelles_inc-3-PAY.csv` | [Réseau Sentinelles](https://www.sentiweb.fr/) (Inserm, Sorbonne Université) | Syndromes grippaux | Semaine ISO, France | `AnneeSemaine` |
| `sentinelles_inc-25-PAY.csv` | Réseau Sentinelles | Infections respiratoires aiguës (IRA) | Semaine ISO | `AnneeSemaine` |
| `sentinelles_inc-6-PAY.csv` | Réseau Sentinelles | Diarrhée aiguë (gastro-entérite) | Semaine ISO | `AnneeSemaine` |
| `sentinelles_inc-7-PAY.csv` | Réseau Sentinelles | Varicelle | Semaine ISO | `AnneeSemaine` |

Les fichiers Sentinelles couvrent tout l'historique disponible ; seule la valeur `inc100` (taux d'incidence pour
100 000 habitants) est utilisée. Le lieu de la météo (Paris) se change dans `build_dataset.py` (`METEO_VILLE`).

Retour à la vue d'ensemble : branche [`main`](../../tree/main).
