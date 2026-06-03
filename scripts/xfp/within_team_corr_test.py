"""Within-team residual correlation test on backfill panel.

Backs out implied total σ from win_probability, splits to per-team σ
proportionally to projected total (proxy — close enough for residual
normalization since σ scales weakly with total). Computes std(z) of
normalized residuals. Estimates σ² scaling factor s and within-team ρ̄.
"""
import numpy as np
import pandas as pd
from scipy.stats import norm

PATH = r"c:\Users\Joshua\plv_clone\data\outputs\predictions_history.csv"

df = pd.read_csv(PATH)
# Keep rows with actuals (backfill panel) and dedup on (date,my_team,opp_team)
df = df.dropna(subset=["actual_my_final", "actual_opp_final"]).copy()
df = df.drop_duplicates(subset=["date", "my_team", "opp_team", "my_projected_total"])
print(f"Panel size (post-dedup): {len(df)}")

# Back out implied total sigma from win_prob
# win_prob = Φ(diff / sigma_total) -> sigma_total = diff / Φ^-1(win_prob)
diff = df["my_projected_total"] - df["opp_projected_total"]
z_wp = norm.ppf(df["win_probability"].clip(1e-4, 1 - 1e-4))
# Avoid division blow-up when z_wp very small
mask = np.abs(z_wp) > 1e-3
sigma_total = np.where(mask, diff / z_wp, np.nan)
df["sigma_total_implied"] = sigma_total
df = df.dropna(subset=["sigma_total_implied"])
df = df[df["sigma_total_implied"] > 0]
print(f"After sigma backout: {len(df)}")

# Split sigma_total between teams proportionally to projected total
# sigma_total^2 = sigma_my^2 + sigma_opp^2
# Assume sigma_team ∝ projected_total (constant CV approximation)
prop_my = df["my_projected_total"] / (df["my_projected_total"] + df["opp_projected_total"])
prop_opp = 1 - prop_my
# Want sigma_my^2 + sigma_opp^2 = sigma_total^2
# Use: sigma_my = sigma_total * prop_my / sqrt(prop_my^2 + prop_opp^2)
denom = np.sqrt(prop_my**2 + prop_opp**2)
sigma_my = df["sigma_total_implied"] * prop_my / denom
sigma_opp = df["sigma_total_implied"] * prop_opp / denom

# Residuals (z = residual / sigma)
resid_my = df["actual_my_final"] - df["my_projected_total"]
resid_opp = df["actual_opp_final"] - df["opp_projected_total"]
z_my = resid_my / sigma_my
z_opp = resid_opp / sigma_opp

# Stack — every team-matchup is one observation
yr = df["backfill_year"].fillna(2026).astype(int)
z_all = pd.DataFrame({
    "z": np.concatenate([z_my, z_opp]),
    "year": np.concatenate([yr, yr]),
})
# Trim extreme outliers (synthetic backfill projection lacks boom_stack — a few
# huge mis-projections shouldn't dominate)
z_all = z_all[np.abs(z_all["z"]) < 5]
print(f"Normalized residuals: {len(z_all)}")

std_pooled = z_all["z"].std()
mean_pooled = z_all["z"].mean()
print(f"\nPOOLED: mean(z) = {mean_pooled:+.4f}, std(z) = {std_pooled:.4f}")

for y, sub in z_all.groupby("year"):
    print(f"  {y}: n={len(sub)}, mean(z)={sub['z'].mean():+.4f}, std(z)={sub['z'].std():.4f}")

# Sigma^2 scaling factor and rho
s_pooled = std_pooled ** 2
n_roster = 22
rho_pooled = (s_pooled - 1) / (n_roster - 1)
print(f"\ns_pooled = std(z)^2 = {s_pooled:.4f}")
print(f"rho_pooled (n={n_roster}) = {rho_pooled:+.5f}")

for y, sub in z_all.groupby("year"):
    s_y = sub["z"].std() ** 2
    rho_y = (s_y - 1) / (n_roster - 1)
    print(f"  {y}: s={s_y:.4f}, rho={rho_y:+.5f}")

# === Win-prob redistribution after scaling ===
df_unique = df.drop_duplicates(subset=["date", "my_team", "opp_team"]).copy()
sigma_total_new = df_unique["sigma_total_implied"] * np.sqrt(s_pooled)
wp_new = norm.cdf(
    (df_unique["my_projected_total"] - df_unique["opp_projected_total"]) / sigma_total_new
)
df_unique["wp_new"] = wp_new
df_unique["wp_old"] = df_unique["win_probability"]

print("\n=== Win-prob distribution: OLD vs NEW ===")
def bucket_stats(col):
    return {
        ">=85%": (df_unique[col] >= 0.85).sum(),
        ">=75%": (df_unique[col] >= 0.75).sum(),
        ">=65%": (df_unique[col] >= 0.65).sum(),
        "35-65%": ((df_unique[col] >= 0.35) & (df_unique[col] < 0.65)).sum(),
        "<=25%": (df_unique[col] <= 0.25).sum(),
        "<=15%": (df_unique[col] <= 0.15).sum(),
    }
print(f"OLD: {bucket_stats('wp_old')}")
print(f"NEW: {bucket_stats('wp_new')}")
print(f"OLD min/max: {df_unique['wp_old'].min():.3f} / {df_unique['wp_old'].max():.3f}")
print(f"NEW min/max: {df_unique['wp_new'].min():.3f} / {df_unique['wp_new'].max():.3f}")

# === Per-bucket calibration ===
df_unique["won"] = (df_unique["actual_my_final"] > df_unique["actual_opp_final"]).astype(int)

print("\n=== Bucket calibration (predicted WP vs actual win rate) ===")
def calib_table(col):
    bins = [0, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 1.01]
    labels = ["0-15", "15-25", "25-35", "35-45", "45-55", "55-65", "65-75", "75-85", "85+"]
    df_unique["bucket"] = pd.cut(df_unique[col], bins=bins, labels=labels)
    g = df_unique.groupby("bucket", observed=True).agg(
        n=("won", "size"),
        actual_winrate=("won", "mean"),
        pred_mean=(col, "mean"),
    )
    return g

print("\nOLD WP buckets:")
print(calib_table("wp_old"))
print("\nNEW WP buckets:")
print(calib_table("wp_new"))

# Overall log-loss
eps = 1e-6
def logloss(p, y):
    p = np.clip(p, eps, 1-eps)
    return -np.mean(y*np.log(p) + (1-y)*np.log(1-p))
print(f"\nLogLoss OLD: {logloss(df_unique['wp_old'].values, df_unique['won'].values):.4f}")
print(f"LogLoss NEW: {logloss(df_unique['wp_new'].values, df_unique['won'].values):.4f}")
print(f"Brier OLD:   {np.mean((df_unique['wp_old']-df_unique['won'])**2):.4f}")
print(f"Brier NEW:   {np.mean((df_unique['wp_new']-df_unique['won'])**2):.4f}")
