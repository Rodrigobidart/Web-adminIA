import streamlit as st
from modules import conciliacion
from modules import conciliador_v2

# --- NUEVOS IMPORTS PARA LA BASE DE DATOS ---
# Importamos la conexión y el modelo de Usuario desde models.py
from models import SessionLocal, User, init_db

# 1. CONFIGURACIÓN GENERAL
st.set_page_config(page_title="Plataforma Contable", layout="wide", page_icon="📊")

# --- INICIALIZACIÓN DE LA BASE DE DATOS ---
# Esto crea las tablas si no existen.
init_db()

# --- SEGURIDAD Y LOGIN (ACTUALIZADO CON BASE DE DATOS) ---

if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'username' not in st.session_state: st.session_state['username'] = ''
if 'user_id' not in st.session_state: st.session_state['user_id'] = None

def login_screen():
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        st.title("🔐 Acceso Seguro")
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        
        if st.button("Ingresar", use_container_width=True):
            # Abrimos sesión temporal con la base de datos
            db = SessionLocal()
            
            # Buscamos al usuario por su nombre
            user = db.query(User).filter(User.username == u).first()
            
            # Verificamos si existe y si la contraseña coincide (usando el método seguro)
            if user and user.check_password(p):
                # Si es correcto, verificamos si está activo (pagó suscripción)
                if user.is_active:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = user.username
                    st.session_state['user_id'] = user.id
                    db.close()
                    st.rerun()
                else:
                    st.error("Su cuenta está inactiva. Contacte a soporte.")
            else:
                st.error("Usuario o contraseña incorrectos")
            
            db.close()

# --- APP PRINCIPAL ---
if not st.session_state['logged_in']:
    login_screen()
else:
    # BARRA LATERAL (MENÚ) - (SIN CAMBIOS)
    with st.sidebar:
        st.write(f"👤 **{st.session_state['username']}**")
        st.divider()
        menu = st.radio("Herramientas", ["Inicio", "Conciliación Bancaria", "Segunda version conciliador", "OCR Facturas (Beta)"])
        st.divider()
        if st.button("Cerrar Sesión"):
            st.session_state['logged_in'] = False
            st.session_state['username'] = ''
            st.session_state['user_id'] = None
            st.rerun()

    # RUTEO DE MÓDULOS - (SIN CAMBIOS)
    if menu == "Inicio":
        st.title("Bienvenido a tu Panel Contable")
        st.info("Selecciona una herramienta en el menú de la izquierda para comenzar.")
        
    elif menu == "Conciliación Bancaria":
        # Llamamos al módulo tal cual estaba
        conciliacion.render()

    elif menu == "Segunda version conciliador":
        conciliador_v2.run()
        
    elif menu == "OCR Facturas (Beta)":
        st.title("📷 OCR de Facturas")
        st.warning("Este módulo está en construcción.")
