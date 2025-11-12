import streamlit as st
import pandas as pd
import plotly.express as px

# Hulpfunctie om numerieke kolommen te identificeren op basis van inhoud
@st.cache_data
def get_numeric_cols(df):
    """
    Identificeer numerieke kolommen door eerste 50 rijen te controleren.
    Een kolom is numeriek als >80% van de waarden numeriek is.
    """
    numeric_cols = []
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            numeric_cols.append(col)
            continue
        try:
            sample = df[col].sample(min(50, len(df))).astype(str).str.replace('.', '', regex=False).str.strip()
            numeric_ratio = pd.to_numeric(sample, errors='coerce').notna().mean()
            if numeric_ratio >= 0.8:
                numeric_cols.append(col)
        except Exception:
            continue
    return numeric_cols

@st.cache_data
def get_year_col(df):
    """Zoekt naar een kolom die waarschijnlijk een jaartal vertegenwoordigt."""
    for col in df.columns:
        col_lower = col.lower().strip()
        if 'jaar' in col_lower or 'onderwijsjaar' in col_lower or col_lower == 'jj':
            return col
    return None

@st.cache_data
def load_data(uploaded_file):
    """Laadt de CSV met puntkomma als scheidingsteken."""
    try:
        df = pd.read_csv(uploaded_file, delimiter=';', dtype=str)
        df.columns = [c.strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Fout bij lezen bestand: {e}")
        return None

# --- PAGINA CONFIGURATIE ---
st.set_page_config(layout="wide", page_title="MBO Dashboard")

st.title("MBO Onderwijsdata Dashboard")
st.write("Upload een CSV-bestand (met puntkomma ';') om te visualiseren.")

uploaded_file = st.file_uploader("Upload DUO data (csv)", type="csv")
if uploaded_file is None:
    st.info("Wacht op het uploaden van een CSV-bestand.")
    st.stop()

df = load_data(uploaded_file)
if df is None or df.empty:
    st.warning("Bestand bevat geen rijen of kon niet worden geladen.")
    st.stop()

all_cols = df.columns.tolist()
numeric_cols = get_numeric_cols(df)
year_col = get_year_col(df)
grouping_cols = [col for col in all_cols if col not in numeric_cols]

# --- ZIJBALK ---
st.sidebar.header("Dashboard Instellingen")
advanced_mode = st.sidebar.toggle("Geavanceerde Weergave", value=False)

# --- Basis Instellingen ---
st.sidebar.subheader("Basis Instellingen")
top_n = st.sidebar.selectbox("Toon Top Aantal:", [5, 10, 20], index=1)
if not grouping_cols:
    st.error("Geen categorische kolommen gevonden voor Y-as. Controleer het CSV-bestand.")
    st.stop()
if not numeric_cols:
    st.error("Geen numerieke kolommen gevonden voor X-as. Controleer het CSV-bestand.")
    st.stop()

y_axis = st.sidebar.selectbox("Y-as (Labels/Groepering):", grouping_cols, index=0)
default_x = [numeric_cols[0]] if numeric_cols else []
x_axes = st.sidebar.multiselect("X-as (Waarden/Sommatie - Meerdere mogelijk):", numeric_cols, default=default_x)
sort_order_str = st.sidebar.selectbox("Ordening:", ["Hoog naar Laag", "Laag naar Hoog"], index=0)
sort_ascending = (sort_order_str == "Laag naar Hoog")

selected_years = []
show_data_labels = False
if advanced_mode:
    st.sidebar.subheader("Geavanceerde Opties")
    # Jaar slicer
    if year_col:
        try:
            years = pd.to_numeric(df[year_col], errors='coerce').dropna().unique()
            if len(years) > 0:
                years = [str(int(y)) for y in sorted(years, reverse=True)]
                selected_years = st.sidebar.multiselect("Filter op Jaar (Slicer):", years, default=years[0:1])
        except Exception as e:
            st.sidebar.error(f"Kon de 'jaar'-kolom niet verwerken: {e}")
    else:
        st.sidebar.info("Geen 'jaar'-kolom gevonden voor de slicer.")
    show_data_labels = st.sidebar.checkbox("Toon waarden in grafiek", value=False)
    st.sidebar.text_input("Formule Editor (Toekomst)", disabled=True)
    st.sidebar.selectbox("Decimale Toggle (Toekomst)", ["Aantallen", "Decimalen"], disabled=True)

if not y_axis or not x_axes:
    st.warning("Selecteer alstublieft een Y-as en minimaal één X-as in de zijbalk.")
    st.stop()

# --- DATA VERWERKEN ---
df_processed = df.copy()

# 1. Jaar filter (indien geselecteerd)
if advanced_mode and year_col and selected_years:
    df_processed = df_processed[df_processed[year_col].astype(str).isin(selected_years)]

# 2. Converteer gekozen X-assen naar numeriek
for col in x_axes:
    df_processed[col] = pd.to_numeric(
        df_processed[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False), 
        errors='coerce'
    ).fillna(0)

# 3. Aggregeer de data
try:
    df_agg = df_processed.groupby(y_axis, as_index=False)[x_axes].sum()
except Exception as e:
    st.error(f"Fout bij aggregeren van data: {e}")
    st.stop()

if df_agg.empty:
    st.warning("Geen geaggregeerde data voor deze selectie.")
    st.stop()

# 4. Bereken totaal per groepering (voor sortering en selectie top N)
df_agg['__Totaal__'] = df_agg[x_axes].sum(axis=1)
df_agg = df_agg.sort_values('__Totaal__', ascending=False)
df_top_n = df_agg.head(top_n).copy()
# Let op: sorteer nogmaals alleen binnen de top N voor het plotten:
df_top_n = df_top_n.sort_values('__Totaal__', ascending=sort_ascending)

# 5. Data "melt" voor Plotly
try:
    df_melted = df_top_n.melt(
        id_vars=[y_axis, '__Totaal__'],
        value_vars=x_axes,
        var_name='Meetwaarde',
        value_name='Waarde'
    )
except Exception as e:
    st.error(f"Fout bij het omvormen van de data voor grafiek: {e}")
    st.stop()

if df_melted.empty:
    st.warning("Geen data gevonden voor de geselecteerde criteria.")
    st.stop()

# --- GRAFIEK MET PLOTLY ---
jaar_info = f"(Jaren: {', '.join(selected_years)})" if advanced_mode and year_col and selected_years else ""
title = f"Top {top_n} {y_axis} | Totaal van: {', '.join(x_axes)} {jaar_info}"

fig = px.bar(
    df_melted,
    y=y_axis,
    x='Waarde',
    color='Meetwaarde',
    orientation='h',
    title=title,
    labels={'Waarde': f"Totaal ({', '.join(x_axes)})", 'Meetwaarde': 'Waarde'}
)

# Sorteer de Y-as op totale waarde (zodat hoogste altijd bovenaan is)
fig.update_layout(
    yaxis={'categoryorder': ('total ascending' if sort_ascending else 'total descending')},
    height=600,
    legend_title_text='Meetwaarden (X-as)'
)

# Toon datalabels indien gewenst
if advanced_mode and show_data_labels:
    fig.update_traces(
        texttemplate='%{x:,.0f}',
        textposition='outside'
    )

st.plotly_chart(fig, use_container_width=True)

# --- DATAFRAME (optioneel) ---
with st.expander("Toon de Top N geaggregeerde data"):
    st.dataframe(df_top_n.set_index(y_axis).sort_values('__Totaal__', ascending=False).drop(columns='__Totaal__'))

with st.expander("Toon de eerste 100 rijen van de ruwe data"):
    st.dataframe(df.head(100))
