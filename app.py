import streamlit as st
import hashlib

# Importamos el módulo (asegúrate de que la carpeta modules tenga __init__.py)
from modules import conciliacion

# 1. CONFIGURACIÓN GENERAL
st.set_page_config(page_title="Plataforma Contable", layout="wide", page_icon="📊")

# --- SEGURIDAD Y LOGIN ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

DB_USERS = {"Tuvieja": "03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4"} # 1234

if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'username' not in st.session_state: st.session_state['username'] = ''

def login_screen():
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        st.title("🔐 Acceso Seguro")
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.button("Ingresar", use_container_width=True):
            if u in DB_USERS and check_hashes(p, DB_USERS[u]):
                st.session_state['logged_in'] = True
                st.session_state['username'] = u
                st.rerun()
            else:
                st.error("Credenciales incorrectas")

# --- APP PRINCIPAL ---
if not st.session_state['logged_in']:
    login_screen()
else:
    # BARRA LATERAL (MENÚ)
    with st.sidebar:
        st.write(f"👤 **{st.session_state['username']}**")
        st.divider()
        menu = st.radio("Herramientas", ["Inicio", "Conciliación Bancaria", "OCR Facturas (Beta)"])
        st.divider()
        if st.button("Cerrar Sesión"):
            st.session_state['logged_in'] = False
            st.rerun()

    # RUTEO DE MÓDULOS
    if menu == "Inicio":
        st.title("Bienvenido a tu Panel Contable")
        st.info("Selecciona una herramienta en el menú de la izquierda para comenzar.")
        
    elif menu == "Conciliación Bancaria":
        # ¡Aquí llamamos al módulo limpio!
        conciliacion.render()
        
    elif menu == "OCR Facturas (Beta)":
        st.title("📷 OCR de Facturas")
        st.warning("Este módulo está en construcción.")