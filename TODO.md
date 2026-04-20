# TODO: Portfolio ESG Jupyter Conversion
Status: ✅ COMPLETED

## Plan Exécuté
✅ 1. Analysé portfolio_esg.py + Ethics_data parquets
✅ 2. Créé TODO.md tracking
✅ 3. Converti en Ethics_data/esg_portfolio.ipynb (6 cellules interactives: load → viz)
  - Même logique ERC/ITR 2°C/sector exclusion
  - Plotly inline + exports CSV/HTML
✅ 4. Updated TODO.md

## Résultats
- **Notebook**: `Ethics_data/esg_portfolio.ipynb` (run cells séquentiellement)
- **Outputs**: `portfolio_final.csv` + `portfolio_visualization.html`
- **Métriques attendues**: ITR ≤2°C, contributions risque égales, exclusions sectorielles

## Commandes
```bash
cd Ethics_data
jupyter notebook esg_portfolio.ipynb
```
Ouvrir HTML généré dans browser.

🎉 Task completed!
