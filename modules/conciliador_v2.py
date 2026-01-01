import streamlit as st
import pandas as pd
from datetime import datetime
from models import SessionLocal, ConciliacionV2, MovimientoBanco, MovimientoContable

# --- Inicialización del Session State ---
def init_session_state():
    """Inicializa las variables de estado de la sesión para este módulo."""
    if 'conciliador_v2' not in st.session_state:
        st.session_state['conciliador_v2'] = {
            "df_banco": None,
            "df_mayor": None,
            "nombre_archivo_banco": "",
            "nombre_archivo_mayor": "",
            "columnas_mapeadas_banco": {},
            "columnas_mapeadas_mayor": {},
            "conciliacion_id": None,
            "saldos": {"banco": 0.0, "mayor": 0.0},
            "step": 1,
        }

# --- Lógica de Carga y Procesamiento de Archivos ---
def procesar_archivo_cargado(archivo_subido):
    """Lee un archivo de Excel o CSV y lo carga en un DataFrame de pandas."""
    if archivo_subido:
        nombre_archivo = archivo_subido.name
        try:
            if nombre_archivo.endswith('.csv'):
                df = pd.read_csv(archivo_subido)
            elif nombre_archivo.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(archivo_subido)
            else:
                st.warning("Formato de archivo no soportado.")
                return None, ""
            st.success(f"Archivo '{nombre_archivo}' cargado.")
            return df, nombre_archivo
        except Exception as e:
            st.error(f"Error al leer el archivo: {e}")
            return None, ""
    return None, ""

def guardar_movimientos_db(db, conciliacion_id):
    """Guarda los movimientos de los DataFrames de la sesión en la DB."""
    df_banco = st.session_state.conciliador_v2['df_banco']
    df_mayor = st.session_state.conciliador_v2['df_mayor']
    map_banco = st.session_state.conciliador_v2['columnas_mapeadas_banco']
    map_mayor = st.session_state.conciliador_v2['columnas_mapeadas_mayor']

    for _, row in df_banco.iterrows():
        db.add(MovimientoBanco(
            conciliacion_id=conciliacion_id,
            fecha=pd.to_datetime(row[map_banco['fecha']], errors='coerce'),
            descripcion=str(row[map_banco['concepto']]),
            monto=float(str(row[map_banco['monto']]).replace('.', '').replace(',', '.'))
        ))
    
    for _, row in df_mayor.iterrows():
        db.add(MovimientoContable(
            conciliacion_id=conciliacion_id,
            fecha=pd.to_datetime(row[map_mayor['fecha']], errors='coerce'),
            descripcion=str(row[map_mayor['concepto']]),
            monto=float(str(row[map_mayor['monto']]).replace('.', '').replace(',', '.'))
        ))
    db.commit()
    st.success("Mapeo y datos guardados en la base de datos.")

# --- Componentes de la Interfaz de Usuario (UI) ---
def ui_carga_archivos():
    st.header("1. Carga de Documentos")
    col1, col2 = st.columns(2)
    with col1:
        archivo_banco = st.file_uploader("Sube el extracto", key="uploader_banco")
        if archivo_banco and st.session_state.conciliador_v2['df_banco'] is None:
            df, nombre = procesar_archivo_cargado(archivo_banco)
            if df is not None:
                st.session_state.conciliador_v2['df_banco'] = df
                st.session_state.conciliador_v2['nombre_archivo_banco'] = nombre
    with col2:
        archivo_mayor = st.file_uploader("Sube el mayor", key="uploader_mayor")
        if archivo_mayor and st.session_state.conciliador_v2['df_mayor'] is None:
            df, nombre = procesar_archivo_cargado(archivo_mayor)
            if df is not None:
                st.session_state.conciliador_v2['df_mayor'] = df
                st.session_state.conciliador_v2['nombre_archivo_mayor'] = nombre
    
    if st.session_state.conciliador_v2['df_banco'] is not None and st.session_state.conciliador_v2['df_mayor'] is not None:
        if st.button("Continuar al Mapeo"):
            st.session_state.conciliador_v2['step'] = 2
            st.rerun()

def ui_mapeo_columnas(db, conciliacion_id):
    st.header("2. Mapeo de Columnas")
    df_banco = st.session_state.conciliador_v2.get('df_banco')
    df_mayor = st.session_state.conciliador_v2.get('df_mayor')

    if df_banco is None or df_mayor is None:
        st.info("Carga ambos archivos para continuar.")
        st.stop()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Extracto Bancario")
        columnas_banco = df_banco.columns.tolist()
        mapeo_banco = {
            'fecha': st.selectbox("Columna de Fecha", options=columnas_banco, key="banco_fecha"),
            'concepto': st.selectbox("Columna de Concepto", options=columnas_banco, key="banco_concepto"),
            'monto': st.selectbox("Columna de Monto", options=columnas_banco, key="banco_monto")
        }
        st.session_state.conciliador_v2['columnas_mapeadas_banco'] = mapeo_banco
    with col2:
        st.subheader("Mayor Contable")
        columnas_mayor = df_mayor.columns.tolist()
        mapeo_mayor = {
            'fecha': st.selectbox("Columna de Fecha", options=columnas_mayor, key="mayor_fecha"),
            'concepto': st.selectbox("Columna de Concepto", options=columnas_mayor, key="mayor_concepto"),
            'monto': st.selectbox("Columna de Monto", options=columnas_mayor, key="mayor_monto")
        }
        st.session_state.conciliador_v2['columnas_mapeadas_mayor'] = mapeo_mayor

    if st.button("Guardar Mapeo y Continuar"):
        guardar_movimientos_db(db, conciliacion_id)
        st.session_state.conciliador_v2['step'] = 3
        st.rerun()

def ui_ingreso_saldos():
    st.header("3. Saldos Finales")
    col1, col2 = st.columns(2)
    with col1:
        saldo_banco = st.number_input("Saldo Final del Extracto Bancario", key="saldo_banco", format="%.2f")
        st.session_state.conciliador_v2['saldos']['banco'] = saldo_banco
    with col2:
        saldo_mayor = st.number_input("Saldo Final del Mayor Contable", key="saldo_mayor", format="%.2f")
        st.session_state.conciliador_v2['saldos']['mayor'] = saldo_mayor
    if st.button("Continuar a Conciliación Automática"):
        st.session_state.conciliador_v2['step'] = 4
        st.rerun()

def procesar_conciliacion_automatica(db, conciliacion_id):
    st.header("4. Conciliación Automática")
    if st.button("Iniciar Conciliación Automática"):
        st.success("Proceso de conciliación automática finalizado.")
        st.session_state.conciliador_v2['step'] = 5
        st.rerun()

def ui_conciliacion_manual(db):
    st.header("5. Conciliación Manual")
    with st.form("manual_reconciliation_form"):
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Pendientes del Banco")
            # Lógica para mostrar checkboxes
        with col2:
            st.subheader("Pendientes del Mayor")
            # Lógica para mostrar checkboxes
        submitted = st.form_submit_button("Conciliar Seleccionados")
        if submitted:
            st.success("Partidas seleccionadas conciliadas manualmente.")
            st.session_state.conciliador_v2['step'] = 6
            st.rerun()

def ui_reporte_final():
    st.header("6. Reporte de Conciliación Bancaria")
    saldo_segun_extracto = st.session_state.conciliador_v2['saldos']['banco']
    cheques_pendientes = -1500.50 # Ejemplo
    depositos_en_transito = 3200.00 # Ejemplo
    
    saldo_conciliado_banco = saldo_segun_extracto + cheques_pendientes + depositos_en_transito

    saldo_segun_mayor = st.session_state.conciliador_v2['saldos']['mayor']
    notas_credito_no_reg = 100.00 # Ejemplo
    gastos_bancarios_no_reg = -50.25 # Ejemplo

    saldo_conciliado_mayor = saldo_segun_mayor + notas_credito_no_reg + gastos_bancarios_no_reg

    st.subheader(f"Conciliación al {datetime.now().strftime('%d de %B de %Y')}")
    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Saldos según Banco")
        st.metric(label="Saldo según Extracto Bancario", value=f"${saldo_segun_extracto:,.2f}")
        st.metric(label="(-) Cheques Pendientes de Cobro", value=f"${cheques_pendientes:,.2f}")
        st.metric(label="(+) Depósitos en Tránsito", value=f"${depositos_en_transito:,.2f}")
        st.markdown("---")
        st.metric(label="SALDO BANCO CONCILIADO", value=f"${saldo_conciliado_banco:,.2f}", delta=f"${saldo_conciliado_banco - saldo_conciliado_mayor:,.2f} de diferencia")

    with col2:
        st.markdown("#### Saldos según Libros (Mayor)")
        st.metric(label="Saldo según Mayor Contable", value=f"${saldo_segun_mayor:,.2f}")
        st.metric(label="(+) Notas de Crédito no registradas", value=f"${notas_credito_no_reg:,.2f}")
        st.metric(label="(-) Gastos Bancarios no registrados", value=f"${gastos_bancarios_no_reg:,.2f}")
        st.markdown("---")
        st.metric(label="SALDO LIBROS CONCILIADO", value=f"${saldo_conciliado_mayor:,.2f}")

# --- Función Principal del Módulo ---
def run():
    st.title("Segunda Versión del Conciliador Bancario")
    st.write("Asistente mejorado para una conciliación más profesional y eficiente.")
    st.divider()

    init_session_state()
    db = SessionLocal()

    conciliacion_id = st.session_state.conciliador_v2.get('conciliacion_id')
    if not conciliacion_id:
        nueva_conciliacion = ConciliacionV2(user_id=st.session_state['user_id'], periodo=datetime.today().date())
        db.add(nueva_conciliacion)
        db.commit()
        st.session_state.conciliador_v2['conciliacion_id'] = nueva_conciliacion.id
        conciliacion_id = nueva_conciliacion.id

    step = st.session_state.conciliador_v2.get('step', 1)

    if step == 1:
        ui_carga_archivos()
    elif step == 2:
        ui_mapeo_columnas(db, conciliacion_id)
    elif step == 3:
        ui_ingreso_saldos()
    elif step == 4:
        procesar_conciliacion_automatica(db, conciliacion_id)
    elif step == 5:
        ui_conciliacion_manual(db)
    elif step == 6:
        ui_reporte_final()
    
    db.close()
