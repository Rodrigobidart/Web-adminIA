import streamlit as st
import pandas as pd
import io
from datetime import timedelta, datetime

# --- 2. FUNCIONES DE PROCESAMIENTO (HELPERS) ---
# Estas funciones se quedan fuera porque son herramientas genéricas

def clean_num(value):
    if pd.isna(value) or value == '': return 0.0
    if isinstance(value, (int, float)): return float(value)
    s = str(value).replace('$', '').replace(' ', '').strip()
    if ',' in s and '.' in s:
        if s.find('.') < s.find(','): s = s.replace('.', '').replace(',', '.')
        else: s = s.replace(',', '')
    elif ',' in s: s = s.replace(',', '.')
    try: return float(s)
    except: return 0.0

def process_amounts(df, col_1, col_2=None):
    val1 = df[col_1].apply(clean_num)
    if col_2 and col_2 != "Ninguna":
        val2 = df[col_2].apply(clean_num)
        return val1 - val2
    return val1

def classify_movement(desc, keywords_dict):
    if not isinstance(desc, str): return "Otros Pendientes"
    desc_upper = desc.upper()
    for categoria, keywords in keywords_dict.items():
        if any(key.upper() in desc_upper for key in keywords):
            return categoria
    return "Otros Pendientes"

def find_matches_v2(df_m, df_b, col_fm, col_mm, col_dm, col_fb, col_mb, col_db, days_tol):
    df_m, df_b = df_m.copy(), df_b.copy()
    df_m['matched'], df_b['matched'] = False, False
    conciliados = []
    
    # Identificar Gastos
    df_b['CATEGORIA'] = df_b[col_db].apply(lambda x: classify_movement(x, st.session_state.keywords_gastos))
    
    for idx_m, row_m in df_m.iterrows():
        monto_m, fecha_m, desc_m = row_m[col_mm], row_m[col_fm], row_m[col_dm]
        if monto_m == 0: continue
        
        mask = (
            (df_b[col_mb] == monto_m) & 
            (df_b['matched'] == False) &
            (df_b['CATEGORIA'] == "Otros Pendientes") & 
            (df_b[col_fb] >= fecha_m - timedelta(days=days_tol)) &
            (df_b[col_fb] <= fecha_m + timedelta(days=days_tol))
        )
        
        possibles = df_b[mask]
        if not possibles.empty:
            possibles['diff_days'] = (possibles[col_fb] - fecha_m).dt.days.abs()
            best_match_idx = possibles.sort_values(by='diff_days').index[0]
            
            df_m.at[idx_m, 'matched'], df_b.at[best_match_idx, 'matched'] = True, True
            conciliados.append({
                'Fecha_Mayor': fecha_m, 'Detalle_Mayor': desc_m, 'Monto': monto_m,
                'Fecha_Banco': df_b.at[best_match_idx, col_fb], 'Detalle_Banco': df_b.at[best_match_idx, col_db]
            })
                
    return df_m[df_m['matched'] == False], df_b[df_b['matched'] == False], pd.DataFrame(conciliados)

def style_summary(row):
    concepto_upper = str(row['Concepto']).upper()
    if "SALDO TEÓRICO" in concepto_upper or "SALDO FINAL" in concepto_upper:
        return ['background-color: #e9ecef; font-weight: bold; color: #212529'] * len(row)
    if "AJUSTADO" in concepto_upper:
        return ['background-color: #f8f9fa; font-weight: bold; color: #212529'] * len(row)
    if "DIFERENCIA" in concepto_upper:
        is_zero = "Importe" in row and row["Importe"] == 0
        color = '#28a745' if is_zero else '#dc3545'
        return [f'color: {color}; font-weight: bold'] * len(row)
    return [''] * len(row)

def convert_df_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Conciliacion')
    return output.getvalue()

# --- 3. RENDERIZADO PRINCIPAL ---
def render():
    
    # ==============================================================================
    # 1. GESTIÓN DE ESTADO Y PERSISTENCIA (MOVIDO AQUÍ PARA EVITAR KEYERROR)
    # ==============================================================================
    if 'db_sistema' not in st.session_state:
        st.session_state['db_sistema'] = {
            'inicializado': False,      # Marca si ya se configuró el saldo inicial histórico
            'saldo_acumulado_m': 0.0,   # Saldo de arrastre Mayor
            'saldo_acumulado_b': 0.0,   # Saldo de arrastre Banco
            'fecha_cierre': None,       # Última fecha real de operación
            'historial': [],            # Lista de conciliaciones cerradas con detalle
            'partidas_arrastradas_m': pd.DataFrame(), # Pendientes del Mayor de períodos anteriores
            'partidas_arrastradas_b': pd.DataFrame(),  # Pendientes del Banco de períodos anteriores
            'last_closed_period': None # Tupla (month_idx, year)
        }

    # Patch para estados de sesión antiguos
    if 'last_closed_period' not in st.session_state['db_sistema']:
        st.session_state['db_sistema']['last_closed_period'] = None

    if 'keywords_gastos' not in st.session_state:
        st.session_state['keywords_gastos'] = {
            'Mantenimiento': ['MANT', 'CUENTA', 'PAQUETE', 'COMISION SERV'],
            'Impuestos/Tasas': ['IMPUESTO', 'LEY 25413', 'PERCEPCION', 'RETENCION', 'SELLOS', 'SIRCREB'],
            'IVA': ['IVA VENTAS', 'IVA DEBITO', 'IVA 21'],
            'Comisiones Bancarias': ['COMISION', 'CARGO', 'GASTO EMISION'],
            'Intereses': ['INTERES', 'INT. PAGO']
        }

    if 'conciliacion_activa' not in st.session_state:
        st.session_state['conciliacion_activa'] = None

    # ==============================================================================
    # 2. INTERFAZ GRÁFICA
    # ==============================================================================
    st.title("🏦 Sistema de Conciliación Bancaria")

    tab_proc, tab_hist, tab_config = st.tabs(["🚀 Conciliación Activa", "📚 Historial de Cierres", "⚙️ Configuración"])

    # ---------------------------------------------------------
    # PESTAÑA 3: CONFIGURACIÓN
    # ---------------------------------------------------------
    with tab_config:
        st.header("⚙️ Configuración del Sistema")
        c_conf1, c_conf2 = st.columns(2)
        
        with c_conf1:
            st.subheader("1. Inicialización de Saldos")
            if not st.session_state['db_sistema']['inicializado']:
                st.info("👋 Configura los saldos iniciales por única vez para arrancar el sistema.")
                with st.form("form_init"):
                    f_inicio = st.date_input("Fecha de Inicio")
                    init_m = st.number_input("Saldo Inicial Histórico - Mayor", value=0.0, format="%.2f")
                    init_b = st.number_input("Saldo Inicial Histórico - Banco", value=0.0, format="%.2f")
                
                    if st.form_submit_button("💾 Inicializar Sistema"):
                        st.session_state['db_sistema']['inicializado'] = True
                        st.session_state['db_sistema']['saldo_acumulado_m'] = init_m
                        st.session_state['db_sistema']['saldo_acumulado_b'] = init_b
                        st.session_state['db_sistema']['fecha_cierre'] = f_inicio
                        st.rerun()
            else:
                st.success("✅ Sistema inicializado.")
                st.metric("Saldo Arrastre Mayor", f"{st.session_state['db_sistema']['saldo_acumulado_m']:,.2f}")
                st.metric("Saldo Arrastre Banco", f"{st.session_state['db_sistema']['saldo_acumulado_b']:,.2f}")
                
                if st.button("⚠️ Reiniciar Sistema (Borrar Todo)"):
                    st.session_state['db_sistema']['inicializado'] = False
                    st.session_state['db_sistema']['historial'] = []
                    st.rerun()

        with c_conf2:
            st.subheader("2. Diccionario de Gastos")
            cat = st.selectbox("Categoría", list(st.session_state.keywords_gastos.keys()))
            current_keys = ", ".join(st.session_state.keywords_gastos[cat])
            new_keys = st.text_area("Palabras clave", value=current_keys, height=100)
            if st.button("Actualizar Diccionario"):
                st.session_state.keywords_gastos[cat] = [k.strip() for k in new_keys.split(",")]
                st.toast("Diccionario actualizado")

    # ---------------------------------------------------------
    # PESTAÑA 1: CONCILIACIÓN ACTIVA
    # ---------------------------------------------------------
    with tab_proc:
        if 'conciliacion_step' not in st.session_state:
            st.session_state.conciliacion_step = 'upload'

        if not st.session_state['db_sistema']['inicializado']:
            st.warning("⚠️ Ve a 'Configuración' e inicializa los saldos primero.")
            st.stop()

        # ----- PASO 1: UPLOAD -----------------------------------------------------------------
        if st.session_state.conciliacion_step == 'upload':
            s_ini_m = st.session_state['db_sistema']['saldo_acumulado_m']
            s_ini_b = st.session_state['db_sistema']['saldo_acumulado_b']
            meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
            anios = list(range(datetime.now().year - 2, datetime.now().year + 5))

            with st.container(border=True):
                st.subheader("📅 1. Definición del Período")
                periodo_bloqueado = st.session_state['db_sistema']['last_closed_period'] is not None
                if periodo_bloqueado:
                    last_month_idx, last_year = st.session_state['db_sistema']['last_closed_period']
                    next_month_idx = (last_month_idx + 1) % 12
                    next_year = last_year if next_month_idx > last_month_idx else last_year + 1
                    st.info(f"El último período cerrado fue {meses[last_month_idx]} {last_year}. Solo puede conciliar el período siguiente.")
                else:
                    next_month_idx = datetime.now().month - 1
                    next_year = datetime.now().year

                cp1, cp2 = st.columns(2)
                sel_mes = cp1.selectbox("Mes a Conciliar", meses, index=next_month_idx, disabled=periodo_bloqueado, key="sel_mes")
                sel_anio = cp2.selectbox("Año", anios, index=anios.index(next_year), disabled=periodo_bloqueado, key="sel_anio")
                
                st.divider()
                st.subheader("📊 2. Control de Saldos")
                c1, c2, c3, c4 = st.columns(4)
                c1.number_input("Saldo Inicial Mayor (Auto)", value=s_ini_m, disabled=True, format="%.2f")
                c2.number_input("Saldo Final Mayor (Libros)", value=0.0, format="%.2f", key="s_fin_m_in")
                c3.number_input("Saldo Inicial Banco (Auto)", value=s_ini_b, disabled=True, format="%.2f")
                c4.number_input("Saldo Final Banco (Extracto)", value=0.0, format="%.2f", key="s_fin_b_in")

            st.subheader("📂 3. Carga de Archivos")
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                f_mayor = st.file_uploader("Cargar Mayor Contable", type=['xlsx', 'csv'], key="up_m")
                sin_mayor = st.checkbox("Comenzar sin Mayor Contable", key="sin_mayor_check")
            with col_u2:
                f_banco = st.file_uploader("Cargar Extracto Bancario", type=['xlsx', 'csv'], key="up_b")

            if st.button("🚀 Continuar a Mapeo de Columnas", use_container_width=True, type="primary", disabled=(not f_banco or (not f_mayor and not sin_mayor))):
                st.session_state.temp_inputs = {
                    "s_fin_m": st.session_state.s_fin_m_in,
                    "s_fin_b": st.session_state.s_fin_b_in,
                    "sel_mes": st.session_state.sel_mes,
                    "sel_anio": st.session_state.sel_anio,
                    "sin_mayor": st.session_state.sin_mayor_check,
                    "f_banco_data": f_banco.getvalue(),
                    "f_banco_name": f_banco.name,
                    "f_mayor_data": f_mayor.getvalue() if f_mayor else None,
                    "f_mayor_name": f_mayor.name if f_mayor else None,
                }
                st.session_state.conciliacion_step = 'map_columns'
                st.rerun()

        # ----- PASO 2: MAPEO DE COLUMNAS ---------------------------------------------------------
        elif st.session_state.conciliacion_step == 'map_columns':
            inputs = st.session_state.temp_inputs
            sin_mayor = inputs['sin_mayor']
            s_ini_m = st.session_state['db_sistema']['saldo_acumulado_m']
            s_ini_b = st.session_state['db_sistema']['saldo_acumulado_b']


            st.info(f"Preparando conciliación para **{inputs['sel_mes']} {inputs['sel_anio']}**.")

            f_banco = io.BytesIO(inputs['f_banco_data'])
            df_b_orig = pd.read_excel(f_banco) if inputs['f_banco_name'].endswith('xlsx') else pd.read_csv(f_banco)

            if not sin_mayor:
                f_mayor = io.BytesIO(inputs['f_mayor_data'])
                df_m_orig = pd.read_excel(f_mayor) if inputs['f_mayor_name'].endswith('xlsx') else pd.read_csv(f_mayor)
            else:
                df_m_orig = pd.DataFrame({
                    'Fecha': pd.Series(dtype='datetime64[ns]'), 
                    'Descripción': pd.Series(dtype='str'), 
                    'NETO': pd.Series(dtype='float64')
                })

            with st.form("form_map_columns"):
                with st.expander("⚙️ Verificar Columnas", expanded=True):
                    m1, m2 = st.columns(2)
                    if not sin_mayor:
                        with m1:
                            st.write("**Mayor Contable**")
                            c_f_m = st.selectbox("Columna Fecha", df_m_orig.columns, key="fm")
                            c_d_m = st.selectbox("Columna Descripción", df_m_orig.columns, key="dm")
                            c_m1_m = st.selectbox("Columna Debe/Ingresos", df_m_orig.columns, key="m1m")
                            c_m2_m = st.selectbox("Columna Haber/Egresos", ["Ninguna"] + list(df_m_orig.columns), key="m2m")
                    with m2:
                        st.write("**Extracto Bancario**")
                        c_f_b = st.selectbox("Columna Fecha", df_b_orig.columns, key="fb")
                        c_d_b = st.selectbox("Columna Descripción", df_b_orig.columns, key="db")
                        c_m1_b = st.selectbox("Columna Ingresos/Créditos", df_b_orig.columns, key="m1b")
                        c_m2_b = st.selectbox("Columna Egresos/Débitos", ["Ninguna"] + list(df_b_orig.columns), key="m2b")
                    st.divider()
                    tol = st.slider("Tolerancia de días para coincidencias", 0, 15, 3, key="tol")

                submitted = st.form_submit_button("✅ Confirmar Mapeo y Procesar", use_container_width=True, type="primary")
                if submitted:
                    df_b = df_b_orig.copy()
                    df_b[c_f_b] = pd.to_datetime(df_b[c_f_b], errors='coerce')
                    df_b['NETO'] = process_amounts(df_b, c_m1_b, c_m2_b)
                    tot_b = df_b['NETO'].sum()
                    dis_b = round(inputs['s_fin_b'] - (s_ini_b + tot_b), 2)

                    s_fin_m = 0.0 if sin_mayor else inputs['s_fin_m']

                    if sin_mayor:
                        p_m = df_m_orig.copy()
                        p_b = df_b.copy()
                        matched = pd.DataFrame()
                        dis_m = 0
                        c_f_m, c_d_m = 'Fecha', 'Descripción' # Dummy columns
                    else:
                        df_m = df_m_orig.copy()
                        df_m[c_f_m] = pd.to_datetime(df_m[c_f_m], errors='coerce')
                        df_m['NETO'] = process_amounts(df_m, c_m1_m, c_m2_m)
                        tot_m = df_m['NETO'].sum()
                        dis_m = round(s_fin_m - (s_ini_m + tot_m), 2)
                        p_m, p_b, matched = find_matches_v2(df_m.dropna(subset=[c_f_m]), df_b.dropna(subset=[c_f_b]), c_f_m, 'NETO', c_d_m, c_f_b, 'NETO', c_d_b, tol)

                    p_m = p_m.reset_index(drop=True)
                    p_b = p_b.reset_index(drop=True)

                    if not sin_mayor and not st.session_state['db_sistema']['partidas_arrastradas_m'].empty:
                        p_m = pd.concat([st.session_state['db_sistema']['partidas_arrastradas_m'], p_m], ignore_index=True)
                    if not st.session_state['db_sistema']['partidas_arrastradas_b'].empty:
                        p_b = pd.concat([st.session_state['db_sistema']['partidas_arrastradas_b'], p_b], ignore_index=True)
                    
                    p_m['Anular por Error'] = False
                    p_b['Ajustar en Libros'] = False
                    
                    st.session_state['conciliacion_activa'] = {
                        'periodo': f"{inputs['sel_mes']} {inputs['sel_anio']}", 's_ini_m': s_ini_m, 's_fin_m': s_fin_m, 
                        's_ini_b': s_ini_b, 's_fin_b': inputs['s_fin_b'], 'dis_m': dis_m, 'dis_b': dis_b, 'matched': matched, 
                        'p_m': p_m, 'p_b': p_b,
                        'column_map': {'c_f_m': c_f_m, 'c_d_m': c_d_m, 
                                       'c_f_b': c_f_b, 'c_d_b': c_d_b}
                    }
                    st.session_state.conciliacion_step = 'reconcile'
                    del st.session_state.temp_inputs
                    st.rerun()

        # ----- PASO 3: RECONCILIACIÓN -------------------------------------------------------------
        elif st.session_state.conciliacion_step == 'reconcile':
            res = st.session_state.get('conciliacion_activa')
            meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

            if not res: 
                st.session_state.conciliacion_step = 'upload'
                st.rerun()

            cmap = res['column_map']
            st.info(f"Trabajando sobre el período: **{res['periodo']}**")

            with st.expander("🔎 Ver y Ajustar Partidas Pendientes", expanded=True):
                tabs = st.tabs(["✅ Conciliados", "📋 Pendientes Mayor", "🏦 Pendientes Banco", "🤝 Match Manual"])
                
                with tabs[0]:
                    st.info("Movimientos que el sistema encontró o que fueron ajustados manualmente.")
                    st.dataframe(res['matched'], use_container_width=True, height=250)
                
                with tabs[1]:
                    st.info("Partidas en el Mayor Contable que no se encontraron en el Extracto Bancario.")
                    if not res['p_m'].empty:
                        b_col1, b_col2, _ = st.columns([1,1,4])
                        if b_col1.button("Marcar Todos p/ Anular", key="btn_anular_all"):
                            res['p_m']['Anular por Error'] = True
                            st.rerun()
                        if b_col2.button("Desmarcar Todos", key="btn_desanular_all"):
                            res['p_m']['Anular por Error'] = False
                            st.rerun()

                        try:
                            cols_to_show_m = [cmap['c_f_m'], cmap['c_d_m'], 'NETO', 'Anular por Error']
                            edited_pm = st.data_editor(res['p_m'][cols_to_show_m], key='editor_pm', use_container_width=True,
                                                       column_config={"Anular por Error": st.column_config.CheckboxColumn(help="Marcar si esta partida fue un error en los libros y debe ser revertida.")})
                            res['p_m']['Anular por Error'] = edited_pm['Anular por Error']
                        except Exception as e:
                            st.warning(f"No hay partidas pendientes del mayor para mostrar o hay un error de configuración.")

                with tabs[2]:
                    st.info("Movimientos en el Extracto Bancario no encontrados en el Mayor. Marque los que ya ha contabilizado y confirme.")
                    if not res['p_b'].empty:
                        b_col3, b_col4, _ = st.columns([1,1,4])
                        if b_col3.button("Marcar Todos p/ Ajustar", key="btn_ajustar_all"):
                            res['p_b']['Ajustar en Libros'] = True
                            st.rerun()
                        if b_col4.button("Desmarcar Todos", key="btn_desajustar_all"):
                            res['p_b']['Ajustar en Libros'] = False
                            st.rerun()

                        cols_to_show_b = [cmap['c_f_b'], cmap['c_d_b'], 'NETO', 'Ajustar en Libros']
                        try:
                            edited_pb = st.data_editor(res['p_b'][cols_to_show_b], key='editor_pb', use_container_width=True,
                                                       column_config={"Ajustar en Libros": st.column_config.CheckboxColumn(help="Marcar si ya contabilizaste esta partida en tus libros.")})
                            res['p_b']['Ajustar en Libros'] = edited_pb['Ajustar en Libros']
                        except Exception as e:
                            st.warning(f"No hay partidas pendientes del banco para mostrar o hay un error de configuración.")
            
                        if st.button("Confirmar Ajustes Realizados", key="btn_confirmar_ajustes", type="primary"):
                            p_b_ajustados_mask = res['p_b']['Ajustar en Libros'].fillna(False).astype(bool)
                            p_b_ajustados = res['p_b'][p_b_ajustados_mask]
                            
                            if not p_b_ajustados.empty:
                                # FIX: Actualizar el saldo final del mayor con los ajustes confirmados
                                total_ajustado = p_b_ajustados['NETO'].sum()
                                res['s_fin_m'] += total_ajustado

                                new_matches = []
                                for _, row in p_b_ajustados.iterrows():
                                    new_matches.append({
                                        'Fecha_Mayor': row[cmap['c_f_b']], 
                                        'Detalle_Mayor': "AJUSTE CONTABILIZADO", 
                                        'Monto': row['NETO'], 
                                        'Fecha_Banco': row[cmap['c_f_b']], 
                                        'Detalle_Banco': row[cmap['c_d_b']]
                                    })
                                
                                res['matched'] = pd.concat([res.get('matched', pd.DataFrame()), pd.DataFrame(new_matches)], ignore_index=True)
                                res['p_b'] = res['p_b'][~p_b_ajustados_mask].reset_index(drop=True)
                                
                                st.success(f"{len(new_matches)} partidas movidas a conciliados. Saldo de mayor actualizado en ${total_ajustado:,.2f}.")
                                st.rerun()

                with tabs[3]:
                    st.markdown("##### 🤝 Cruce Manual de Partidas")
                    st.info("Selecciona partidas del Mayor (Izquierda) y del Banco (Derecha). Si la suma de ambas selecciones coincide, podrás confirmar el match.")

                    # --- CORRECCION: LIMPIEZA DE COLUMNAS DUPLICADAS ---
                    def rename_duplicates(df):
                        cols = pd.Series(df.columns)
                        for dup in cols[cols.duplicated()].unique():
                            cols[cols[cols == dup].index.values.tolist()] = [
                                f"{dup}_{i}" if i != 0 else dup for i in range(sum(cols == dup))
                            ]
                        df.columns = cols
                        return df

                    res['p_m'] = rename_duplicates(res['p_m'])
                    res['p_b'] = rename_duplicates(res['p_b'])

                    # --- 1. Inicialización de columnas de selección si no existen ---
                    if 'Select_Match' not in res['p_m'].columns:
                        res['p_m']['Select_Match'] = False
                    if 'Select_Match' not in res['p_b'].columns:
                        res['p_b']['Select_Match'] = False

                    # --- 2. Filtros de Disponibilidad (Solo lo que no se marcó para anular/ajustar en pestañas anteriores) ---
                    # Usamos índices reales para poder actualizar el DataFrame original después
                    idx_disp_m = res['p_m'][res['p_m']['Anular por Error'].fillna(False) == False].index
                    idx_disp_b = res['p_b'][res['p_b']['Ajustar en Libros'].fillna(False) == False].index

                    # --- 3. Layout Principal ---
                    col_izq, col_cen, col_der = st.columns([0.48, 0.04, 0.48])

                    # ----------------- COLUMNA IZQUIERDA: MAYOR -----------------
                    with col_izq:
                        st.write(f"**📖 Pendientes Mayor ({len(idx_disp_m)})**")
                        
                        # Botones de selección masiva Mayor
                        c_btn_m1, c_btn_m2 = st.columns(2)
                        if c_btn_m1.button("✅ Todos", key="sel_all_m"):
                            res['p_m'].loc[idx_disp_m, 'Select_Match'] = True
                            st.rerun()
                        if c_btn_m2.button("⬜ Ninguno", key="desel_all_m"):
                            res['p_m'].loc[idx_disp_m, 'Select_Match'] = False
                            st.rerun()

                        # Editor de datos Mayor
                        # Recuperamos nombre actual de la columna por si fue renombrada
                        c_f_m_actual = res['p_m'].columns[res['p_m'].columns.get_loc(cmap['c_f_m'])] if cmap['c_f_m'] in res['p_m'].columns else cmap['c_f_m']
                        
                        cols_view_m = ['Select_Match', c_f_m_actual, cmap['c_d_m'], 'NETO']
                        
                        edited_m = st.data_editor(
                            res['p_m'].loc[idx_disp_m, cols_view_m],
                            key="editor_manual_m",
                            hide_index=True,
                            use_container_width=True,
                            column_config={
                                "Select_Match": st.column_config.CheckboxColumn("Seleccionar", width="small"),
                                "NETO": st.column_config.NumberColumn("Importe", format="$ %.2f")
                            }
                        )
                        # Actualizamos estado de selección en el DF original
                        if not edited_m.empty:
                            res['p_m'].update(edited_m['Select_Match'])

                    # ----------------- COLUMNA DERECHA: BANCO -----------------
                    with col_der:
                        st.write(f"**🏦 Pendientes Banco ({len(idx_disp_b)})**")

                        # Botones de selección masiva Banco
                        c_btn_b1, c_btn_b2 = st.columns(2)
                        if c_btn_b1.button("✅ Todos", key="sel_all_b"):
                            res['p_b'].loc[idx_disp_b, 'Select_Match'] = True
                            st.rerun()
                        if c_btn_b2.button("⬜ Ninguno", key="desel_all_b"):
                            res['p_b'].loc[idx_disp_b, 'Select_Match'] = False
                            st.rerun()

                        # Editor de datos Banco
                        # Recuperamos nombre actual de la columna por si fue renombrada (Corrección del error)
                        c_f_b_actual = res['p_b'].columns[res['p_b'].columns.get_loc(cmap['c_f_b'])] if cmap['c_f_b'] in res['p_b'].columns else cmap['c_f_b']

                        cols_view_b = ['Select_Match', c_f_b_actual, cmap['c_d_b'], 'NETO']
                        
                        edited_b = st.data_editor(
                            res['p_b'].loc[idx_disp_b, cols_view_b],
                            key="editor_manual_b",
                            hide_index=True,
                            use_container_width=True,
                            column_config={
                                "Select_Match": st.column_config.CheckboxColumn("Seleccionar", width="small"),
                                "NETO": st.column_config.NumberColumn("Importe", format="$ %.2f")
                            }
                        )
                        # Actualizamos estado de selección en el DF original
                        if not edited_b.empty:
                            res['p_b'].update(edited_b['Select_Match'])

                    # ----------------- LÓGICA DE VALIDACIÓN Y CRUCE -----------------
                    st.divider()
                    
                    # Calcular sumas de lo seleccionado (buscando en el DF original actualizado)
                    sel_m = res['p_m'].loc[res['p_m']['Select_Match'] == True]
                    sel_b = res['p_b'].loc[res['p_b']['Select_Match'] == True]

                    sum_m = sel_m['NETO'].sum()
                    sum_b = sel_b['NETO'].sum()
                    diff_match = round(sum_m - sum_b, 2)

                    # Panel de Resultados
                    c_res1, c_res2, c_res3, c_res4 = st.columns([1, 1, 1, 1.5])
                    c_res1.metric("Seleccionado Mayor", f"${sum_m:,.2f}")
                    c_res2.metric("Seleccionado Banco", f"${sum_b:,.2f}")
                    
                    color_diff = "normal" if diff_match == 0 else "inverse"
                    c_res3.metric("Diferencia", f"${diff_match:,.2f}", delta_color=color_diff)

                    with c_res4:
                        st.write("### Acciones")
                        # Condiciones para habilitar el botón:
                        # 1. Diferencia cero.
                        # 2. Algo seleccionado en ambos lados (o al menos que la suma no sea 0 si es una anulación interna).
                        valid_match = (abs(diff_match) < 0.01) and (len(sel_m) > 0 or len(sel_b) > 0)
                        
                        if st.button("🔗 CONFIRMAR MATCH", type="primary", disabled=not valid_match, use_container_width=True):
                            
                            new_matches = []
                            match_id = datetime.now().strftime("%H%M%S") # ID simple para agrupar

                            # LÓGICA DE TRAZABILIDAD LINEA A LINEA
                            desc_group_b = f"Match Manual (Ref: {sel_b[cmap['c_d_b']].iloc[0] if not sel_b.empty else 'Var'}...)"
                            desc_group_m = f"Match Manual (Ref: {sel_m[cmap['c_d_m']].iloc[0] if not sel_m.empty else 'Var'}...)"
                            
                            # A. Procesar líneas del Mayor seleccionadas
                            for idx, row in sel_m.iterrows():
                                new_matches.append({
                                    'Fecha_Mayor': row[cmap['c_f_m']] if cmap['c_f_m'] in row else row[c_f_m_actual],
                                    'Detalle_Mayor': row[cmap['c_d_m']],
                                    'Monto': row['NETO'],
                                    'Fecha_Banco': (sel_b[cmap['c_f_b']].iloc[0] if not sel_b.empty else row[c_f_m_actual]) if cmap['c_f_b'] in sel_b.columns else datetime.now(),
                                    'Detalle_Banco': f"🖇️ {desc_group_b} [ID:{match_id}]"
                                })

                            # B. Procesar líneas del Banco seleccionadas (SOLO si hay más items en banco que en mayor)
                            if sel_m.empty and not sel_b.empty:
                                for idx, row in sel_b.iterrows():
                                    new_matches.append({
                                        'Fecha_Mayor': row[c_f_b_actual], # Usamos fecha banco
                                        'Detalle_Mayor': f"🖇️ {desc_group_m} [ID:{match_id}]",
                                        'Monto': row['NETO'], # Monto real
                                        'Fecha_Banco': row[c_f_b_actual],
                                        'Detalle_Banco': row[cmap['c_d_b']]
                                    })
                            
                            # Eliminar de los pendientes (Esto es lo CRÍTICO para el cálculo matemático)
                            res['p_m'] = res['p_m'].drop(sel_m.index).reset_index(drop=True)
                            res['p_b'] = res['p_b'].drop(sel_b.index).reset_index(drop=True)
                            
                            # Agregar a conciliados
                            res['matched'] = pd.concat([res.get('matched', pd.DataFrame()), pd.DataFrame(new_matches)], ignore_index=True)
                            
                            st.success(f"✅ ¡Conciliado! Se cruzaron {len(sel_m)} partidas de Mayor con {len(sel_b)} de Banco.")
                            st.rerun()

                        if not valid_match and (len(sel_m) > 0 or len(sel_b) > 0):
                            st.caption("⚠️ Las sumas deben ser idénticas para conciliar.")
            
            # --- CÁLCULOS Y CIERRE ---
            p_m_anulados = res['p_m'][res['p_m']['Anular por Error'].fillna(False)]
            ajuste_por_anulacion = p_m_anulados['NETO'].sum()
            
            # Este ajuste es solo para el cálculo teórico, el real ya está en s_fin_m
            p_b_para_ajuste_teorico = res['p_b'][res['p_b']['Ajustar en Libros'].fillna(False)]
            ajuste_por_banco_teorico = p_b_para_ajuste_teorico['NETO'].sum()
            
            mayor_ajustado_real = res['s_fin_m'] - ajuste_por_anulacion + ajuste_por_banco_teorico
          
            p_m_no_anular = res['p_m'][~res['p_m']['Anular por Error'].fillna(False)]
            p_b_no_ajustar = res['p_b'][~res['p_b']['Ajustar en Libros'].fillna(False)]
            
            partidas_m_pend_neto = p_m_no_anular['NETO'].sum()
            partidas_b_pend_neto = p_b_no_ajustar['NETO'].sum()
            
            m_ajustado_teorico = mayor_ajustado_real - partidas_m_pend_neto + partidas_b_pend_neto
            
            s_fin_b_numeric = pd.to_numeric(res.get('s_fin_b'), errors='coerce')
            if pd.isna(s_fin_b_numeric):
                s_fin_b_numeric = 0.0
            dif_final = round(m_ajustado_teorico - s_fin_b_numeric, 2)

            st.divider()
            st.markdown("### 📊 Totales de Conciliación")
            col1, col2, col3 = st.columns(3)
            col1.metric("Saldo Mayor Contable Teórico", f"${m_ajustado_teorico:,.2f}")
            col2.metric("Saldo Final Extracto Bancario", f"${s_fin_b_numeric:,.2f}")
            col3.metric("Diferencia", f"${dif_final:,.2f}")
            st.divider()

            df_reconcile = pd.DataFrame([
                {"Concepto": "Saldo Contable Ajustado (p/ Cierre)", "Importe": mayor_ajustado_real},
                {"Concepto": "(-) Partidas de Mayor no conciliadas", "Importe": -partidas_m_pend_neto},
                {"Concepto": "(+) Partidas de Banco no conciliadas", "Importe": partidas_b_pend_neto},
                {"Concepto": "SALDO TEÓRICO CONCILIADO", "Importe": m_ajustado_teorico},
                {"Concepto": "SALDO FINAL BANCARIO (Extracto)", "Importe": s_fin_b_numeric},
                {"Concepto": "DIFERENCIA DE CONCILIACIÓN", "Importe": dif_final},
            ])

            st.markdown("### 📝 Hoja de Trabajo (Análisis de Diferencias)")
            st.table(df_reconcile.style.format({"Importe": "{:,.2f}"}).apply(style_summary, axis=1))

            st.divider()
            st.markdown("### 🔐 Cerrar Período")
            c_close1, c_close2, c_close3 = st.columns([2, 1, 1])
            
            if dif_final != 0: c_close1.warning(f"⚠️ ¡Atención! La diferencia de conciliación es de ${dif_final:,.2f}.")
            else: c_close1.success("✅ ¡Todo conciliado! Puede cerrar el período.")
            
            if c_close2.button("✅ Confirmar Cierre", type="primary", disabled=(dif_final != 0)):
                sel_mes, sel_anio = res['periodo'].split()
                st.session_state['db_sistema']['historial'].append({
                    "Periodo": res['periodo'], "Fecha Cierre": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "Saldo Final Mayor": mayor_ajustado_real, "Saldo Final Banco": res['s_fin_b'],
                    "Estado": "CERRADO OK" if dif_final == 0 else "CERRADO CON DIF.", "Hoja_Trabajo": df_reconcile
                })
                st.session_state['db_sistema']['saldo_acumulado_m'] = mayor_ajustado_real
                st.session_state['db_sistema']['saldo_acumulado_b'] = res['s_fin_b']
                st.session_state['db_sistema']['last_closed_period'] = (meses.index(sel_mes), int(sel_anio))
                st.session_state['db_sistema']['partidas_arrastradas_m'] = p_m_no_anular.drop(columns=['Anular por Error'], errors='ignore')
                st.session_state['db_sistema']['partidas_arrastradas_b'] = p_b_no_ajustar.drop(columns=['Ajustar en Libros'], errors='ignore')
            
                st.session_state['conciliacion_activa'] = None
                st.session_state.conciliacion_step = 'upload'
                st.success(f"✨ ¡CONCILIACIÓN DE {res['periodo']} CERRADA!")
                st.rerun()

            if c_close3.button("❌ Cancelar"):
                st.session_state['conciliacion_activa'] = None
                st.session_state.conciliacion_step = 'upload'
                st.toast("Conciliación cancelada.")
                st.rerun()

    # ---------------------------------------------------------
    # PESTAÑA 2: HISTORIAL DE CIERRES
    # ---------------------------------------------------------
    with tab_hist:
        st.subheader("📚 Historial de Conciliaciones")
        historial = st.session_state['db_sistema']['historial']
        if len(historial) > 0:
            df_hist_view = pd.DataFrame(historial)[['Periodo', 'Fecha Cierre', 'Saldo Final Mayor', 'Saldo Final Banco', 'Estado']]
            st.dataframe(df_hist_view, use_container_width=True)
            st.divider()
            st.write("#### 🔎 Visualizar Conciliación Anterior")
            opciones = [f"{r['Periodo']} (Cerrado el: {r['Fecha Cierre']})" for r in historial]
            seleccion_str = st.selectbox("Selecciona un período cerrado:", opciones)
            if seleccion_str:
                periodo_buscado = seleccion_str.split(" (")[0]
                registro_sel = next((r for r in historial if r['Periodo'] == periodo_buscado), None)
                if registro_sel:
                    st.info(f"Mostrando Hoja de Trabajo del período: {registro_sel['Periodo']}")
                    df_recuperado = registro_sel['Hoja_Trabajo']
                    st.table(df_recuperado.style.format({"Importe": "{:,.2f}"}).apply(style_summary, axis=1))
                    excel_data = convert_df_to_excel(df_recuperado)
                    st.download_button(
                        label="📥 Descargar esta Conciliación (Excel)",
                        data=excel_data,
                        file_name=f"Conciliacion_{registro_sel['Periodo']}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
        else:
            st.info("Aún no hay períodos cerrados en el historial.")
