import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils import detect_and_clean_data

# Hulpfunctie om de CSV te laden
@st.cache_data
def get_year_col(df):
    """Zoekt naar een kolom die waarschijnlijk een jaartal vertegenwoordigt."""
    for col in df.columns:
        col_lower = col.lower()
        if 'jaar' in col_lower or 'onderwijsjaar' in col_lower or col_lower == 'jj':
            return col
    return None

@st.cache_data
def load_data(uploaded_file):
    """
    Laadt de CSV met een puntkomma als scheidingsteken.
    Gebruikt 'latin-1' codering om UnicodeDecodeError te voorkomen bij speciale karakters.
    """
    try:
        # We lezen de data in met 'object' dtype om te voorkomen dat pandas 
        # getallen met een '.' (bijv. 1.000) als floats interpreteert.
        # Belangrijk: gebruik encoding='latin-1' voor de DUO-bestanden
        df = pd.read_csv(uploaded_file, delimiter=';', dtype=str, encoding='latin-1')
        return df
    except Exception as e:
        st.error(f"Fout bij het lezen van het bestand: {e}")
        return None

# --- PAGINA CONFIGURATIE ---
st.set_page_config(layout="wide", page_title="MBO Dashboard")

st.title("MBO Onderwijsdata Dashboard")
st.write("Upload een CSV-bestand van DUO (met puntkomma ';') om de visualisatie te starten.")

# --- FILE UPLOAD ---
uploaded_file = st.file_uploader("Upload DUO data (csv)", type="csv")

if uploaded_file is None:
    st.info("Wacht op het uploaden van een CSV-bestand.")
    st.stop()

# --- DATA LADEN & VERWERKEN ---
df_raw = load_data(uploaded_file)
if df_raw is None:
    st.stop()

# Automatische detectie en opschoning
df_clean, mask_lt5, categoricals, numerics = detect_and_clean_data(df_raw)
year_col = get_year_col(df_raw)

# --- ZIJBALK VOOR CONTROLES ---
st.sidebar.header("Dashboard Instellingen")

# --- Basis Instellingen ---
st.sidebar.subheader("Basis Instellingen")

y_axis = st.sidebar.selectbox(
    "Y-as (Labels/Groepering):", 
    categoricals,
    index=0
)

# Probeer de eerste numerieke kolom als standaard te selecteren
default_x = [numerics[0]] if numerics else []
x_axes = st.sidebar.multiselect(
    "X-as (Waarden/Sommatie - Meerdere mogelijk):", 
    numerics,
    default=default_x
)

top_n = st.sidebar.selectbox(
    "Toon Top Aantal:",
    [5, 10, 20, 50, "Alles"],
    index=1 # Standaard Top 10
)

sort_order_str = st.sidebar.selectbox(
    "Ordening:", 
    ["Hoog naar Laag", "Laag naar Hoog"], 
    index=0
)
sort_ascending = (sort_order_str == "Laag naar Hoog")

show_data_labels = st.sidebar.checkbox("Toon waarden in grafiek", value=False)

# --- Geavanceerde Opties (alleen als een jaarkolom is gevonden) ---
selected_years = []
if year_col:
    st.sidebar.subheader("Filters")
    try:
        years = pd.to_numeric(df_raw[year_col], errors='coerce').dropna().unique()
        years.sort()
        years = [str(int(y)) for y in years][::-1]

        selected_years = st.sidebar.multiselect(
            "Filter op Jaar:",
            years,
            default=years[0] if years else []
        )
    except Exception as e:
        st.sidebar.error(f"Kon de 'jaar'-kolom niet verwerken: {e}")

# --- DATA AGGREGATIE ---

if not y_axis or not x_axes:
    st.warning("Selecteer alstublieft een Y-as en minimaal één X-as in de zijbalk.")
    st.stop()

# Filter op jaar (indien van toepassing)
df_filtered = df_clean.copy()
if year_col and selected_years:
    df_filtered = df_filtered[df_filtered[year_col].isin(selected_years)]

# Aggregeer de data
try:
    df_agg = df_filtered.groupby(y_axis)[x_axes].sum().reset_index()
except Exception as e:
    st.error(f"Fout bij het aggregeren van data. Controleer of {y_axis} correct is: {e}")
    st.stop()

# Bereken Totaal voor sortering
df_agg['Totaal'] = df_agg[x_axes].sum(axis=1)

# Sorteer en pas Top N toe
df_sorted = df_agg.sort_values('Totaal', ascending=sort_ascending)
if top_n != "Alles":
    # Als we aflopend sorteren (hoog naar laag), willen we de eerste N rijen
    # Als we oplopend sorteren, willen we de laatste N rijen
    df_top_n = df_sorted.head(top_n) if not sort_ascending else df_sorted.tail(top_n)
else:
    df_top_n = df_sorted

# 'Melt' de data voor gestapelde grafiek in Plotly
try:
    df_melted = df_top_n.melt(
        id_vars=[y_axis, 'Totaal'],
        value_vars=x_axes,
        var_name='Meetwaarde',
        value_name='Waarde'
    )
except Exception as e:
    st.error(f"Fout bij het 'melten' van de data: {e}")
    st.stop()

# --- GRAFIEK RENDEREN ---
if df_melted.empty or df_top_n['Totaal'].sum() == 0:
    st.warning("Geen data om te tonen voor de geselecteerde criteria.")
    st.stop()

# Maak de titel dynamisch met jaartal-info
jaar_info = f"(Jaren: {', '.join(selected_years)})" if selected_years else "(Alle jaren)"
title = f"Top {top_n} {y_axis} | Totaal van: {', '.join(x_axes)} {jaar_info}"

fig = px.bar(
    df_melted,
    y=y_axis,
    x='Waarde',
    color='Meetwaarde',
    orientation='h',
    title=title,
    labels={'Waarde': f"Totaal ({', '.join(x_axes)})", 'Meetwaarde': 'Geselecteerde X-as'}
)

fig.update_layout(
    yaxis={'categoryorder': 'total ascending' if sort_ascending else 'total descending'},
    height=600,
    legend_title_text='Meetwaarden (X-as)'
)

if show_data_labels:
    fig.update_traces(texttemplate='%{value:,.0f}', textposition='outside')

st.plotly_chart(fig, use_container_width=True)


# --- DATA KWALITEIT & PRIVACY CHECK ---
st.markdown("---")
st.subheader("⚠️ Data Kwaliteit & Privacy Check")

# Filter de mask op de categorieën die in de Top N zitten
visible_categories = df_top_n[y_axis].unique()
mask_sub = mask_lt5[df_clean[y_axis].isin(visible_categories)].copy()
mask_sub['__Dim__'] = df_clean.loc[mask_sub.index, y_axis]

# Tel '<5' per categorie voor de geselecteerde meetwaarden
lt5_counts = mask_sub.groupby('__Dim__')[x_axes].sum()
lt5_counts['Totaal_Verborgen'] = lt5_counts.sum(axis=1)
report = lt5_counts[lt5_counts['Totaal_Verborgen'] > 0]

if not report.empty:
    st.warning(
        "De onderstaande tabel toont hoe vaak de waarde **'<5'** voorkomt in de "
        "brongegevens voor de huidige selectie. Deze waarden zijn in de grafiek als **0** geteld."
    )
    st.dataframe(report.drop(columns=['Totaal_Verborgen']))
else:
    st.success("Geen privacy-gevoelige waarden ('<5') gevonden in de getoonde selectie.")


# --- TOON DATA (optioneel) ---
with st.expander("Toon de Top N geaggregeerde data"):
    st.dataframe(df_top_n.set_index(y_axis).sort_values('Totaal', ascending=False))

with st.expander("Toon de eerste 100 rijen van de ruwe data"):
    st.dataframe(df_raw.head(100))
