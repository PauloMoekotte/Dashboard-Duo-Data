import streamlit as st
import pandas as pd
import plotly.express as px

# -----------------------------------------------------------------------------
# 1. CONFIGURATIE
# -----------------------------------------------------------------------------
st.set_page_config(page_title="DUO MBO Dashboard", layout="wide")

# DUO Open Data links (MBO)
# Bron: https://duo.nl/open_onderwijsdata/middelbaar-beroepsonderwijs/
duo_links = {
    "Kies een dataset...": None,
    "01. Studenten per instelling (2023)": "https://duo.nl/open_onderwijsdata/images/01-studenten-per-instelling-mbo-bestuur-2023.csv",
    "03. Studenten per opleiding (2023)": "https://duo.nl/open_onderwijsdata/images/03-studenten-per-opleiding-mbo-2023.csv",
    "06. Erediploma's (2022)": "https://duo.nl/open_onderwijsdata/images/06-gediplomeerden-mbo-erediploma-2022.csv",
    "VSV: Vroegtijdig schoolverlaters": "https://duo.nl/open_onderwijsdata/images/01-vsv-in-het-mbo-naar-instelling-en-gemeente-2022-2023.csv"
}

# -----------------------------------------------------------------------------
# 2. HELPER FUNCTIES
# -----------------------------------------------------------------------------

@st.cache_data
def load_data(uploaded_file):
    """Leest CSV in en probeert separator (en decimalen) te raden."""
    try:
        # Veel NL overheidsdata gebruikt ; als separator en , als decimaal
        df = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='latin-1')
        
        # Fallback: als de data in 1 kolom wordt gepropt, is het waarschijnlijk toch een komma
        if df.shape[1] < 2:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, sep=',', decimal='.')
        
        return df
    except Exception as e:
        st.error(f"Kon bestand niet lezen: {e}")
        return None

def detect_column_types(df):
    """Retourneert initiële lijsten van categorische en numerieke kolommen."""
    numerics = df.select_dtypes(include=['number']).columns.tolist()
    categoricals = df.select_dtypes(exclude=['number']).columns.tolist()
    return categoricals, numerics

# -----------------------------------------------------------------------------
# 3. INTERFACE OPBOUW
# -----------------------------------------------------------------------------

st.title("📊 Interactief Dashboard - DUO Data")

# --- STAP A: DUO DATA SELECTIE (Dropdown & Download link) ---
with st.container():
    st.markdown("### 1. Data Ophalen")
    st.write("Selecteer een bestand uit het DUO portaal, download het, en upload het vervolgens hieronder.")
    
    col_link, col_info = st.columns([1, 3])
    with col_link:
        selected_dataset = st.selectbox("Selecteer DUO bestand:", list(duo_links.keys()))
    
    with col_info:
        if selected_dataset and duo_links[selected_dataset]:
            url = duo_links[selected_dataset]
            st.info(f"📥 **[Klik hier om '{selected_dataset}' te downloaden]({url})**")

st.divider()

# --- STAP B: UPLOAD BUTTON ---
st.markdown("### 2. Data Visualiseren")
uploaded_file = st.file_uploader("Upload DUO data (csv)", type=['csv'])

if uploaded_file is not None:
    # Data inladen
    df = load_data(uploaded_file)

    if df is not None:
        # Automatische detectie uitvoeren
        init_cats, init_nums = detect_column_types(df)
        all_cols = df.columns.tolist()

        # --- LAYOUT: GRAFIEK (Links) vs INSTELLINGEN (Rechts) ---
        col_graph, col_settings = st.columns([3, 1])

        # ---------------------------------------------------------
        # RECHTERKANT: INSTELLINGEN & CONTROLES
        # ---------------------------------------------------------
        with col_settings:
            st.header("Instellingen")
            
            # 1. Kolom Identificatie (Modify)
            with st.expander("🛠️ Kolom Identificatie", expanded=True):
                st.caption("Controleer of de kolommen juist zijn herkend.")
                
                # We laten de gebruiker de lijsten aanpassen.
                # Default waarde is wat de automatische detectie vond.
                selected_dims_cfg = st.multiselect(
                    "Dimensies (Labels/Tekst)", 
                    options=all_cols, 
                    default=init_cats
                )
                
                selected_meas_cfg = st.multiselect(
                    "Meetwaarden (Getallen)", 
                    options=all_cols, 
                    default=init_nums
                )

            st.divider()

            # 2. As Selectie
            st.subheader("Assen Selectie")
            
            # X-As (slechts 1 keuze mogelijk)
            if selected_dims_cfg:
                x_axis = st.selectbox("Kies X-as (Label)", selected_dims_cfg)
            else:
                x_axis = None
                st.warning("Geen dimensies gevonden.")

            # Y-As (Meerdere keuzes mogelijk voor gestapeld)
            if selected_meas_cfg:
                y_axis = st.multiselect("Kies Y-as (Waarden)", selected_meas_cfg, default=selected_meas_cfg[:1])
            else:
                y_axis = None
                st.warning("Geen meetwaarden gevonden.")

            st.divider()

            # 3. Filters & Sortering
            st.subheader("Weergave")
            
            top_n_optie = st.radio("Toon aantal:", ["Top 5", "Top 10", "Top 20", "Alles"], index=1)
            
            sort_direction = st.radio("Sortering:", ["Hoog naar Laag", "Laag naar Hoog"], index=0)
            ascending_bool = True if sort_direction == "Laag naar Hoog" else False

        # ---------------------------------------------------------
        # LINKERKANT: DATA PROCESSING & GRAFIEK
        # ---------------------------------------------------------
        with col_graph:
            if x_axis and y_axis and len(y_axis) > 0:
                
                # A. Data Aggregatie (Sommeren per categorie)
                # Dit voorkomt dat je 1000 losse regels ziet; we tellen totalen op per unieke X-waarde
                try:
                    df_grouped = df.groupby(x_axis)[y_axis].sum().reset_index()

                    # B. Sortering voorbereiden
                    # We maken een hulpkolom 'Total' om te sorteren op de som van alle geselecteerde Y-assen
                    df_grouped['__Totaal_Sort__'] = df_grouped[y_axis].sum(axis=1)
                    df_grouped = df_grouped.sort_values(by='__Totaal_Sort__', ascending=ascending_bool)
                    
                    # C. Top N Filtering
                    if top_n_optie != "Alles":
                        n = int(top_n_optie.split(" ")[1])
                        # Bij Top N wil je normaal de 'grootste' zien.
                        # Als we oplopend sorteren (laag->hoog), pakken we head(n) = de laagste n.
                        # Als we aflopend sorteren (hoog->laag), pakken we head(n) = de hoogste n.
                        # Vanwege de sort_values hierboven werkt .head(n) in beide gevallen correct voor wat er op dat moment bovenaan staat.
                        df_viz = df_grouped.head(n)
                    else:
                        df_viz = df_grouped

                    # D. Grafiek Bouwen
                    st.subheader(f"Grafiek: {', '.join(y_axis)} per {x_axis}")
                    
                    fig = px.bar(
                        df_viz,
                        x=x_axis,
                        y=y_axis, # Doordat dit een lijst kan zijn, maakt Plotly automatisch een gestapelde grafiek
                        title=f"{top_n_optie} weergave",
                        template="plotly_white",
                        barmode='stack' # Expliciet gestapeld
                    )

                    # Layout finetuning
                    fig.update_layout(
                        legend_title_text="Legenda",
                        xaxis_title=x_axis,
                        yaxis_title="Waarde",
                        xaxis={'categoryorder':'array', 'categoryarray': df_viz[x_axis]} # Behoud onze sortering
                    )

                    st.plotly_chart(fig, use_container_width=True)

                    # E. Tabel weergave (optioneel)
                    with st.expander("Bekijk onderliggende data tabel"):
                        st.dataframe(df_viz.drop(columns=['__Totaal_Sort__']))
                
                except Exception as e:
                    st.error(f"Fout bij genereren grafiek. Controleer of de geselecteerde meetwaarden echt getallen zijn.\nDetail: {e}")
            else:
                st.info("Selecteer aan de rechterzijde tenminste één dimensie (X-as) en één meetwaarde (Y-as).")

else:
    # Lege staat
    st.info("👆 Upload een bestand om te beginnen.")
