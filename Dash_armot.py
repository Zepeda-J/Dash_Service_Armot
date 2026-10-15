import io
import re
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import qrcode
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import hashlib
import hmac
from html import escape as _esc
import traceback
import json
from datetime import datetime
import streamlit.components.v1 as components

try:
    from google import genai
except ImportError:
    genai = None

try:
    import gspread
except ImportError:
    gspread = None

try:
    from google.oauth2.service_account import Credentials as ServiceAccountCredentials
except ImportError:
    ServiceAccountCredentials = None

try:
    from googleapiclient.discovery import build
    DRIVE_LIBS_DISPONIBLES = True
except ImportError:
    build = None
    DRIVE_LIBS_DISPONIBLES = False

BASE_DIR = Path(__file__).resolve().parent

# Pantalla ancha: usa todo el ancho del navegador en TODAS las pestañas.
# (Debe ser el primer comando de Streamlit del script.)
try:
    st.set_page_config(page_title="Dashboard Armot", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
except Exception:
    pass


# =============================================================================
# ÍNDICE DEL ARCHIVO
# =============================================================================
#   1. AUTENTICACIÓN GLOBAL
#   2. CONFIGURACIÓN DE IA SEGURA (Gemini)
#   3. UTILIDADES COMPARTIDAS (avatares, credenciales PNG, QR, WhatsApp)
#   4. ENCABEZADO CON LOGO
#   5. CARGA Y PROCESAMIENTO DE DATOS (Google Sheets)
#   6. FILTROS GLOBALES EN CASCADA
#   7. PESTAÑA "Resumen Global"
#   8. PESTAÑA "Coordinadores"
#   9. PESTAÑA "Administración"
#  10. PESTAÑA "Seguimiento de Facturación"
# =============================================================================




# ============================================================================
# AUTENTICACIÓN GLOBAL
# ============================================================================
USUARIOS = {
    "admin": {"clave": "Alex", "rol": "admin"},
    "Fernando": {"clave": "Fernando_armot2026", "rol": "usuario"},
    "Alfonso": {"clave": "Alfonso_armot2026", "rol": "usuario"},
    "Nayeli": {"clave": "Naye_armot2026", "rol": "usuario"},
    "Cass": {"clave": "Cass.contratos", "rol": "usuario"},
    "Karla": {"clave": "Karla.conbranza", "rol": "usuario"},
    "Nora": {"clave": "Nora.cdmx", "rol": "usuario"},
    "Pilar": {"clave": "Pilar.toluca", "rol": "usuario"},
    "Adolfo": {"clave": "Adolfo.mexico", "rol": "usuario"},
    "Berenice": {"clave": "Berenice.foraneos", "rol": "usuario"},
    "Iñaki": {"clave": "Iñaki.licitaciones", "rol": "usuario"},
}

for clave, valor in {
    "autenticado": False,
    "usuario_actual": "",
    "rol_actual": "",
}.items():
    if clave not in st.session_state:
        st.session_state[clave] = valor

SESSION_SECRET = st.secrets.get("SESSION_SECRET", "armot_dashboard_2026_secret")


def _generar_token_sesion(usuario: str) -> str:
    """Token derivado del usuario + un secreto del servidor (nunca la contraseña),
    para poder validar la sesión guardada en la URL sin exponer credenciales."""
    return hashlib.sha256(f"{usuario}:{SESSION_SECRET}".encode()).hexdigest()[:32]


def _restaurar_sesion_desde_url():
    """Si la URL trae un usuario y token válidos de un login anterior en este mismo
    navegador, restaura la sesión automáticamente. Así, refrescar la página (F5) o
    que Streamlit reinicie la conexión no obliga a volver a iniciar sesión."""
    if st.session_state.get("autenticado"):
        return
    usuario_url = st.query_params.get("u", "")
    token_url = st.query_params.get("t", "")
    if usuario_url and token_url:
        datos_usuario = USUARIOS.get(usuario_url)
        if datos_usuario and token_url == _generar_token_sesion(usuario_url):
            st.session_state["autenticado"] = True
            st.session_state["usuario_actual"] = usuario_url
            st.session_state["rol_actual"] = datos_usuario["rol"]


_restaurar_sesion_desde_url()

def mostrar_login_global():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 Acceso al Dashboard Armot")
        st.write("Ingresa tus credenciales para continuar.")

        with st.form("form_login_global", clear_on_submit=False):
            usuario = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Ingresar", use_container_width=True)

        if submit:
            datos_usuario = USUARIOS.get(usuario.strip())
            if datos_usuario and hmac.compare_digest(str(datos_usuario["clave"]).encode("utf-8"), password.encode("utf-8")):
                st.session_state["autenticado"] = True
                st.session_state["usuario_actual"] = usuario.strip()
                st.session_state["rol_actual"] = datos_usuario["rol"]
                # Guarda un token (no la contraseña) en la URL para mantener la
                # sesión activa si la página se recarga.
                st.query_params["u"] = usuario.strip()
                st.query_params["t"] = _generar_token_sesion(usuario.strip())
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")

if not st.session_state["autenticado"]:
    mostrar_login_global()
    st.stop()

with st.sidebar:
    st.markdown(f"👤 **Usuario:** `{st.session_state['usuario_actual']}`")
    st.markdown(f"🪪 **Rol:** `{st.session_state['rol_actual'].upper()}`")
    if st.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["autenticado"] = False
        st.session_state["usuario_actual"] = ""
        st.session_state["rol_actual"] = ""
        st.query_params.clear()
        st.rerun()
    st.markdown("---")


# =========================================================================
# CONFIGURACIÓN DE IA SEGURA (SDK GOOGLE-GENAI)
# =========================================================================
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "").strip()

def obtener_cliente_gemini():
    if not GEMINI_API_KEY or genai is None:
        return None
    try:
        return genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        st.error(f"Error al inicializar el cliente Gemini: {e}")
        return None

client_gemini = obtener_cliente_gemini()


# =========================================================================
# UTILIDADES COMPARTIDAS — avatares, credenciales PNG, QR y WhatsApp
# (usadas por las pestañas "Coordinadores" y "Administración")
# =========================================================================
def generar_link_whatsapp(telefono: str) -> str:
    digitos = re.sub(r"\D", "", str(telefono or ""))
    if digitos:
        if len(digitos) == 10:
            digitos = "52" + digitos
        return f"https://wa.me/{digitos}"
    return ""


def _cargar_fuente(tamano):
    rutas_candidatas = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "arial.ttf",
    ]
    for ruta in rutas_candidatas:
        try:
            return ImageFont.truetype(ruta, tamano)
        except Exception:
            continue
    return ImageFont.load_default()


def generar_avatar_iniciales(nombre, tamano=300):
    nombre = (nombre or "").strip()
    iniciales = "".join([p[0].upper() for p in nombre.split() if p][:2]) or "?"
    paleta = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#0891b2", "#ea580c"]
    color = paleta[int(hashlib.sha256(nombre.encode("utf-8")).hexdigest(), 16) % len(paleta)]

    img = Image.new("RGB", (tamano, tamano), color)
    draw = ImageDraw.Draw(img)
    font = _cargar_fuente(int(tamano * 0.4))
    bbox = draw.textbbox((0, 0), iniciales, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((tamano - w) / 2 - bbox[0], (tamano - h) / 2 - bbox[1]),
        iniciales, fill="white", font=font,
    )
    return img


def obtener_imagen_usuario(usuario, tamano=300):
    foto = usuario.get("foto")
    foto_bytes = usuario.get("foto_bytes")
    if foto_bytes:
        try:
            return Image.open(io.BytesIO(foto_bytes)).convert("RGB")
        except Exception:
            pass
    if isinstance(foto, str) and foto.strip():
        return foto
    return generar_avatar_iniciales(usuario.get("nombre", "?"), tamano)


PLOTLY_CONFIG_MOVIL = {
    "responsive": True,      # el gráfico se redimensiona al girar el celular o al mostrar/ocultar el sidebar
    "displayModeBar": False,  # la barra de herramientas de Plotly estorba y es difícil de usar en pantallas táctiles
    "scrollZoom": False,
}


def aplicar_layout_movil(fig, alto_escritorio=550, alto_movil=380, titulo_size=15):
    """Ajusta una figura de Plotly para que se vea bien tanto en escritorio como
    en celular: márgenes más chicos, títulos y leyendas legibles, y una altura
    razonable en pantallas angostas (usamos alto_movil como límite superior en
    lugar de depender del ancho, que Streamlit ya adapta con width='stretch')."""
    fig.update_layout(
        height=min(alto_escritorio, max(alto_movil, 320)),
        autosize=True,
        margin=dict(l=10, r=10, t=60, b=10),
        title=dict(font=dict(size=titulo_size)),
        legend=dict(font=dict(size=10)),
        font=dict(size=11),
    )
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    return fig


def aplicar_layout_compacto(fig, alto, titulo_size=12):
    """Layout para el tablero 'Resumen Global': misma lógica que aplicar_layout_movil
    pero con altura exacta (para que 6 gráficas quepan en una sola pantalla),
    márgenes mínimos y tipografías pequeñas."""
    fig.update_layout(
        height=int(alto),
        autosize=True,
        margin=dict(l=6, r=6, t=34, b=6),
        title=dict(font=dict(size=titulo_size), x=0.5, xanchor="center", y=0.97, yanchor="top"),
        font=dict(size=9),
    )
    fig.update_xaxes(automargin=True, title_font=dict(size=9))
    fig.update_yaxes(automargin=True, title_font=dict(size=9))
    return fig


def mostrar_grafico(fig, **kwargs):
    """Envoltorio de st.plotly_chart con configuración responsiva para móvil."""
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG_MOVIL, **kwargs)


def generar_qr(data: str) -> Image.Image:
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def generar_credencial_png(usuario) -> bytes:
    ancho, alto = 1000, 620
    tarjeta = Image.new("RGB", (ancho, alto), "white")
    draw = ImageDraw.Draw(tarjeta)

    draw.rectangle([0, 0, ancho, 110], fill="#0f172a")
    font_empresa = _cargar_fuente(40)
    draw.text((40, 30), "ARMOT — CREDENCIAL", fill="white", font=font_empresa)

    foto_img = obtener_imagen_usuario(usuario, tamano=300)
    if isinstance(foto_img, str):
        foto_img = generar_avatar_iniciales(usuario.get("nombre", "?"), 300)
    foto_img = foto_img.resize((260, 300))
    tarjeta.paste(foto_img, (40, 150))

    font_nombre = _cargar_fuente(34)
    font_texto = _cargar_fuente(24)
    x_texto = 330
    draw.text((x_texto, 150), (usuario.get("nombre", "") or "").strip(), fill="black", font=font_nombre)
    draw.text((x_texto, 200), usuario.get("puesto", ""), fill="#334155", font=font_texto)
    draw.text((x_texto, 240), f"ID: {usuario.get('id', '')}", fill="black", font=font_texto)
    draw.text((x_texto, 275), f"Zona: {usuario.get('departamento', '')}", fill="black", font=font_texto)
    draw.text((x_texto, 310), f"Estado: {usuario.get('estado', '')}", fill="black", font=font_texto)
    draw.text((x_texto, 345), f"Nivel: {usuario.get('nivel_acceso', '')}", fill="black", font=font_texto)
    draw.text((x_texto, 380), f"Ingreso: {usuario.get('fecha_ingreso', '')}", fill="black", font=font_texto)

    qr_data = (
        f"ID:{usuario.get('id','')};Nombre:{usuario.get('nombre','')};"
        f"Puesto:{usuario.get('puesto','')};Zona:{usuario.get('departamento','')}"
    )
    qr_img = generar_qr(qr_data).resize((160, 160))
    tarjeta.paste(qr_img, (ancho - 200, alto - 200))

    buf = io.BytesIO()
    tarjeta.save(buf, format="PNG")
    return buf.getvalue()


_PATRON_SERVICIO = re.compile(r"^(.*?)\s*:\s*(\d+)\s*[A-Za-zÁÉÍÓÚáéíóúñÑ]*\s*\(?([^)]*)\)?\s*$")


def parsear_servicio_texto(texto):
    m = _PATRON_SERVICIO.match(texto.strip())
    if m:
        return {
            "Dependencia": m.group(1).strip(),
            "Clue/ID": "",
            "Unidad": m.group(3).strip(),
            "Cantidad requerida": int(m.group(2)),
            "Cantidad real": int(m.group(2)),
        }
    return {
        "Dependencia": texto.strip(),
        "Clue/ID": "",
        "Unidad": "",
        "Cantidad requerida": 0,
        "Cantidad real": 0,
    }


def asegurar_servicios_estructurados(usuario):
    if "servicios" not in usuario or usuario["servicios"] is None:
        usuario["servicios"] = [parsear_servicio_texto(p) for p in usuario.get("proyectos", [])]
    return usuario["servicios"]


def exportar_servicios_excel(usuario) -> bytes:
    servicios = asegurar_servicios_estructurados(usuario)
    if not servicios:
        servicios = [{
            "Dependencia": "",
            "Clue/ID": "",
            "Unidad": "",
            "Cantidad requerida": 0,
            "Cantidad real": 0
        }]
    
    df_serv = pd.DataFrame(servicios)
    
    columnas_ordenadas = ["Dependencia", "Clue/ID", "Unidad", "Cantidad requerida", "Cantidad real"]
    for col in columnas_ordenadas:
        if col not in df_serv.columns:
            df_serv[col] = "" if "Cantidad" not in col else 0

    df_serv = df_serv[columnas_ordenadas]

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_serv.to_excel(writer, index=False, sheet_name="Servicios")
    return buf.getvalue()



# --- ENCABEZADO CENTRADO CON LOGO AJUSTADO ---
st.markdown(
    """
    <style>
    /* ---- Ajuste a todo el entorno: sin máximos de ancho y con márgenes mínimos ---- */
    .block-container, [data-testid="stMainBlockContainer"] {
        max-width: 100% !important;
        padding-top: 3rem !important;
        padding-bottom: 0.5rem !important;
        padding-left: 1.2rem !important;
        padding-right: 1.2rem !important;
    }
    /* ---- Resumen Global: estilo app de datos ---- */
    .st-key-resumen_global [data-testid="stVerticalBlock"] { gap: 0.5rem; }
    .st-key-resumen_global [data-testid="stHorizontalBlock"] { gap: 0.7rem; }
    .rg-head { display: flex; align-items: center; justify-content: space-between; padding: 2px 4px 4px 4px; }
    .rg-head-l { display: flex; align-items: center; gap: 12px; }
    .rg-logo { width: 38px; height: 38px; border-radius: 10px; display: flex; align-items: center; justify-content: center;
               font-size: 1.2rem; background: rgba(29,155,240,0.14); }
    .rg-title { font-size: 1.15rem; font-weight: 700; line-height: 1.2; }
    .rg-subtitle { font-size: 0.78rem; opacity: 0.7; }
    .rg-pill { display: inline-flex; align-items: center; gap: 7px; font-size: 0.75rem; padding: 4px 12px; border-radius: 999px;
               border: 1px solid rgba(29,155,240,0.35); background: rgba(29,155,240,0.09); }
    .rg-dot { width: 8px; height: 8px; border-radius: 50%; background: #10b981; display: inline-block; margin-right: 6px; }
    .rg-pill .rg-dot { margin-right: 0; }
    .rg-dot.rojo { background: #ef4444; }
    /* Panel de controles */
    .st-key-panel_resumen { background: rgba(128,128,128,0.07); border: 1px solid rgba(128,128,128,0.22);
                            border-radius: 12px; padding: 12px 14px 14px 14px; }
    .st-key-panel_resumen [data-testid="stVerticalBlock"] { gap: 0.55rem; }
    .st-key-panel_resumen [data-testid="stWidgetLabel"] p {
        font-size: 0.68rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; opacity: 0.75; }
    .rg-panel-tit { font-size: 0.68rem; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.55; }
    /* Tarjetas de montos (sin / con IVA) */
    .rg-cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
    .rg-card { border: 1px solid rgba(128,128,128,0.25); border-radius: 10px; background: rgba(128,128,128,0.05);
               padding: 9px 14px 8px 14px; min-width: 0; }
    .rg-card-lbl { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; opacity: 0.7; }
    .rg-card-val { font-size: clamp(1.25rem, 1.9vw, 1.85rem); font-weight: 700; line-height: 1.25; white-space: nowrap; }
    .rg-up { color: #10b981; font-size: 0.78rem; font-weight: 600; }
    .rg-sub { opacity: 0.7; font-size: 0.78rem; }
    @media (max-width: 900px) { .rg-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    /* Resumen de cobertura y personal */
    .rg-chips { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
    .rg-chip { display: flex; align-items: center; gap: 7px; padding: 4px 8px; min-width: 0;
               border: 1px solid rgba(128,128,128,0.22); border-radius: 8px; background: rgba(128,128,128,0.05); }
    .rg-chip-ico { font-size: 1rem; }
    .rg-chip-val { font-size: 0.95rem; font-weight: 700; line-height: 1.1; }
    .rg-chip-lbl { font-size: 0.62rem; opacity: 0.7; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    /* Tarjetas de gráficas */
    .st-key-resumen_global [class*="st-key-cel_"] {
        position: relative; border: 1px solid rgba(128,128,128,0.25); border-radius: 12px;
        background: rgba(128,128,128,0.04); padding: 8px 10px 4px 10px; }
    .st-key-resumen_global [class*="st-key-cel_"] [data-testid="stVerticalBlock"] { gap: 0.2rem; }
    .rg-card-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; padding-right: 40px; }
    .rg-card-tit { font-weight: 700; font-size: 0.85rem; white-space: nowrap; }
    .rg-card-stat { font-size: 0.72rem; opacity: 0.7; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    /* Barra de estado inferior */
    .rg-foot { display: flex; justify-content: space-between; gap: 12px; font-size: 0.72rem; opacity: 0.8;
               border-top: 1px solid rgba(128,128,128,0.25); padding-top: 5px; }
    /* ---- Botón 🔍 sobre cada gráfica ---- */
    .st-key-resumen_global [class*="st-key-cel_"] { position: relative; }
    .st-key-resumen_global [class*="st-key-amp_"] {
        position: absolute; top: 6px; right: 8px; z-index: 20; width: auto !important;
    }
    .st-key-resumen_global [class*="st-key-amp_"] button {
        min-height: 1.7rem; padding: 0 0.5rem; border-radius: 8px; font-size: 0.85rem; opacity: 0.7;
    }
    .st-key-resumen_global [class*="st-key-amp_"] button:hover { opacity: 1; }
    /* ---- Ventana ampliada (st.dialog) casi a pantalla completa ---- */
    div[data-testid="stDialog"] div[role="dialog"] { width: 92vw !important; max-width: 92vw !important; }
    @media (max-width: 640px) {
        /* Métricas (st.metric) más compactas en celulares */
        div[data-testid="stMetricValue"] { font-size: 1.3rem; }
        div[data-testid="stMetricLabel"] { font-size: 0.75rem; }
        /* Evita que las tablas anchas obliguen a hacer zoom-out */
        div[data-testid="stDataFrame"] { font-size: 0.8rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)



# ==============================================================================
# CARGA Y PROCESAMIENTO DE DATOS
# ==============================================================================
def normalizar_dataframe(df_in):
    if df_in.empty:
        return df_in
    df_in.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df_in.columns]
    return df_in

# --- HOJA DE CÁLCULO DE ORIGEN (GOOGLE SHEETS) ---
GOOGLE_SHEET_URL = st.secrets.get(
    "GOOGLE_SHEET_URL",
    "https://docs.google.com/spreadsheets/d/1NuuCMa4-FBrwGVdeeqJp-vRKaKZ4BZXgxC7a8QxDPJM/edit?gid=24184152#gid=24184152",
)
GOOGLE_SHEET_ID = str(st.secrets.get("GOOGLE_SHEET_ID", "1NuuCMa4-FBrwGVdeeqJp-vRKaKZ4BZXgxC7a8QxDPJM")).strip()
GOOGLE_SHEET_GID = str(st.secrets.get("GOOGLE_SHEET_GID", "24184152")).strip()
GOOGLE_SHEET_TAB_NAME = str(st.secrets.get("GOOGLE_SHEET_TAB_NAME", "")).strip()

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _normalizar_info_cuenta(info):
    """Normaliza credenciales provenientes de secrets.toml o JSON."""
    info = dict(info or {})
    if isinstance(info.get("private_key"), str):
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    return info


def _obtener_lista_credenciales():
    """
    Obtiene las credenciales disponibles desde Streamlit Secrets (incluyendo
    [connections.gsheets]) y archivos .json locales.
    """

    credenciales_lista = []

    # 1. Carga desde llaves estándar en Streamlit Secrets
    for secret_key in ["gcp_service_account", "gcp_service_account_2"]:
        if secret_key in st.secrets:
            try:
                info = _normalizar_info_cuenta(st.secrets[secret_key])
                if info.get("client_email") and info.get("private_key"):
                    credenciales_lista.append(info)
            except Exception:
                pass

    # 2. Carga desde la sección anidada [connections.gsheets] de Streamlit Secrets
    if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
        try:
            info_gsheets = _normalizar_info_cuenta(st.secrets["connections"]["gsheets"])
            if info_gsheets.get("client_email") and info_gsheets.get("private_key"):
                if info_gsheets not in credenciales_lista:
                    credenciales_lista.append(info_gsheets)
        except Exception:
            pass

    # 3. Carga desde archivos .json locales junto al script (BASE_DIR) y,
    # como respaldo, en el directorio desde el que se ejecutó streamlit run
    # (Path(".") depende de la carpeta de trabajo actual, que puede no ser
    # la misma que la del script).
    carpetas_busqueda = {BASE_DIR, Path(".").resolve()}
    archivos_json = []
    for carpeta in carpetas_busqueda:
        archivos_json.extend(carpeta.glob("*.json"))

    for ruta_json in archivos_json:
        try:
            contenido = json.loads(ruta_json.read_text(encoding="utf-8"))
            if isinstance(contenido, dict) and contenido.get("type") == "service_account":
                info = _normalizar_info_cuenta(contenido)
                if info not in credenciales_lista:
                    credenciales_lista.append(info)
        except Exception:
            continue

    return credenciales_lista



@st.cache_resource(show_spinner=False)
def obtener_clientes_gspread():
    """
    Crea y autoriza una lista de clientes gspread para todas las cuentas de servicio encontradas.
    """
    if gspread is None:
        return [], "La librería 'gspread' no está instalada. Ejecuta: pip install gspread google-auth."
    if ServiceAccountCredentials is None:
        return [], "Falta la librería 'google-auth'. Ejecuta: pip install google-auth."

    lista_info = _obtener_lista_credenciales()
    if not lista_info:
        return [], (
            "No se encontraron credenciales de Google. En Streamlit Cloud configura "
            "[gcp_service_account] en Secrets; en local coloca el archivo .json de la cuenta "
            f"de servicio en: {BASE_DIR} (o en la carpeta desde la que ejecutaste `streamlit run`)."
        )

    clientes = []
    errores = []

    for info in lista_info:
        try:
            credenciales = ServiceAccountCredentials.from_service_account_info(
                info, scopes=SHEETS_SCOPES
            )
            cliente = gspread.authorize(credenciales)
            clientes.append((cliente, info.get("client_email", "Email desconocido")))
        except Exception as e:
            errores.append(f"Error con {info.get('client_email')}: {e}")

    if not clientes:
        return [], f"No se pudo autenticar con ninguna cuenta de servicio: {'; '.join(errores)}"

    return clientes, None


def _extraer_id_desde_url(url):
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", str(url or ""))
    return match.group(1) if match else ""


def _obtener_hoja_google(libro):
    """Localiza la pestaña sin depender exclusivamente del GID."""
    if GOOGLE_SHEET_TAB_NAME:
        try:
            return libro.worksheet(GOOGLE_SHEET_TAB_NAME)
        except Exception:
            pass

    if GOOGLE_SHEET_GID:
        try:
            gid = int(GOOGLE_SHEET_GID)
            for hoja in libro.worksheets():
                if int(hoja.id) == gid:
                    return hoja
        except (ValueError, TypeError):
            pass

    hojas = libro.worksheets()
    if hojas:
        return hojas[0]
    raise RuntimeError("El archivo de Google Sheets no contiene ninguna pestaña.")


def _leer_hoja_a_dataframe(hoja):
    """Lee valores crudos y construye el DataFrame de forma robusta."""
    valores = hoja.get_all_values()
    if not valores:
        return pd.DataFrame()

    encabezados_originales = [re.sub(r"\s+", " ", str(x)).strip() for x in valores[0]]
    encabezados = []
    usados = {}
    for i, nombre in enumerate(encabezados_originales, start=1):
        nombre = nombre or f"Columna_{i}"
        base = nombre
        usados[base] = usados.get(base, 0) + 1
        if usados[base] > 1:
            nombre = f"{base}_{usados[base]}"
        encabezados.append(nombre)

    filas = valores[1:]
    ancho = len(encabezados)
    filas_ajustadas = []
    for fila in filas:
        fila = list(fila)
        if len(fila) < ancho:
            fila += [""] * (ancho - len(fila))
        elif len(fila) > ancho:
            fila = fila[:ancho]
        filas_ajustadas.append(fila)

    df = pd.DataFrame(filas_ajustadas, columns=encabezados)
    if not df.empty:
        df = df.loc[~df.astype(str).apply(lambda fila: fila.str.strip().eq("").all(), axis=1)].reset_index(drop=True)
    return normalizar_dataframe(df)


@st.cache_data(ttl=300, show_spinner="Cargando datos de servicios desde Google Sheets...")
def cargar_datos():
    clientes, error_sheets = obtener_clientes_gspread()
    if not clientes:
        return pd.DataFrame(), f"No se pudo conectar con Google Sheets: {error_sheets}"

    sheet_id = _extraer_id_desde_url(GOOGLE_SHEET_ID) or GOOGLE_SHEET_ID
    if not sheet_id:
        sheet_id = _extraer_id_desde_url(GOOGLE_SHEET_URL)
    if not sheet_id:
        return pd.DataFrame(), "GOOGLE_SHEET_ID está vacío o no es un ID/URL válido de Google Sheets."

    errores_cuentas = []

    # Probar con cada una de las cuentas de servicio disponibles hasta tener éxito
    for cliente, email_cuenta in clientes:
        try:
            libro = cliente.open_by_key(sheet_id)
            hoja = _obtener_hoja_google(libro)
            df_datos = _leer_hoja_a_dataframe(hoja)

            if df_datos.empty:
                return pd.DataFrame(), (
                    f"La conexión con Google Sheets fue exitosa usando `{email_cuenta}`, pero la "
                    f"pestaña '{hoja.title}' no contiene datos debajo de la fila de encabezados."
                )

            st.session_state["google_sheet_diagnostico"] = (
                libro.title, hoja.title, len(df_datos), len(df_datos.columns), email_cuenta
            )
            return df_datos, None

        except gspread.exceptions.SpreadsheetNotFound:
            errores_cuentas.append(f"`{email_cuenta}`: Archivo no encontrado o sin permisos de compartir.")
        except gspread.exceptions.APIError as e:
            detalle = str(e)
            try:
                cuerpo = e.response.json().get("error", {})
                detalle = cuerpo.get("message") or detalle
            except Exception:
                pass
            errores_cuentas.append(f"`{email_cuenta}`: {detalle}")
        except Exception as e:
            errores_cuentas.append(f"`{email_cuenta}`: {type(e).__name__}: {e}")
            st.session_state["google_sheet_traceback"] = traceback.format_exc()

    # Si ninguna cuenta funcionó
    mensaje_error = "No se pudo leer la hoja con ninguna de las cuentas de servicio configuradas:\n\n" + "\n".join([f"- {err}" for err in errores_cuentas])
    return pd.DataFrame(), mensaje_error


df, error_carga_datos = cargar_datos()

with st.sidebar:
    if st.button(
        "🔄 Actualizar datos desde Google Sheets",
        key="btn_actualizar_datos_sheets",  # <-- Clave única para evitar el duplicado
        use_container_width=True
    ):
        cargar_datos.clear()
        obtener_clientes_gspread.clear()
        st.rerun()

if error_carga_datos:
    st.warning(f"⚠️ {error_carga_datos}")
    _tb = st.session_state.get("google_sheet_traceback")
    if _tb:
        with st.expander("Detalles técnicos (para depurar)"):
            st.code(_tb)

_diag = st.session_state.get("google_sheet_diagnostico")
if _diag and not error_carga_datos:
    st.caption(f"Google Sheets conectado: {_diag[0]} · Pestaña: {_diag[1]} · {_diag[2]:,} filas · {_diag[3]} columnas (Cuenta: `{_diag[4]}`)")


# ==============================================================================
# MAPEO CENTRALIZADO DE ENCABEZADOS DEL GOOGLE SHEET
# ==============================================================================
# Si cambia un encabezado en el Google Sheet, actualízalo AQUÍ y se propaga
# automáticamente a todo el dashboard (Resumen Global, IA, filtros, gráficas).
COLUMNAS = {
    "dependencia": "Abreviatura Dependencia",
    "estado": "Entidad Federativa",
    "unidades": "Inmuebles / unidades",
    "operarios_min": "No. Operarios Mínimo",
    "operarios_max": "No. Operarios Máximo",
    "monto_min_sin_iva": "Monto mínimo s/IVA",
    "monto_max_sin_iva": "Monto máximo s/IVA",
    "monto_min_con_iva": "Monto mínimo c/IVA",
    "monto_max_con_iva": "Monto máximo c/IVA",
    "Inicio": "Fecha inicio",
    "Fin": "Fecha término",
    "Contratos": "No. contrato",
}

def col(clave):
    """Devuelve el nombre real de columna del Sheet a partir de la clave lógica."""
    valor = COLUMNAS.get(clave, clave)
    return re.sub(r"\s+", " ", str(valor)).strip()


def contar_credenciales_por_puesto(*palabras_clave):
    """Cuenta cuántas credenciales generadas en la pestaña 'Coordinadores'
    (st.session_state.usuarios) tienen alguna de las palabras clave dentro
    de su campo 'puesto' (sin distinguir mayúsculas/acentos exactos)."""
    usuarios = st.session_state.get("usuarios", [])
    palabras = [p.lower() for p in palabras_clave]
    return sum(
        1 for u in usuarios
        if any(p in str(u.get("puesto", "")).lower() for p in palabras)
    )


def _a_numero(serie):
    """Convierte una columna de texto (con $, comas, espacios) a números."""
    limpio = (
        serie.astype(str)
        .str.replace(r"[^\d,.\-]", "", regex=True)  # quita $, letras, espacios
        .str.replace(",", "", regex=False)           # quita separador de miles
        .str.strip()
    )
    return pd.to_numeric(limpio, errors="coerce").fillna(0)


_COLUMNAS_NUMERICAS = [
    "unidades", "operarios_min", "operarios_max",
    "monto_min_sin_iva", "monto_max_sin_iva",
    "monto_min_con_iva", "monto_max_con_iva",
]
if not df.empty:
    for _clave in _COLUMNAS_NUMERICAS:
        _nombre_col = col(_clave)
        if _nombre_col in df.columns:
            df[_nombre_col] = _a_numero(df[_nombre_col])







# --- ASISTENTE DE IA EN LA BARRA LATERAL ---
with st.sidebar:
    st.header("🤖 Asistente de IA Armot")
    st.write("Pregúntame estadísticas o dudas sobre el reporte de servicios.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for chat in st.session_state.chat_history:
        with st.chat_message(chat["role"]):
            st.markdown(chat["content"])

    if prompt_ia := st.chat_input("¿Qué deseas saber de los datos?"):
        st.chat_message("user").markdown(prompt_ia)
        st.session_state.chat_history.append({"role": "user", "content": prompt_ia})

        with st.chat_message("assistant"):
            if client_gemini is None:
                st.info("ℹ️ El asistente IA está desactivado. Configura GEMINI_API_KEY en los secretos de Streamlit.")
            elif df is None or df.empty:
                st.error("⚠️ Los datos de servicios están vacíos o no se pudieron cargar desde Google Sheets.")
            else:
                with st.spinner("Pensando..."):
                    num_dep = df[col("dependencia")].nunique() if col("dependencia") in df.columns else 0
                    tot_uni = df[col("unidades")].sum() if col("unidades") in df.columns else 0
                    ele_min = df[col("operarios_min")].sum() if col("operarios_min") in df.columns else 0
                    ele_max = df[col("operarios_max")].sum() if col("operarios_max") in df.columns else 0
                    monto_min = f"${df[col('monto_min_con_iva')].sum():,.2f}" if col("monto_min_con_iva") in df.columns else "$0.00"
                    monto_max = f"${df[col('monto_max_con_iva')].sum():,.2f}" if col("monto_max_con_iva") in df.columns else "$0.00"

                    palabras_clave = [p.strip().lower() for p in prompt_ia.split() if len(p) > 3]
                    df_filtrado_ia = pd.DataFrame()
                    if palabras_clave:
                        mascara = df.astype(str).apply(
                            lambda x: x.str.lower().str.contains("|".join(re.escape(p) for p in palabras_clave), regex=True, na=False)
                        ).any(axis=1)
                        df_filtrado_ia = df[mascara]

                    if not df_filtrado_ia.empty:
                        muestra_datos = df_filtrado_ia.head(25)
                        nota_contexto = "Nota: Se han extraído las filas del reporte que coinciden dinámicamente con la búsqueda del usuario."
                    else:
                        muestra_datos = df.head(15)
                        nota_contexto = "Nota: Mostrando una vista previa general de las primeras filas del reporte debido a falta de palabras clave explícitas."

                    muestra_tabla = (
                        muestra_datos.to_markdown() if hasattr(muestra_datos, "to_markdown") else muestra_datos.to_string()
                    )

                    instrucciones_sistema = (
                        "Eres un asistente analítico experto de la empresa Armot. Tu objetivo único es responder "
                        "preguntas del usuario basándote strictly en el resumen de métricas y la tabla provista. "
                        "Sé ejecutivo, claro, preciso y responde siempre en español. No inventes datos fuera del contexto dado."
                    )

                    prompt_completo = f"""--- INSTRUCCIONES DEL SISTEMA ---
{instrucciones_sistema}

--- CONTEXTO DE DATOS DE LA EMPRESA (GOOGLE SHEETS) ---
- Número de Dependencias Únicas: {num_dep}
- Total de Unidades: {tot_uni}
- Elementos Mínimos de Seguridad: {ele_min}
- Elementos Máximos de Seguridad: {ele_max}
- Monto Mínimo con IVA Global de la empresa: {monto_min}
- Monto Máximo con IVA Global de la empresa: {monto_max}
{nota_contexto}

--- MUESTRA DE FILAS DEL DATAFRAME ---
{muestra_tabla}

--- PREGUNTA A RESPONDER ---
Pregunta del usuario: {prompt_ia}"""

                    try:
                        respuesta = client_gemini.models.generate_content(
                            model=st.secrets.get("GEMINI_MODEL", "gemini-2.5-flash"),
                            contents=prompt_completo,
                        )
                        if respuesta and respuesta.text:
                            st.markdown(respuesta.text)
                            st.session_state.chat_history.append({"role": "assistant", "content": respuesta.text})
                        else:
                            st.warning("La IA recibió los datos pero no generó texto. Intenta reformular tu pregunta.")
                    except Exception as e:
                        st.error(f"Ocurrió un problema al procesar la respuesta: {e}")


# ==============================================================================
# Totales de personal. Los filtros de datos ahora viven dentro de cada pestaña
# (Resumen Global tiene su panel; Coordinadores y Administración, su barra superior),
# así la barra lateral queda solo con sesión, actualización y asistente.
# ==============================================================================
st.sidebar.caption("💡 Los filtros de cada sección están dentro de su pestaña.")
Total_coordinadores = contar_credenciales_por_puesto("coordinador", "coordinadora")
Total_gerentes = contar_credenciales_por_puesto("gerente")

st.html(
    """
    <style>
        .stSubheader { text-align: center !important; }
        [data-testid="stMetric"] {
            text-align: center !important; display: flex !important;
            flex-direction: column !important; align-items: center !important;
            justify-content: center !important; width: 100% !important;
        }
        [data-testid="stMetricLabel"], [data-testid="stMetricValue"] {
            text-align: center !important; justify-content: center !important;
            display: flex !important; width: 100% !important;
        }
        .wa-link {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            color: #25D366 !important;
            font-weight: bold;
            text-decoration: none;
            border: 1px solid #25D366;
            padding: 2px 8px;
            border-radius: 6px;
            background-color: #f0fdf4;
            transition: all 0.2s ease-in-out;
        }
        .wa-link:hover {
            background-color: #25D366;
            color: #ffffff !important;
        }
        .wa-link svg {
            fill: currentColor;
        }
    </style>
    """
)

st.markdown("<h1 style='text-align: center; font-size: 1.7rem; margin: 0; padding: 0 0 0.3rem 0;'>Corporativo de Limpieza</h1>", unsafe_allow_html=True)

pestana_resumen_global, pestana_contratos, pestana_coordinadores, pestana_administracion, pestana_facturacion, pestana_acuerdos = st.tabs(
    ["Resumen Global", "Contratos", "Coordinadores", "Administración", "Seguimiento de facturación", "Acuerdos"]
)

# ==============================================================================
# PESTAÑA "Resumen Global" — DASHBOARD EJECUTIVO (KPIs + INSIGHTS + TABLERO EN VIVO)
# ==============================================================================
# Estructura:
#   · Banner con periodo fiscal, fecha de actualización y estado "Live"
#   · 4 tarjetas de montos (mín/máx, sin/con IVA) con barra comparativa
#   · Franja de "Hallazgos clave": dependencia líder, estado líder, concentración
#     Top 3 y semáforo de vigencia de contratos (vigente / por vencer / vencido)
#   · Panel de controles (izquierda) + 6 vistas en tarjetas (derecha)
#   · Barra de estado inferior (conexión, filas, # de actualización)
# Todo se recalcula en vivo al mover cualquier control. Cada vista tiene un botón
# 🔍 que la abre en una ventana ampliada (st.dialog).
PERIODO_FISCAL_INICIAL = 2026   # periodo que se muestra al abrir el tablero
ALTO_VISTA_DEFECTO = 800        # px de contenido disponible bajo las pestañas
ALTO_FIJO_TABLERO = 330         # px del banner, tarjetas, hallazgos, barra de estado y espacios
ALTO_CHROME_TARJETA = 44        # px de cabecera + márgenes de cada tarjeta de gráfica
ALTO_GRAFICA_AMPLIADA = 620     # px de la gráfica dentro de la ventana ampliada
DIAS_POR_VENCER = 90            # un contrato "por vencer" termina dentro de este número de días
TOP_BARRAS_COMPACTO = 8         # barras visibles en las tarjetas (la ventana ampliada muestra todas)

# Paleta unificada para todas las gráficas (legible en tema claro y oscuro)
PALETA = ["#2563eb", "#0ea5e9", "#14b8a6", "#f59e0b", "#8b5cf6", "#ef4444", "#22c55e", "#ec4899", "#64748b", "#a16207"]
COLOR_VIGENTE, COLOR_POR_VENCER, COLOR_VENCIDO, COLOR_SIN_FECHA = "#10b981", "#f59e0b", "#ef4444", "#94a3b8"
COLOR_GRID = "rgba(128,128,128,0.18)"

st.markdown(
    """
    <style>
    /* ---- Banner superior ---- */
    .rg-banner { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
                 padding: 12px 18px; border-radius: 14px; color: #ffffff;
                 background: linear-gradient(120deg, #0f172a 0%, #1e3a8a 55%, #2563eb 100%);
                 box-shadow: 0 4px 14px rgba(15,23,42,0.18); }
    .rg-banner .rg-title { font-size: 1.25rem; font-weight: 800; letter-spacing: 0.01em; }
    .rg-banner .rg-subtitle { font-size: 0.8rem; opacity: 0.85; }
    .rg-banner .rg-logo { background: rgba(255,255,255,0.16); }
    .rg-banner-l { display: flex; align-items: center; gap: 12px; }
    .rg-banner-r { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .rg-banner .rg-pill { border: 1px solid rgba(255,255,255,0.35); background: rgba(255,255,255,0.12); color: #ffffff; }
    /* ---- Tarjetas de montos ---- */
    .rg-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
    .rg-kpi { position: relative; overflow: hidden; border: 1px solid rgba(128,128,128,0.25); border-radius: 12px;
              background: rgba(128,128,128,0.05); padding: 10px 14px 12px 18px; min-width: 0;
              transition: transform .15s ease, box-shadow .15s ease; }
    .rg-kpi:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(0,0,0,0.10); }
    .rg-kpi::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 5px; background: var(--ac); }
    .rg-kpi-top { display: flex; justify-content: space-between; align-items: center; }
    .rg-kpi-lbl { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; opacity: 0.7; }
    .rg-kpi-ico { font-size: 1.05rem; opacity: 0.9; }
    .rg-kpi-val { font-size: clamp(1.3rem, 2vw, 1.95rem); font-weight: 800; line-height: 1.25; white-space: nowrap; color: var(--ac); }
    .rg-kpi-sub { font-size: 0.76rem; opacity: 0.75; margin-top: 1px; }
    .rg-kpi-bar { height: 5px; border-radius: 99px; background: rgba(128,128,128,0.2); margin-top: 7px; overflow: hidden; }
    .rg-kpi-bar > span { display: block; height: 100%; border-radius: 99px; background: var(--ac); }
    @media (max-width: 900px) { .rg-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    /* ---- Hallazgos clave ---- */
    .rg-ins { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
    .rg-in { border: 1px dashed rgba(128,128,128,0.35); border-radius: 12px; padding: 8px 12px; min-width: 0;
             background: rgba(37,99,235,0.045); }
    .rg-in-lbl { font-size: 0.64rem; font-weight: 800; letter-spacing: 0.07em; text-transform: uppercase; opacity: 0.6; }
    .rg-in-val { font-size: 0.98rem; font-weight: 700; line-height: 1.3; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .rg-in-sub { font-size: 0.74rem; opacity: 0.75; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .rg-sem { display: flex; height: 8px; border-radius: 99px; overflow: hidden; margin: 5px 0 3px 0; background: rgba(128,128,128,0.2); }
    .rg-sem > span { display: block; height: 100%; }
    .rg-sem-leg { display: flex; gap: 10px; font-size: 0.72rem; flex-wrap: wrap; }
    .rg-sem-leg i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 4px; }
    @media (max-width: 900px) { .rg-ins { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    /* ---- Tarjetas de gráficas más pulidas ---- */
    .st-key-resumen_global [class*="st-key-cel_"] { border-radius: 14px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
    .rg-card-tit { font-size: 0.88rem; letter-spacing: 0.01em; }
    .rg-card-stat { background: rgba(37,99,235,0.10); padding: 1px 8px; border-radius: 999px; font-size: 0.7rem; opacity: 0.95; }
    </style>
    """,
    unsafe_allow_html=True,
)

col_dep = col("dependencia")
col_est = col("estado")
col_ini = col("Inicio")
col_fin = col("Fin")
COL_EMPRESA = "Empresa operando"


def _ahora():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Mexico_City"))
    except Exception:
        return datetime.now()


def _mdp(valor):
    """Formato compacto en millones de pesos: $1,234.5 M (o 'mil M' si pasa de mil millones)."""
    if abs(valor) >= 1e9:
        return f"${valor / 1e9:,.2f} mil M"
    return f"${valor / 1e6:,.1f} M"


def _fecha(serie):
    """Convierte texto a fecha asumiendo formato mexicano (día/mes/año)."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:   # format="mixed": acepta 2026-07-28 y 28/07/2026 en la misma columna
            return pd.to_datetime(serie, errors="coerce", dayfirst=True, format="mixed")
        except (TypeError, ValueError):   # pandas < 2.0 no soporta format="mixed"
            return pd.to_datetime(serie, errors="coerce", dayfirst=True)


def _estatus_vigencia(fin, hoy):
    """Semáforo de vigencia a partir de la fecha de término."""
    limite = hoy + pd.Timedelta(days=DIAS_POR_VENCER)
    cond = [fin.isna(), fin < hoy, fin <= limite]
    return pd.Series(np.select(cond, ["Sin fecha", "Vencido", "Por vencer"], default="Vigente"), index=fin.index)


# ---------------- Periodo fiscal ----------------
def _usa_columna_ejercicio(d):
    return "Ejercicio Fiscal" in d.columns and pd.to_numeric(d["Ejercicio Fiscal"], errors="coerce").notna().any()


def _anios_disponibles(d):
    """Años fiscales presentes: columna 'Ejercicio Fiscal' si existe; si no, años que abarca la vigencia."""
    if d.empty:
        return []
    if _usa_columna_ejercicio(d):
        s = pd.to_numeric(d["Ejercicio Fiscal"], errors="coerce").dropna().astype(int)
        return sorted(s.unique().tolist())
    if {col_ini, col_fin}.issubset(d.columns):
        ini = _fecha(d[col_ini])
        fin = _fecha(d[col_fin])
        if ini.notna().any() and fin.notna().any():
            return list(range(int(ini.dt.year.min()), int(fin.dt.year.max()) + 1))
    return []


def _mascara_periodo(d, anio):
    if _usa_columna_ejercicio(d):
        return pd.to_numeric(d["Ejercicio Fiscal"], errors="coerce") == anio
    ini = _fecha(d[col_ini])
    fin = _fecha(d[col_fin])
    return (ini.dt.year <= anio) & (fin.dt.year >= anio)


# ---------------- Cálculos de la vista (se recalculan con cada cambio de control) ----------------
def _top_con_otros(datos, eje, etiqueta_otros):
    """Top N por monto y el resto agrupado en una sola barra 'Otras (k)'."""
    d = datos.sort_values("Monto total", ascending=False).copy()
    if len(d) > TOP_BARRAS_COMPACTO:
        cabeza = d.head(TOP_BARRAS_COMPACTO - 1)
        resto = d.iloc[TOP_BARRAS_COMPACTO - 1:]
        fila = pd.DataFrame({eje: [f"{etiqueta_otros} ({len(resto)})"],
                             "Monto total": [float(resto["Monto total"].sum())],
                             "Monto (M)": [float(resto["Monto (M)"].sum())]})
        d = pd.concat([cabeza, fila], ignore_index=True)
    return d


def _preparar_datos(d):
    r = {"agrupado": None, "dep_montos": None, "est_montos": None,
         "max_unidades": 0, "monto_max_dep": 0.0, "monto_max_est": 0.0}
    if d.empty:
        return r
    if {col_dep, col("unidades"), col("monto_max_con_iva"), col("operarios_max")}.issubset(d.columns):
        a = d.groupby(col_dep).agg(
            {col("unidades"): "sum", col("monto_max_con_iva"): "sum", col("operarios_max"): "sum"}
        ).reset_index()
        a.columns = ["Dependencia", "Unidades", "Monto total", "Operarios Máximos"]
        a["Monto (M)"] = a["Monto total"] / 1e6
        r["agrupado"] = a
        r["max_unidades"] = int(a["Unidades"].max()) if not a.empty else 0
    if {col_dep, col("monto_max_con_iva")}.issubset(d.columns):
        m = (d.groupby(col_dep)[col("monto_max_con_iva")].sum().reset_index()
             .rename(columns={col_dep: "Dependencia", col("monto_max_con_iva"): "Monto total"})
             .sort_values("Monto total", ascending=False))
        m["Monto (M)"] = m["Monto total"] / 1e6
        r["dep_montos"] = m
        # El tope del slider es la barra más larga que se dibuja (puede ser la suma de "Otras").
        r["monto_max_dep"] = float(_top_con_otros(m, "Dependencia", "Otras dependencias")["Monto total"].max()) if not m.empty else 0.0
    if {col_est, col("monto_max_con_iva")}.issubset(d.columns):
        e = d.groupby(col_est)[col("monto_max_con_iva")].sum().reset_index()
        e.columns = ["Estado", "Monto total"]
        e = e.sort_values("Monto total", ascending=False)
        e["Monto (M)"] = e["Monto total"] / 1e6
        r["est_montos"] = e
        r["monto_max_est"] = float(_top_con_otros(e, "Estado", "Otros estados")["Monto total"].max()) if not e.empty else 0.0
    return r


def _calcular_kpis(d):
    def suma(clave):
        return float(d[col(clave)].sum()) if (not d.empty and col(clave) in d.columns) else 0.0

    def unicos(c):
        return int(d[c].nunique()) if (not d.empty and c in d.columns) else 0

    return {
        "entidades": unicos(col_dep), "estados": unicos(col_est), "unidades": int(suma("unidades")),
        "contratos": unicos(col("Contratos")),
        "op_min": int(suma("operarios_min")), "op_max": int(suma("operarios_max")),
        "min_sin": suma("monto_min_sin_iva"), "max_sin": suma("monto_max_sin_iva"),
        "min_con": suma("monto_min_con_iva"), "max_con": suma("monto_max_con_iva"),
        "filas": 0 if d.empty else len(d),
    }


def _calcular_insights(d, dv, k):
    """Hallazgos clave: líderes, concentración y semáforo de vigencia."""
    ins = {"dep": None, "est": None, "top3": None, "vig": None}
    m = dv["dep_montos"]
    if m is not None and not m.empty:
        total = float(m["Monto total"].sum())
        if total > 0:
            f = m.iloc[0]
            ins["dep"] = (str(f["Dependencia"]), float(f["Monto total"]), float(f["Monto total"]) / total * 100)
            ins["top3"] = (float(m["Monto total"].head(3).sum()) / total * 100, min(3, len(m)))
    e = dv["est_montos"]
    if e is not None and not e.empty:
        total = float(e["Monto total"].sum())
        if total > 0:
            f = e.iloc[0]
            ins["est"] = (str(f["Estado"]), float(f["Monto total"]), float(f["Monto total"]) / total * 100)
    if not d.empty and {col_fin}.issubset(d.columns):
        t = d.copy()
        t["_fin"] = _fecha(t[col_fin])
        ccon = col("Contratos")
        if ccon in t.columns:
            # Un contrato puede tener varias filas: se cuenta una vez con su fecha de término más tardía.
            # (drop_duplicates(keep="last") dejaba la fila sin fecha, porque NaT se ordena al final,
            #  y marcaba como "Sin fecha" contratos que sí tenían fechas.)
            clave = t[ccon].astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
            t["_k"] = clave.fillna(pd.Series("fila-" + t.index.astype(str), index=t.index))
            t = t.groupby("_k", as_index=False)["_fin"].max()
        hoy = pd.Timestamp(_ahora().date())
        est = _estatus_vigencia(t["_fin"], hoy).value_counts()
        ins["vig"] = {k2: int(est.get(k2, 0)) for k2 in ["Vigente", "Por vencer", "Vencido", "Sin fecha"]}
    return ins


def _estilo_base(fig, grande, alto_compacto=0):
    """Aspecto común de todas las gráficas: rejilla suave y fondo transparente."""
    fig.update_xaxes(gridcolor=COLOR_GRID, zeroline=False)
    fig.update_yaxes(gridcolor=COLOR_GRID, zeroline=False)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def _layout_grafica(fig, grande, alto_compacto=0):
    """Layout compacto (tarjeta de la cuadrícula, sin título: lo da la cabecera) o grande (ventana ampliada)."""
    if grande:
        fig.update_layout(
            height=ALTO_GRAFICA_AMPLIADA, autosize=True, margin=dict(l=10, r=10, t=60, b=10),
            title=dict(font=dict(size=18), x=0.5, xanchor="center"), font=dict(size=12),
        )
        fig.update_xaxes(automargin=True)
        fig.update_yaxes(automargin=True)
    else:
        aplicar_layout_compacto(fig, alto_compacto)
        fig.update_layout(title=None, margin=dict(l=6, r=6, t=6, b=6))
    return _estilo_base(fig, grande, alto_compacto)


# ---------------- Constructores de cada vista (tarjeta y ventana ampliada) ----------------
def construir_dispersion(grande, alto=0):
    a = DV["agrupado"]
    if a is None:
        return None, None, "No hay datos para la gráfica de dispersión."
    d = a
    if DV["max_unidades"] > 0:
        d = d[(d["Unidades"] >= rango_unidades[0]) & (d["Unidades"] <= rango_unidades[1])]
    if d.empty:
        return None, None, "Sin dependencias en el rango de unidades seleccionado."
    fig = px.scatter(
        d, x="Unidades", y="Monto (M)", color="Dependencia", size="Operarios Máximos",
        size_max=55 if grande else 22, hover_name="Dependencia",
        color_discrete_sequence=PALETA,
        hover_data={"Unidades": ":,", "Monto (M)": ":,.2f", "Operarios Máximos": ":,", "Dependencia": False},
        labels={"Unidades": "Número de unidades", "Monto (M)": "Monto máx. c/IVA (millones)"},
    )
    fig.update_traces(marker=dict(line=dict(width=1, color="white"), opacity=0.85))
    fig.update_layout(
        title=f"<b>Dispersión de Servicios</b> · {PERIODO_TXT} <span style='font-size:0.7em'>(tamaño = operarios máx.)</span>",
        showlegend=grande,
        yaxis=dict(tickprefix="$", ticksuffix=" M", tickformat=",.0f"),
        xaxis=dict(range=[rango_unidades[0], rango_unidades[1]] if DV["max_unidades"] > 0 else None, fixedrange=True),
    )
    return _layout_grafica(fig, grande, alto), d.drop(columns=["Monto (M)"]), None


def construir_vigencia(grande, alto=0):
    d0 = DV_DF
    if d0.empty or not {col_ini, col_fin, col_dep}.issubset(d0.columns):
        return None, None, "No hay datos de fechas para mostrar la vigencia."
    d = d0.copy()
    d["_ini"] = _fecha(d[col_ini])
    d["_fin"] = _fecha(d[col_fin])
    d = d.dropna(subset=["_ini", "_fin", col_dep])
    if d.empty:
        return None, None, "No hay fechas válidas para mostrar la vigencia."
    ccon = col("Contratos")
    tiene_con = ccon in d.columns
    nom_con = "Contrato" if grande else "Contratos"   # en la tarjeta compacta es un conteo por dependencia
    if grande:
        cols_base = [col_dep, "_ini", "_fin"] + ([ccon] if tiene_con else [])
        t = d[cols_base].copy()
        if tiene_con:
            t = t.rename(columns={ccon: "Contrato"})
        else:
            t["Contrato"] = ""
    else:
        agg = {"_ini": ("_ini", "min"), "_fin": ("_fin", "max")}
        if tiene_con:
            agg[nom_con] = (ccon, "nunique")
        t = d.groupby(col_dep).agg(**agg).reset_index()
        if not tiene_con:
            t[nom_con] = ""
    hoy = pd.Timestamp(_ahora().date())
    t["Estatus"] = _estatus_vigencia(t["_fin"], hoy)
    t = t.sort_values("_fin").reset_index(drop=True)
    orden = list(dict.fromkeys(t[col_dep].tolist()))
    fig = px.timeline(
        t, x_start="_ini", x_end="_fin", y=col_dep, color="Estatus",
        color_discrete_map={"Vigente": COLOR_VIGENTE, "Por vencer": COLOR_POR_VENCER,
                            "Vencido": COLOR_VENCIDO, "Sin fecha": COLOR_SIN_FECHA},
        category_orders={"Estatus": ["Vigente", "Por vencer", "Vencido"]},
        hover_data={nom_con: True, "_ini": "|%d/%m/%Y", "_fin": "|%d/%m/%Y", col_dep: False},
        labels={col_dep: "Dependencia", "_ini": "Inicio", "_fin": "Término"},
    )
    fig.update_yaxes(categoryorder="array", categoryarray=orden, autorange="reversed",
                     tickfont=dict(size=11 if grande else 8))
    fig.add_shape(type="line", x0=hoy.isoformat(), x1=hoy.isoformat(), y0=0, y1=1, yref="paper",
                  line=dict(color="#ef4444", width=1.6, dash="dot"))
    if grande:
        fig.add_annotation(x=hoy.isoformat(), y=1, yref="paper", text="Hoy", showarrow=False,
                           font=dict(size=11, color="#ef4444"), yanchor="bottom")
    fig.update_layout(
        title=f"<b>Vigencia de Contratos</b> · {PERIODO_TXT}", xaxis_title=None, yaxis_title=None,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, title=None,
                    font=dict(size=11 if grande else 8)),
        xaxis=dict(tickformat="%b\n%Y" if grande else "%b\n%y", ticklabelmode="period"),
    )
    datos = t[[col_dep, nom_con, "_ini", "_fin", "Estatus"]].copy()
    datos = datos.rename(columns={col_dep: "Dependencia", nom_con: "Contrato", "_ini": "Inicio", "_fin": "Término"})
    for c in ("Inicio", "Término"):
        datos[c] = datos[c].dt.strftime("%d/%m/%Y")
    return _layout_grafica(fig, grande, alto), datos, None


def construir_empresas(grande, alto=0):
    d = DV_DF
    if d.empty or not {COL_EMPRESA, col_dep}.issubset(d.columns):
        return None, None, "No hay datos de empresas operando."
    emp = d.groupby(COL_EMPRESA, dropna=False)[col_dep].nunique().reset_index(name="Dependencias")
    emp = emp.sort_values("Dependencias", ascending=False)
    total = int(d[col_dep].nunique())
    fig = go.Figure(data=[go.Pie(
        labels=emp[COL_EMPRESA], values=emp["Dependencias"], hole=0.58, sort=False,
        marker=dict(colors=PALETA, line=dict(color="white", width=2)),
        textinfo="percent+label+value" if grande else "percent", insidetextorientation="radial",
        hovertemplate="<b>%{label}</b><br>%{value} dependencias (%{percent})<extra></extra>",
    )])
    fig.add_annotation(
        text=f"<b style='font-size:{22 if grande else 16}px'>{total}</b><br>"
             f"<span style='font-size:{12 if grande else 9}px'>dependencias</span>",
        x=0.5, y=0.5, showarrow=False,
    )
    fig.update_layout(
        title=f"<b>Empresas operando los servicios</b> · {PERIODO_TXT}",
        showlegend=True,
        legend=dict(orientation="h", yanchor="top", y=-0.02, xanchor="center", x=0.5,
                    font=dict(size=11 if grande else 8)),
    )
    return _layout_grafica(fig, grande, alto), emp, None


def _barras(datos, eje, escala, limite_pesos, grande, alto, etiqueta_otros):
    """Barras horizontales ordenadas (mayor arriba) con etiqueta de monto.
    En la tarjeta compacta muestra el Top N y agrupa el resto en 'Otros'."""
    d = datos.sort_values("Monto total", ascending=False).copy() if grande else _top_con_otros(datos, eje, etiqueta_otros)
    tope = max(limite_pesos / 1e6, 0.0001) * 1.22   # holgura para que quepa la etiqueta
    fig = go.Figure(go.Bar(
        x=d["Monto (M)"], y=d[eje], orientation="h",
        marker=dict(color=d["Monto (M)"], colorscale=escala, line=dict(width=0)),
        text=[f"${v:,.1f} M" for v in d["Monto (M)"]], textposition="outside", cliponaxis=False,
        textfont=dict(size=11 if grande else 9),
        hovertemplate="<b>%{y}</b><br>$%{x:,.2f} M<extra></extra>",
    ))
    fig.update_layout(
        xaxis=dict(range=[0, tope], tickprefix="$", ticksuffix=" M", tickformat=",.0f", fixedrange=True, title=None),
        yaxis=dict(autorange="reversed", type="category", fixedrange=True, title=None,
                   tickfont=dict(size=11 if grande else 9)),
        bargap=0.28, showlegend=False,
    )
    return fig


def construir_dependencias(grande, alto=0):
    m = DV["dep_montos"]
    if m is None:
        return None, None, "No hay datos para la gráfica de dependencias."
    fig = _barras(m, "Dependencia", "Blues", limite_y_dep, grande, alto, "Otras dependencias")
    fig.update_layout(title=f"<b>Monto Máximo con IVA por Dependencia</b> · {PERIODO_TXT}")
    return _layout_grafica(fig, grande, alto), m.drop(columns=["Monto (M)"]), None


def construir_estados(grande, alto=0):
    e = DV["est_montos"]
    if e is None:
        return None, None, "Columnas incompletas para la gráfica por estado."
    fig = _barras(e, "Estado", "Teal", limite_y_est, grande, alto, "Otros estados")
    fig.update_layout(title=f"<b>Inversión Máxima con IVA por Estado</b> · {PERIODO_TXT}")
    return _layout_grafica(fig, grande, alto), e.drop(columns=["Monto (M)"]), None


def construir_tabla_estados(grande, alto=0):
    d = DV_DF
    if d.empty or not {col_est, col_dep, col("unidades")}.issubset(d.columns):
        return None, None, "No hay datos para el desglose geográfico."
    agg = {col_dep: "nunique", col("unidades"): "sum"}
    nombres = ["Estado", "Dependencias", "Unidades"]
    if col("monto_max_con_iva") in d.columns:
        agg[col("monto_max_con_iva")] = "sum"
        nombres.append("Monto (M)")
    t = d.groupby(col_est).agg(agg).reset_index()
    t.columns = nombres
    if "Monto (M)" in t.columns:
        t["Monto (M)"] = t["Monto (M)"] / 1e6
    t = t.sort_values("Unidades", ascending=False).reset_index(drop=True)
    return None, t, None


def mostrar_tabla_estados(t, alto):
    cfg = {
        "Estado": st.column_config.TextColumn("Estado", width="small"),
        "Dependencias": st.column_config.NumberColumn("Dep.", format="%d", width="small"),
        "Unidades": st.column_config.ProgressColumn(
            "Unidades", format="%d", min_value=0, max_value=max(1, int(t["Unidades"].max())), width="medium"),
    }
    if "Monto (M)" in t.columns:
        cfg["Monto (M)"] = st.column_config.ProgressColumn(
            "Monto máx. c/IVA", format="$%.1f M", min_value=0.0, max_value=max(1.0, float(t["Monto (M)"].max())), width="medium")
    st.dataframe(t, width="stretch", hide_index=True, height=int(alto), column_config=cfg)


CATALOGO_GRAFICAS = {
    "dispersion": construir_dispersion,
    "vigencia": construir_vigencia,
    "empresas": construir_empresas,
    "dependencias": construir_dependencias,
    "estados": construir_estados,
    "tabla": construir_tabla_estados,
}


def cabecera_tarjeta(clave):
    """(título, dato destacado) que se muestra en la cabecera de cada tarjeta."""
    if clave == "dispersion":
        n = 0 if DV["agrupado"] is None else len(DV["agrupado"])
        return "Dispersión de servicios", f"{n} dependencias"
    if clave == "vigencia":
        return "Vigencia de contratos", f"{KP['contratos']} contratos"
    if clave == "empresas":
        n = DV_DF[COL_EMPRESA].nunique() if (not DV_DF.empty and COL_EMPRESA in DV_DF.columns) else 0
        return "Empresas operando", f"{n} empresas"
    if clave == "dependencias":
        t = 0.0 if DV["dep_montos"] is None else float(DV["dep_montos"]["Monto total"].sum())
        return "Monto máx. c/IVA por dependencia", f"Total {_mdp(t)}"
    if clave == "estados":
        e = DV["est_montos"]
        return "Inversión máx. c/IVA por estado", (f"{len(e)} estados · {_mdp(float(e['Monto total'].sum()))}" if e is not None else "—")
    return "Desglose por estado", f"{KP['estados']} entidades"


@st.dialog("🔍 Vista ampliada", width="large")
def dialogo_ampliar(clave):
    """Muestra la vista elegida en grande, con sus datos en una tabla desplegable."""
    fig, datos, aviso = CATALOGO_GRAFICAS[clave](True)
    if aviso:
        st.info(aviso)
        return
    if fig is not None:
        mostrar_grafico(fig, key=f"dlg_{clave}")
        if datos is not None:
            with st.expander("📋 Ver datos de la gráfica", expanded=False):
                st.dataframe(datos, width="stretch", hide_index=True)
    else:
        st.markdown(f"**📍 Desglose por Estado** · {PERIODO_TXT}")
        mostrar_tabla_estados(datos, ALTO_GRAFICA_AMPLIADA)


def celda_grafica(clave, alto):
    """Tarjeta de la cuadrícula: cabecera (título + dato) + gráfica + botón 🔍 para ampliarla."""
    with st.container(key=f"cel_{clave}"):
        if st.button("🔍", key=f"amp_{clave}", help="Ampliar esta vista"):
            dialogo_ampliar(clave)
        titulo, dato = cabecera_tarjeta(clave)
        st.markdown(
            f'<div class="rg-card-head"><span class="rg-card-tit">{titulo}</span>'
            f'<span class="rg-card-stat">{dato}</span></div>',
            unsafe_allow_html=True,
        )
        fig, datos, aviso = CATALOGO_GRAFICAS[clave](False, alto)
        if aviso:
            st.info(aviso)
        elif fig is not None:
            mostrar_grafico(fig, key=f"grafico_{clave}")
        else:
            mostrar_tabla_estados(datos, alto)


# ---------------- Bloques HTML (banner, tarjetas de montos, hallazgos, resumen, barra de estado) ----------------
def html_encabezado(periodo_txt, filtros_txt=""):
    fecha = _ahora().strftime("%d/%m/%Y")
    return (
        '<div class="rg-banner"><div class="rg-banner-l"><div class="rg-logo">📈</div><div>'
        '<div class="rg-title">Resumen Global</div>'
        f'<div class="rg-subtitle">Servicios y contratos · {periodo_txt}'
        f'{" · 🔎 " + _esc(filtros_txt) if filtros_txt else ""}</div></div></div>'
        f'<div class="rg-banner-r"><span class="rg-pill">🗓️ {fecha}</span>'
        '<span class="rg-pill"><span class="rg-dot"></span>Live · filtros en tiempo real</span></div></div>'
    )


def html_tarjetas_montos(k):
    tope = max(k["max_con"], k["max_sin"], 1.0)
    iva_min = k["min_con"] - k["min_sin"]
    iva_max = k["max_con"] - k["max_sin"]

    def pct(a, b):
        return f"{a / b * 100:,.0f}% del máximo" if b else "—"

    tarjetas = [
        ("Mínimo sin IVA", "🪙", "#64748b", k["min_sin"], pct(k["min_sin"], k["max_sin"])),
        ("Máximo sin IVA", "💼", "#2563eb", k["max_sin"], "Base antes de IVA"),
        ("Mínimo con IVA", "🧾", "#0d9488", k["min_con"], f"▲ {_mdp(iva_min)} de IVA"),
        ("Máximo con IVA", "💰", "#16a34a", k["max_con"], f"▲ {_mdp(iva_max)} de IVA"),
    ]
    celdas = "".join(
        f'<div class="rg-kpi" style="--ac:{ac}" title="${valor:,.2f}">'
        f'<div class="rg-kpi-top"><span class="rg-kpi-lbl">{et}</span><span class="rg-kpi-ico">{ic}</span></div>'
        f'<div class="rg-kpi-val">{_mdp(valor)}</div><div class="rg-kpi-sub">{sub}</div>'
        f'<div class="rg-kpi-bar"><span style="width:{min(100, valor / tope * 100):.1f}%"></span></div></div>'
        for et, ic, ac, valor, sub in tarjetas
    )
    return f'<div class="rg-kpis">{celdas}</div>'


def html_insights(ins, k):
    def tile(lbl, val, sub):
        val, sub = _esc(str(val)), _esc(str(sub))
        return (f'<div class="rg-in"><div class="rg-in-lbl">{lbl}</div>'
                f'<div class="rg-in-val" title="{val}">{val}</div><div class="rg-in-sub">{sub}</div></div>')

    t = []
    if ins["dep"]:
        n, m, p = ins["dep"]
        t.append(tile("🏆 Dependencia líder", n, f"{_mdp(m)} · {p:,.1f}% del total"))
    else:
        t.append(tile("🏆 Dependencia líder", "—", "Sin datos"))
    if ins["est"]:
        n, m, p = ins["est"]
        t.append(tile("📍 Estado líder", n, f"{_mdp(m)} · {p:,.1f}% del total"))
    else:
        t.append(tile("📍 Estado líder", "—", "Sin datos"))
    if ins["top3"]:
        p, n = ins["top3"]
        t.append(tile(f"🎯 Concentración Top {n}", f"{p:,.1f}%", "del monto en las mayores dependencias"))
    else:
        t.append(tile("🎯 Concentración Top 3", "—", "Sin datos"))

    v = ins["vig"]
    if v and sum(v.values()) > 0:
        total = sum(v.values())
        seg = [("Vigente", COLOR_VIGENTE), ("Por vencer", COLOR_POR_VENCER),
               ("Vencido", COLOR_VENCIDO), ("Sin fecha", COLOR_SIN_FECHA)]
        barra = "".join(f'<span style="width:{v[n] / total * 100:.1f}%;background:{c}"></span>' for n, c in seg if v[n])
        leyenda = "".join(f'<span><i style="background:{c}"></i>{v[n]} {n.lower()}</span>' for n, c in seg if v[n])
        t.append(
            '<div class="rg-in"><div class="rg-in-lbl">🚦 Vigencia de contratos</div>'
            f'<div class="rg-sem">{barra}</div><div class="rg-sem-leg">{leyenda}</div></div>'
        )
    else:
        t.append(tile("🚦 Vigencia de contratos", "—", "Sin fechas válidas"))
    return f'<div class="rg-ins">{"".join(t)}</div>'


def html_resumen(k):
    items = [
        ("🏛️", f"{k['entidades']}", "Entidades"), ("🗺️", f"{k['estados']}", "Estados"),
        ("🏢", f"{k['unidades']:,}", "Unidades"), ("📄", f"{k['contratos']}", "Contratos"),
        ("👷", f"{k['op_min']:,}", "Elementos mín."), ("👷", f"{k['op_max']:,}", "Elementos máx."),
        ("🧭", f"{int(Total_coordinadores)}", "Coordinadores"), ("🎖️", f"{int(Total_gerentes)}", "Gerentes"),
    ]
    chips = "".join(
        f'<div class="rg-chip"><span class="rg-chip-ico">{i}</span><div><div class="rg-chip-val">{v}</div>'
        f'<div class="rg-chip-lbl">{e}</div></div></div>'
        for i, v, e in items
    )
    return f'<div class="rg-chips">{chips}</div>'


def html_barra_estado(k, periodo_txt):
    conectado = not (error_carga_datos or df.empty)
    estado = (f'<span class="rg-dot"></span>Conectado · Google Sheets · {k["filas"]:,} filas en vista'
              if conectado else '<span class="rg-dot rojo"></span>Sin datos / sin conexión')
    return (
        f'<div class="rg-foot"><span>{estado}</span>'
        f'<span>{periodo_txt} · actualización #{st.session_state["resumen_actualizaciones"]} · '
        f'{st.session_state["resumen_hora_datos"]}</span></div>'
    )


def _limpiar_filtros_resumen():
    """Botón 🧹: vacía los cuatro filtros del panel."""
    for k in ("estado", "dep", "emp", "estatus"):
        st.session_state[f"f_resumen_{k}"] = []


def _actualizar_datos():
    """Botón 🔄: descarta la caché del Google Sheet y fuerza una nueva lectura."""
    cargar_datos.clear()
    st.session_state["resumen_actualizaciones"] += 1
    st.session_state["resumen_hora_datos"] = _ahora().strftime("%H:%M:%S")


if "resumen_actualizaciones" not in st.session_state:
    st.session_state["resumen_actualizaciones"] = 1
    st.session_state["resumen_hora_datos"] = _ahora().strftime("%H:%M:%S")


with pestana_resumen_global:
  with st.container(key="resumen_global"):
    ph_encabezado = st.empty()          # se rellena abajo, cuando ya se conoce el periodo elegido
    col_panel, col_main = st.columns([1.15, 5], gap="small")

    # =========================== PANEL DE CONTROLES ===========================
    with col_panel:
      with st.container(key="panel_resumen"):
        st.markdown('<div class="rg-panel-tit">Filtros</div>', unsafe_allow_html=True)

        anios = _anios_disponibles(df)
        opciones_periodo = [str(a) for a in anios] + ["Todos"]
        periodo_defecto = str(PERIODO_FISCAL_INICIAL) if PERIODO_FISCAL_INICIAL in anios else "Todos"
        periodo = st.radio(
            "Periodo fiscal", opciones_periodo, index=opciones_periodo.index(periodo_defecto),
            horizontal=True, key="periodo_fiscal_resumen",
        )
        df_p = df if (periodo == "Todos" or df.empty) else df[_mascara_periodo(df, int(periodo))]

        def _filtro_multi(d, columna, clave, etiqueta, vacio):
            """Filtro compacto en cascada; descarta selecciones que ya no existen tras otro filtro."""
            if columna not in d.columns or d.empty:
                return d, []
            op = sorted(d[columna].dropna().astype(str).unique().tolist())
            k = f"f_resumen_{clave}"
            if k in st.session_state:
                st.session_state[k] = [v for v in st.session_state[k] if v in op]
            sel = st.multiselect(etiqueta, op, key=k, placeholder=vacio)
            return (d[d[columna].astype(str).isin(sel)] if sel else d), sel

        df_f, estados_sel = _filtro_multi(df_p, col_est, "estado", "Estado", "Todos")
        df_f, deps_sel = _filtro_multi(df_f, col_dep, "dep", "Dependencia", "Todas")
        df_f, empresas_sel = _filtro_multi(df_f, COL_EMPRESA, "emp", "Empresa operando", "Todas")
        df_f, estatus_sel = _filtro_multi(df_f, "Estatus", "estatus", "Estatus", "Todos")
        DV_DF = df_f
        _filtros_activos = [("Estado", estados_sel), ("Dependencia", deps_sel),
                            ("Empresa", empresas_sel), ("Estatus", estatus_sel)]
        FILTROS_TXT = " · ".join(
            f"{n}: {', '.join(v[:2])}{' +' + str(len(v) - 2) if len(v) > 2 else ''}" for n, v in _filtros_activos if v
        )
        if FILTROS_TXT:
            st.button("🧹 Limpiar filtros", key="btn_limpiar_resumen", width="stretch", on_click=_limpiar_filtros_resumen)
        DV = _preparar_datos(DV_DF)
        KP = _calcular_kpis(DV_DF)
        INS = _calcular_insights(DV_DF, DV, KP)
        PERIODO_TXT = f"Ejercicio fiscal {periodo}" if periodo != "Todos" else "Todos los periodos"

        # Los límites de los ejes dependen de los datos filtrados: la clave incluye los filtros
        # para que, al cambiarlos, los sliders se reinicien a su rango completo.
        firma = hashlib.md5(
            f"{periodo}|{estados_sel}|{deps_sel}|{empresas_sel}|{estatus_sel}".encode("utf-8")
        ).hexdigest()[:8]
        with st.expander("📐 Ajuste de ejes", expanded=False):
            if DV["max_unidades"] > 0:
                rango_unidades = st.slider(
                    "Rango de unidades (dispersión)", min_value=0, max_value=DV["max_unidades"],
                    value=(0, DV["max_unidades"]), step=1, key=f"slider_dispersion_x_{firma}",
                )
            else:
                rango_unidades = (0, 0)
            if DV["monto_max_dep"] > 0:
                limite_y_dep = st.slider(
                    "Límite horizontal (monto por dependencia)", min_value=0.0, max_value=DV["monto_max_dep"],
                    value=DV["monto_max_dep"], step=100000.0, format="$%,.2f", key=f"slider_y_dep_{firma}",
                )
            else:
                limite_y_dep = 0.0
            if DV["monto_max_est"] > 0:
                limite_y_est = st.slider(
                    "Límite horizontal (monto por estado)", min_value=0.0, max_value=DV["monto_max_est"],
                    value=DV["monto_max_est"], step=500000.0, format="$%,.2f", key=f"slider_y_est_{firma}",
                )
            else:
                limite_y_est = 0.0

        alto_vista = st.slider(
            "Alto de la vista (px)", min_value=560, max_value=1500, value=ALTO_VISTA_DEFECTO, step=20,
            key="alto_vista_resumen",
            help="Si te sobra espacio abajo o te hace scroll, sube o baja este valor hasta que las 6 vistas queden justas en tu pantalla.",
        )

        st.markdown('<div class="rg-panel-tit">Resumen</div>', unsafe_allow_html=True)
        st.markdown(html_resumen(KP), unsafe_allow_html=True)

        st.button("🔄 Actualizar datos", type="primary", width="stretch",
                  key="btn_actualizar_resumen", on_click=_actualizar_datos)
        st.link_button("Abrir Google Sheets", url=GOOGLE_SHEET_URL, icon="📊", width="stretch")
        st.download_button(
            "⬇️ Exportar vista (CSV)", data=DV_DF.to_csv(index=False).encode("utf-8-sig"),
            file_name="resumen_global_filtrado.csv", mime="text/csv", key="btn_exportar_resumen",
            width="stretch", disabled=DV_DF.empty,
        )

    alto_fila = max(180, int((alto_vista - ALTO_FIJO_TABLERO) / 2) - ALTO_CHROME_TARJETA)
    ph_encabezado.markdown(html_encabezado(PERIODO_TXT, FILTROS_TXT), unsafe_allow_html=True)

    # =========================== TABLERO ===========================
    with col_main:
        st.markdown(html_tarjetas_montos(KP), unsafe_allow_html=True)
        st.markdown(html_insights(INS, KP), unsafe_allow_html=True)
        fila1 = st.columns([5, 4, 3])
        fila2 = st.columns(3)
        with fila1[0]:
            celda_grafica("dependencias", alto_fila)
        with fila1[1]:
            celda_grafica("vigencia", alto_fila)
        with fila1[2]:
            celda_grafica("empresas", alto_fila)
        with fila2[0]:
            celda_grafica("dispersion", alto_fila)
        with fila2[1]:
            celda_grafica("estados", alto_fila)
        with fila2[2]:
            celda_grafica("tabla", alto_fila)
        st.markdown(html_barra_estado(KP, PERIODO_TXT), unsafe_allow_html=True)


# ==============================================================================
# PESTAÑA "Coordinadores" — CREDENCIALES INTERACTIVAS POR REGIÓN
# ==============================================================================
REGIONES = ["CDMX", "Toluca", "Estado de México", "Foraneos"]

def normalizar_ids_unicos(registros, prefijo="USR"):
    usados = set()
    for i, registro in enumerate(registros, start=1):
        original = str(registro.get("id", "")).strip() or f"{prefijo}-{i:04d}"
        candidato = original
        contador = 2
        while candidato in usados:
            candidato = f"{original}-{contador}"
            contador += 1
        registro["id"] = candidato
        usados.add(candidato)
    return registros

def limpiar_registro_personal(registro):
    registro.setdefault("foto_bytes", None)
    registro.setdefault("servicios", None)
    registro.setdefault("proyectos", [])
    registro.setdefault("habilidades", [])
    for clave in ["nombre", "puesto", "departamento", "estado", "email", "telefono", "ubicacion", "nivel_acceso", "fecha_ingreso"]:
        registro[clave] = str(registro.get(clave, "") or "").strip()
    return registro






# ==============================================================================
# COMPONENTES COMPARTIDOS DE LAS PESTAÑAS
# (banner, tarjetas KPI, barra de búsqueda/filtros del personal y tableros editables)
# ==============================================================================
st.markdown(
    """
    <style>
    .rg-kpis.c3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .rg-kpis.c5 { grid-template-columns: repeat(5, minmax(0, 1fr)); }
    .rg-kpis.c6 { grid-template-columns: repeat(6, minmax(0, 1fr)); }
    @media (max-width: 900px) {
        .rg-kpis.c3, .rg-kpis.c5, .rg-kpis.c6 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 14px; }
    button[data-baseweb="tab"] p { font-weight: 600; }
    .tb-espacio { height: 6px; }
    .tb-resumen { font-size: 0.8rem; opacity: 0.7; margin: 2px 2px 8px 2px; }
    .tb-grupo { display: flex; align-items: center; gap: 8px; margin: 14px 0 6px 2px; font-size: 1.02rem; font-weight: 700; }
    .tb-grupo span { font-size: 0.72rem; font-weight: 600; padding: 1px 9px; border-radius: 999px; background: rgba(37,99,235,0.12); }
    .tb-vacio { text-align: center; padding: 26px 12px; border: 1px dashed rgba(128,128,128,0.4);
                border-radius: 14px; opacity: 0.85; font-size: 0.92rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

ESTADOS_PERSONAL = ("Activo", "Pendiente", "Inactivo")
NIVELES_ACCESO = ["Nivel 1 (Coordinador)", "Nivel 2 (Gerente)", "Nivel 3 (Administrativo)", "Nivel 4 (Director)"]


def html_banner_tab(icono, titulo, subtitulo, pills=()):
    """Banner de encabezado con el mismo estilo del Resumen Global."""
    chips = "".join(f'<span class="rg-pill">{p}</span>' for p in pills)
    return (
        '<div class="rg-banner"><div class="rg-banner-l">'
        f'<div class="rg-logo">{icono}</div><div><div class="rg-title">{titulo}</div>'
        f'<div class="rg-subtitle">{subtitulo}</div></div></div>'
        f'<div class="rg-banner-r">{chips}</div></div>'
    )


def html_kpis_tab(items):
    """Tarjetas KPI. items: (etiqueta, icono, color, valor, detalle, porcentaje 0-100 o None)."""
    celdas = ""
    for et, ic, ac, val, det, pct in items:
        barra = (
            f'<div class="rg-kpi-bar"><span style="width:{max(0.0, min(100.0, float(pct))):.1f}%"></span></div>'
            if pct is not None else ""
        )
        celdas += (
            f'<div class="rg-kpi" style="--ac:{ac}">'
            f'<div class="rg-kpi-top"><span class="rg-kpi-lbl">{et}</span><span class="rg-kpi-ico">{ic}</span></div>'
            f'<div class="rg-kpi-val">{val}</div><div class="rg-kpi-sub">{det}</div>{barra}</div>'
        )
    return f'<div class="rg-kpis c{len(items)}">{celdas}</div>'


def _moneda(valor):
    """$12,345 para importes pequeños; $1.25 M para millones."""
    valor = float(valor or 0)
    return f"${valor / 1e6:,.2f} M" if abs(valor) >= 1e6 else f"${valor:,.0f}"


def _pct(parte, total):
    return (float(parte) / float(total) * 100.0) if total else 0.0


def siguiente_id(lista, prefijo):
    """Siguiente ID libre con el formato PREFIJO-####."""
    nums = []
    for x in lista:
        m = re.search(r"(\d+)$", str(x.get("id", "")))
        if m:
            nums.append(int(m.group(1)))
    return f"{prefijo}-{(max(nums) if nums else 1000) + 1}"


# ---------------- Personal (Coordinadores y Administración) ----------------
def barra_filtros_personal(prefijo, conteos):
    """Una sola fila: búsqueda + estado (un clic) + vista tarjetas/tabla.
    Devuelve (texto_busqueda, estado, vista, columna_para_boton_nuevo)."""
    c_bus, c_est, c_vista, c_nuevo = st.columns([3.2, 3.6, 2.2, 1.5], vertical_alignment="center")
    busqueda = c_bus.text_input(
        "Buscar", key=f"busq_{prefijo}", placeholder="🔎 Buscar por nombre, puesto, correo o ID",
        label_visibility="collapsed",
    )
    estado = c_est.segmented_control(
        "Estado", ["Todos", *ESTADOS_PERSONAL], default="Todos", key=f"estado_{prefijo}",
        format_func=lambda e: f"{e} ({conteos.get(e, 0)})", label_visibility="collapsed",
    ) or "Todos"
    vista = c_vista.segmented_control(
        "Vista", ["🗂️ Tarjetas", "📋 Tabla"], default="🗂️ Tarjetas", key=f"vista_{prefijo}",
        label_visibility="collapsed",
    ) or "🗂️ Tarjetas"
    return busqueda.strip().lower(), estado, vista, c_nuevo


def conteo_estados(lista):
    return {"Todos": len(lista), **{e: sum(1 for p in lista if p["estado"] == e) for e in ESTADOS_PERSONAL}}


def filtrar_personal(lista, busqueda, estado):
    def coincide(p):
        texto = " ".join(
            str(p.get(k, "")) for k in ("nombre", "id", "puesto", "email", "departamento", "ubicacion")
        ).lower()
        return busqueda in texto
    return [p for p in lista if coincide(p) and (estado == "Todos" or p["estado"] == estado)]


def selector_grupo(prefijo, grupos, iconos, lista_filtrada):
    """Selector de zona/área con contador por opción. Devuelve 'Todas' o el grupo elegido."""
    conteo = {g: sum(1 for p in lista_filtrada if p["departamento"] == g) for g in grupos}
    return st.pills(
        "Grupo", ["Todas", *grupos], default="Todas", key=f"grupo_{prefijo}", label_visibility="collapsed",
        format_func=lambda g: f"{iconos.get(g, '📁')} {g} ({len(lista_filtrada) if g == 'Todas' else conteo[g]})",
    ) or "Todas"


def tabla_personal(lista, nombre_archivo, etiqueta_grupo, extras=None):
    """Vista de tabla ordenable con descarga a CSV."""
    if not lista:
        st.markdown('<div class="tb-vacio">Sin resultados con la búsqueda y el estado elegidos.</div>', unsafe_allow_html=True)
        return
    filas = []
    for p in lista:
        fila = {
            "ID": p["id"], "Nombre": p["nombre"], "Puesto": p["puesto"], etiqueta_grupo: p["departamento"],
            "Estado": p["estado"], "Correo": p["email"], "Teléfono": p["telefono"], "Ubicación": p["ubicacion"],
        }
        if extras:
            fila.update(extras(p))
        filas.append(fila)
    tabla = pd.DataFrame(filas)
    st.dataframe(tabla, width="stretch", hide_index=True, height=min(640, 60 + 36 * len(tabla)))
    st.download_button(
        "⬇️ Descargar tabla (CSV)", data=tabla.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{nombre_archivo}.csv", mime="text/csv", key=f"csv_{nombre_archivo}",
    )


# ---------------- Tableros editables (Seguimiento de facturación y Acuerdos) ----------------
# Cada tablero guarda su tabla en st.session_state (se conserva mientras dure la sesión;
# se puede descargar/importar en Excel). Para persistirla de forma permanente se puede
# reemplazar _cargar_tabla/_guardar_tabla por lecturas y escrituras a Google Sheets.
TABLEROS = {}


def _tabla_vacia(campos):
    series = {}
    for c in campos:
        if c["t"] == "numero":
            series[c["n"]] = pd.Series(dtype="float64")
        elif c["t"] == "fecha":
            series[c["n"]] = pd.Series(dtype="datetime64[ns]")
        else:
            series[c["n"]] = pd.Series(dtype="object")
    return pd.DataFrame(series)


def _normalizar_tabla(d, campos):
    """Mismo tipo y formato en todas partes: evita falsos 'cambios' al comparar."""
    d = d.copy()
    for c in campos:
        n = c["n"]
        if n not in d.columns:
            d[n] = None
        if c["t"] == "numero":
            d[n] = pd.to_numeric(d[n], errors="coerce").astype("float64")
        elif c["t"] == "fecha":
            d[n] = pd.to_datetime(d[n], errors="coerce")
        else:
            d[n] = d[n].fillna("").astype(str)
    return d[[c["n"] for c in campos]]


def _cargar_tabla(clave):
    k = f"tab_{clave}"
    if k not in st.session_state:
        st.session_state[k] = _tabla_vacia(TABLEROS[clave]["campos"])
        st.session_state[f"{k}_ver"] = 0
        st.session_state[f"{k}_sig"] = 1
    return st.session_state[k]


def _guardar_tabla(clave, nueva):
    k = f"tab_{clave}"
    st.session_state[k] = _normalizar_tabla(nueva, TABLEROS[clave]["campos"])
    st.session_state[f"{k}_ver"] += 1


def _agregar_filas(clave, filas):
    """Agrega una lista de dicts a la tabla del tablero."""
    campos = TABLEROS[clave]["campos"]
    k = f"tab_{clave}"
    maestra = _cargar_tabla(clave)
    base = st.session_state[f"{k}_sig"]
    nuevas = _normalizar_tabla(pd.DataFrame(filas, index=range(base, base + len(filas))), campos)
    st.session_state[f"{k}_sig"] = base + len(filas)
    _guardar_tabla(clave, pd.concat([maestra, nuevas]) if len(maestra) else nuevas)


def _config_columnas(campos):
    cfg = {}
    for c in campos:
        n, t = c["n"], c["t"]
        if t == "numero":
            cfg[n] = st.column_config.NumberColumn(n, min_value=0.0, format=c.get("fmt", "%.2f"))
        elif t == "fecha":
            cfg[n] = st.column_config.DateColumn(n, format="DD/MM/YYYY")
        elif t == "opcion":
            cfg[n] = st.column_config.SelectboxColumn(n, options=c["op"], required=True)
        elif t == "link":
            cfg[n] = st.column_config.LinkColumn(n)
        else:
            cfg[n] = st.column_config.TextColumn(n, required=bool(c.get("req")))
    return cfg


def _a_excel(d, campos):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        _normalizar_tabla(d, campos).to_excel(w, index=False, sheet_name="Datos")
    return buf.getvalue()


@st.dialog("➕ Agregar registro")
def dialogo_nuevo_registro(clave):
    cfg = TABLEROS[clave]
    with st.form(f"form_nuevo_{clave}", clear_on_submit=True):
        valores = {}
        cols = st.columns(2)
        for i, c in enumerate(cfg["campos"]):
            n, t = c["n"], c["t"]
            etiqueta = n + (" *" if c.get("req") else "")
            with cols[i % 2]:
                if t == "numero":
                    valores[n] = st.number_input(etiqueta, min_value=0.0, step=100.0, format="%.2f")
                elif t == "fecha":
                    valores[n] = st.date_input(etiqueta, value=None, format="DD/MM/YYYY")
                elif t == "opcion":
                    valores[n] = st.selectbox(etiqueta, c["op"])
                else:
                    valores[n] = st.text_input(etiqueta)
        if st.form_submit_button("💾 Guardar", type="primary", width="stretch"):
            faltan = [c["n"] for c in cfg["campos"] if c.get("req") and not str(valores[c["n"]]).strip()]
            if faltan:
                st.error("Completa los campos obligatorios (*): " + ", ".join(faltan))
            else:
                _agregar_filas(clave, [valores])
                st.toast("Registro agregado.")
                st.rerun()


def tablero_registros(clave):
    """Tablero completo: KPIs, gráficas, búsqueda + filtro de estatus en una fila,
    tabla editable (editar celdas, marcar y eliminar) e importar/exportar Excel."""
    cfg = TABLEROS[clave]
    campos, col_est = cfg["campos"], cfg["col_estatus"]
    k = f"tab_{clave}"
    maestra = _cargar_tabla(clave)
    version = st.session_state[f"{k}_ver"]

    st.markdown(html_kpis_tab(cfg["kpis"](maestra)), unsafe_allow_html=True)
    if len(maestra):
        cfg["visual"](maestra)

    # ---- Barra única: búsqueda · estatus · agregar · importar/exportar ----
    extras = cfg.get("extras", {})
    opciones = ["Todos", *cfg["estatus"], *extras.keys()]
    conteo = {"Todos": len(maestra)}
    for e in cfg["estatus"]:
        conteo[e] = int((maestra[col_est] == e).sum()) if len(maestra) else 0
    for e, f in extras.items():
        conteo[e] = int(f(maestra).sum()) if len(maestra) else 0

    c_bus, c_est, c_add, c_io = st.columns([3, 5.2, 1.4, 1.6], vertical_alignment="center")
    busqueda = c_bus.text_input(
        "Buscar", key=f"busq_{clave}", placeholder="🔎 Buscar en toda la tabla", label_visibility="collapsed"
    ).strip().lower()
    filtro = c_est.pills(
        "Estatus", opciones, default="Todos", key=f"filtro_{clave}", label_visibility="collapsed",
        format_func=lambda e: f"{e} ({conteo.get(e, 0)})",
    ) or "Todos"
    with c_add:
        if st.button("➕ Agregar", key=f"btn_add_{clave}", type="primary", width="stretch"):
            dialogo_nuevo_registro(clave)
    with c_io:
        with st.popover("⇅ Excel", width="stretch"):
            st.download_button(
                "⬇️ Descargar Excel", data=_a_excel(maestra, campos), file_name=f"{clave}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_{clave}", width="stretch",
            )
            st.caption("Para importar, el archivo debe tener estas columnas: " + ", ".join(c["n"] for c in campos))
            archivo = st.file_uploader("Importar Excel o CSV", type=["xlsx", "csv"], key=f"up_{clave}_{version}")
            if archivo is not None:
                try:
                    nuevo = pd.read_csv(archivo) if archivo.name.lower().endswith(".csv") else pd.read_excel(archivo)
                    comunes = [c["n"] for c in campos if c["n"] in nuevo.columns]
                    if not comunes:
                        st.error("El archivo no tiene ninguna de las columnas esperadas.")
                    else:
                        st.success(f"{len(nuevo)} fila(s) listas para agregar.")
                        if st.button("✅ Agregar filas importadas", key=f"imp_{clave}_{version}", width="stretch"):
                            _agregar_filas(clave, nuevo[comunes].to_dict("records"))
                            st.rerun()
                except Exception as e:
                    st.error(f"No se pudo leer el archivo: {e}")

    vista = maestra
    if len(vista):
        if filtro in extras:
            vista = vista[extras[filtro](vista)]
        elif filtro != "Todos":
            vista = vista[vista[col_est] == filtro]
        if busqueda:
            texto = vista[[c["n"] for c in campos if c["t"] in ("texto", "opcion", "link")]].astype(str).fillna("").agg(" ".join, axis=1).str.lower()
            vista = vista[texto.str.contains(re.escape(busqueda), regex=True, na=False)]

    if not len(maestra):
        st.markdown(f'<div class="tb-vacio">{cfg["vacio"]}</div>', unsafe_allow_html=True)
        return
    st.markdown(f'<div class="tb-resumen">Mostrando <b>{len(vista)}</b> de <b>{len(maestra)}</b> registros · '
                'edita las celdas directamente; los cambios se conservan durante tu sesión (descarga el Excel para respaldarlos).</div>', unsafe_allow_html=True)
    if vista.empty:
        st.markdown('<div class="tb-vacio">Ningún registro coincide con la búsqueda o el filtro.</div>', unsafe_allow_html=True)
        return

    # ---- Tabla editable. La clave cambia con filtros/versión para no arrastrar ediciones viejas ----
    firma = hashlib.md5(f"{filtro}|{busqueda}|{version}".encode("utf-8")).hexdigest()[:8]
    entrada = vista.copy()
    entrada.insert(0, "🗑️", False)
    cfg_cols = {"🗑️": st.column_config.CheckboxColumn("🗑️", help="Marca para eliminar", width="small")}
    cfg_cols.update(_config_columnas(campos))
    editada = st.data_editor(
        entrada, key=f"ed_{clave}_{firma}", num_rows="fixed", hide_index=True, width="stretch",
        height=min(560, 60 + 36 * len(entrada)), column_config=cfg_cols,
    )
    datos = _normalizar_tabla(editada.drop(columns="🗑️"), campos)
    if not datos.equals(_normalizar_tabla(vista, campos)):
        nueva = maestra.copy()
        for c in campos:
            nueva.loc[datos.index, c["n"]] = datos[c["n"]]
        _guardar_tabla(clave, nueva)
        st.rerun()

    marcadas = editada.index[editada["🗑️"].fillna(False).astype(bool)]
    if len(marcadas):
        if st.button(f"🗑️ Eliminar {len(marcadas)} registro(s) marcado(s)", key=f"del_{clave}_{firma}", type="primary"):
            _guardar_tabla(clave, maestra.drop(index=marcadas))
            st.toast("Registros eliminados.")
            st.rerun()


#===========================
#Pestaña de Contratos
#===========================
with pestana_contratos:
    

    # ==============================================================================
    # CONFIGURACIÓN DE CONEXIÓN CON GOOGLE DRIVE API
    # ==============================================================================
    # ID de la carpeta principal que deseas mostrar
    _FOLDER_URL_RAIZ = "https://drive.google.com/drive/folders/1eVDyjip3olampBF8ia_tAvCqtWkaqRLY?usp=drive_link"
    _match_folder_id = re.search(r"/folders/([a-zA-Z0-9_-]+)", _FOLDER_URL_RAIZ)
    FOLDER_ID_RAIZ = _match_folder_id.group(1) if _match_folder_id else _FOLDER_URL_RAIZ

    SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


    @st.cache_resource
    def get_drive_service():
        """Autentica y crea el cliente de la API de Google Drive, usando las
        mismas credenciales (st.secrets o archivos .json locales) que ya se
        usan para leer el Google Sheet."""
        if build is None or ServiceAccountCredentials is None:
            st.error(
                "Faltan las librerías de Google Drive/Auth (google-api-python-client, "
                "google-auth). Ejecuta: pip install google-api-python-client google-auth."
            )
            return None
        lista_info = _obtener_lista_credenciales()
        if not lista_info:
            st.error(
                "No se encontraron credenciales de Google. En Streamlit Cloud configura "
                "[gcp_service_account] en Secrets; en local coloca el archivo .json de la "
                f"cuenta de servicio en: {BASE_DIR}."
            )
            return None
        for info in lista_info:
            try:
                creds = ServiceAccountCredentials.from_service_account_info(info, scopes=SCOPES)
                return build("drive", "v3", credentials=creds)
            except Exception:
                continue
        st.error("No se pudo autenticar con Google Drive con ninguna de las credenciales encontradas.")
        return None


    def obtener_icono_y_tipo(mime_type):
        """Devuelve el tipo de icono y clase de color según el tipo MIME del archivo."""
        if "folder" in mime_type:
            return "folder", "folder"
        elif "pdf" in mime_type:
            return "picture_as_pdf", "pdf"
        elif "spreadsheet" in mime_type or "excel" in mime_type or "csv" in mime_type:
            return "table_chart", "sheet"
        elif "document" in mime_type or "word" in mime_type:
            return "description", "doc"
        elif "image" in mime_type:
            return "image", "image"
        else:
            return "insert_drive_file", "file"


    @st.cache_data(ttl=300)
    def construir_arbol_drive(parent_id, depth=0, max_depth=2):
        """Obtiene recursivamente las carpetas y archivos de Google Drive."""
        service = get_drive_service()
        if not service:
            return {"id": parent_id, "name": "Mi Unidad", "folders": [], "files": []}

        # Obtener el nombre de la carpeta actual
        folder_info = (
            service.files().get(fileId=parent_id, fields="name").execute()
        )
        folder_name = folder_info.get("name", "Mi Unidad")

        # Consultar elementos dentro del directorio actual
        query = f"'{parent_id}' in parents and trashed = false"
        results = (
            service.files()
            .list(
                q=query,
                pageSize=100,
                fields=(
                    "files(id, name, mimeType, size, modifiedTime, webViewLink,"
                    " thumbnailLink)"
                ),
            )
            .execute()
        )
        items = results.get("files", [])

        folders = []
        files = []

        for item in items:
            mime = item.get("mimeType", "")
            if mime == "application/vnd.google-apps.folder":
                # Subcarpeta: si no superamos la profundidad máxima, escaneamos subcarpetas
                if depth < max_depth:
                    subfolder_data = construir_arbol_drive(
                        item["id"], depth + 1, max_depth
                    )
                else:
                    subfolder_data = {
                        "id": item["id"],
                        "name": item["name"],
                        "folders": [],
                        "files": [],
                    }
                folders.append(subfolder_data)
            else:
                # Archivo
                icon, file_type = obtener_icono_y_tipo(mime)
                size_bytes = int(item.get("size", 0))
                size_mb = (
                    f"{size_bytes / (1024*1024):.1f} MB"
                    if size_bytes > 0
                    else "Google Doc"
                )

                files.append(
                    {
                        "name": item["name"],
                        "type": file_type,
                        "icon": icon,
                        "size": size_mb,
                        "date": item.get("modifiedTime", "")[:10],
                        "url": (
                            item.get("webViewLink", "").replace(
                                "/view", "/preview"
                            )
                        ),
                        "previewImg": item.get("thumbnailLink", ""),
                    }
                )

        return {
            "id": parent_id,
            "name": folder_name,
            "folders": folders,
            "files": files,
        }


    # ==============================================================================
    # COMPONENTE INTERFAZ GRÁFICA GOOGLE DRIVE (búsqueda global, filtros por tipo, orden y vista tarjetas/lista)
    # ==============================================================================
    DRIVE_HTML = r'''<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/icon?family=Material+Icons+Outlined" rel="stylesheet">
<style>
:root{--card:#fff;--line:#e0e3e7;--soft:#f1f5fb;--txt:#1f2937;--mut:#667085;--ac:#2563eb;--acs:rgba(37,99,235,.10)}
@media (prefers-color-scheme:dark){:root{--card:#161b22;--line:#2d333b;--soft:#1c2330;--txt:#e6edf3;--mut:#9aa4b2;--ac:#60a5fa;--acs:rgba(96,165,250,.16)}}
*{box-sizing:border-box;margin:0;padding:0;font-family:'Roboto',sans-serif}
.material-icons-outlined{display:inline-block;width:1em;height:1em;overflow:hidden;white-space:nowrap;line-height:1;font-size:24px;flex:none}
body{background:transparent;color:var(--txt);padding:4px}
.wrap{background:var(--card);border:1px solid var(--line);border-radius:16px;overflow:hidden}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:12px 16px;border-bottom:1px solid var(--line)}
.search{display:flex;align-items:center;gap:8px;background:var(--soft);border:1px solid var(--line);padding:8px 14px;border-radius:24px;flex:1 1 260px;min-width:200px}
.search input{border:none;background:transparent;outline:none;width:100%;font-size:14px;color:var(--txt)}
.search .clear{cursor:pointer;color:var(--mut);display:none}
select,.seg button{font-size:13px;color:var(--txt);background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:7px 10px;cursor:pointer}
.seg{display:flex;border-radius:10px;overflow:hidden;border:1px solid var(--line)}
.seg button{border:none;border-radius:0;display:flex;align-items:center;padding:6px 9px}
.seg button.on{background:var(--ac);color:#fff}
.chips{display:flex;gap:8px;flex-wrap:wrap;padding:10px 16px 0 16px}
.chip{display:flex;align-items:center;gap:6px;font-size:12.5px;font-weight:500;padding:5px 12px;border-radius:999px;border:1px solid var(--line);background:var(--card);cursor:pointer;color:var(--txt)}
.chip b{font-weight:700;opacity:.65}
.chip.on{background:var(--ac);border-color:var(--ac);color:#fff}.chip.on b{opacity:.9}
.crumb{display:flex;align-items:center;flex-wrap:wrap;gap:4px;padding:12px 16px 4px 16px;font-size:16px;font-weight:500}
.crumb .it{cursor:pointer;border-radius:8px;padding:3px 8px}.crumb .it:hover{background:var(--soft)}
.crumb .sep{color:var(--mut);font-size:18px}
.meta{padding:0 16px 8px 16px;font-size:12px;color:var(--mut)}
.sec{padding:0 16px 14px 16px}
.sec h4{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);margin:8px 0 8px 2px;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px;margin-bottom:10px}
.folder{display:flex;align-items:center;gap:10px;padding:12px 14px;background:var(--soft);border:1px solid var(--line);border-radius:12px;cursor:pointer;transition:.15s}
.folder:hover{border-color:var(--ac);background:var(--acs)}
.folder .material-icons-outlined{color:var(--ac)}
.folder .n{font-size:14px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.folder .s{font-size:11px;color:var(--mut)}
.file{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;cursor:pointer;display:flex;flex-direction:column;transition:.15s}
.file:hover{border-color:var(--ac);box-shadow:0 4px 12px rgba(0,0,0,.10);transform:translateY(-2px)}
.pv{height:118px;background:var(--soft);display:flex;align-items:center;justify-content:center;border-bottom:1px solid var(--line)}
.pv img{width:100%;height:100%;object-fit:cover}
.fi{padding:10px 12px;display:flex;align-items:center;gap:10px}
.fi .t{font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fi .m{font-size:11px;color:var(--mut);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fi>div{min-width:0}
.ic.pdf{color:#ea4335}.ic.doc{color:#4285f4}.ic.sheet{color:#0f9d58}.ic.image{color:#a855f7}.ic.file{color:var(--mut)}
.list{display:flex;flex-direction:column;border:1px solid var(--line);border-radius:12px;overflow:hidden}
.row{display:grid;grid-template-columns:30px 1fr 110px 90px;gap:10px;align-items:center;padding:9px 14px;cursor:pointer;border-bottom:1px solid var(--line);font-size:13px}
.row:last-child{border-bottom:none}.row:hover{background:var(--acs)}
.row .n{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:500}
.row .p{font-size:11px;color:var(--mut);font-weight:400}
.row .c{color:var(--mut);font-size:12px}
.empty{text-align:center;color:var(--mut);padding:36px 12px;font-size:14px}
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:1000;align-items:center;justify-content:center}
.mc{background:var(--card);border-radius:12px;width:88%;max-width:960px;height:88%;display:flex;flex-direction:column;overflow:hidden}
.mh{padding:10px 18px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);gap:10px}
.mh a{color:var(--ac);font-size:13px;text-decoration:none;display:flex;align-items:center;gap:4px;white-space:nowrap}
.mb{flex:1;background:var(--soft)}.mb iframe{width:100%;height:100%;border:none}
@media (max-width:640px){.row{grid-template-columns:30px 1fr 80px}.row .c.d{display:none}}
</style></head><body>
<div class="wrap">
  <div class="bar">
    <div class="search"><span class="material-icons-outlined">search</span>
      <input id="q" type="text" placeholder="Buscar en todo el Drive (carpetas y archivos)">
      <span class="material-icons-outlined clear" id="clr">close</span></div>
    <select id="ord" title="Ordenar">
      <option value="name">Nombre A–Z</option><option value="namez">Nombre Z–A</option>
      <option value="new">Más recientes</option><option value="old">Más antiguos</option>
    </select>
    <div class="seg"><button id="vg" class="on" title="Tarjetas"><span class="material-icons-outlined">grid_view</span></button>
      <button id="vl" title="Lista"><span class="material-icons-outlined">view_list</span></button></div>
  </div>
  <div class="chips" id="chips"></div>
  <div class="crumb" id="crumb"></div>
  <div class="meta" id="meta"></div>
  <div class="sec" id="body"></div>
</div>
<div class="modal" id="modal"><div class="mc">
  <div class="mh"><b id="mt" style="font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></b>
    <span style="display:flex;gap:14px;align-items:center"><a id="mopen" target="_blank" rel="noopener"><span class="material-icons-outlined" style="font-size:18px">open_in_new</span>Abrir en Drive</a>
    <span class="material-icons-outlined" style="cursor:pointer" id="mx">close</span></span></div>
  <div class="mb" id="mbody"></div></div></div>
<script>
const root = __DATA__;
const S = {path:[root], q:"", tipo:"all", orden:"name", vista:"grid"};
const TIPOS = {all:"Todos", pdf:"PDF", doc:"Documentos", sheet:"Hojas", image:"Imágenes", file:"Otros"};
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const cur = () => S.path[S.path.length-1];
function walk(node, nodes, out){
  (node.folders||[]).forEach(f => { out.folders.push({node:f, nodes:nodes}); walk(f, nodes.concat([f]), out); });
  (node.files||[]).forEach(f => out.files.push({file:f, nodes:nodes}));
}
function scope(){
  const q = S.q.trim().toLowerCase();
  if(!q){
    const base = S.path.slice(1), c = cur();
    return {folders:(c.folders||[]).map(f=>({node:f,nodes:base})), files:(c.files||[]).map(f=>({file:f,nodes:base})), busq:false};
  }
  const all = {folders:[], files:[]}; walk(root, [], all);
  return {folders: all.folders.filter(x=>x.node.name.toLowerCase().includes(q)),
          files: all.files.filter(x=>x.file.name.toLowerCase().includes(q)), busq:true};
}
function sorter(a, b){
  const na = (a.node||a.file).name, nb = (b.node||b.file).name;
  const da = a.file ? (a.file.date||"") : "", db = b.file ? (b.file.date||"") : "";
  if(S.orden==="namez") return nb.localeCompare(na,"es");
  if(S.orden==="new" && a.file && b.file) return db.localeCompare(da);
  if(S.orden==="old" && a.file && b.file) return da.localeCompare(db);
  return na.localeCompare(nb,"es");
}
function render(){
  const sc = scope();
  const cnt = {all:sc.files.length, pdf:0, doc:0, sheet:0, image:0, file:0};
  sc.files.forEach(x => cnt[x.file.type] = (cnt[x.file.type]||0)+1);
  $("chips").innerHTML = Object.keys(TIPOS).filter(k => k==="all" || cnt[k]>0).map(k =>
    `<div class="chip ${S.tipo===k?'on':''}" data-t="${k}">${TIPOS[k]} <b>${cnt[k]}</b></div>`).join("");
  document.querySelectorAll(".chip").forEach(el => el.onclick = () => { S.tipo = el.dataset.t; render(); });
  const files = sc.files.filter(x => S.tipo==="all" || x.file.type===S.tipo).sort(sorter);
  const folders = (S.tipo==="all" ? sc.folders : []).slice().sort(sorter);

  if(sc.busq){
    $("crumb").innerHTML = `<span class="material-icons-outlined">search</span>&nbsp;Resultados para “${esc(S.q)}”`;
  } else {
    $("crumb").innerHTML = S.path.map((f,i) => `<span class="it" data-i="${i}">${esc(f.name)}</span>` +
      (i<S.path.length-1 ? '<span class="material-icons-outlined sep">chevron_right</span>' : '')).join("");
    document.querySelectorAll(".crumb .it").forEach(el => el.onclick = () => { S.path = S.path.slice(0, +el.dataset.i+1); render(); });
  }
  $("meta").textContent = `${folders.length} carpeta(s) · ${files.length} archivo(s)` + (sc.busq ? " · en todo el Drive" : "");

  let h = "";
  if(folders.length){
    h += `<h4>Carpetas</h4><div class="grid">` + folders.map((x,i) => {
      const n = (x.node.folders||[]).length, a = (x.node.files||[]).length;
      const ruta = sc.busq && x.nodes.length ? x.nodes.map(p=>esc(p.name)).join(" / ") + " · " : "";
      return `<div class="folder" data-f="${i}"><span class="material-icons-outlined">folder</span><div style="min-width:0"><div class="n">${esc(x.node.name)}</div><div class="s">${ruta}${n} carpetas · ${a} archivos</div></div></div>`;
    }).join("") + `</div>`;
  }
  if(files.length){
    h += `<h4>Archivos</h4>`;
    if(S.vista==="grid"){
      h += `<div class="grid">` + files.map((x,i) => {
        const f = x.file;
        const pv = f.previewImg ? `<img src="${esc(f.previewImg)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
          : `<span class="material-icons-outlined ic ${esc(f.type)}" style="font-size:46px">${esc(f.icon)}</span>`;
        const ruta = sc.busq && x.nodes.length ? x.nodes.map(p=>esc(p.name)).join(" / ") + " · " : "";
        return `<div class="file" data-a="${i}"><div class="pv">${pv}</div><div class="fi"><span class="material-icons-outlined ic ${esc(f.type)}">${esc(f.icon)}</span><div><div class="t" title="${esc(f.name)}">${esc(f.name)}</div><div class="m">${ruta}${esc(f.size)} · ${esc(f.date)}</div></div></div></div>`;
      }).join("") + `</div>`;
    } else {
      h += `<div class="list">` + files.map((x,i) => {
        const f = x.file;
        const ruta = sc.busq && x.nodes.length ? `<div class="p">${x.nodes.map(p=>esc(p.name)).join(" / ")}</div>` : "";
        return `<div class="row" data-a="${i}"><span class="material-icons-outlined ic ${esc(f.type)}">${esc(f.icon)}</span><div style="min-width:0"><div class="n" title="${esc(f.name)}">${esc(f.name)}</div>${ruta}</div><span class="c d">${esc(f.date)}</span><span class="c">${esc(f.size)}</span></div>`;
      }).join("") + `</div>`;
    }
  }
  if(!folders.length && !files.length) h = `<div class="empty">${sc.busq ? "Sin resultados para esa búsqueda." : "Esta carpeta está vacía."}</div>`;
  $("body").innerHTML = h;
  document.querySelectorAll("[data-f]").forEach(el => el.onclick = () => {
    const x = folders[+el.dataset.f];
    S.path = [root].concat(x.nodes, [x.node]); S.q = ""; $("q").value = ""; $("clr").style.display = "none"; S.tipo = "all"; render();
  });
  document.querySelectorAll("[data-a]").forEach(el => el.onclick = () => openFile(files[+el.dataset.a].file));
}
function openFile(f){
  $("mt").textContent = f.name;
  $("mopen").href = (f.url||"#").replace("/preview", "/view");
  $("mbody").innerHTML = f.url ? `<iframe src="${esc(f.url)}" allow="autoplay"></iframe>` : `<div class="empty">No hay previsualización disponible.</div>`;
  $("modal").style.display = "flex";
}
function closeModal(){ $("modal").style.display = "none"; $("mbody").innerHTML = ""; }
$("mx").onclick = closeModal;
$("modal").onclick = e => { if(e.target.id==="modal") closeModal(); };
document.addEventListener("keydown", e => { if(e.key==="Escape") closeModal(); });
$("q").oninput = e => { S.q = e.target.value; $("clr").style.display = S.q ? "block" : "none"; render(); };
$("clr").onclick = () => { S.q = ""; $("q").value = ""; $("clr").style.display = "none"; render(); };
$("ord").onchange = e => { S.orden = e.target.value; render(); };
$("vg").onclick = () => { S.vista = "grid"; $("vg").className = "on"; $("vl").className = ""; render(); };
$("vl").onclick = () => { S.vista = "list"; $("vl").className = "on"; $("vg").className = ""; render(); };
render();
function ajustarAlto(){ try { const f = window.frameElement; if (f) f.style.height = Math.max(520, window.parent.innerHeight - 250) + 'px'; } catch (e) {} }
ajustarAlto(); window.addEventListener('resize', ajustarAlto);
</script></body></html>'''


    def render_drive_explorer(drive_json_data):
        datos_js = json.dumps(drive_json_data, ensure_ascii=False).replace("</", "<\\/")
        components.html(DRIVE_HTML.replace("__DATA__", datos_js), height=760, scrolling=True)


    def _resumen_arbol(nodo, acc=None):
        """Cuenta carpetas, archivos por tipo y la fecha más reciente de todo el árbol."""
        if acc is None:
            acc = {"carpetas": 0, "archivos": 0, "pdf": 0, "sheet": 0, "doc": 0, "ultima": ""}
        for f in nodo.get("files", []):
            acc["archivos"] += 1
            if f.get("type") in acc:
                acc[f["type"]] += 1
            acc["ultima"] = max(acc["ultima"], f.get("date", "") or "")
        for sub in nodo.get("folders", []):
            acc["carpetas"] += 1
            _resumen_arbol(sub, acc)
        return acc


    def _refrescar_drive():
        construir_arbol_drive.clear()
        st.session_state["drive_hora"] = _ahora().strftime("%H:%M:%S")


    # ==============================================================================
    # EJECUCIÓN PRINCIPAL DE LA PESTAÑA
    # ==============================================================================
    if "drive_hora" not in st.session_state:
        st.session_state["drive_hora"] = _ahora().strftime("%H:%M:%S")

    with st.spinner("Cargando estructura de Google Drive..."):
        datos_drive = construir_arbol_drive(FOLDER_ID_RAIZ)

    _r = _resumen_arbol(datos_drive)
    _ultima = "—"
    if _r["ultima"]:
        try:
            _ultima = datetime.strptime(_r["ultima"], "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            _ultima = _r["ultima"]

    st.markdown(
        html_banner_tab(
            "📁", "Contratos", f"Expediente digital · {datos_drive.get('name', 'Google Drive')}",
            pills=["🔒 Solo lectura", f"🔄 Leído a las {st.session_state['drive_hora']}"],
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        html_kpis_tab([
            ("Carpetas", "📂", "#2563eb", f"{_r['carpetas']}", "en el expediente", None),
            ("Archivos", "🗄️", "#0d9488", f"{_r['archivos']}", "documentos totales", None),
            ("PDF", "📕", "#ef4444", f"{_r['pdf']}", f"{_pct(_r['pdf'], _r['archivos']):.0f}% de los archivos", _pct(_r["pdf"], _r["archivos"])),
            ("Hojas de cálculo", "📊", "#16a34a", f"{_r['sheet']}", f"{_pct(_r['sheet'], _r['archivos']):.0f}% de los archivos", _pct(_r["sheet"], _r["archivos"])),
            ("Última modificación", "🕒", "#f59e0b", _ultima, "archivo más reciente", None),
        ]),
        unsafe_allow_html=True,
    )
    _c_info, _c_btn = st.columns([6, 1.3], vertical_alignment="center")
    _c_info.caption("Busca en todo el Drive, filtra por tipo, ordena y cambia entre tarjetas y lista. Clic en un archivo para previsualizarlo.")
    _c_btn.button("🔄 Actualizar Drive", key="btn_actualizar_drive", width="stretch", on_click=_refrescar_drive)

    if not datos_drive.get("folders") and not datos_drive.get("files"):
        st.markdown('<div class="tb-vacio">No se pudo leer contenido de Google Drive (revisa las credenciales o los permisos de la carpeta).</div>', unsafe_allow_html=True)
    else:
        render_drive_explorer(datos_drive)










#==========================
#Pestaña de Coordinadores
#==========================
with pestana_coordinadores:
    st.markdown(
        """
        <style>
            .status-badge {
                display: inline-block; padding: 4px 10px; border-radius: 12px;
                font-size: 0.78rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;
            }
            .badge-activo { background-color: #dcfce7; color: #166534; border: 1px solid #86efac; }
            .badge-inactivo { background-color: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
            .badge-pendiente { background-color: #fef3c7; color: #92400e; border: 1px solid #fcd34d; }
            .id-tag {
                font-family: 'Courier New', Courier, monospace; background-color: #f1f5f9;
                padding: 3px 8px; border-radius: 6px; color: #334155; font-weight: bold;
                font-size: 0.85rem; border: 1px solid #cbd5e1;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if "usuarios" not in st.session_state:
        st.session_state.usuarios = [
            {
                "id": "USR-1001", "nombre": "Nora Garcia Alarcon", "puesto": "Gerente CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/tPYFnBdV/Nora-Garcia.jpg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 12345678",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 2 (Gerente)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-100", "nombre": "Maria Jose Diaz", "puesto": "Auxiliar Administrativo",
                "departamento": "CDMX", "estado": "Inactivo",
                "foto": "https://i.ibb.co/svsQztPw/Maria-Jose-Diaz.jpg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 30682627",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Auxiliar Admvo.)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-100", "nombre": "Renata Espitia", "puesto": "Auxiliar Administrativo",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/tTsYCZxF/Renata-Espitia.jpg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 30573454",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Auxiliar Admvo.)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-100", "nombre": "Monica Neira", "puesto": "Auxiliar Administrativo",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/CKf8sHyZ/Monica-Neira.jpg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 14761951",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Auxiliar Admvo.)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1002", "nombre": "Alberto Torres Gutierrez", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/tw1ThgDY/Alberto-Torres.jpg",
                "email": "alberto.at840@gmail.com", "telefono": "(+52) 55 31119554",
                "fecha_ingreso": "01-Febrero-2021", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 28 Unidades () ", "Central del Sur : 1 Unidades (Tlalpan)"],
                "habilidades": ["Docker", "Python", "Terraform"],
            },
            {
                "id": "USR-1003", "nombre": "Alejandro Gomez", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/kVK4NDq0/Alejandro-Gomez.jpg",
                "email": "pako.gomez.p@gmail.com", "telefono": "(+52) 5535377489",
                "fecha_ingreso": "10-Agosto-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 13 Unidades ()", "Secretaria de las Mujeres : 2 Unidades (Milpa Alta)"],
                "habilidades": ["Figma", "User Research", "Prototipado"],
            },
            {
                "id": "USR-1004", "nombre": "Amairani Ramirez", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/WpgPY1gc/Amairani-Ramirez.jpg",
                "email": "ramireztorresamairani@gmail.com", "telefono": "(+52) 5521756716",
                "fecha_ingreso": "01-Julio-2025", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["ATRAPI : 2 Unidades (Coyoacan)", "IMSS-Bienestar CDMX : 32 Unidades ()", "SPOTMET : 3 Unidades (Benito Juarez, Azcapozalco, Iztacalco)"],
                "habilidades": ["Penetration Testing", "SIEM", "Criptografía"],
            },
            {
                "id": "USR-1005", "nombre": "Anayeli Lazaro", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/LXBqW57d/Anayeli-Lazaro.jpg",
                "email": "coordinador.acl25@gmail.com", "telefono": "(+52) 5539982055",
                "fecha_ingreso": "15-Marzo-2023", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": [
                    "FINABIEN : 1 Unidad (Sonora)", "IMSS-Bienestar CDMX : 11 Unidades ()",
                    "IPN : 2 Unidades (Iztapalapa)", "PROFECO : 1 Unidad (EDO. MEX : Nezahualcoyotl)",
                    "Secretaria de las Mujeres : 21 Unidades (Coyoacan, Iztapalapa, Tlalpan, Benito Juarez, Albaro Obregon, Cuajimalpa, Iztacalco, Magdalena Contreras, Miguel Hidalgo, Venustiano Carranza)",
                ],
                "habilidades": ["Gestión de Proyectos", "Comunicación Efectiva", "Liderazgo"],
            },
            {
                "id": "USR-1006", "nombre": "Armado Medina", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/QFnsMkJb/Armando-Medina.jpg",
                "email": "medina.971@outlook.com ", "telefono": "(+52) 5531042782",
                "fecha_ingreso": "20-Enero-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 20 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1007", "nombre": "Eduardo Valerdi", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/NggXvLZ9/Eduardo-Valerdi.jpg",
                "email": "coordinador.evr@gmail.com ", "telefono": "(+52) 5531037543",
                "fecha_ingreso": "15-Febrero-2023", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": [
                    "IPN : 6 Unidades (Gustavo A. Madero)", "ISSTE : 19 Unidades (Hidalgo)",
                    "Salud Federal : 1 Unidad (Miguel Hidalgo)", "Secretaria de las Mujeres : 2 Unidades (Gustavo A. Madero)",
                ],
                "habilidades": ["Gestión de Proyectos", "Comunicación Efectiva", "Liderazgo"],
            },
            {
                "id": "USR-1008", "nombre": "Enrique Gonzalez", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/ZRB3NRYQ/Enrique-Gonzalez.png",
                "email": "enriquegonzalezg1963@gmail.com", "telefono": "(+52) 5531411830",
                "fecha_ingreso": "10-Marzo-2023", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 18 Unidades ()", "Secretaria de las Mujeres : 3 Unidades (Tlahuac, Xochimilco)"],
                "habilidades": ["Gestión de Proyectos", "Comunicación Efectiva", "Liderazgo"],
            },
            {
                "id": "USR-1009", "nombre": "Erika Cristan", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/nMqWNntZ/Erika-Cristan.jpg",
                "email": "ceakire@gmail.com", "telefono": "(+52) 5534988267",
                "fecha_ingreso": "20-Enero-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinadora)",
                "proyectos": ["IMSS-Bienestar CDMX : 20 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1010", "nombre": "Fernando Dali", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": " ",
                "email": "Sin correo ", "telefono": "(+52) Sin numero",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IPN : 5 Unidades (Gustavo A. Madero, Miguel Hidalgo)"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1011", "nombre": "Fernando Valerdi", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/7JQnT1Ww/Fernando-Valerdi.jpg",
                "email": "fernando.valerdi.rebollo@gmail.com", "telefono": "(+52) 5530830567",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 10 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1012", "nombre": "Francisco Garcia", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/3yLb4Gpq/Francisco-Garcia.jpg",
                "email": "franciscogarcia2101@hotmail.com", "telefono": "(+52) 5530847440",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": [
                    "IPN : 22 Unidades ()", "ISSTE : 11 Unidades ()",
                    "PROFECO : 1 Unidad (Tlalnepantla)", "Salud Federal : 4 Unidades (Cuauhtemoc)",
                ],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1013", "nombre": "Gloria Hernandez", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/mCnRvJRZ/Gloria-Hernandez.jpg",
                "email": "gloriacoordi.08@gmail.com", "telefono": "(+52) 5531065274",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMMS-Bienestar CDMX : 30 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1014", "nombre": "Guadalupe Barbosa", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/hxg8mYYJ/Guadalupe-Barbosa.jpg",
                "email": "g.barbosa.a1212@gmail.com", "telefono": "(+52) 5554985160",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": [
                    "IPN : 2 Unidades (Xochimilco, Iztacalco)", "SRE : 8 Unidades (Cuahutemoc, Venustiano Crarranza)",
                    "Salud Federal : 6 Unidades ()", "IPN :1 Unidad (MIguel Hidalgo)", "METROBUS : 2 Unidades ()",
                ],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1015", "nombre": "Jhon Ramos", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/MxwcHpDM/Jhon-Ramos.jpg",
                "email": "jhon.coordinacion32@gmail.com", "telefono": "(+52) 5521756502",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": [
                    "IPN : 20 Unidades ()", "ISSTE : 1 Unidad ()", "METROBUS : 3 Unidades ()",
                    "Secretaria de las MUjeres : 2 Unidades ()",
                ],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1016", "nombre": "Jose Luis Ruiz", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/7dR1WzZt/Jose-Luis-Ruiz.jpg",
                "email": "munejl14@hotmail.com ", "telefono": "(+52) 5527117537",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 12 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1017", "nombre": "Juan Pablo Cruz", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/hFms0zDF/Juan-Pablo-Cruz.jpg",
                "email": "so.ni1110@hotmail.com", "telefono": "(+52) 5521756417",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["FINABIEN : 2 Unidades ()", "IMSS-Bienestar CDMX : 24 Unidades ()", "ISSSTE : 11 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1018", "nombre": "Julio Barrientos", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/XZjHWzPd/Julio-Cesar-Barrientos.jpg",
                "email": "julibarri589@gmail.com", "telefono": "(+52) 5521529515",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 19 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1019", "nombre": "Manuel Hernandez", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/wFnPT8fL/Manuel-Hernandez.jpg",
                "email": "mhernandez.p@youhoo.com", "telefono": "(+52) 5510589560",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 11 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1020", "nombre": "Maria Almanza", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/BHKbyrC9/Maria-Almanza.jpg",
                "email": "almanza93marii@gmail.com", "telefono": "(+52) 5530591633",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 1 Unidades ()", "ISSSTE : 9 Unidades ()", "PLAZA ARTZ : 1 Unidad ()", "PROFECO : 8 Unidades ()", "Salud Federal : 6 Unidades ()", "SHCP : 8 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1021", "nombre": "Marisol Meraz", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/cHgcTmh/Marisol-Meraz.jpg",
                "email": "marimerlop8560@gmail.com", "telefono": "(+52) 5551956442",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 17 Unidades ()", "Salud Federal : 4 Unidades ()", "SEBIEN : 18 Unidades ()", "SEGIAGUA :  31 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1022", "nombre": "Michelle Carlon", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/JwNJJ0PM/Michelle-Carlon.jpg",
                "email": "Sin datos", "telefono": "(+52) sin datos",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IPN : # Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1023", "nombre": "Oscar Lavadores", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/SkMtYGJ/Oscar-Lavadores.jpg",
                "email": "oscarlpineda0123@gmail.com", "telefono": "(+52) 5531337212",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 11 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1024", "nombre": "Roberto Reyes", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/JWy1Lz7p/Roberto-Reyes.jpg",
                "email": "reyesz.robertojavier@gmail.com", "telefono": "(+52) 5526922378",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["ISSSTE : 21 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1025", "nombre": "Victor Munguia", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/nMP1x8Fg/Victor-Munguia.jpg",
                "email": "brian_jes@hotmail.com", "telefono": "(+52) 5522404313",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 9 Unidades ()", "METROBUS : 1 Unidad ()", "SAPCI : 21 Unidades ()", "Secretaria de las Mujeres : 2 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1026", "nombre": "Victor Uzcanga", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://i.ibb.co/DDnG1wc5/Victor-Uzcanga.jpg",
                "email": "vic.uzcanga_chavez@hotmail.com", "telefono": "(+52) 5530785781",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 22 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1101", "nombre": "Pilar Hernandez", "puesto": "Gerente de Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://i.ibb.co/8DWmywcY/Pilar-Hernandez.jpg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 72 22694403",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 2 (Gerente)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1102", "nombre": "Andrea Feliciano", "puesto": "Auxiliar Administrativo",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://i.ibb.co/4nHzKj9C/Andrea-Feliciano.jpg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 31186668",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel # (Auxiliar Admvo.)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1103", "nombre": "Alexandra Gomora", "puesto": "Auxiliar Administrativo",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://i.ibb.co/N6dBQWS6/Alexandra-Gomora.jpg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 30787614",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel # (Auxiliar Admvo.)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1104", "nombre": "Maria Eugenia Alonso", "puesto": "Auxiliar Administrativo",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://i.ibb.co/XkGs9WkW/Maria-Eugenia-Alonso.jpg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 31037494",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel # (Auxiliar Admvo.)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1105", "nombre": "Adriana Zarco", "puesto": "Coordinadora Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://i.ibb.co/BVrS913Z/Adriana-Zarco.jpg",
                "email": "---", "telefono": "(+52) 55 30476909",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["ISEM : 49 Unidades", "Poder Judicial Edo. Mex : 11 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1106", "nombre": "Alejandro Giacomo", "puesto": "Coordinador Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://i.ibb.co/cXgsRbRX/Alejandro-Giacomo.jpg",
                "email": "---", "telefono": "(+52) 55 31200565",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 64 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1107", "nombre": "Carlos Zarco", "puesto": "Coordinador Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://i.ibb.co/DfKCdBn2/Carlos-Zarco.jpg",
                "email": "---", "telefono": "(+52) 55 31217189",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 59 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1108", "nombre": "Francisco Anzaldo", "puesto": "Coordinador Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://i.ibb.co/S47wZ3jy/Francisco-Anzaldo.jpg",
                "email": "---", "telefono": "(+52) 55 31318418",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 46 Unidades", "ISSSTE : 6 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1109", "nombre": "Humbert Campuzano", "puesto": "Coordinador Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://i.ibb.co/pFv7tP9/Humbert-Campuzano.jpg",
                "email": "---", "telefono": "(+52) 55 30702088",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 47 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1110", "nombre": "Javier Salgado", "puesto": "Coordinador Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://i.ibb.co/VptV8vrc/Javier-Salgado.jpg",
                "email": "---", "telefono": "(+52) 55 31037269",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["ISEM : 38 Unidades",  "ISSSTE : 14 Unidades", "Poder Judicial Edo. Mex : 14 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1111", "nombre": "Jonathan Mercado", "puesto": "Coordinador Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://i.ibb.co/vCjPgbY9/Jonathan-Mercado.jpg",
                "email": "---", "telefono": "(+52) 55 31271396",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 53 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1112", "nombre": "Mauricio Rojas", "puesto": "Coordinador Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://i.ibb.co/sJ1WsCbf/Mauricio-Rojas.jpg",
                "email": "---", "telefono": "(+52) 55 31347301",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 56 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1113", "nombre": "Nancy Giacomo", "puesto": "Coordinadora Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://i.ibb.co/wrxhgshf/Nancy-Giacomo.jpg",
                "email": "---", "telefono": "(+52) 55 30825691",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 60 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1114", "nombre": "Ulises Mociño", "puesto": "Coordinador Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://i.ibb.co/dwC67RkY/Ulises-Muci-o.jpg",
                "email": "---", "telefono": "(+52) 55 30787679",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 49 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1115", "nombre": "-----", "puesto": "Coordinador Toluca",
                "departamento": "Toluca", "estado": "Inactivo",
                "foto": "",
                "email": "---", "telefono": "(+52) -----",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["ISEM : 36 Unidades",  "Poder Judicial Edo. Mex : 11 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1200", "nombre": "Adolfo Sanabria Jiménez", "puesto": "Gerente del Estado de México",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://i.ibb.co/zV6vJW3B/Adolfo-Sanabria.jpg",
                "email": "", "telefono": "(+52) 55 91678805",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 2 (Gerente)",
                "proyectos": ["Oficialia Mayor", "Poder Judicial"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1201", "nombre": "Miguel Alexis Martinez Martinez", "puesto": "Auxiliar Administrativo",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://i.ibb.co/cSRQh7JP/Alexis-Martinez.jpg",
                "email": "", "telefono": "(+52) 55 31057105",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Auxiliar Admvo.)",
                "proyectos": ["Oficialia Mayor", "Poder Judicial"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1202", "nombre": "José Luis Rivera", "puesto": "Auxiliar Administrativo",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://i.ibb.co/7dR1WzZt/Jose-Luis-Ruiz.jpg",
                "email": "", "telefono": "(+52) 55 31057105",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Auxiliar Admvo.)",
                "proyectos": ["Oficialia Mayor", "Poder Judicial"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1203", "nombre": "Carlos Cesar Serrano Ramirez", "puesto": "Coordinador Edo. México",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://i.ibb.co/4gpKJLvW/Cesar-Serrano.jpg",
                "email": "", "telefono": "(+52) 56 28213647",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Poder Judicial : 24 Unidades"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1204", "nombre": "Eduardo Ramírez López", "puesto": "Coordinador Edo. México",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://i.ibb.co/chY99LpL/Eduardo-Ramirez.jpg",
                "email": "", "telefono": "(+52) 56 37268956",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 47 Unidades"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1205", "nombre": "José Ascensión Arreola González", "puesto": "Coordinador Edo. México",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://i.ibb.co/k60rKFkt/Jose-Arreola.jpg",
                "email": "", "telefono": "(+52) 56 27915122",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 55 Unidades"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1206", "nombre": "María Magdalena García Cruz", "puesto": "Coordinador Edo. México",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://i.ibb.co/R4p2RZ3M/Magdalena-Garcia.jpg",
                "email": "", "telefono": "(+52) 56 17907344",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 22 Unidades"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1207", "nombre": "Mauro Araujo Gallegos", "puesto": "Coordinador Edo. México",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://i.ibb.co/3yJx0P0p/Mauro-Araujo.jpg",
                "email": "", "telefono": "(+52) 55 21969640",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 61 Unidades"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1208", "nombre": "Omar Terreros Mendoza", "puesto": "Coordinador Edo. México",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://i.ibb.co/mFNBBF2H/Omar-Terreros.jpg",
                "email": "", "telefono": "(+52) 55 71111709",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 51 Unidades"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1209", "nombre": "Samuel Rosas Canales", "puesto": "Coordinador Edo. México",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://i.ibb.co/bMDrnxT6/Samuel-Rosas.jpg",
                "email": "", "telefono": "(+52) 55 49593643",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 32 Unidades"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1300", "nombre": "Berenice Bellacetin Peña", "puesto": " Gerente de Foráneos",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://i.ibb.co/zzsNwMq/Bere-Bellacetin.jpg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 12793205",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 2 (Gerente)",
                "proyectos": ["IMSS - Bienestar Tabasco", "IMSS - Bienestar Colima", "IMSS - Bienestar Chiapas", "IMSS - Bienestar Campeche", "IMSS - Bienestar Oficinas", "Relaciones Exteriores Foraneo", "Banjercito", "Prodecon", "Infonavit Foraneo", "ISSSTE Campeche", "IPN Foraneo", "CONAFE", "ATRAPI Foraneo",
                              "PROFECO"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1301", "nombre": "Renata Peña Trejo", "puesto": "Auxiliar Administrativo",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://i.ibb.co/x8PVwdV0/Renata-Pe-a.jpg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 21400127",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Auxiliar Admvo.)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1302", "nombre": "Adan Elias Ceja", "puesto": "Coordinador Regional de Tabasco",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://i.ibb.co/PvQT72Mv/Elias-Ceja.jpg",
                "email": "---", "telefono": "(+52) 55 68180737",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Tabasco",
                "nivel_acceso": "Nivel # (Coordinador de Regional)",
                "proyectos": ["IMSS - Bienestar Tabasco"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1303", "nombre": "Luis Guerrero", "puesto": "Coordinador Regional de Puebla",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "",
                "email": "---", "telefono": "(+52) 55 ",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Puebla",
                "nivel_acceso": "Nivel # (Coordinador de Regional)",
                "proyectos": ["IMSS - Bienestar Puebla"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1304", "nombre": "Alejandra Sanchez", "puesto": "Coordinadora Tabasco",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://i.ibb.co/jvWXsqzm/ALEJANDRA-SANCHEZ.jpg",
                "email": "---", "telefono": "(+52) 55 31136817",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Tabasco",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS - Bienestar Tabasco : 117 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1305", "nombre": "Alan Reyna", "puesto": "Coordinador de Proyecto",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://i.ibb.co/RpVgvPG5/Alan-Reyna.jpg",
                "email": "---", "telefono": "(+52) 55 31058296",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador de Proyecto)",
                "proyectos": ["IMSS - Bienestar Colima : ", "IMSS - Bienestar Chiapas : 542 Unidades", "Relaciones Exteriores Foraneo : 18 Unidades", "Banjercito : 14 Unidades",
                              "PRODECON : 9 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1306", "nombre": "Arturo Sanchez Mendoza", "puesto": "Coordinador Foraneo",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://i.ibb.co/Tx7bp4vB/Arturo-Sanchez.jpg",
                "email": "---", "telefono": "(+52) 55 34882785",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Relaciones Exteriores Foraneo : 19 Unidades", "Banjercito : 23 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1307", "nombre": "Betza Gamez Hernandez", "puesto": "Coordinadora Foraneoa",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "",
                "email": "---", "telefono": "(+52) 55 31034049",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["INFONAVIT Foraneo : 31 Unidades", "Banjercito : 31 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1308", "nombre": "Daniel Mar", "puesto": "Coordinador Foraneo",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "",
                "email": "---", "telefono": "(+52) 55 69319319",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Banjercito : 8 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1309", "nombre": "Emiliano Mendez", "puesto": "Coordinador Tabasco",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://i.ibb.co/1tn7gXDW/EMILIANO-MENDEZ.jpg",
                "email": "---", "telefono": "(+52) 55 30787804",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Tabasco",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS - Bienestar Tabasco : 70 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1310", "nombre": "Gabriel Alejandro Espinosa", "puesto": "Coordinador Foraneo",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "",
                "email": "---", "telefono": "(+52) 98 11993924",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Sin ubicación",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS - Bienestar Campeche : 10 Unidades", "ISSSTE Campeche : 7 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1311", "nombre": "Gabriela Rojas", "puesto": "Coordinadora Tabasco",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://i.ibb.co/fVFjsB29/GABRIELA-ROJAS.jpg",
                "email": "---", "telefono": "(+52) 55 31213187",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Tabasco",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS - Bienestar Tabasco : 109 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1312", "nombre": "Iveth Broca", "puesto": "Coordinadora Tabasco",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://i.ibb.co/TqhVsK8z/Iveth-Broca.jpg",
                "email": "---", "telefono": "(+52) 55 31098614",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Tabasco",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS - Bienestar Tabasco : 125 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1313", "nombre": "Ivonne Garcia Martinez", "puesto": "Coordinadora Foranea",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://i.ibb.co/39nDHtcY/Ivonne-Garcia.jpg",
                "email": "---", "telefono": "(+52) 55 30838497",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS - Bienestar Colima : 135 Unidades", " IPN Foraneo : 40 Unidades", "PRODECON : 8 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1314", "nombre": "Jair Estrada", "puesto": "Coordinador Foraneo",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://i.ibb.co/mV4tD9D2/Jair-Estrada.jpg",
                "email": "---", "telefono": "(+52) 55 30527704",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["INFONAVIT Foraneo : 26 Unidades", "CONAFE : 28 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1315", "nombre": "Jazmin Gomez", "puesto": "Coordinadora Tabasco",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://i.ibb.co/XrMSbJjp/JAZMIN-GOMEZ.jpg",
                "email": "---", "telefono": "(+52) 55 30857671",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Tabasco",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS - Bienestar Tabasco : 128 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1316", "nombre": "Jesus Salazar Hinojosa", "puesto": "Coordinador de Proyecto",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://i.ibb.co/Mx2yhHdy/Jesus-Salazar-Hinojosa.jpg",
                "email": "---", "telefono": "(+52) 55 31322612",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Relaciones Exteriores Foraneo : 8 Unidades", "ATRAPI Foraneo : 2 Unidades", "IMSS - Bienestar Campeche : Unidades", "ISSSTE Campeche :  ", "PROFECO : 2 Unidades"
                              , "PRODECON : 8 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1317", "nombre": "Fernanda de la Torre Acevedo", "puesto": "Coordinadora Foranea",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://i.ibb.co/jv4m0JtW/Fernandad-Acevedo.jpg",
                "email": "---", "telefono": "(+52) 55 29687664",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Banjercito : 14 Unidades", "PRODECON : 9 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1318", "nombre": "Melisa Martinez", "puesto": "Coordinadora Foranea",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://i.ibb.co/93S7FSWy/Melissa-Martinez.jpg",
                "email": "---", "telefono": "(+52) 98 12220644",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS - Bienestar Campeche : 33 Unidades", "ISSSTE Campeche : 5 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1319", "nombre": "Sandra Isabel Morales", "puesto": "Coordinadora Foranea",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "",
                "email": "---", "telefono": "(+52) 98 21044475",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Sin información",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS - Bienestar Campeche : 68 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1320", "nombre": "Blanca Viridiana Lopez Zuñiga", "puesto": "Coordinadora Foranea",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://i.ibb.co/kVJN61Dv/Viridiana-Zu-iga-copia.jpg",
                "email": "---", "telefono": "(+52) 55 30798520",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["ISSTE Puebla : 41 Unidades", "ISSSTE Guerrero : 48 Unidades", "SHCP Veracruz : 2 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            

        ]

    st.session_state.usuarios = [limpiar_registro_personal(u) for u in st.session_state.usuarios]
    st.session_state.usuarios = normalizar_ids_unicos(st.session_state.usuarios, "USR")

    if "confirmar_borrado" not in st.session_state:
        st.session_state.confirmar_borrado = None

    def _entero(x):
        try:
            return int(float(x))
        except (TypeError, ValueError):
            return 0

    _us = st.session_state.usuarios
    _serv_real = sum(_entero(s.get("Cantidad real", 0)) for u in _us for s in asegurar_servicios_estructurados(u))
    _ce = conteo_estados(_us)
    st.markdown(
        html_banner_tab(
            "🪪", "Coordinadores", "Credenciales del personal operativo por zona: busca, filtra y gestiona en un clic",
            pills=[f"👥 {len(_us)} credenciales", f"🗓️ {_ahora().strftime('%d/%m/%Y')}"],
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        html_kpis_tab([
            ("Credenciales", "🪪", "#2563eb", f"{_ce['Todos']}", f"{contar_credenciales_por_puesto('coordinador', 'coordinadora')} coordinadores · {contar_credenciales_por_puesto('gerente')} gerentes", None),
            ("Activas", "✅", "#16a34a", f"{_ce['Activo']}", f"{_pct(_ce['Activo'], _ce['Todos']):.0f}% del total", _pct(_ce["Activo"], _ce["Todos"])),
            ("Pendientes", "⏳", "#f59e0b", f"{_ce['Pendiente']}", "por activar", _pct(_ce["Pendiente"], _ce["Todos"])),
            ("Inactivas", "⛔", "#ef4444", f"{_ce['Inactivo']}", "sin acceso", _pct(_ce["Inactivo"], _ce["Todos"])),
            ("Servicios asignados", "🧰", "#0d9488", f"{_serv_real:,}", "cantidad real en total", None),
        ]),
        unsafe_allow_html=True,
    )
    st.markdown('<div class="tb-espacio"></div>', unsafe_allow_html=True)

    @st.dialog("✏️ Editar credencial")
    def dialogo_editar(usuario_id):
        usuario = next((u for u in st.session_state.usuarios if u["id"] == usuario_id), None)
        if usuario is None:
            st.error("El usuario ya no existe.")
            return
        with st.form(f"form_editar_{usuario_id}"):
            nombre_e = st.text_input("Nombre completo", value=(usuario["nombre"] or "").strip())
            puesto_e = st.text_input("Puesto / Cargo", value=usuario["puesto"])
            depto_e = st.selectbox(
                "Área geográfica", REGIONES,
                index=REGIONES.index(usuario["departamento"]) if usuario["departamento"] in REGIONES else 0,
            )
            estado_e = st.selectbox("Estado", ["Activo", "Pendiente", "Inactivo"], index=["Activo", "Pendiente", "Inactivo"].index(usuario["estado"]))
            email_e = st.text_input("Correo electrónico", value=(usuario["email"] or "").strip())
            tel_e = st.text_input("Teléfono", value=usuario["telefono"])
            nivel_e = st.text_input("Nivel de acceso", value=usuario["nivel_acceso"])
            foto_nueva = st.file_uploader("Reemplazar foto (opcional)", type=["jpg", "jpeg", "png"])

            col_a, col_b = st.columns(2)
            guardar = col_a.form_submit_button("💾 Guardar cambios", width="stretch")
            cancelar = col_b.form_submit_button("Cancelar", width="stretch")

            if guardar:
                usuario["nombre"] = nombre_e
                usuario["puesto"] = puesto_e
                usuario["departamento"] = depto_e
                usuario["estado"] = estado_e
                usuario["email"] = email_e
                usuario["telefono"] = tel_e
                usuario["nivel_acceso"] = nivel_e
                if foto_nueva is not None:
                    usuario["foto_bytes"] = foto_nueva.read()
                    usuario["foto"] = None
                st.success("Credencial actualizada.")
                st.rerun()
            if cancelar:
                st.rerun()

    @st.dialog("➕ Nueva credencial")
    def dialogo_nuevo():
        with st.form("form_nuevo_usuario", clear_on_submit=True):
            c1, c2 = st.columns(2)
            nuevo_nombre = c1.text_input("Nombre completo *")
            nuevo_id = c2.text_input("ID de usuario *", value=siguiente_id(st.session_state.usuarios, "USR"))
            nuevo_puesto = c1.selectbox("Puesto / Cargo", ["Coordinador", "Coordinadora", "Gerente", "Administrativo"])
            nuevo_depto = c2.selectbox("Zona", REGIONES)
            nuevo_estado = c1.selectbox("Estado", list(ESTADOS_PERSONAL))
            nuevo_nivel = c2.selectbox("Nivel de acceso", NIVELES_ACCESO)
            nuevo_email = c1.text_input("Correo electrónico")
            nuevo_tel = c2.text_input("Teléfono")
            nueva_foto = st.file_uploader("Foto de perfil", type=["jpg", "jpeg", "png"])

            if st.form_submit_button("💾 Guardar credencial", type="primary", width="stretch"):
                ids_existentes = {u["id"] for u in st.session_state.usuarios}
                if not nuevo_nombre.strip() or not nuevo_id.strip():
                    st.error("Completa los campos obligatorios (*).")
                elif nuevo_id in ids_existentes:
                    st.error(f"El ID '{nuevo_id}' ya existe. Usa un identificador distinto.")
                else:
                    st.session_state.usuarios.append({
                        "id": nuevo_id.strip(), "nombre": nuevo_nombre.strip(), "puesto": nuevo_puesto,
                        "departamento": nuevo_depto, "estado": nuevo_estado,
                        "foto": None, "foto_bytes": nueva_foto.read() if nueva_foto else None,
                        "email": nuevo_email or f"{nuevo_nombre.lower().strip().replace(' ', '.')}@empresa.com",
                        "telefono": nuevo_tel or "+52 (55) 0000-0000",
                        "fecha_ingreso": "Reciente", "ubicacion": "Por asignar",
                        "nivel_acceso": nuevo_nivel, "proyectos": [], "servicios": [],
                        "habilidades": ["Colaboración"],
                    })
                    st.toast("Credencial agregada.")
                    st.rerun()

    busqueda_lower, filtro_estado, vista_coord, _c_nuevo = barra_filtros_personal("coord", conteo_estados(_us))
    with _c_nuevo:
        if st.button("➕ Nueva", key="btn_nueva_cred", type="primary", width="stretch"):
            dialogo_nuevo()
    usuarios_filtrados = filtrar_personal(_us, busqueda_lower, filtro_estado)
    columnas_grid = 4

    def renderizar_tarjeta(usuario, idx):
        with st.container(border=True):
            badge_class = f"badge-{usuario['estado'].lower()}"
            st.markdown(
                f"""
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <span class="id-tag">🪪 {usuario['id']}</span>
                    <span class="status-badge {badge_class}">{usuario['estado']}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            c_foto, c_datos = st.columns([1, 1.8])
            with c_foto:
                st.image(obtener_imagen_usuario(usuario), width="stretch")
            with c_datos:
                st.markdown(f"### {(usuario['nombre'] or '').strip()}")
                st.markdown(f"**💼 Puesto:** {usuario['puesto']}")
                st.markdown(f"**🏢 Zona:** `{usuario['departamento']}`")
                

            st.divider()

            with st.expander("📂 Menú de Información Completa", expanded=False):
                tab_contacto, tab_servicios, tab_excel, tab_skills = st.tabs(
                    ["📧 Contacto", "🛡️ Resumen", "📊 Servicios (Excel)", "⭐ Funciones"]
                )

                with tab_contacto:
                    email_limpio = (usuario["email"] or "").strip()
                    link_wa = generar_link_whatsapp(usuario['telefono'])
                    
                    st.markdown(f"**Email:** [{email_limpio}](mailto:{email_limpio})")
                    
                    if link_wa:
                        st.markdown(
                            f"""**Teléfono:** {usuario['telefono']} 
                            <a href="{link_wa}" target="_blank" class="wa-link">
                                <svg width="14" height="14" viewBox="0 0 24 24">
                                    <path d="M.057 24l1.687-6.163c-1.041-1.804-1.588-3.849-1.587-5.946.003-6.556 5.338-11.891 11.893-11.891 3.181.001 6.167 1.24 8.413 3.488 2.245 2.248 3.481 5.236 3.48 8.414-.003 6.557-5.338 11.892-11.893 11.892-1.99-.001-3.951-.5-5.688-1.448l-6.305 1.654zm6.597-3.807c1.676.995 3.276 1.591 5.392 1.592 5.448 0 9.886-4.434 9.889-9.885.002-5.462-4.415-9.89-9.881-9.892-5.452 0-9.887 4.434-9.889 9.884-.001 2.225.651 3.891 1.746 5.634l-.999 3.648 3.742-.981zm11.387-5.464c-.074-.124-.272-.198-.57-.347-.297-.149-1.758-.868-2.031-.967-.272-.099-.47-.149-.669.149-.198.297-.768.967-.941 1.165-.173.198-.347.223-.644.074-.297-.149-1.255-.462-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.521.151-.172.2-.296.3-.495.099-.198.05-.372-.025-.521-.075-.148-.669-1.611-.916-2.206-.242-.579-.487-.501-.669-.51l-.57-.01c-.198 0-.52.074-.792.372s-1.04 1.016-1.04 2.479 1.065 2.876 1.213 3.074c.149.198 2.095 3.2 5.076 4.487.709.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.695.248-1.29.173-1.414z"/>
                                </svg> WhatsApp
                            </a>""",
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(f"**Teléfono:** {usuario['telefono']}")
                        
                    st.markdown(f"**Ubicación:** {usuario['ubicacion']}")
                    st.markdown(f"**Nivel de Acceso:** {usuario['nivel_acceso']}")
                    st.markdown(f"**Ingreso:** {usuario['fecha_ingreso']}")

                with tab_servicios:
                    servicios = asegurar_servicios_estructurados(usuario)
                    if servicios:
                        total_unidades_usuario = sum(s.get("Cantidad real", 0) for s in servicios)
                        st.metric("Total de cantidad real asignada", total_unidades_usuario)
                        for s in servicios:
                            id_str = f" [{s['Clue/ID']}]" if s.get("Clue/ID") else ""
                            st.markdown(f"- **{s['Dependencia']}**{id_str}: {s.get('Unidad', '')} (Req: {s.get('Cantidad requerida', 0)} | Real: {s.get('Cantidad real', 0)})")
                    else:
                        st.caption("Sin servicios asignados todavía.")

                with tab_excel:
                    st.caption("Edita la tabla como si fuera Excel: puedes agregar o eliminar filas/columnas. Los datos se guardan en tiempo real.")
                    servicios = asegurar_servicios_estructurados(usuario)
                    
                    df_servicios = pd.DataFrame(servicios) if servicios else pd.DataFrame(
                        columns=["Dependencia", "Clue/ID", "Unidad", "Cantidad requerida", "Cantidad real"]
                    )
                    
                    cols_deseadas = ["Dependencia", "Clue/ID", "Unidad", "Cantidad requerida", "Cantidad real"]
                    for col in cols_deseadas:
                        if col not in df_servicios.columns:
                            df_servicios[col] = "" if "Cantidad" not in col else 0
                    df_servicios = df_servicios[cols_deseadas]

                    df_editado = st.data_editor(
                        df_servicios,
                        num_rows="dynamic",
                        width="stretch",
                        key=f"editor_servicios_{usuario['id']}_{idx}",
                        column_config={
                            "Dependencia": st.column_config.TextColumn("Dependencia", required=True),
                            "Clue/ID": st.column_config.TextColumn("Clue/ID"),
                            "Unidad": st.column_config.TextColumn("Unidad"),
                            "Cantidad requerida": st.column_config.NumberColumn("Cantidad requerida", min_value=0, step=1),
                            "Cantidad real": st.column_config.NumberColumn("Cantidad real", min_value=0, step=1),
                        },
                    )
                    
                    usuario["servicios"] = df_editado.fillna({
                        "Dependencia": "", "Clue/ID": "", "Unidad": "", "Cantidad requerida": 0, "Cantidad real": 0
                    }).to_dict("records")

                    col_x1, col_x2 = st.columns(2)
                    with col_x1:
                        st.download_button(
                            "⬇️ Descargar Excel",
                            data=exportar_servicios_excel(usuario),
                            file_name=f"servicios_{usuario['id']}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"xlsx_dl_{usuario['id']}_{idx}",
                            width="stretch",
                        )
                    with col_x2:
                        excel_subido = st.file_uploader(
                            "⬆️ Reemplazar desde Excel", type=["xlsx"],
                            key=f"xlsx_up_{usuario['id']}_{idx}", label_visibility="collapsed",
                        )
                        if excel_subido is not None:
                            try:
                                df_nuevo = pd.read_excel(excel_subido, engine="openpyxl")
                                columnas_requeridas = {"Dependencia", "Clue/ID", "Unidad", "Cantidad requerida", "Cantidad real"}
                                if columnas_requeridas.issubset(df_nuevo.columns):
                                    usuario["servicios"] = df_nuevo.fillna({
                                        "Dependencia": "", "Clue/ID": "", "Unidad": "", "Cantidad requerida": 0, "Cantidad real": 0
                                    }).to_dict("records")
                                    st.success("Servicios actualizados desde el Excel subido.")
                                    st.rerun()
                                else:
                                    st.error("El Excel debe tener las columnas: Dependencia, Clue/ID, Unidad, Cantidad requerida, Cantidad real.")
                            except Exception as e:
                                st.error(f"No se pudo leer el archivo: {e}")

                with tab_skills:
                    st.markdown("**Funciones Clave:**")
                    st.write(", ".join([f"`{h}`" for h in usuario["habilidades"]]))

                st.markdown("---")

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    with st.popover("📱 Ver QR", width="stretch"):
                        qr_data = f"ID:{usuario['id']};Nombre:{usuario['nombre']};Puesto:{usuario['puesto']}"
                        st.image(generar_qr(qr_data), width=180)
                        st.caption("Escanea para verificar la identidad del portador.")
                with col_btn2:
                    png_bytes = generar_credencial_png(usuario)
                    st.download_button(
                        "🖨️ Descargar", data=png_bytes, file_name=f"credencial_{usuario['id']}.png",
                        mime="image/png", key=f"download_{usuario['id']}_{idx}", width="stretch",
                    )

                col_btn3, col_btn4 = st.columns(2)
                with col_btn3:
                    if st.button("✏️ Editar", key=f"edit_{usuario['id']}_{idx}", width="stretch"):
                        dialogo_editar(usuario["id"])
                with col_btn4:
                    if st.session_state.confirmar_borrado == usuario["id"]:
                        if st.button("⚠️ Confirmar", key=f"confirm_del_{usuario['id']}_{idx}", width="stretch", type="primary"):
                            st.session_state.usuarios = [u for u in st.session_state.usuarios if u["id"] != usuario["id"]]
                            st.session_state.confirmar_borrado = None
                            st.toast(f"Credencial {usuario['id']} eliminada.")
                            st.rerun()
                    else:
                        if st.button("🗑️ Eliminar", key=f"del_{usuario['id']}_{idx}", width="stretch"):
                            st.session_state.confirmar_borrado = usuario["id"]
                            st.rerun()

    def renderizar_grid(usuarios_zona, columnas):
        if not usuarios_zona:
            st.info("No hay credenciales en esta zona con los filtros actuales.")
            return
        cols = st.columns(columnas)
        for idx, usuario in enumerate(usuarios_zona):
            with cols[idx % columnas]:
                renderizar_tarjeta(usuario, idx)

    ICONOS_ZONA = {"CDMX": "🏙️", "Toluca": "🌆", "Estado de México": "🗺️", "Foraneos": "📍"}

    def _extras_coord(u):
        serv = asegurar_servicios_estructurados(u)
        return {"Servicios": len(serv), "Cantidad real": sum(_entero(s.get("Cantidad real", 0)) for s in serv)}

    if "Tabla" in vista_coord:
        st.caption(f"{len(usuarios_filtrados)} de {len(_us)} credenciales · clic en el encabezado para ordenar.")
        tabla_personal(usuarios_filtrados, "coordinadores", "Zona", extras=_extras_coord)
    else:
        zona_sel = selector_grupo("coord", REGIONES, ICONOS_ZONA, usuarios_filtrados)
        st.caption(f"Mostrando {len(usuarios_filtrados)} de {len(_us)} credenciales.")
        if not usuarios_filtrados:
            st.markdown('<div class="tb-vacio">Sin resultados. Prueba otra búsqueda o elige "Todos" en el estado.</div>', unsafe_allow_html=True)
        zonas = REGIONES if zona_sel == "Todas" else [zona_sel]
        for z in zonas:
            grupo = [u for u in usuarios_filtrados if u["departamento"] == z]
            if zona_sel == "Todas":
                if not grupo:
                    continue
                st.markdown(f'<div class="tb-grupo">{ICONOS_ZONA[z]} {z} <span>{len(grupo)}</span></div>', unsafe_allow_html=True)
            renderizar_grid(grupo, columnas_grid)
        if zona_sel == "Todas":
            sin_zona = [u for u in usuarios_filtrados if u["departamento"] not in REGIONES]
            if sin_zona:
                st.markdown(f'<div class="tb-grupo">📁 Sin zona <span>{len(sin_zona)}</span></div>', unsafe_allow_html=True)
                renderizar_grid(sin_zona, columnas_grid)






# ==============================================================================
# PESTAÑA "Administradores"
# ==============================================================================
DEPARTAMENTOS_ADMIN = [
    "Licitaciones",
    "Operaciones",
    "Auditoria",
    "Finanzas",
    "Nomina",
    "Movimiento de Personal",
    "Recursos Humanos",
    "Almacen",
    "Juridico",
    "Planeación y Desarrollo",

]

with pestana_administracion:
    st.markdown(
        """
        <style>
            .status-badge {
                display: inline-block; padding: 4px 10px; border-radius: 12px;
                font-size: 0.78rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;
            }
            .badge-activo { background-color: #dcfce7; color: #166534; border: 1px solid #86efac; }
            .badge-inactivo { background-color: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
            .badge-pendiente { background-color: #fef3c7; color: #92400e; border: 1px solid #fcd34d; }
            .id-tag {
                font-family: 'Courier New', Courier, monospace; background-color: #f1f5f9;
                padding: 3px 8px; border-radius: 6px; color: #334155; font-weight: bold;
                font-size: 0.85rem; border: 1px solid #cbd5e1;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if "administradores" not in st.session_state:
        st.session_state.administradores = [
            {
                "id": "ADM-2001",
                "nombre": "Iñaki",
                "puesto": "Director de Licitaciones",
                "departamento": "Licitaciones",
                "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=300&auto=format&fit=crop&q=80",
                "email": "licitaciones@empresa.com",
                "telefono": "(+52) 55 11223344",
                "fecha_ingreso": "10-Enero-2020",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 4 (Directivo)",
                "proyectos": ["Licitación Pública IMSS : 1 Unidad ()"],
                "habilidades": ["Contratación Pública", "Análisis de Bases"],
            },
            {
                "id": "ADM-3000",
                "nombre": "Alfonso Acevedo",
                "puesto": "Director de Operaciones",
                "departamento": "Operaciones",
                "estado": "Activo",
                "foto": "https://i.ibb.co/KjK3zKnV/Alofonso-Acevedo.jpg",
                "email": "operaciones@empresa.com",
                "telefono": "(+52) 55 81746632",
                "fecha_ingreso": "15-Mayo-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 4 (Directivo)",
                "proyectos": ["Control Logístico : 5 Unidades ()"],
                "habilidades": ["Logística", "Supervisión de Campo"],
            },
            {
                 "id": "ADM-3001",
                "nombre": "Julio Cesar Ibarra Yañez",
                "puesto": "Subdirector de Cumplimiento Operativo",
                "departamento": "Operaciones",
                "estado": "Activo",
                "foto": "https://i.ibb.co/cS0JG153/Julio-Ibarra.jpg",
                "email": "operaciones@empresa.com",
                "telefono": "(+52) 55 13431933",
                "fecha_ingreso": "01-Septiembre-2025",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Subdirección)",
                "proyectos": ["Control Logístico"],
                "habilidades": ["Logística", "Supervisión de Campo"],
            },
            {
                "id": "ADM-3002",
                "nombre": "Cassandra Sosa",
                "puesto": "Subdirectora de Análisis y Administración de Contratos",
                "departamento": "Operaciones",
                "estado": "Activo",
                "foto": "https://i.ibb.co/vCNzFrDd/Cassandra-Sosa.jpg",
                "email": "operaciones@empresa.com",
                "telefono": "(+52) 55 30726931",
                "fecha_ingreso": "01-Septiembre-2025",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Subdirección)",
                "proyectos": ["Control Logístico : 5 Unidades ()"],
                "habilidades": ["Logística", "Supervisión de Campo"],
            },
            {
                "id": "ADM-3003",
                "nombre": "Karla Ayala",
                "puesto": "Subdirectora de Gestión de Cartera y Cobranza",
                "departamento": "Operaciones",
                "estado": "Activo",
                "foto": "https://i.ibb.co/xwZSqyK/Karla-Ayala.jpg",
                "email": "operaciones@empresa.com",
                "telefono": "(+52) 55 30840595",
                "fecha_ingreso": "15-Mayo-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Subdirección)",
                "proyectos": ["Control Logístico : 5 Unidades ()"],
                "habilidades": ["Logística", "Supervisión de Campo"],
            },
            {
                "id": "ADM-3004",
                "nombre": "Rodrigo Rebolledo",
                "puesto": "Analista de Contratos",
                "departamento": "Operaciones",
                "estado": "Activo",
                "foto": "https://i.ibb.co/Lz3861jb/Rodrigo-Rebolledo.jpg",
                "email": "operaciones@empresa.com",
                "telefono": "(+52) 55 31280991",
                "fecha_ingreso": "15-Mayo-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Analista)",
                "proyectos": ["Control Logístico : 5 Unidades ()"],
                "habilidades": ["Logística", "Supervisión de Campo"],
            },
            {
                "id": "ADM-3005",
                "nombre": "Abigail Pacheco",
                "puesto": "Analista de Contratos",
                "departamento": "Operaciones",
                "estado": "Activo",
                "foto": "https://i.ibb.co/dssyQ0QR/Abigail-Pacheco.jpg",
                "email": "operaciones@empresa.com",
                "telefono": "(+52) 55 31469619",
                "fecha_ingreso": "15-Mayo-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Analista)",
                "proyectos": ["Control Logístico : 5 Unidades ()"],
                "habilidades": ["Logística", "Supervisión de Campo"],
            },
            {
                "id": "ADM-3006",
                "nombre": "Bernardino Gonzalez",
                "puesto": "Auxiliar Administrativo",
                "departamento": "Operaciones",
                "estado": "Activo",
                "foto": "https://i.ibb.co/wFtgHYPk/Bernardino-Gonzalez.jpg",
                "email": "operaciones@empresa.com",
                "telefono": "(+52) 55 30723293",
                "fecha_ingreso": "15-Mayo-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Auxiliar Admvo.)",
                "proyectos": ["Control Logístico : 5 Unidades ()"],
                "habilidades": ["Logística", "Supervisión de Campo"],
            },
            {
                "id": "ADM-3007",
                "nombre": "Nicte Gonzalez",
                "puesto": "Analista de Facturación",
                "departamento": "Operaciones",
                "estado": "Activo",
                "foto": "https://i.ibb.co/5WBVM87K/Nicte-Gonzalez.jpg",
                "email": "operaciones@empresa.com",
                "telefono": "(+52) 55 30682823",
                "fecha_ingreso": "01-Septiembre-2025",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Analista)",
                "proyectos": ["Control Logístico : 5 Unidades ()"],
                "habilidades": ["Logística", "Supervisión de Campo"],
            },
            {
                "id": "ADM-3008",
                "nombre": "Cristian Merino Cosina",
                "puesto": "Analista ",
                "departamento": "Operaciones",
                "estado": "Inactivo",
                "foto": "https://i.ibb.co/39wjy6gp/Cristian-Merino.jpg",
                "email": "operaciones@empresa.com",
                "telefono": "(+52) 55 31912517",
                "fecha_ingreso": "15-Mayo-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Analista)",
                "proyectos": [""],
                "habilidades": [""],
            },
            {
                "id": "ADM-3009",
                "nombre": "Alejandro Vazquez",
                "puesto": "Automatización de Procesos y TI",
                "departamento": "Operaciones",
                "estado": "Activo",
                "foto": "https://i.ibb.co/TMNDPJZG/Alejandro-Vazquez.png",
                "email": "operaciones@empresa.com",
                "telefono": "(+52) 55 30606377",
                "fecha_ingreso": "01-Septiembre-2025",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Analista)",
                "proyectos": ["Control Logístico : 5 Unidades ()"],
                "habilidades": ["Logística", "Supervisión de Campo"],
            },
            {
                "id": "ADM-",
                "nombre": "Sara Tovar",
                "puesto": "Subdirección de Auditoria y Control",
                "departamento": "Auditoria",
                "estado": "Activo",
                "foto": "https://i.ibb.co/vCwFxwRq/Sara-Tovar.jpg",
                "email": "operaciones@empresa.com",
                "telefono": "(+52) 55 30606377",
                "fecha_ingreso": "01-Septiembre-2025",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Analista)",
                "proyectos": ["Control Logístico : 5 Unidades ()"],
                "habilidades": ["Logística", "Supervisión de Campo"],
            },
            {
                "id": "ADM-4000",
                "nombre": "Nayeli Madrid",
                "puesto": "Directora de Finanzas",
                "departamento": "Finanzas",
                "estado": "Activo",
                "foto": "",
                "email": "finanzas@empresa.com",
                "telefono": "(+52) 55 ",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 4 (Directivo)",
                "proyectos": ["Presupuesto Anual : 1 Unidad ()"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-4001",
                "nombre": "Daniel Vega",
                "puesto": "Subdirector de Finanzas",
                "departamento": "Finanzas",
                "estado": "Activo",
                "foto": "https://i.ibb.co/8LL7PzXc/Daniel-Vega.jpg",
                "email": "finanzas@empresa.com",
                "telefono": "(+52) 55 64601723",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel  (Subdirector)",
                "proyectos": [""],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-4002",
                "nombre": "Gabriel",
                "puesto": "Gerente Contable",
                "departamento": "Finanzas",
                "estado": "Activo",
                "foto": "",
                "email": "finanzas@empresa.com",
                "telefono": "(+52) 55 29676166",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel  (Gerente)",
                "proyectos": [""],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-5001",
                "nombre": "Norma Fuentes",
                "puesto": "Gerente de Nomina",
                "departamento": "Nomina",
                "estado": "Activo",
                "foto": "",
                "email": "finanzas@empresa.com",
                "telefono": "(+52) 55 33445566",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 2 (Gerente)",
                "proyectos": ["Presupuesto Anual : 1 Unidad ()"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-5002",
                "nombre": "Said Xala",
                "puesto": "Gerente de Nomina",
                "departamento": "Nomina",
                "estado": "Activo",
                "foto": "",
                "email": "finanzas@empresa.com",
                "telefono": "(+52) 55 33445566",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 2 (Analista)",
                "proyectos": ["Presupuesto Anual : 1 Unidad ()"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-6000",
                "nombre": "Antonio Cadena",
                "puesto": "Gerente de IMSS",
                "departamento": "Movimiento de Personal",
                "estado": "Activo",
                "foto": "https://i.ibb.co/yKcJJVf/Antonio-Cadena.jpg",
                "email": "imss.armont@gmail.com",
                "telefono": "(+52) 55 31083478",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 2 (Gerente)",
                "proyectos": ["Slycom", "Armot", "Retimar", "Géminis", "Lideres"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-6001",
                "nombre": "Brianda Barrón",
                "puesto": "Capturista",
                "departamento": "Movimiento de Personal",
                "estado": "Activo",
                "foto": "https://i.ibb.co/6c2bzTxq/Brianda-Barr-n.jpg",
                "email": "imss.armotbarron@gmail.com",
                "telefono": "(+52) 55 31289012",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel  (Capturista)",
                "proyectos": ["Slycom", "Armot", "Retimar", "Géminis", "Lideres"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-6002",
                "nombre": "Jessyca Mendoza",
                "puesto": "Capturista",
                "departamento": "Movimiento de Personal",
                "estado": "Activo",
                "foto": "https://i.ibb.co/pBp2t25b/Jessyca-Mendoza.jpg",
                "email": "mgjy.5433@gmail.com",
                "telefono": "(+52) 55 31315433",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel  (Capturista)",
                "proyectos": ["Slycom", "Armot", "Retimar", "Géminis", "Lideres"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-6003",
                "nombre": "Ana León",
                "puesto": "Analista de Seguridad Social",
                "departamento": "Movimiento de Personal",
                "estado": "Activo",
                "foto": "https://i.ibb.co/9QsdJZk/Ana-Leon.jpg",
                "email": "imssanigl@gmail.com",
                "telefono": "(+52) 55 30550579",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel  (Analista)",
                "proyectos": ["Slycom : Poder Judicial, IMSS - Bienestar Campeche, IMSS - Bienestar Colima, IMSS - Bienestar Puebla, ATTRAPI", "Lideres : SPOTMET"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-6004",
                "nombre": "Astrid Hernández",
                "puesto": "Analista de Seguridad Social",
                "departamento": "Movimiento de Personal",
                "estado": "Activo",
                "foto": "https://i.ibb.co/8D56ZsV1/Astrid-Hernandez.jpg",
                "email": "imss.armot2@gmail.com",
                "telefono": "(+52) 55 30466843",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel  (Analista)",
                "proyectos": ["Slycom : Metro","Armot : PROFECO, CONAFE, Salud Federal, Relaciones Exteriores Pasaportes",
                               "Lideres : PRODECOM, ISEM", "GÉMINIS : Plaza Artz"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-6005",
                "nombre": "David Hernández",
                "puesto": "Analista de Seguridad Social",
                "departamento": "Movimiento de Personal",
                "estado": "Activo",
                "foto": "https://i.ibb.co/mr3S7JrZ/David-Hernandez.jpg",
                "email": "recursoshumanos.armot21@gmail.com",
                "telefono": "(+52) 55 5531183180",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel  (Analista)",
                "proyectos": ["Slycom : ISSSTE, Oficialia Mayor", "Armot : INFONAVIT Foráneo",
                               "Lideres : IMSS - Bienestar Oficinas, DGRT", "GÉMINIS : IMSS - Bienestar Tabasco, IMSS - Bienestar CDMX, IMSS - Bienestar Edo. México, "
                               "IMSS - Bienestar Chiapas, Central del Sur"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-6006",
                "nombre": "Susana Ortiz",
                "puesto": "Analista de Seguridad Social",
                "departamento": "Movimiento de Personal",
                "estado": "Activo",
                "foto": "https://i.ibb.co/V0NqF7kB/Susana-Ortiz.jpg",
                "email": "imssrhortiz@gmail.com",
                "telefono": "(+52) 55 306781961",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel  (Analista)",
                "proyectos": ["Slycom : Participacion Ciudadana, Relaciones Exteriores", "Retimar : Banjercito, IPN", 
                              "Lideres : SHCP(CDMX / Veracruz), FONACOT (Diego Mora), SEBIEN, SEGIAGUA, FINABIEN, Secretaria de las Mujeres"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-7000",
                "nombre": "Damaris",
                "puesto": "Gerente de Recursos Humanos",
                "departamento": "Recursos Humanos",
                "estado": "Activo",
                "foto": "",
                "email": "finanzas@empresa.com",
                "telefono": "(+52) 55 33445566",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 2 (Gerente)",
                "proyectos": ["Presupuesto Anual : 1 Unidad ()"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-7001",
                "nombre": "Brenda Elizabeth Carmona Alcala",
                "puesto": "Auxiliar de Recursos Humanos",
                "departamento": "Recursos Humanos",
                "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Brenda%20Carmona.jpg",
                "email": "finanzas@empresa.com",
                "telefono": "(+52) 55 31932503",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel  (Auxiliar de RH)",
                "proyectos": ["Presupuesto Anual : 1 Unidad ()"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-7002",
                "nombre": "Osvaldo Palomino",
                "puesto": "Auxiliar de Recursos Humanos",
                "departamento": "Recursos Humanos",
                "estado": "Activo",
                "foto": "https://i.ibb.co/pjzSHDYX/Osvaldo-Palomino.jpg",
                "email": "finanzas@empresa.com",
                "telefono": "(+52) 55 ",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel  (Auxiliar de RH)",
                "proyectos": ["Presupuesto Anual : 1 Unidad ()"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-7003",
                "nombre": "Cristian Alvarado",
                "puesto": "Auxiliar de Recursos Humanos",
                "departamento": "Recursos Humanos",
                "estado": "Activo",
                "foto": "https://i.ibb.co/vCV4PWYJ/Cristian-Alvado.jpg",
                "email": "finanzas@empresa.com",
                "telefono": "(+52) 55 ",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel  (Auxiliar de RH)",
                "proyectos": ["Presupuesto Anual : 1 Unidad ()"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-7004",
                "nombre": "Lorena Chavarria",
                "puesto": "Auxiliar de Recursos Humanos",
                "departamento": "Recursos Humanos",
                "estado": "Activo",
                "foto": "https://i.ibb.co/1twTJTcv/Lorena-Chavarria.jpg",
                "email": "finanzas@empresa.com",
                "telefono": "(+52) 55 ",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel  (Auxiliar de RH)",
                "proyectos": ["Presupuesto Anual : 1 Unidad ()"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-8000",
                "nombre": "Juan Carlos Yepes Cano",
                "puesto": "Director Jurídico",
                "departamento": "Juridico",
                "estado": "Activo",
                "foto": "https://i.ibb.co/gLGtQ09v/Juan-Carlos-Yepes.png",
                "email": "jc.yepez@armot.com.mx",
                "telefono": "(+52) 55 78280127",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 4 (Directivo)",
                "proyectos": ["Titular de la Dirección Juridica"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-8001",
                "nombre": "Tania Dolores Servin Godinez",
                "puesto": "Coordinadora de cumplimiento normativo y consultoría",
                "departamento": "Juridico",
                "estado": "Activo",
                "foto": "https://i.ibb.co/CXqnNzT/Tania.jpg",
                "email": "t.servin@armot.com.mx",
                "telefono": "(+52) 55 30844772",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel ()",
                "proyectos": ["Presupuesto Anual : 1 Unidad ()"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-8002",
                "nombre": "Fernando Rodríguez Domínguez",
                "puesto": "Coordinador de contratos y asuntos corporativos",
                "departamento": "Juridico",
                "estado": "Activo",
                "foto": "https://i.ibb.co/KxJVQt0w/Fernando-Rodriguez.jpg",
                "email": "f.rodriguez@armot.com.mx",
                "telefono": "(+52) 55 45607428",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel ()",
                "proyectos": ["Presupuesto Anual : 1 Unidad ()"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-9001",
                "nombre": "Isabel",
                "puesto": "Gerente de Almacén",
                "departamento": "Almacen",
                "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=300&auto=format&fit=crop&q=80",
                "email": "finanzas@empresa.com",
                "telefono": "(+52) 55 33445566",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Almacén",
                "nivel_acceso": "Nivel 2 (Gerente)",
                "proyectos": ["Presupuesto Anual : 1 Unidad ()"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-",
                "nombre": "Raúl Pérez",
                "puesto": "Gerente de Almacén",
                "departamento": "Planeación y Desarrollo",
                "estado": "Activo",
                "foto": "https://i.ibb.co/1tNB6B0j/Raul-Perez.png",
                "email": "finanzas@empresa.com",
                "telefono": "(+52) 55 48485798",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel  (Director)",
                "proyectos": [""],
                "habilidades": [""],
            },
        ]

    st.session_state.administradores = [limpiar_registro_personal(a) for a in st.session_state.administradores]
    st.session_state.administradores = normalizar_ids_unicos(st.session_state.administradores, "ADM")

    if "confirmar_borrado_admin" not in st.session_state:
        st.session_state.confirmar_borrado_admin = None

    _ad = st.session_state.administradores
    _ca = conteo_estados(_ad)
    _areas_con_personal = len({a["departamento"] for a in _ad})
    st.markdown(
        html_banner_tab(
            "💼", "Administración", "Credenciales del personal administrativo por área",
            pills=[f"👥 {len(_ad)} personas", f"🗓️ {_ahora().strftime('%d/%m/%Y')}"],
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        html_kpis_tab([
            ("Personal", "💼", "#2563eb", f"{_ca['Todos']}", f"en {_areas_con_personal} de {len(DEPARTAMENTOS_ADMIN)} áreas", None),
            ("Activos", "✅", "#16a34a", f"{_ca['Activo']}", f"{_pct(_ca['Activo'], _ca['Todos']):.0f}% del total", _pct(_ca["Activo"], _ca["Todos"])),
            ("Pendientes", "⏳", "#f59e0b", f"{_ca['Pendiente']}", "por activar", _pct(_ca["Pendiente"], _ca["Todos"])),
            ("Inactivos", "⛔", "#ef4444", f"{_ca['Inactivo']}", "sin acceso", _pct(_ca["Inactivo"], _ca["Todos"])),
        ]),
        unsafe_allow_html=True,
    )
    st.markdown('<div class="tb-espacio"></div>', unsafe_allow_html=True)

    @st.dialog("✏️ Editar credencial de Administrador")
    def dialogo_editar_admin(admin_id):
        admin = next((a for a in st.session_state.administradores if a["id"] == admin_id), None)
        if admin is None:
            st.error("El administrador ya no existe.")
            return
        with st.form(f"form_editar_admin_{admin_id}"):
            nombre_e = st.text_input("Nombre completo", value=(admin["nombre"] or "").strip())
            puesto_e = st.text_input("Puesto / Cargo", value=admin["puesto"])
            depto_e = st.selectbox(
                "Departamento",
                DEPARTAMENTOS_ADMIN,
                index=DEPARTAMENTOS_ADMIN.index(admin["departamento"]) if admin["departamento"] in DEPARTAMENTOS_ADMIN else 0,
            )
            estado_e = st.selectbox("Estado", ["Activo", "Pendiente", "Inactivo"], index=["Activo", "Pendiente", "Inactivo"].index(admin["estado"]))
            email_e = st.text_input("Correo electrónico", value=(admin["email"] or "").strip())
            tel_e = st.text_input("Teléfono", value=admin["telefono"])
            nivel_e = st.text_input("Nivel de acceso", value=admin["nivel_acceso"])
            foto_nueva = st.file_uploader("Reemplazar foto (opcional)", type=["jpg", "jpeg", "png"])

            col_a, col_b = st.columns(2)
            guardar = col_a.form_submit_button("💾 Guardar cambios", width="stretch")
            cancelar = col_b.form_submit_button("Cancelar", width="stretch")

            if guardar:
                admin["nombre"] = nombre_e
                admin["puesto"] = puesto_e
                admin["departamento"] = depto_e
                admin["estado"] = estado_e
                admin["email"] = email_e
                admin["telefono"] = tel_e
                admin["nivel_acceso"] = nivel_e
                if foto_nueva is not None:
                    admin["foto_bytes"] = foto_nueva.read()
                    admin["foto"] = None
                st.success("Administrador actualizado.")
                st.rerun()
            if cancelar:
                st.rerun()

    def renderizar_tarjeta_admin(admin, idx):
        with st.container(border=True):
            badge_class = f"badge-{admin['estado'].lower()}"
            st.markdown(
                f"""
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <span class="id-tag">🪪 {admin['id']}</span>
                    <span class="status-badge {badge_class}">{admin['estado']}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            c_foto, c_datos = st.columns([1, 1.8])
            with c_foto:
                st.image(obtener_imagen_usuario(admin), width="stretch")
            with c_datos:
                st.markdown(f"### {(admin['nombre'] or '').strip()}")
                st.markdown(f"**💼 Puesto:** {admin['puesto']}")
                st.markdown(f"**🏢 Área:** `{admin['departamento']}`")

            st.divider()

            with st.expander("📂 Menú de Información Completa", expanded=False):
                tab_contacto_admin, tab_funciones_admin = st.tabs(["📧 Contacto", "⭐ Funciones"])

                with tab_contacto_admin:
                    email_limpio = (admin["email"] or "").strip()
                    link_wa = generar_link_whatsapp(admin["telefono"])

                    st.markdown(f"**Email:** [{email_limpio}](mailto:{email_limpio})")

                    if link_wa:
                        st.markdown(
                            f"""**Teléfono:** {admin['telefono']} 
                            <a href="{link_wa}" target="_blank" class="wa-link">
                                <svg width="14" height="14" viewBox="0 0 24 24">
                                    <path d="M.057 24l1.687-6.163c-1.041-1.804-1.588-3.849-1.587-5.946.003-6.556 5.338-11.891 11.893-11.891 3.181.001 6.167 1.24 8.413 3.488 2.245 2.248 3.481 5.236 3.48 8.414-.003 6.557-5.338 11.892-11.893 11.892-1.99-.001-3.951-.5-5.688-1.448l-6.305 1.654zm6.597-3.807c1.676.995 3.276 1.591 5.392 1.592 5.448 0 9.886-4.434 9.889-9.885.002-5.462-4.415-9.89-9.881-9.892-5.452 0-9.887 4.434-9.889 9.884-.001 2.225.651 3.891 1.746 5.634l-.999 3.648 3.742-.981zm11.387-5.464c-.074-.124-.272-.198-.57-.347-.297-.149-1.758-.868-2.031-.967-.272-.099-.47-.149-.669.149-.198.297-.768.967-.941 1.165-.173.198-.347.223-.644.074-.297-.149-1.255-.462-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.521.151-.172.2-.296.3-.495.099-.198.05-.372-.025-.521-.075-.148-.669-1.611-.916-2.206-.242-.579-.487-.501-.669-.51l-.57-.01c-.198 0-.52.074-.792.372s-1.04 1.016-1.04 2.479 1.065 2.876 1.213 3.074c.149.198 2.095 3.2 5.076 4.487.709.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.695.248-1.29.173-1.414z"/>
                                </svg> WhatsApp
                            </a>""",
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(f"**Teléfono:** {admin['telefono']}")

                    st.markdown(f"**Ubicación:** {admin['ubicacion']}")
                    st.markdown(f"**Nivel de Acceso:** {admin['nivel_acceso']}")
                    st.markdown(f"**Ingreso:** {admin['fecha_ingreso']}")

                with tab_funciones_admin:
                    st.markdown("**Funciones Clave:**")
                    st.write(", ".join([f"`{h}`" for h in admin.get("habilidades", [])]) or "Sin funciones registradas.")

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("✏️ Editar", key=f"edit_adm_{admin['id']}_{idx}", width="stretch"):
                    dialogo_editar_admin(admin["id"])
            with col_btn2:
                if st.session_state.confirmar_borrado_admin == admin["id"]:
                    if st.button("⚠️ Confirmar", key=f"confirm_del_adm_{admin['id']}_{idx}", width="stretch", type="primary"):
                        st.session_state.administradores = [a for a in st.session_state.administradores if a["id"] != admin["id"]]
                        st.session_state.confirmar_borrado_admin = None
                        st.toast(f"Administrador {admin['id']} eliminado.")
                        st.rerun()
                else:
                    if st.button("🗑️ Eliminar", key=f"del_adm_{admin['id']}_{idx}", width="stretch"):
                        st.session_state.confirmar_borrado_admin = admin["id"]
                        st.rerun()

    @st.dialog("➕ Nuevo administrador")
    def dialogo_nuevo_admin():
        with st.form("form_nuevo_admin", clear_on_submit=True):
            c1, c2 = st.columns(2)
            n_nombre = c1.text_input("Nombre completo *")
            n_puesto = c2.text_input("Puesto / Cargo *")
            n_depto = c1.selectbox("Área", DEPARTAMENTOS_ADMIN)
            n_estado = c2.selectbox("Estado", list(ESTADOS_PERSONAL))
            n_email = c1.text_input("Correo electrónico")
            n_tel = c2.text_input("Teléfono")
            n_nivel = c1.selectbox("Nivel de acceso", NIVELES_ACCESO)
            n_foto = st.file_uploader("Foto de perfil", type=["jpg", "jpeg", "png"])
            if st.form_submit_button("💾 Guardar administrador", type="primary", width="stretch"):
                if not n_nombre.strip() or not n_puesto.strip():
                    st.error("Completa los campos obligatorios (*).")
                else:
                    st.session_state.administradores.append({
                        "id": siguiente_id(st.session_state.administradores, "ADM"),
                        "nombre": n_nombre.strip(), "puesto": n_puesto.strip(), "departamento": n_depto,
                        "estado": n_estado, "foto": None, "foto_bytes": n_foto.read() if n_foto else None,
                        "email": n_email or f"{n_nombre.lower().strip().replace(' ', '.')}@empresa.com",
                        "telefono": n_tel or "+52 (55) 0000-0000", "fecha_ingreso": "Reciente",
                        "ubicacion": "Por asignar", "nivel_acceso": n_nivel, "proyectos": [],
                        "habilidades": ["Colaboración"],
                    })
                    st.toast("Administrador agregado.")
                    st.rerun()

    busq_adm, filtro_est_adm, vista_adm, _c_nuevo_adm = barra_filtros_personal("adm", conteo_estados(_ad))
    with _c_nuevo_adm:
        if st.button("➕ Nuevo", key="btn_nuevo_admin", type="primary", width="stretch"):
            dialogo_nuevo_admin()
    admins_filtrados = filtrar_personal(_ad, busq_adm, filtro_est_adm)

    if "Tabla" in vista_adm:
        st.caption(f"{len(admins_filtrados)} de {len(_ad)} personas · clic en el encabezado para ordenar.")
        tabla_personal(admins_filtrados, "administracion", "Área")
    else:
        ICONOS_AREA = {
            "Licitaciones": "📜", "Operaciones": "🛠️", "Auditoria": "🔍", "Finanzas": "💰", "Nomina": "🧾",
            "Movimiento de Personal": "🔁", "Recursos Humanos": "🧑‍🤝‍🧑", "Almacen": "📦", "Juridico": "⚖️",
            "Planeación y Desarrollo": "🧭",
        }
        area_sel = selector_grupo("adm", DEPARTAMENTOS_ADMIN, ICONOS_AREA, admins_filtrados)
        st.caption(f"Mostrando {len(admins_filtrados)} de {len(_ad)} personas.")
        if not admins_filtrados:
            st.markdown('<div class="tb-vacio">Sin resultados. Prueba otra búsqueda o elige "Todos" en el estado.</div>', unsafe_allow_html=True)
        for depto in (DEPARTAMENTOS_ADMIN if area_sel == "Todas" else [area_sel]):
            grupo_a = [a for a in admins_filtrados if a["departamento"] == depto]
            if area_sel == "Todas":
                if not grupo_a:
                    continue
                st.markdown(f'<div class="tb-grupo">{ICONOS_AREA.get(depto, "📁")} {depto} <span>{len(grupo_a)}</span></div>', unsafe_allow_html=True)
            elif not grupo_a:
                st.info(f"No hay personal en el área de {depto} con los filtros actuales.")
            cols_adm = st.columns(4)
            for idx_a, adm in enumerate(grupo_a):
                with cols_adm[idx_a % 4]:
                    renderizar_tarjeta_admin(adm, idx_a)


# ==============================================================================
# PESTAÑA "Seguimiento de Facturación"
# ==============================================================================
ESTATUS_FACTURA = ["Por facturar", "Facturada", "Pagada", "Cancelada"]


def _hoy():
    return pd.Timestamp(_ahora().date())


def _facturas_vencidas(d):
    return (d["Estatus"] == "Facturada") & (d["Vencimiento"] < _hoy())


def _kpis_facturacion(d):
    monto = d["Monto c/IVA"].fillna(0) if len(d) else pd.Series(dtype=float)
    por_est = {e: float(monto[d["Estatus"] == e].sum()) if len(d) else 0.0 for e in ESTATUS_FACTURA}
    facturado = por_est["Facturada"] + por_est["Pagada"]
    venc = d[_facturas_vencidas(d)] if len(d) else d
    monto_venc = float(venc["Monto c/IVA"].fillna(0).sum()) if len(d) else 0.0
    return [
        ("Facturado", "🧾", "#2563eb", _moneda(facturado), f"{int(d['Estatus'].isin(['Facturada', 'Pagada']).sum()) if len(d) else 0} facturas", None),
        ("Cobrado", "✅", "#16a34a", _moneda(por_est["Pagada"]), f"{_pct(por_est['Pagada'], facturado):.0f}% de lo facturado", _pct(por_est["Pagada"], facturado)),
        ("Por cobrar", "⏳", "#f59e0b", _moneda(por_est["Facturada"]), f"{int((d['Estatus'] == 'Facturada').sum()) if len(d) else 0} facturas abiertas", _pct(por_est["Facturada"], facturado)),
        ("Vencido", "⚠️", "#ef4444", _moneda(monto_venc), f"{len(venc)} facturas fuera de plazo", _pct(monto_venc, facturado)),
        ("Por facturar", "📝", "#64748b", _moneda(por_est["Por facturar"]), f"{int((d['Estatus'] == 'Por facturar').sum()) if len(d) else 0} pendientes", None),
    ]


def _visual_facturacion(d):
    c1, c2 = st.columns([1, 1.4])
    monto = d.groupby("Estatus")["Monto c/IVA"].sum().reindex(ESTATUS_FACTURA).fillna(0)
    colores = {"Por facturar": "#94a3b8", "Facturada": "#f59e0b", "Pagada": "#10b981", "Cancelada": "#ef4444"}
    fig = go.Figure(go.Pie(
        labels=monto.index, values=monto.values, hole=0.6, sort=False,
        marker=dict(colors=[colores[e] for e in monto.index], line=dict(color="white", width=2)),
        textinfo="percent", hovertemplate="<b>%{label}</b><br>$%{value:,.2f}<extra></extra>",
    ))
    fig.update_layout(title="<b>Importe por estatus</b>", height=260, margin=dict(l=6, r=6, t=40, b=6),
                      legend=dict(orientation="h", y=-0.05, x=0.5, xanchor="center"), paper_bgcolor="rgba(0,0,0,0)")
    with c1:
        with st.container(border=True):
            mostrar_grafico(fig, key="graf_fact_estatus")
    por_cobrar = (d[d["Estatus"] == "Facturada"].groupby("Dependencia")["Monto c/IVA"].sum()
                  .sort_values(ascending=False).head(8))
    with c2:
        with st.container(border=True):
            if por_cobrar.empty:
                st.markdown('<div class="tb-vacio" style="border:none">Sin facturas abiertas por cobrar.</div>', unsafe_allow_html=True)
            else:
                por_cobrar = por_cobrar.sort_values()
                fig2 = go.Figure(go.Bar(
                    x=por_cobrar.values, y=[v or "(sin dependencia)" for v in por_cobrar.index], orientation="h",
                    marker=dict(color="#f59e0b"), text=[_moneda(v) for v in por_cobrar.values], textposition="outside",
                    cliponaxis=False, hovertemplate="<b>%{y}</b><br>$%{x:,.2f}<extra></extra>",
                ))
                fig2.update_layout(title="<b>Por cobrar · top dependencias</b>", height=260,
                                   margin=dict(l=6, r=70, t=40, b=6), paper_bgcolor="rgba(0,0,0,0)",
                                   plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(showgrid=False, visible=False),
                                   yaxis=dict(type="category"))
                mostrar_grafico(fig2, key="graf_fact_cobrar")


TABLEROS["facturacion"] = {
    "campos": [
        {"n": "Folio", "t": "texto", "req": True},
        {"n": "Contrato", "t": "texto"},
        {"n": "Dependencia", "t": "texto"},
        {"n": "Concepto", "t": "texto"},
        {"n": "Monto c/IVA", "t": "numero", "fmt": "$%.2f"},
        {"n": "Emisión", "t": "fecha"},
        {"n": "Vencimiento", "t": "fecha"},
        {"n": "Fecha de pago", "t": "fecha"},
        {"n": "Estatus", "t": "opcion", "op": ESTATUS_FACTURA},
    ],
    "col_estatus": "Estatus",
    "estatus": ESTATUS_FACTURA,
    "extras": {"⚠️ Vencidas": _facturas_vencidas},
    "kpis": _kpis_facturacion,
    "visual": _visual_facturacion,
    "vacio": "Aún no hay facturas registradas.<br>Usa <b>➕ Agregar</b> o importa tu Excel desde <b>⇅ Excel</b> para ver aquí los indicadores de cobranza.",
}

with pestana_facturacion:
    st.markdown(
        html_banner_tab(
            "📑", "Seguimiento de facturación", "Facturación, cobranza y facturas vencidas en un solo tablero",
            pills=[f"🗓️ {_ahora().strftime('%d/%m/%Y')}", "✏️ Tabla editable"],
        ),
        unsafe_allow_html=True,
    )
    tablero_registros("facturacion")


#===============================================================================
#PESTAÑA "Acuerdos y Convenios"
#===============================================================================
ESTATUS_ACUERDO = ["Borrador", "En revisión", "Vigente", "Vencido", "Cancelado"]


def _acuerdos_por_vencer(d):
    return (d["Estatus"] == "Vigente") & (d["Vigencia hasta"] <= _hoy() + pd.Timedelta(days=DIAS_POR_VENCER))


def _kpis_acuerdos(d):
    n = len(d)
    vig = d[d["Estatus"] == "Vigente"] if n else d
    pv = d[_acuerdos_por_vencer(d)] if n else d
    tramite = int(d["Estatus"].isin(["Borrador", "En revisión"]).sum()) if n else 0
    cli = int((d["Relación"] == "Cliente").sum()) if n else 0
    prov = int((d["Relación"] == "Proveedor").sum()) if n else 0
    monto_vig = float(vig["Monto"].fillna(0).sum()) if n else 0.0
    return [
        ("Acuerdos", "🤝", "#2563eb", f"{n}", f"{cli} con clientes · {prov} con proveedores", None),
        ("Vigentes", "✅", "#16a34a", f"{len(vig)}", f"{_pct(len(vig), n):.0f}% del total", _pct(len(vig), n)),
        (f"Por vencer ({DIAS_POR_VENCER} d)", "⏳", "#f59e0b", f"{len(pv)}", "vigentes que cierran pronto", _pct(len(pv), len(vig))),
        ("En trámite", "📝", "#8b5cf6", f"{tramite}", "borradores y en revisión", _pct(tramite, n)),
        ("Monto vigente", "💰", "#0d9488", _moneda(monto_vig), "suma de acuerdos vigentes", None),
    ]


def _visual_acuerdos(d):
    c1, c2 = st.columns([1.4, 1])
    cuenta = d["Estatus"].value_counts().reindex(ESTATUS_ACUERDO).fillna(0)
    colores = {"Borrador": "#94a3b8", "En revisión": "#8b5cf6", "Vigente": "#10b981", "Vencido": "#ef4444", "Cancelado": "#64748b"}
    fig = go.Figure(go.Bar(
        x=cuenta.index, y=cuenta.values, marker=dict(color=[colores[e] for e in cuenta.index]),
        text=[int(v) for v in cuenta.values], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>%{y} acuerdos<extra></extra>",
    ))
    fig.update_layout(title="<b>Acuerdos por estatus</b>", height=250, margin=dict(l=6, r=6, t=40, b=6),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      yaxis=dict(visible=False), xaxis=dict(title=None))
    with c1:
        with st.container(border=True):
            mostrar_grafico(fig, key="graf_acu_estatus")
    rel = d[d["Relación"] != ""]["Relación"].value_counts()
    with c2:
        with st.container(border=True):
            if rel.empty:
                st.markdown('<div class="tb-vacio" style="border:none">Sin relación cliente/proveedor capturada.</div>', unsafe_allow_html=True)
            else:
                fig2 = go.Figure(go.Pie(
                    labels=rel.index, values=rel.values, hole=0.6,
                    marker=dict(colors=PALETA, line=dict(color="white", width=2)), textinfo="label+value",
                ))
                fig2.update_layout(title="<b>Clientes vs. proveedores</b>", height=250, showlegend=False,
                                   margin=dict(l=6, r=6, t=40, b=6), paper_bgcolor="rgba(0,0,0,0)")
                mostrar_grafico(fig2, key="graf_acu_relacion")


TABLEROS["acuerdos"] = {
    "campos": [
        {"n": "Folio", "t": "texto", "req": True},
        {"n": "Tipo", "t": "opcion", "op": ["Convenio", "Acuerdo", "Convenio modificatorio", "Addendum"]},
        {"n": "Contraparte", "t": "texto", "req": True},
        {"n": "Relación", "t": "opcion", "op": ["Cliente", "Proveedor"]},
        {"n": "Objeto", "t": "texto"},
        {"n": "Fecha de firma", "t": "fecha"},
        {"n": "Vigencia hasta", "t": "fecha"},
        {"n": "Monto", "t": "numero", "fmt": "$%.2f"},
        {"n": "Responsable", "t": "texto"},
        {"n": "Enlace", "t": "link"},
        {"n": "Estatus", "t": "opcion", "op": ESTATUS_ACUERDO},
    ],
    "col_estatus": "Estatus",
    "estatus": ESTATUS_ACUERDO,
    "extras": {"⏳ Por vencer": _acuerdos_por_vencer},
    "kpis": _kpis_acuerdos,
    "visual": _visual_acuerdos,
    "vacio": "Aún no hay acuerdos ni convenios registrados.<br>Usa <b>➕ Agregar</b> o importa tu Excel desde <b>⇅ Excel</b> para ver aquí vigencias y alertas.",
}

with pestana_acuerdos:
    st.markdown(
        html_banner_tab(
            "🤝", "Acuerdos y convenios", "Convenios con clientes y proveedores: vigencias, estatus y alertas",
            pills=[f"🗓️ {_ahora().strftime('%d/%m/%Y')}", "✏️ Tabla editable"],
        ),
        unsafe_allow_html=True,
    )
    tablero_registros("acuerdos")



