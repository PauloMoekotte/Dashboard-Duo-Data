import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# -----------------------------------------------------------------------------
# 1. CONFIGURATIE & STARTPUNT
# -----------------------------------------------------------------------------
st.set_page_config(page_title="DUO MBO Dashboard", layout="wide")

# Dit is de specifieke startpagina zoals gevraagd
START_URL = "https://duo.nl/open_onderwijsdata/middelbaar-beroepsonderwijs/aantal-studenten/aantal-studenten-mbo-per-instelling.jsp"

# -----------------------------------------------------------------------------
# 2. SCRAPER FUNCTIES
# -----------------------------------------------------------------------------

@st.cache_data(ttl=86400) # Cache voor 24 uur
def scrape_duo_specific_structure(start_url):
    """
    Start op de 'Aantal studenten' pagina.
    Zoekt CSV's op de pagina zelf, en zoekt links naar subpagina's
    om daar ook CSV's te zoeken.
    """
    results = {"Selecteer een bestand...": None}
    status_msg = st.empty()
    
    try:
        # 1. Haal de startpagina op
        status_msg.info(f"🌐 Startpagina ophalen: {start_url} ...")
        response = requests.get(start_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Focus op content area (om navigatie links te vermijden)
        content = soup.find('main') or soup.find('div', id='content') or soup

        # 2. Zoek CSV's direct op de startpagina
        csvs_on_start = find_csv_links(content, start_url, "Startpagina")
        results.update(csvs_on_start)
        
        # 3. Zoek subpagina's (links die NIET naar een bestand wijzen)
        subpages = set()
        for a in content.find_all('a', href=True):
            href = a['href']
            full_url = urljoin(start_url, href)
            
            # Filter regels: 
            # - Moet op duo.nl blijven
            # - Geen bestanden (.csv, .pdf, etc)
            # - Geen mailto/tel
            # - Vermijd links terug naar bovenliggende pagina's (vaak broodkruimels)
            if "duo.nl" in full_url and not any(ext in href.lower() for ext in ['.csv', '.pdf', '.xls', '.zip', 'mailto:', 'javascript:', '#']):
                # Extra check: we willen alleen dieper de structuur in, of gerelateerde pagina's
                # We sluiten 'home' en algemene pagina's uit door te kijken of 'open_onderwijsdata' erin zit
                if "open_onderwijsdata" in full_url:
                    link_text = a.get_text(strip=True)
                    if link_text:
                        subpages.add((link_text, full_url))

        # 4. Bezoek gevonden subpagina's
        total = len(subpages)
        for idx, (title, url) in enumerate(subpages):
            # Vermijd duplicaten (de startpagina zelf)
            if url == start_url: 
                continue
                
            status_msg.info(f"🕵️ Scannen subpagina {idx+1}/{total}: {title}")
            try:
                sub_resp = requests.get(url, timeout=5)
                sub_soup = BeautifulSoup(sub_resp.text, 'html.parser')
                sub_content = sub_soup.find('main') or sub_soup.find('div', id='content') or sub_soup
                
                found_csvs = find_csv_links(sub_content, url, title)
                results.update(found_csvs)
            except Exception:
                continue # Skip broken links

        status_msg.empty()
        
        # Als we niks vinden, geef feedback
        if len(results) == 1:
            results["Geen CSV bestanden gevonden via automatische scan"] = None
            
        return results

    except Exception as e:
        status_msg.error(f"Fout bij verbinden met DUO: {e}")
        return {"Fout bij ophalen data": None}

def find_csv_links(soup_element, base_url, category_prefix):
    """Helper functie om CSV links uit een stuk HTML te vissen."""
    found = {}
    for a in soup_element.find_all('a', href=True):
        href = a['href']
        if href.lower().endswith('.csv'):
            full_url = urljoin(base_url, href)
            text = a.get_text(strip=True)
            filename = href.split('/')[-1]
            
            # Label maken: "Pagina Titel - Link Tekst (Bestandsnaam)"
            label = f"{category_prefix} | {text} ({filename})"
            found[label] = full_url
    return found

# -----------------------------------------------------------------------------
# 3. DATA VERWERKING LOGICA (Ongewijzigd, want werkt goed)
# -----------------------------------------------------------------------------

@st.cache_data
def load_raw_data(uploaded_file):
    try:
        df = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='latin-1', dtype=str)
        if df.shape[1] < 2:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, sep=',', decimal='.', dtype=str)
        return df
    except Exception as e:
        st.error(f"Kon bestand niet lezen: {e}")
        return None

def detect_and_clean_data(df_raw):
    df_clean = df_raw.copy()
    mask_less_than_5 = pd.DataFrame(False, index=df_raw.index, columns=df_raw.columns)
    numerics = []
    categoricals = []

    for col in df_raw.columns:
        series_clean = df_raw[col].str.strip()
        is_privacy_val = series_clean == '<5'
        mask_less_than_5[col] = is_privacy_val
        
        series_numeric_ready = series_clean.str.replace(',', '.', regex=False)
        converted = pd.to_numeric(series_numeric_ready, errors='coerce')
        
        valid_count = converted.notna().sum()
        total_count = len(df_raw)
        
        if valid_count > 0 and (is_privacy_val.any() or valid_count > 0.5 * total_count):
            df_clean[col] = converted
            numerics.append(col)
        else:
            categoricals.append(col)

    return df_clean, mask_less_than_5, categoricals, numerics

# -----------------------------------------------------------------------------
# 4. DASHBOARD UI
# -----------------------------------------------------------------------------

st.title("📊 Interactief Dashboard - DUO MBO")

# --- SECTIE 1: SCRAPER ---
with st.container():
    st.markdown(f"### 1. Selecteer Dataset")
    st.markdown(f"*Bron: {START_URL}*")
    
    # Run scraper
    csv_options = scrape_duo_specific_structure(START_URL)
    
    col_sel, col_act = st.columns([2, 2])
    with col_sel:
        selected_label = st.selectbox("Beschikbare CSV bestanden:", list(csv_options.keys()))
    
    with col_act:
        if selected_label and csv_options[selected_label]:
            dl_link = csv_options[selected_label]
            st.success("Link gevonden!")
            st.markdown(f"📥 **[Klik hier om bestand te downloaden]({dl_link})**")
            st.caption("Sla dit bestand op en upload het hieronder.")

st.divider()

# --- SECTIE 2: UPLOAD & VISUALISATIE ---
st.markdown("### 2. Visualisatie")
uploaded_file = st.file_uploader("Upload het CSV bestand", type=['csv'])

if uploaded_file is not None:
    df_raw = load_raw_data(uploaded_file)

    if df_raw is not None:
        df_clean, mask_lt5, init_cats, init_nums = detect_and_clean_data(df_raw)
        all_cols = df_clean.columns.tolist()

        col_graph, col_settings = st.columns([3, 1])

        # --- RECHTERKANT: INSTELLINGEN ---
        with col_settings:
            st.header("Instellingen")
            
            with st.expander("🛠️ Kolom Identificatie", expanded=True):
                st.caption("Sleep kolommen als de automatische detectie onjuist is.")
                selected_dims_cfg = st.multiselect("Dimensies (X-as)", all_cols, default=init_cats)
                selected_meas_cfg = st.multiselect("Meetwaarden (Y-as)", all_cols, default=init_nums)

            st.divider()
            
            x_axis = st.selectbox("X-as (Dimensie)", selected_dims_cfg) if selected_dims_cfg else None
            
            y_axis = None
            if selected_meas_cfg:
                y_axis = st.multiselect("Y-as (Meetwaarden)", selected_meas_cfg, default=selected_meas_cfg[:1])

            st.divider()
            top_n_optie = st.radio("Top N:", ["Top 5", "Top 10", "Top 20", "Alles"], index=1)
            sort_order = st.radio("Sortering:", ["Hoog naar Laag", "Laag naar Hoog"])
            ascending = True if sort_order == "Laag naar Hoog" else False

        # --- LINKERKANT: GRAFIEK ---
        with col_graph:
            if x_axis and y_axis:
                # Data prep: <5 (NaN) wordt 0 voor de grafiek
                df_viz = df_clean.copy()
                df_viz[y_axis] = df_viz[y_axis].fillna(0)
                
                # Aggregeren
                df_grouped = df_viz.groupby(x_axis)[y_axis].sum().reset_index()
                
                # Sorteren
                df_grouped['__Sort__'] = df_grouped[y_axis].sum(axis=1)
                df_grouped = df_grouped.sort_values('__Sort__', ascending=ascending)
                
                # Top N
                if "Top" in top_n_optie:
                    n = int(top_n_optie.split()[1])
                    df_final = df_grouped.head(n)
                else:
                    df_final = df_grouped

                # Plot
                st.subheader(f"Analyse: {', '.join(y_axis)} per {x_axis}")
                fig = px.bar(
                    df_final, x=x_axis, y=y_axis, 
                    template="plotly_white", barmode='stack',
                    title=f"{top_n_optie} Weergave"
                )
                fig.update_layout(legend_title="Legenda", xaxis={'categoryorder':'array', 'categoryarray': df_final[x_axis]})
                st.plotly_chart(fig, use_container_width=True)

                # --- RAPPORTAGE <5 ---
                st.markdown("---")
                
                # Filter mask op zichtbare categorieën
                mask_sub = mask_lt5.loc[df_clean[x_axis].isin(df_final[x_axis])].copy()
                mask_sub['__Dim__'] = df_clean.loc[mask_sub.index, x_axis]
                
                # Tel <5 per categorie voor de gekozen meetwaarden
                lt5_counts = mask_sub.groupby('__Dim__')[y_axis].sum()
                lt5_counts['Totaal_Verborgen'] = lt5_counts.sum(axis=1)
                report = lt5_counts[lt5_counts['Totaal_Verborgen'] > 0].sort_values('Totaal_Verborgen', ascending=False)

                st.subheader("⚠️ Data Kwaliteit & Privacy Check")
                if not report.empty:
                    st.warning("Onderstaande tabel toont hoe vaak de waarde **'<5'** voorkomt in de brongegevens voor de huidige selectie. Deze waarden zijn in de grafiek als **0** geteld.")
                    st.dataframe(report.drop(columns=['Totaal_Verborgen']))
                else:
                    st.success(f"Geen waarden '<5' aangetroffen voor de getoonde categorieën in **{x_axis}**.")

            else:
                st.info("Kies links een bestand, en rechts de Assen.")
else:
    st.info("Wacht op de scraper en kies een bestand om te beginnen.")
