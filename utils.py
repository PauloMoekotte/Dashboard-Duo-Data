import pandas as pd

def detect_and_clean_data(df_raw):
    """
    Detecteert numerieke en categorische kolommen.
    Converteert numerieke kolommen en houdt rekening met '<5' als privacy-waarde.
    """
    df_clean = df_raw.copy()
    mask_less_than_5 = pd.DataFrame(False, index=df_raw.index, columns=df_raw.columns)
    numerics = []
    categoricals = []

    for col in df_raw.columns:
        # Strip whitespace van alle cellen
        series_clean = df_raw[col].astype(str).str.strip()

        # Markeer waar '<5' voorkomt
        is_privacy_val = series_clean == '<5'
        mask_less_than_5[col] = is_privacy_val

        # Converteer naar numeriek, met Nederlandse notatie
        series_numeric_ready = series_clean.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
        converted = pd.to_numeric(series_numeric_ready, errors='coerce')

        # Beslis of het een numerieke kolom is
        # We kijken of er uberhaupt getallen in staan, of de '<5' waarde
        valid_count = converted.notna().sum()
        total_non_empty = len(series_clean.dropna())

        # Een kolom is numeriek als >50% numeriek is OF als '<5' erin voorkomt
        if total_non_empty > 0 and (is_privacy_val.any() or (valid_count / total_non_empty) > 0.5):
            # Vervang NaN door 0, dit is veilig omdat we de '<5' apart hebben
            df_clean[col] = converted.fillna(0)
            numerics.append(col)
        else:
            df_clean[col] = series_clean # Zet de gestripte versie terug
            categoricals.append(col)

    return df_clean, mask_less_than_5, categoricals, numerics
