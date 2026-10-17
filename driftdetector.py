import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import ks_2samp, chi2_contingency

st.set_page_config(page_title="Data Drift Detector", layout="wide")
st.title("📊 Data Drift Detector")

# ---------- Helper functions ----------
def psi(expected, actual, bins=10):
    """Population Stability Index for numeric columns."""
    cuts = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    cuts[0], cuts[-1] = -np.inf, np.inf
    e = np.histogram(expected, cuts)[0] / len(expected)
    a = np.histogram(actual, cuts)[0] / len(actual)
    e, a = np.clip(e, 1e-4, None), np.clip(a, 1e-4, None)
    return float(np.sum((a - e) * np.log(a / e)))

def categorical_test(train_col, new_col):
    """Chi-square test for categorical columns."""
    t = train_col.value_counts()
    n = new_col.value_counts()
    table = pd.concat([t, n], axis=1).fillna(0)
    _, p, _, _ = chi2_contingency(table.values)
    return p

def demo_data():
    rng = np.random.default_rng(42)
    train = pd.DataFrame({
        "age": rng.normal(35, 8, 1000),
        "income": rng.normal(50000, 10000, 1000),
        "city": rng.choice(["Kolkata", "Delhi", "Mumbai"], 1000, p=[.4, .3, .3]),
    })
    today = pd.DataFrame({
        "age": rng.normal(42, 8, 500),            # drifted
        "income": rng.normal(50500, 10000, 500),  # almost same
        "city": rng.choice(["Kolkata", "Delhi", "Mumbai"], 500, p=[.1, .2, .7]),  # drifted
    })
    return train, today

# ---------- Sidebar ----------
st.sidebar.header("Data")
use_demo = st.sidebar.checkbox("Use demo data", value=True)
alpha = st.sidebar.slider("Significance level (alpha)", 0.01, 0.10, 0.05, 0.01)

if use_demo:
    train_df, new_df = demo_data()
else:
    f1 = st.sidebar.file_uploader("Training data (CSV)", type="csv")
    f2 = st.sidebar.file_uploader("Today's data (CSV)", type="csv")
    if not (f1 and f2):
        st.info("Upload both CSV files to continue.")
        st.stop()
    train_df, new_df = pd.read_csv(f1), pd.read_csv(f2)

# ---------- Drift calculation ----------
rows = []
for col in train_df.columns:
    if col not in new_df.columns:
        continue
    tr, nw = train_df[col].dropna(), new_df[col].dropna()
    if pd.api.types.is_numeric_dtype(tr):
        stat, p = ks_2samp(tr, nw)
        rows.append({"feature": col, "type": "numeric", "test": "KS",
                     "p_value": p, "PSI": psi(tr.values, nw.values)})
    else:
        p = categorical_test(tr, nw)
        rows.append({"feature": col, "type": "categorical", "test": "Chi-square",
                     "p_value": p, "PSI": np.nan})

res = pd.DataFrame(rows)
res["drift"] = res["p_value"] < alpha

# ---------- Drift score ----------
drift_score = res["drift"].mean() * 100   # % of features drifted
c1, c2, c3 = st.columns(3)
c1.metric("Drift Score", f"{drift_score:.1f}%")
c2.metric("Drifted Features", f"{res['drift'].sum()} / {len(res)}")
c3.metric("Status", "🚨 DRIFT" if drift_score > 30 else "✅ Stable")

st.subheader("Feature-wise results")
st.dataframe(res.style.format({"p_value": "{:.4f}", "PSI": "{:.3f}"}), use_container_width=True)
st.caption("PSI guide: < 0.1 no drift, 0.1–0.25 moderate, > 0.25 significant.")

# ---------- Visual comparison ----------
st.subheader("Distribution comparison")
col = st.selectbox("Pick a feature", res["feature"])
if pd.api.types.is_numeric_dtype(train_df[col]):
    bins = np.histogram_bin_edges(pd.concat([train_df[col], new_df[col]]).dropna(), bins=20)
    chart = pd.DataFrame({
        "Training": np.histogram(train_df[col].dropna(), bins, density=True)[0],
        "Today": np.histogram(new_df[col].dropna(), bins, density=True)[0],
    })
else:
    chart = pd.DataFrame({
        "Training": train_df[col].value_counts(normalize=True),
        "Today": new_df[col].value_counts(normalize=True),
    }).fillna(0)
st.bar_chart(chart)