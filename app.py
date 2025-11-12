import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Hulpfunctie om numerieke kolommen te identificeren op basis van inhoud
@st.cache_data
def get_numeric_cols(df):
    """
    Identificeert numerieke kolommen door de eerste 50 rijen te controleren.
    Een kolom wordt als numeriek beschouwd als >80% van de waarden numeriek is.
    """
    numeric_cols = []
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            numeric_cols.append(col)
            continue
        
        # Probeer te converteren als het geen numeriek type is (bijv. object)
        try:
            sample = df[col].sample(min(50, len(df))).astype(str).str.replace('.', '', regex=False).str.strip()
            # Check of het (na opschonen) numeriek is
            numeric_ratio = pd.to_numeric(sample, errors='coerce').notna().mean()
            if numeric_ratio >= 0.8:
                numeric_cols.append(col)
        except Exception:
            continue
    return numeric_cols

# Hulpfunctie om de 'jaar'-kolom te vinden
@st.cache_data
def get_year_col(df):
    """Zoekt naar een kolom die waarschijnlijk een jaartal vertegenwoordigt."""
    for col in df.columns:
        col_lower = col.lower()
        if 'jaar' in col_lower or 'onderwijsjaar' in col_lower or col_lower == 'jj':
            return col
    return None

# Hulpfunctie om de CSV te laden
@st.cache_data
def load_data(uploaded_file):
    """Laadt de CSV met een puntkomma als scheidingsteken."""
    try:
        # We lezen de data in met 'object' dtype om te voorkomen dat pandas 
        # getallen met een '.' (bijv. 1.000) als floats interpreteert.
        df = pd.read_csv(uploaded_file, delimiter=';', dtype=str)
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

# --- DATA LADEN ---
df = load_data(uploaded_file)
if df is None:
    st.stop()

# --- KOLOM IDENTIFICATIE ---
all_cols = df.columns.tolist()
numeric_cols = get_numeric_cols(df)
year_col = get_year_col(df)

# Groeperingskolommen zijn alle kolommen die niet als numeriek zijn geïdentificeerd
grouping_cols = [col for col in all_cols if col not in numeric_cols]

# --- ZIJBALK VOOR CONTROLES ---
st.sidebar.header("Dashboard Instellingen")

# Toggle voor geavanceerde modus
advanced_mode = st.sidebar.toggle("Geavanceerde Weergave", value=False)

# --- Basis Instellingen ---
st.sidebar.subheader("Basis Instellingen")
top_n = st.sidebar.selectbox(
    "Toon Top Aantal:", 
    [5, 10, 20], 
    index=1 # Standaard Top 10
)

y_axis = st.sidebar.selectbox(
    "Y-as (Labels/Groepering):", 
    grouping_cols, 
    index=0
)

# Probeer de eerste numerieke kolom als standaard te selecteren
default_x = [numeric_cols[0]] if numeric_cols else []

x_axes = st.sidebar.multiselect(
    "X-as (Waarden/Sommatie - Meerdere mogelijk):", 
    numeric_cols, 
    default=default_x
)

sort_order_str = st.sidebar.selectbox(
    "Ordening:", 
    ["Hoog naar Laag", "Laag naar Hoog"], 
    index=0
)
sort_ascending = (sort_order_str == "Laag naar Hoog")

# --- Geavanceerde Instellingen ---
selected_years = []
show_data_labels = False

if advanced_mode:
    st.sidebar.subheader("Geavanceerde Opties")
    
    # Jaar Slicer
    if year_col:
        try:
            # Converteer jaarkolom naar numeriek voor sortering
            years = pd.to_numeric(df[year_col], errors='coerce').dropna().unique()
            years.sort()
            years = [str(int(y)) for y in years][::-1] # Sorteer aflopend
            
            selected_years = st.sidebar.multiselect(
                "Filter op Jaar (Slicer):", 
                years, 
                default=years[0] if years else [] # Standaard nieuwste jaar
            )
        except Exception as e:
            st.sidebar.error(f"Kon de 'jaar'-kolom niet verwerken: {e}")
    else:
        st.sidebar.info("Geen 'jaar'-kolom gevonden voor de slicer.")

    # Data Labels Toggle
    show_data_labels = st.sidebar.checkbox("Toon waarden in grafiek", value=False)

    # Placeholders voor toekomstige functies
    st.sidebar.text_input("Formule Editor (Toekomst)", disabled=True)
    st.sidebar.selectbox("Decimale Toggle (Toekomst)", ["Aantallen", "Decimalen"], disabled=True)


# --- DATA VERWERKING ---

if not y_axis or not x_axes:
    st.warning("Selecteer alstublieft een Y-as en minimaal één X-as in de zijbalk.")
    st.stop()

# Kopieer de data om te verwerken
df_processed = df.copy()

# 1. Jaar Filter (indien geselecteerd)
if advanced_mode and year_col and selected_years:
    df_processed = df_processed[df_processed[year_col].isin(selected_years)]

# 2. Converteer geselecteerde X-assen naar numeriek
for col in x_axes:
    # Verwijder '.' (duizendtal) en converteer naar numeriek
    df_processed[col] = pd.to_numeric(
        df_processed[col].astype(str).str.replace('.', '', regex=False), 
        errors='coerce'
    ).fillna(0)

# 3. Aggregeer de data
try:
    df_agg = df_processed.groupby(y_axis)[x_axes].sum().reset_index()
except Exception as e:
    st.error(f"Fout bij het aggregeren van data: {e}")
    st.stop()

# 4. Bereken Totaal voor sortering
df_agg['Totaal'] = df_agg[x_axes].sum(axis=1)

# 5. Sorteer en Top N
df_top_n = df_agg.sort_values('Totaal', ascending=sort_ascending).tail(top_n)

# 6. 'Melt' de data voor gestapelde grafiek in Plotly
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

if df_melted.empty:
    st.warning("Geen data gevonden voor de geselecteerde criteria.")
    st.stop()

# Maak de titel
jaar_info = f"(Jaren: {', '.join(selected_years)})" if selected_years else "(Alle jaren)"
if not advanced_mode or not year_col:
    jaar_info = ""

title = f"Top {top_n} {y_axis} | Totaal van: {', '.join(x_axes)} {jaar_info}"

# Maak de gestapelde staafgrafiek
fig = px.bar(
    df_melted,
    y=y_axis,
    x='Waarde',
    color='Meetwaarde',
    orientation='h',
    title=title,
    labels={'Waarde': f"Totaal ({', '.join(x_axes)})", 'Meetwaarde': 'Geselecteerde X-as'}
)

# Sorteer de Y-as op basis van de totale waarde
fig.update_layout(
    yaxis={'categoryorder': ('total ascending' if sort_ascending else 'total descending')},
    height=600,
    legend_title_text='Meetwaarden (X-as)'
)

# Voeg datalabels toe indien aangevinkt
if advanced_mode and show_data_labels:
    # Formatteer de labels met een duizendtal-separator
    fig.update_traces(
        texttemplate='%{value:,.0f}', 
        textposition='auto'
    )

st.plotly_chart(fig, use_container_width=True)

# --- TOON DATA (optioneel) ---
with st.expander("Toon de Top N geaggregeerde data"):
    st.dataframe(df_top_n.set_index(y_axis).sort_values('Totaal', ascending=False))

with st.expander("Toon de eerste 100 rijen van de ruwe data"):
    st.dataframe(df.head(100))
