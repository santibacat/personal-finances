import streamlit as st
import pandas as pd
import plotly.express as px
from modules import database, data_processor, auto_tagger

# Configuración de página
st.set_page_config(
    page_title="Finanzas Personales",
    page_icon="💰",
    layout="wide"
)

# Inicializar BD
database.init_db()

# --- Navigation ---

st.sidebar.title("💰 Mi Finanza")
page = st.sidebar.selectbox("Ir a:", ["📥 Importar", "📋 Movimientos", "📊 Análisis"])

def show_import_page():
    st.header("📥 Importar Movimientos")
    
    uploaded_file = st.file_uploader("Sube tu archivo del banco (CSV, Excel)", type=['csv', 'xls', 'xlsx'])
    
    if uploaded_file is not None:
        df, error_msg = data_processor.load_file(uploaded_file)
        
        if df is not None:
            st.success("Archivo cargado correctamente. Previsualización:")
            st.dataframe(df.head())
            
            st.subheader("🔧 Configuración de Columnas")
            # Detectar columnas
            mapping_suggestion = data_processor.detect_columns(df)
            
            col1, col2, col3 = st.columns(3)
            
            cols = list(df.columns)
            
            # Selectores con valores por defecto sugeridos
            with col1:
                idx = cols.index(mapping_suggestion['date']) if mapping_suggestion['date'] in cols else 0
                date_col = st.selectbox("Columna Fecha", cols, index=idx)
            
            with col2:
                idx = cols.index(mapping_suggestion['concept']) if mapping_suggestion['concept'] in cols else 0
                concept_col = st.selectbox("Columna Concepto", cols, index=idx)
                
            with col3:
                idx = cols.index(mapping_suggestion['amount']) if mapping_suggestion['amount'] in cols else 0
                amount_col = st.selectbox("Columna Importe", cols, index=idx)

            bank_name = st.text_input("Nombre del Banco / Origen", value="Banco General")
            
            if st.button("✅ Confirmar e Importar"):
                # Crear mapeo final
                final_mapping = {
                    'date': date_col,
                    'concept': concept_col,
                    'amount': amount_col
                }
                    
                # Procesar
                try:
                    df_final = data_processor.process_data(df, final_mapping)
                    inserted, duplicates = database.insert_transactions(df_final, bank_name)
                    
                    st.toast(f"Proceso completado: {inserted} nuevos, {duplicates} duplicados ignorados.", icon="🎉")
                    if inserted > 0:
                        st.balloons()
                        
                except Exception as e:
                    st.error(f"Error al procesar: {e}")
        else:
            st.error(f"No se pudo leer el archivo. Error: {error_msg}")

def show_transactions_page():
    st.header("📋 Movimientos y Etiquetas")
    
    # Filtros
    col1, col2 = st.columns(2)
    with col1:
        search_term = st.text_input("🔍 Buscar en concepto")
    
    # Cargar datos
    df = database.get_all_transactions()
    
    if df.empty:
        st.info("No hay datos. Ve al apartado 'Importar' para subir movimientos.")
        return

    # Preparar datos
    tags_all = database.get_all_tags()
    available_tags = tags_all['name'].tolist() if not tags_all.empty else []
    
    if search_term:
        df_display = df[df['concept'].str.contains(search_term, case=False, na=False)].copy()
    else:
        df_display = df.copy()

    st.caption("Edita directamente las etiquetas en la tabla. Separa varias por comas.")

    # Mostrar editor
    # Columnas: Banco (Bank_source), Fecha, Importe, Concepto, Etiquetas
    edited_df = st.data_editor(
        df_display[['id', 'bank_source', 'date', 'amount', 'concept', 'tags_list']],
        column_config={
            "id": None,
            "bank_source": st.column_config.TextColumn("Banco", disabled=True),
            "date": st.column_config.DateColumn("Fecha", disabled=True),
            "amount": st.column_config.NumberColumn("Importe", format="%.2f €", disabled=True),
            "concept": st.column_config.TextColumn("Concepto", disabled=True),
            "tags_list": st.column_config.TextColumn("Etiquetas (p.ej: comida, ocio)")
        },
        width="stretch",
        height=500,
        key="tx_editor",
        hide_index=True
    )

    # Detectar cambios y guardar
    if st.button("💾 Guardar Cambios"):
        changes_count = 0
        for idx, row in edited_df.iterrows():
            orig_row = df[df['id'] == row['id']].iloc[0]
            if str(row['tags_list']) != str(orig_row['tags_list']):
                new_tags_raw = str(row['tags_list']).split(',') if row['tags_list'] else []
                new_tags = [t.strip() for t in new_tags_raw if t.strip()]
                database.sync_transaction_tags(row['id'], new_tags)
                changes_count += 1
        
        if changes_count > 0:
            st.success(f"Se han actualizado {changes_count} movimientos.")
            st.rerun()
        else:
            st.info("No hay cambios para guardar.")

    # --- Gestión ---
    st.divider()
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("🤖 Inteligencia")
        st.caption("Aplica etiquetas por similitud basándose en tu historial.")
        threshold = st.slider("Precisión", 50, 100, 85)
        if st.button("🚀 Iniciar Auto-etiquetado"):
            applied, skipped = auto_tagger.auto_tag_transactions(threshold=threshold)
            if applied > 0:
                st.success(f"¡Éxito! Etiquetados {applied} movimientos.")
                st.rerun()
            else:
                st.info("Nada que etiquetar.")

    with c2:
        st.subheader("🏷️ Etiquetas")
        new_tag = st.text_input("Nueva etiqueta")
        if st.button("Crear"):
            if new_tag and database.add_tag(new_tag):
                st.success(f"Creada: {new_tag}")
                st.rerun()

def show_analysis_page():
    st.header("📊 Análisis de Gastos")
    
    df_raw = database.get_all_transactions()
    if df_raw.empty:
        st.info("No hay datos.")
        return

    # Preparación base de fechas
    df_raw['date'] = pd.to_datetime(df_raw['date'])
    
    # 1. Filtro de Fechas (Afectará a todo el análisis)
    min_date = df_raw['date'].min().date()
    max_date = df_raw['date'].max().date()
    
    c_f1, c_f2 = st.columns([2, 3])
    with c_f1:
        date_range = st.date_input("📅 Rango de Fechas", 
                                   value=(min_date, max_date),
                                   min_value=min_date,
                                   max_value=max_date)
    
    # Aplicar filtro de fecha
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        df = df_raw[(df_raw['date'].dt.date >= start_date) & (df_raw['date'].dt.date <= end_date)].copy()
    else:
        df = df_raw.copy()

    if df.empty:
        st.warning("No hay datos para el rango de fechas seleccionado.")
        return

    df['month_year'] = df['date'].dt.to_period('M').astype(str)
    
    # Procesamiento por Tags
    df_tags = df.assign(tag=df['tags_list'].str.split(',')).explode('tag')
    df_tags['tag'] = df_tags['tag'].fillna('Sin Etiqueta')
    
    # --- FILTRADO DE ETIQUETAS ---
    all_available_tags = sorted(df_tags['tag'].unique().tolist())
    
    # Persistir selección en session_state
    if "analysis_tags" not in st.session_state:
        st.session_state.analysis_tags = []
        
    selected_tags = st.multiselect("🔍 Filtrar por Etiquetas", 
                                   options=all_available_tags,
                                   default=[t for t in st.session_state.analysis_tags if t in all_available_tags])
    st.session_state.analysis_tags = selected_tags
    
    # Dataset filtrado por tags (solo si hay selección)
    if selected_tags:
        df_tags_filtered = df_tags[df_tags['tag'].isin(selected_tags)]
    else:
        df_tags_filtered = df_tags.copy()
    
    # Solo gastos
    df_expenses_filtered = df_tags_filtered[df_tags_filtered['amount'] < 0].copy()
    df_expenses_all = df[df['amount'] < 0].copy()
    
    if df_expenses_filtered.empty:
        st.warning("No hay gastos para los filtros actuales.")
        return
        
    df_expenses_filtered.loc[:, 'abs_amount'] = df_expenses_filtered['amount'].abs()
    
    # --- KPIs ---
    total_income = df[df['amount'] > 0]['amount'].sum()
    total_spend_all = df_expenses_all['amount'].sum()
    filtered_spend = df_expenses_filtered.groupby('id')['amount'].first().sum() # Sin duplicados por explode
    
    # Calcular % sobre el gasto total
    percentage_of_total = (abs(filtered_spend) / abs(total_spend_all) * 100) if total_spend_all != 0 else 0
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Ingresos Periodo", f"{total_income:,.2f} €")
    k2.metric("Gasto Filtrado", f"{filtered_spend:,.2f} €")
    k3.metric("% sobre Gasto Total", f"{percentage_of_total:.1f}%")
    
    st.divider()

    # Gráficos
    c1, c2 = st.columns(2)
    spend_by_tag = df_expenses_filtered.groupby('tag')['abs_amount'].sum().reset_index().sort_values('abs_amount', ascending=False)
    
    with c1:
        st.subheader("Distribución (%)")
        st.plotly_chart(px.pie(spend_by_tag, values='abs_amount', names='tag', hole=0.4), use_container_width=True)
        
    with c2:
        st.subheader("Gasto por Etiqueta (€)")
        st.plotly_chart(px.bar(spend_by_tag, x='tag', y='abs_amount', color='tag'), use_container_width=True)

    st.subheader("Evolución Temporal")
    monthly_tag = df_expenses_filtered.groupby(['month_year', 'tag'])['abs_amount'].sum().reset_index()
    st.plotly_chart(px.area(monthly_tag, x='month_year', y='abs_amount', color='tag'), use_container_width=True)

    # Tablas
    st.divider()
    st.subheader("📑 Desglose de Gastos")
    
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.markdown("**Total Acumulado**")
        table_accum = spend_by_tag.rename(columns={"tag": "Etiqueta", "abs_amount": "Total (€)"})
        total_sum = table_accum['Total (€)'].sum()
        total_row = pd.DataFrame({"Etiqueta": ["👉 TOTAL"], "Total (€)": [total_sum]})
        table_accum = pd.concat([total_row, table_accum], ignore_index=True)
        st.dataframe(table_accum, width=None, use_container_width=True, hide_index=True)
    
    with col_t2:
        st.markdown("**Por Mes**")
        pivot_df = monthly_tag.pivot(index='tag', columns='month_year', values='abs_amount').fillna(0)
        total_pivot = pd.DataFrame(pivot_df.sum(axis=0)).T
        total_pivot.index = ["👉 TOTAL"]
        pivot_df = pd.concat([total_pivot, pivot_df])
        st.dataframe(pivot_df, width=None, use_container_width=True)

    # --- EDITOR DE MOVIMIENTOS FILTRADOS ---
    if selected_tags:
        st.divider()
        st.subheader("📝 Revisar y Corregir Gastos Filtrados")
        
        sel_set = set(selected_tags)
        mask = df['tags_list'].apply(lambda x: any(t.strip() in sel_set for t in str(x).split(',')) if x else False)
        if 'Sin Etiqueta' in sel_set:
            mask = mask | df['tags_list'].isna() | (df['tags_list'] == '')
            
        df_to_edit = df[mask].copy()
        
        edited_df = st.data_editor(
            df_to_edit[['id', 'bank_source', 'date', 'amount', 'concept', 'tags_list']],
            column_config={
                "id": None,
                "bank_source": st.column_config.TextColumn("Banco", disabled=True),
                "date": st.column_config.DateColumn("Fecha", disabled=True),
                "amount": st.column_config.NumberColumn("Importe", format="%.2f €", disabled=True),
                "concept": st.column_config.TextColumn("Concepto", disabled=True),
                "tags_list": st.column_config.TextColumn("Etiquetas")
            },
            use_container_width=True,
            height=300,
            key="analysis_tx_editor",
            hide_index=True
        )
        
        if st.button("💾 Guardar Cambios en Análisis"):
            changes = 0
            for _, row in edited_df.iterrows():
                orig_row = df_to_edit[df_to_edit['id'] == row['id']].iloc[0]
                if str(row['tags_list']) != str(orig_row['tags_list']):
                    new_tags = [t.strip() for t in str(row['tags_list']).split(',') if t.strip()]
                    database.sync_transaction_tags(row['id'], new_tags)
                    changes += 1
            if changes > 0:
                st.success(f"¡Actualizados {changes} movimientos!")
                st.rerun()

# --- Routing ---
if page == "📥 Importar":
    show_import_page()
elif page == "📋 Movimientos":
    show_transactions_page()
else:
    show_analysis_page()
