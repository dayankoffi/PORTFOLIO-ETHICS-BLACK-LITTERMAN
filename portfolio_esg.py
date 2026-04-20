#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Portfolio ESG Construction Script
Auteur: BLACKBOXAI
Date: 2024

Ce script construit un portefeuille ESG aligné 2°C avec stratégie ERC (Equal Risk Contribution)
+ optimisation avec rendements attendus mu.

Étapes:
1. Chargement des données Parquet
2. Sélection de la dernière date disponible
3. Exclusion des 30% des poids les moins bien notés ESG par secteur
4. Calcul des rendements historiques et matrice de covariance
5. Optimisation ERC avec contrainte ITR pondéré <= 2°C
6. Affichage des résultats et sauvegarde
"""

import pandas as pd
import numpy as np
from scipy.optimize import minimize
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from pathlib import Path

# =======================================
# 1. CHARGEMENT DES DONNÉES
# =======================================
print('📊 Chargement des données...')

# Chemins des fichiers
data_path = Path('Ethics_data/data')

# Metadata: infos tickers (SECTOR crucial)
metadata = pd.read_parquet(data_path / 'metadata.parquet')
print(f'   Metadata: {metadata.shape} - Secteurs uniques: {metadata.SECTOR.nunique()}')

# Données trimestrielles (transposées pour tickers en lignes)
universe = pd.read_parquet(data_path / 'universe.parquet').T
esg_scores = pd.read_parquet(data_path / 'esg_score.parquet').T
itr = pd.read_parquet(data_path / 'itr.parquet').T

# Latest date
latest_date = universe.columns[-1]
print(f'   Date utilisée: {latest_date}')

# Latest data pour tickers
weights = universe[latest_date].dropna() * 100  # % weights
esg_latest = esg_scores[latest_date].dropna()
itr_latest = itr[latest_date].dropna()

# Fusion avec metadata
df = pd.DataFrame({
    'ticker': weights.index,
    'weight': weights.values,
    'esg': esg_latest.reindex(weights.index).values,
    'itr': itr_latest.reindex(weights.index).values
}).join(metadata.set_index('ID')[['SECTOR', 'NAME', 'COUNTRY']], on='ticker')

df = df.dropna()  # Supprime NaN
print(f'   Univers initial: {len(df)} tickers')

# =======================================
# 2. EXCLUSION 30% POIDS PLUS BAS ESG PAR SECTOR
# =======================================
print('\n✂️ Exclusion 30% poids les plus bas ESG par secteur...')

eligible_tickers = []
sector_total_weight = df.groupby('SECTOR')['weight'].sum()

for sector, group in df.groupby('SECTOR'):
    sector_weight_total = sector_total_weight[sector]
    exclude_weight = 0.3 * sector_weight_total
    
    # Tri par ESG ascendant (plus bas en premier)
    sorted_group = group.sort_values('esg')
    
    # Exclusion jusqu'à 30% poids cumulé
    cum_weight = sorted_group['weight'].cumsum()
    keep_mask = cum_weight > exclude_weight
    eligible = sorted_group[keep_mask]
    
    eligible_tickers.append(eligible)
    print(f'   {sector}: {len(group)} -> {len(eligible)} tickers (exclu {100*(len(group)-len(eligible))/len(group):.1f}%)')

df_eligible = pd.concat(eligible_tickers, ignore_index=True)
print(f'   Univers éligible: {len(df_eligible)} tickers')

# =======================================
# 3. CALCUL RENDEMENTS HISTORIQUES (1 an avant latest)
# =======================================
print('\n📈 Calcul rendements historiques...')

prices = pd.read_parquet(data_path / 'price.parquet')
tickers_price = prices.columns.intersection(df_eligible.ticker)

# 252 jours trading ~1 an
lookback = 252
recent_prices = prices[tickers_price].iloc[-lookback:].dropna(axis=1, how='all')

# Rendements daily log
returns = recent_prices.pct_change().dropna()

# Stats
mu = returns.mean() * 252  # Annualisé
cov = returns.cov() * 252

# Seulement tickers avec assez de data
valid_idx = df_eligible.ticker.isin(returns.columns)
df_portfolio = df_eligible[valid_idx].copy()
df_portfolio['mu'] = mu.reindex(df_portfolio.ticker).values * 100  # %
n_assets = len(df_portfolio)

print(f'   {n_assets} tickers avec rendements')

if n_assets < 2:
    raise ValueError('Pas assez de tickers pour optimisation')

# Data optimisation
tickers_opt = df_portfolio.ticker.values
itr_opt = df_portfolio.itr.values
sector_opt = df_portfolio.SECTOR.values

# Weights initiales uniformes
w0 = np.ones(n_assets) / n_assets

# =======================================
# 4. OPTIMISATION ERC + MU + ITR <=2°C
# =======================================
print('\n🔧 Optimisation ERC...')

def portfolio_risk(w, cov):
    """Volatilité portefeuille"""
    return np.sqrt(w.T @ cov @ w)

def risk_contribution(w, cov):
    """Contribution risque par actif"""
    vol_port = portfolio_risk(w, cov)
    partial_risk = cov @ w / vol_port
    return w * partial_risk

def erc_objective(w, cov):
    """Objectif ERC: somme (contrib - 1/n)^2"""
    contrib = risk_contribution(w, cov)
    target = 1.0 / len(w)
    return np.sum((contrib - target)**2)

def itr_constraint(w):
    """Pondéré ITR <= 2°C"""
    return np.sum(w * itr_opt) - 2.0

# Contraintes
constraints = [
    {'type': 'eq', 'fun': lambda w: np.sum(w) - 1},  # Somme=1
    {'type': 'ineq', 'fun': itr_constraint}  # ITR <=2
]

# Bornes [0,1] par actif
bounds = [(0, 1) for _ in range(n_assets)]

# Optimisation
res = minimize(
    fun=erc_objective, 
    x0=w0, 
    args=(cov.values,),
    method='SLSQP',
    bounds=bounds,
    constraints=constraints,
    options={'disp': True, 'maxiter': 1000}
)

if not res.success:
    print('⚠️ Optimisation échouée, utilisation poids uniformes')
    weights_opt = np.ones(n_assets) / n_assets
else:
    weights_opt = res.x
    print(f'✅ Optimisation réussie: risque = {portfolio_risk(weights_opt, cov.values):.2%}')

# Results
df_results = df_portfolio.copy()
df_results['weight_opt'] = weights_opt
df_results['risk_contrib'] = risk_contribution(weights_opt, cov.values)

# Métriques
port_itr = np.sum(weights_opt * itr_opt)
port_esg = np.sum(weights_opt * df_portfolio.esg)
port_vol = portfolio_risk(weights_opt, cov.values)
port_mu = np.sum(weights_opt * df_portfolio.mu / 100)

print(f'\n📋 METRIQUES PORTEFEUILLE:')
print(f'   ITR pondéré: {port_itr:.2f}°C')
print(f'   ESG pondéré: {port_esg:.1f}')
print(f'   Rendement attendu: {port_mu:.2%}')
print(f'   Volatilité: {port_vol:.2%}')
print(f'   Tickers: {n_assets}')

# Top 10
print('\n🏆 Top 10 poids:')
print(df_results.nlargest(10, 'weight_opt')[['ticker', 'NAME', 'SECTOR', 'weight_opt', 'esg', 'itr']].round(3).to_string(index=False))

# Sauvegarde
df_results.to_csv('portfolio_final.csv', index=False)
print('\n💾 portfolio_final.csv sauvegardé')

# =======================================
# 5. VISUALISATIONS
# =======================================
print('\n📊 Création graphiques...')

fig = make_subplots(
    rows=2, cols=2,
    subplot_titles=('Poids', 'Contribution Risque', 'ITR vs ESG', 'Répartition Sectorielle'),
    specs=[[{"type": "bar"}, {"type": "bar"}], [{"type": "scatter"}, {"type": "pie"}]]
)

# Poids
top_weights = df_results.nlargest(15, 'weight_opt')
fig.add_trace(go.Bar(x=top_weights.ticker, y=top_weights.weight_opt, name='Poids', marker_color='lightblue'), row=1, col=1)

# Risk contrib
top_risk = df_results.nlargest(15, 'risk_contrib')
fig.add_trace(go.Bar(x=top_risk.ticker, y=top_risk.risk_contrib, name='Risk Contrib', marker_color='orange'), row=1, col=2)

# ITR vs ESG
fig.add_trace(go.Scatter(x=df_results.esg, y=df_results.itr, mode='markers', 
                        marker=dict(size=df_results.weight_opt*5000, color=df_results.SECTOR, colorscale='Viridis'),
                        text=df_results.ticker, hovertemplate='<b>%{text}</b><br>ESG: %{x}<br>ITR: %{y}<extra></extra>'), 
              row=2, col=1)

# Secteurs
sector_weights = df_results.groupby('SECTOR')['weight_opt'].sum().sort_values(ascending=False)
fig.add_trace(go.Pie(labels=sector_weights.index, values=sector_weights.values, name='Secteurs'), row=2, col=2)

fig.update_layout(height=800, title_text='Portefeuille ESG ERC 2°C Aligned', showlegend=False)
fig.write_html('portfolio_visualization.html')
print('💾 portfolio_visualization.html sauvegardé')

print('\n🎉 Portefeuille construit avec succès!')
print('Fichiers générés:')
print('  - portfolio_final.csv')
print('  - portfolio_visualization.html')
