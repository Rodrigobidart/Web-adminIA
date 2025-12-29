import streamlit as st
import pandas as pd
import io
from datetime import timedelta

# --- MINI BASE DE DATOS DE GASTOS (Configurable) ---
# En una versión futura, esto podría guardarse en un archivo JSON o base de datos.
KEYWORDS_GASTOS = {
    'Mantenimiento': ['MANT', 'CUENTA', 'PAQUETE', 'COMISION SERV'],
    'Impuestos/Tasas': ['IMPUESTO', 'LEY 25413', 'PERCEPCION', 'RETENCION', 'SELLOS', 'TASAS', 'SIRCREB',],
    'IVA': ['IVA VENTAS', 'IVA DEBITO', 'IVA 21', 'IVA 10.5'],
    'Comisiones Bancarias': ['COMISION', 'CARGO', 'GASTO EMISION', 'MOVIMIENTO'],
    'Intereses': ['INTERES', 'INT. PAGO', 'FINANCIACION']
}

# --- FUNCIONES DE APOYO ---
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

def classify_movement(desc):
    """Clasifica la descripción basada en palabras clave."""
    if not isinstance(desc, str): return "Otros Pendientes"
    desc_upper = desc.upper()
    for categoria, keywords in KEYWORDS_GASTOS.items():
        if any(key in desc_upper for key in keywords):
            return categoria
    return "Otros Pendientes"

def find_matches(df_m, df_b, col_fm, col_mm, col_dm, col_fb, col_mb, col_db, days_tol):
    df_m = df_m.copy()
    df_b = df_b.copy()
    df_m['matched'] = False
    df_b['matched'] = False
    conciliados = []
    for idx_m, row_m in df_m.iterrows():
        monto_m = row_m[col_mm]
        if monto_m == 0: continue
        fecha_m = row_m[col_fm]
        mask = (
            (df_b[col_mb] == monto_m) & 
            (df_b['matched'] == False) &
            (df_b[col_fb] >= fecha_m - timedelta(days=days_tol)) &
            (df_b[col_fb] <= fecha_m + timedelta(days=days_tol))
        )
        possibles = df_b[mask]
        if not possibles.empty:
            idx_b = possibles.index[0]
            df_m.at[idx_m, 'matched'] = True
            df_b.at[idx_b, 'matched'] = True
            conciliados.append({
                'Fecha_Mayor': fecha_m, 'Detalle_Mayor': row_m[col_dm], 'Monto': monto_m,
                'Fecha_Banco': df_b.at[idx_b, col_fb], 'Detalle_Banco': df_b.at[idx_b, col_db]
            })
    return df_m[df_m['matched'] == False], df_b[df_b['matched'] == False], pd.DataFrame(conciliados)

def style_summary(row):
    is_error = "DISCREPANCIA" in str(row['Concepto']) or "DIFERENCIA" in str(row['Concepto'])
    if is_error and row['Importe'] != 0:
        return ['color: #ff4b4b; font-weight: bold'] * len(row)
    return [''] * len(row)

# --- FUNCIÓN PRINCIPAL ---
def render():
    st.title("🏦 Conciliador Contable Pro (con IA de Gastos)")

    # 1. SALDOS
    with st.container(border=True):
        st.subheader("📊 Control de Saldos")
        c1, c2, c3, c4 = st.columns(4)
        s_ini_m = c1.number_input("Saldo Inicial Mayor", value=0.0, format="%.2f")
        s_fin_m = c2.number_input("Saldo Final Mayor", value=0.0, format="%.2f")
        s_ini_b = c3.number_input("Saldo Inicial Banco", value=0.0, format="%.2f")
        s_fin_b = c4.number_input("Saldo Final Banco", value=0.0, format="%.2f")

    col_u1, col_u2 = st.columns(2)
    with col_u1:
        f_mayor = st.file_uploader("📂 Subir Mayor Contable", type=['xlsx', 'csv'])
    with col_u2:
        f_banco = st.file_uploader("📂 Subir Extracto Bancario", type=['xlsx', 'csv'])

    if f_mayor and f_banco:
        df_m = pd.read_excel(f_mayor) if f_mayor.name.endswith('xlsx') else pd.read_csv(f_mayor)
        df_b = pd.read_excel(f_banco) if f_banco.name.endswith('xlsx') else pd.read_csv(f_banco)

        with st.expander("⚙️ Configuración de Mapeo", expanded=True):
            m1, m2 = st.columns(2)
            with m1:
                c_f_m = st.selectbox("Fecha (Mayor)", df_m.columns, key="fm")
                c_d_m = st.selectbox("Descripción (Mayor)", df_m.columns, key="dm")
                c_m1_m = st.selectbox("Monto/Debe (Mayor)", df_m.columns, key="m1m")
                c_m2_m = st.selectbox("Haber (Mayor - Opc)", ["Ninguna"] + list(df_m.columns), key="m2m")
            with m2:
                c_f_b = st.selectbox("Fecha (Banco)", df_b.columns, key="fb")
                c_d_b = st.selectbox("Descripción (Banco)", df_b.columns, key="db")
                c_m1_b = st.selectbox("Monto/Depósitos (Banco)", df_b.columns, key="m1b")
                c_m2_b = st.selectbox("Retiros (Banco - Opc)", ["Ninguna"] + list(df_b.columns), key="m2b")
            inv_sign = st.toggle("Invertir signo del banco")
            tol = st.slider("Días de tolerancia", 0, 15, 3)

        if st.button("🚀 Procesar Conciliación", use_container_width=True):
            df_m[c_f_m] = pd.to_datetime(df_m[c_f_m], errors='coerce')
            df_b[c_f_b] = pd.to_datetime(df_b[c_f_b], errors='coerce')
            df_m['NETO'] = process_amounts(df_m, c_m1_m, c_m2_m)
            df_b['NETO'] = process_amounts(df_b, c_m1_b, c_m2_b)
            if inv_sign: df_b['NETO'] *= -1

            # Cruce y Pendientes
            p_m, p_b, matched = find_matches(df_m.dropna(subset=[c_f_m]), df_b.dropna(subset=[c_f_b]), c_f_m, 'NETO', c_d_m, c_f_b, 'NETO', c_d_b, tol)

            # Clasificación de Gastos en lo que falta en Mayor
            p_b['CATEGORIA'] = p_b[c_d_b].apply(classify_movement)
            resumen_gastos = p_b[p_b['CATEGORIA'] != "Otros Pendientes"].groupby('CATEGORIA')['NETO'].sum().reset_index()

            # Resumen de saldos (Igual que el código anterior)
            total_mov_m, total_mov_b = df_m['NETO'].sum(), df_b['NETO'].sum()
            s_teor_m, s_teor_b = s_ini_m + total_mov_m, s_ini_b + total_mov_b
            dis_m, dis_b = round(s_fin_m - s_teor_m, 2), round(s_fin_b - s_teor_b, 2)
            sum_p_m_pos = p_m[p_m['NETO'] > 0]['NETO'].sum()
            sum_p_m_neg = p_m[p_m['NETO'] < 0]['NETO'].sum()
            sum_p_b_neto = p_b['NETO'].sum()
            b_ajustado, m_ajustado = s_fin_b + sum_p_m_pos + sum_p_m_neg, s_fin_m + sum_p_b_neto
            dif_final = round(b_ajustado - m_ajustado, 2)

            # UI: TABLA RESUMEN
            st.subheader("📋 Resumen y Validación")
            df_res = pd.DataFrame([
                {"Concepto": "Saldo Inicial Banco", "Importe": s_ini_b},
                {"Concepto": "(+) Movimientos en Extracto", "Importe": total_mov_b},
                {"Concepto": "DISCREPANCIA INTEGRIDAD BANCO", "Importe": dis_b},
                {"Concepto": "Saldo Final Banco (Informado)", "Importe": s_fin_b},
                {"Concepto": "--- BANCO AJUSTADO ---", "Importe": b_ajustado},
                {"Concepto": "---", "Importe": 0},
                {"Concepto": "Saldo Inicial Mayor", "Importe": s_ini_m},
                {"Concepto": "(+) Movimientos en Mayor", "Importe": total_mov_m},
                {"Concepto": "DISCREPANCIA INTEGRIDAD MAYOR", "Importe": dis_m},
                {"Concepto": "Saldo Final Mayor (Informado)", "Importe": s_fin_m},
                {"Concepto": "--- MAYOR AJUSTADO ---", "Importe": m_ajustado},
                {"Concepto": "DIFERENCIA FINAL CONCILIACIÓN", "Importe": dif_final},
            ])
            st.table(df_res.style.apply(style_summary, axis=1).format({"Importe": "{:,.2f}"}))

            # PESTAÑAS DE DETALLE
            t1, t2, t3 = st.tabs(["✅ Match", "📋 Faltan en Banco", "🏦 Faltan en Mayor"])
            
            with t1: 
                st.dataframe(matched, use_container_width=True)
            
            with t2: 
                st.dataframe(p_m[[c_f_m, c_d_m, 'NETO']].rename(columns={c_f_m:'Fecha', c_d_m:'Detalle'}), use_container_width=True)
            
            with t3:
                st.subheader("💡 Gastos Bancarios Sugeridos (Para Contabilizar)")
                if not resumen_gastos.empty:
                    st.table(resumen_gastos.style.format({"NETO": "{:,.2f}"}))
                    st.caption("Estos gastos fueron detectados automáticamente por su descripción.")
                else:
                    st.info("No se detectaron patrones de gastos conocidos.")
                
                st.divider()
                st.subheader("Detalle Completo de Faltantes en Mayor")
                st.dataframe(p_b[[c_f_b, c_d_b, 'NETO', 'CATEGORIA']].rename(columns={c_f_b:'Fecha', c_d_b:'Detalle'}), use_container_width=True)

            # EXPORTACIÓN
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_res.to_excel(writer, sheet_name='Resumen', index=False)
                resumen_gastos.to_excel(writer, sheet_name='Gastos_Sugeridos', index=False)
                p_b.to_excel(writer, sheet_name='Faltan_en_Mayor', index=False)
            st.download_button("📥 Descargar Reporte (Excel)", data=output.getvalue(), file_name="conciliacion_gastos.xlsx", use_container_width=True)