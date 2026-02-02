import pandas as pd
import unicodedata

def normalize_text(text):
    """Normalize text to lowercase and remove accents for comparison."""
    if not isinstance(text, str):
        return str(text).lower()
    text = text.lower()
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    return text.strip()

def detect_columns(df):
    """
    Attempts to map the dataframe columns to the standard schema:
    - date
    - concept
    - amount
    """
    mapping = {
        'date': None,
        'concept': None,
        'amount': None
    }
    
    # Palabras clave comunes en bancos españoles
    keywords = {
        'date': ['fecha', 'dia', 'date', 'f.valor', 'f. valor'],
        'concept': ['concepto', 'descripcion', 'movimiento', 'detalles', 'concept'],
        'amount': ['importe', 'cantidad', 'monto', 'euros', 'amount']
    }
    
    columns = df.columns.tolist()
    
    for col_std, keys in keywords.items():
        for col_orig in columns:
            norm_col = normalize_text(col_orig)
            if any(k in norm_col for k in keys):
                mapping[col_std] = col_orig
                break
                
    return mapping

def load_file(uploaded_file):
    """Reads CSV or Excel file and returns a DataFrame. Returns (df, error_msg)."""
    try:
        if uploaded_file.name.endswith('.csv'):
            # Probar diferentes separadores comunes
            try:
                df = pd.read_csv(uploaded_file, sep=';')
                if len(df.columns) < 2: # Si fallo el separador
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, sep=',')
            except:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, sep=',')
                
        elif uploaded_file.name.endswith('.xls'):
            # Los .xls viejos necesitan xlrd
            df = pd.read_excel(uploaded_file, engine='xlrd')
        else: # .xlsx y otros
            df = pd.read_excel(uploaded_file)
            
        if df is not None:
            # Limpiar nombres de columnas (quitar espacios en blanco)
            df.columns = [str(c).strip() for c in df.columns]
            
        return df, None
    except Exception as e:
        return None, str(e)

def clean_amount(val):
    """Maneja la conversión de formatos europeos '1.000,00' -> float."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.replace('€', '').strip()
        # Intentar detectar si el formato es europeo (,) o standard (.)
        if ',' in val and '.' in val:
            val = val.replace('.', '').replace(',', '.')
        elif ',' in val:
            # Si solo tiene coma, comprobamos si parece decimal (ej: 123,45 o 1.234)
            # Si hay 3 digitos tras la coma, podria ser miles, pero lo mas seguro es decimal en banca
            val = val.replace(',', '.')
            
        try:
            # Volver a quitar espacios internos si los hay (ej: "1 234.56")
            val = val.replace(' ', '').replace('\xa0', '')
            return float(val)
        except:
            return 0.0
    return 0.0

def process_data(df, mapping):
    """Processes data based on mapping by creating a new standardized DataFrame."""
    df_processed = pd.DataFrame()
    
    # 1. Extraer columnas según el mapeo
    for std_col, orig_col in mapping.items():
        if orig_col and orig_col in df.columns:
            df_processed[std_col] = df[orig_col]

    # Verificación de columnas mínimas antes de seguir
    required = ['date', 'amount']
    missing = [c for c in required if c not in df_processed.columns]
    if missing:
        available_in_upload = list(df.columns)
        raise ValueError(f"No se pudieron encontrar las columnas mapeadas: {missing}. Columnas en el archivo: {available_in_upload}")

    # 2. Limpieza y Formato
    
    # Fecha
    df_processed['date'] = pd.to_datetime(df_processed['date'], dayfirst=True, errors='coerce').dt.date
        
    # Importe
    df_processed['amount'] = df_processed['amount'].apply(clean_amount)

    # Concepto
    if 'concept' in df_processed.columns:
        df_processed['concept'] = df_processed['concept'].astype(str)
    else:
        df_processed['concept'] = "Sin concepto"
        
    # 3. Eliminar filas inválidas (fecha o importe nulo tras limpieza)
    df_processed = df_processed.dropna(subset=['date', 'amount'])
    
    return df_processed
