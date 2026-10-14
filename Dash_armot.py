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
import mimetypes
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
            if datos_usuario and datos_usuario["clave"] == password:
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
# FILTROS GLOBALES EN CASCADA
# ==============================================================================
st.sidebar.header("🔍 Filtros Globales")

if not df.empty:
    with st.sidebar.expander("📥 Exportar datos filtrados", expanded=False):
        st.download_button(
            "Descargar CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="servicios_filtrados.csv",
            mime="text/csv",
            use_container_width=True,
        )

if not df.empty:
    col_estado = col("estado")
    col_dependencia = col("dependencia")

    estados_disponibles = sorted(df[col_estado].dropna().unique().tolist())
    estados_seleccionados = st.sidebar.multiselect("Seleccionar Estado:", options=estados_disponibles, default=[])

    df_filtrado_estado = df[df[col_estado].isin(estados_seleccionados)] if estados_seleccionados else df.copy()

    dependencias_disponibles = sorted(df_filtrado_estado[col_dependencia].dropna().unique().tolist())
    dependencias_seleccionadas = st.sidebar.multiselect("Seleccionar Dependencia:", options=dependencias_disponibles, default=[])

    df = df_filtrado_estado[df_filtrado_estado[col_dependencia].isin(dependencias_seleccionadas)] if dependencias_seleccionadas else df_filtrado_estado

if not df.empty and "Ejercicio Fiscal" in df.columns:
    ejercicios_disponibles = sorted(df["Ejercicio Fiscal"].dropna().unique().tolist())
    ejercicios_seleccionados = st.sidebar.multiselect("Seleccionar Ejercicio Fiscal:", options=ejercicios_disponibles, default=[])
    df = df[df["Ejercicio Fiscal"].isin(ejercicios_seleccionados)] if ejercicios_seleccionados else df

if not df.empty and "Estatus" in df.columns:
    estatus_disponibles = sorted(df["Estatus"].dropna().unique().tolist())
    estatus_seleccionados = st.sidebar.multiselect("Seleccionar Estatus:", options=estatus_disponibles, default=[])
    df = df[df["Estatus"].isin(estatus_seleccionados)] if estatus_seleccionados else df

if not df.empty:
    col_estado = col("estado")
    col_dependencia = col("dependencia")
    Dependencias_unicas = df[col_dependencia].nunique() if col_dependencia in df.columns else 0
    Total_unidades = df[col("unidades")].sum() if col("unidades") in df.columns else 0
    Total_de_operarios_min_en_contrato = df[col("operarios_min")].sum() if col("operarios_min") in df.columns else 0
    Total_de_operarios_maximos_en_contrato = df[col("operarios_max")].sum() if col("operarios_max") in df.columns else 0
    Total_estados_presentes = df[col_estado].nunique() if col_estado in df.columns else 0
    Total_coordinadores = contar_credenciales_por_puesto("coordinador", "coordinadora")
    Total_gerentes = contar_credenciales_por_puesto("gerente")
    Total_contratos = df[col("Contratos")].nunique() if col("Contratos") in df.columns else 0

    Cantidad_formateada_min_sin_IVA = f"${df[col('monto_min_sin_iva')].sum():,.2f}" if col("monto_min_sin_iva") in df.columns else "$0.00"
    Cantidad_formateada_min_con_IVA = f"${df[col('monto_min_con_iva')].sum():,.2f}" if col("monto_min_con_iva") in df.columns else "$0.00"
    Cantidad_formateada_max_sin_IVA = f"${df[col('monto_max_sin_iva')].sum():,.2f}" if col("monto_max_sin_iva") in df.columns else "$0.00"
    Cantidad_formateada_max_con_IVA = f"${df[col('monto_max_con_iva')].sum():,.2f}" if col("monto_max_con_iva") in df.columns else "$0.00"
else:
    Dependencias_unicas = 0
    Total_unidades = 0
    Total_de_operarios_min_en_contrato = 0
    Total_de_operarios_maximos_en_contrato = 0
    Total_estados_presentes = 0
    Total_coordinadores = contar_credenciales_por_puesto("coordinador", "coordinadora")
    Total_gerentes = contar_credenciales_por_puesto("gerente")
    Cantidad_formateada_min_sin_IVA = "$0.00"
    Cantidad_formateada_min_con_IVA = "$0.00"
    Cantidad_formateada_max_sin_IVA = "$0.00"
    Cantidad_formateada_max_con_IVA = "$0.00"

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
        r["monto_max_dep"] = float(m["Monto total"].max()) if not m.empty else 0.0
    if {col_est, col("monto_max_con_iva")}.issubset(d.columns):
        e = d.groupby(col_est)[col("monto_max_con_iva")].sum().reset_index()
        e.columns = ["Estado", "Monto total"]
        e = e.sort_values("Monto total", ascending=False)
        e["Monto (M)"] = e["Monto total"] / 1e6
        r["est_montos"] = e
        r["monto_max_est"] = float(e["Monto total"].max()) if not e.empty else 0.0
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
            t = t.sort_values("_fin").drop_duplicates(subset=[ccon], keep="last")
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
            agg["Contrato"] = (ccon, "nunique")
        t = d.groupby(col_dep).agg(**agg).reset_index()
        if not tiene_con:
            t["Contrato"] = ""
    hoy = pd.Timestamp(_ahora().date())
    t["Estatus"] = _estatus_vigencia(t["_fin"], hoy)
    t = t.sort_values("_fin").reset_index(drop=True)
    orden = list(dict.fromkeys(t[col_dep].tolist()))
    fig = px.timeline(
        t, x_start="_ini", x_end="_fin", y=col_dep, color="Estatus",
        color_discrete_map={"Vigente": COLOR_VIGENTE, "Por vencer": COLOR_POR_VENCER,
                            "Vencido": COLOR_VENCIDO, "Sin fecha": COLOR_SIN_FECHA},
        category_orders={"Estatus": ["Vigente", "Por vencer", "Vencido"]},
        hover_data={"Contrato": True, "_ini": "|%d/%m/%Y", "_fin": "|%d/%m/%Y", col_dep: False},
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
    datos = t[[col_dep, "Contrato", "_ini", "_fin", "Estatus"]].copy()
    datos = datos.rename(columns={col_dep: "Dependencia", "_ini": "Inicio", "_fin": "Término"})
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
    d = datos.sort_values("Monto total", ascending=False).copy()
    if not grande and len(d) > TOP_BARRAS_COMPACTO:
        cabeza = d.head(TOP_BARRAS_COMPACTO - 1)
        resto = d.iloc[TOP_BARRAS_COMPACTO - 1:]
        fila = pd.DataFrame({eje: [f"{etiqueta_otros} ({len(resto)})"],
                             "Monto total": [float(resto["Monto total"].sum())],
                             "Monto (M)": [float(resto["Monto (M)"].sum())]})
        d = pd.concat([cabeza, fila], ignore_index=True)
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
def html_encabezado(periodo_txt):
    fecha = _ahora().strftime("%d/%m/%Y")
    return (
        '<div class="rg-banner"><div class="rg-banner-l"><div class="rg-logo">📈</div><div>'
        '<div class="rg-title">Resumen Global</div>'
        f'<div class="rg-subtitle">Servicios y contratos · {periodo_txt}</div></div></div>'
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
        st.markdown('<div class="rg-panel-tit">Controles</div>', unsafe_allow_html=True)

        anios = _anios_disponibles(df)
        opciones_periodo = [str(a) for a in anios] + ["Todos"]
        periodo_defecto = str(PERIODO_FISCAL_INICIAL) if PERIODO_FISCAL_INICIAL in anios else "Todos"
        periodo = st.radio(
            "Periodo fiscal", opciones_periodo, index=opciones_periodo.index(periodo_defecto),
            horizontal=True, key="periodo_fiscal_resumen",
        )
        df_p = df if (periodo == "Todos" or df.empty) else df[_mascara_periodo(df, int(periodo))]

        empresas_sel = []
        if COL_EMPRESA in df_p.columns:
            opciones_emp = sorted(df_p[COL_EMPRESA].dropna().astype(str).unique().tolist())
            empresas_sel = st.multiselect(
                "Empresa operando", opciones_emp, default=[], placeholder="Todas", key=f"empresas_resumen_{periodo}",
            )
        DV_DF = df_p[df_p[COL_EMPRESA].astype(str).isin(empresas_sel)] if empresas_sel else df_p
        DV = _preparar_datos(DV_DF)
        KP = _calcular_kpis(DV_DF)
        INS = _calcular_insights(DV_DF, DV, KP)
        PERIODO_TXT = f"Ejercicio fiscal {periodo}" if periodo != "Todos" else "Todos los periodos"

        # Los límites de los ejes dependen de los datos filtrados: la clave incluye los filtros
        # para que, al cambiarlos, los sliders se reinicien a su rango completo.
        firma = hashlib.md5(f"{periodo}|{'|'.join(empresas_sel)}".encode("utf-8")).hexdigest()[:8]
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

    alto_fila = max(180, int((alto_vista - ALTO_FIJO_TABLERO) / 2) - ALTO_CHROME_TARJETA)
    ph_encabezado.markdown(html_encabezado(PERIODO_TXT), unsafe_allow_html=True)

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
    # COMPONENTE INTERFAZ GRÁFICA GOOGLE DRIVE
    # ==============================================================================
    def render_drive_explorer(drive_json_data):
        html_code = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
            <link href="https://fonts.googleapis.com/icon?family=Material+Icons+Outlined" rel="stylesheet">
            <style>
                * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Roboto', sans-serif; }}
                body {{ background: #f8fafd; color: #1f1f1f; padding: 10px; }}
                .drive-container {{ background: #ffffff; border-radius: 16px; border: 1px solid #e0e3e7; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
                .top-bar {{ display: flex; align-items: center; padding: 12px 24px; border-bottom: 1px solid #f1f3f4; gap: 16px; }}
                .search-box {{ display: flex; align-items: center; background-color: #e9eef6; padding: 8px 16px; border-radius: 24px; flex-grow: 1; max-width: 600px; }}
                .search-box input {{ border: none; background: transparent; outline: none; margin-left: 10px; width: 100%; font-size: 14px; }}
                .breadcrumb {{ display: flex; align-items: center; padding: 16px 24px; font-size: 18px; font-weight: 500; color: #1f1f1f; gap: 8px; }}
                .breadcrumb-item {{ cursor: pointer; border-radius: 8px; padding: 4px 8px; transition: background 0.2s; }}
                .breadcrumb-item:hover {{ background-color: #f1f3f4; }}
                .breadcrumb-separator {{ color: #747775; font-size: 18px; }}
                .content-section {{ padding: 0 24px 24px 24px; }}
                .section-title {{ font-size: 14px; font-weight: 500; color: #444746; margin-bottom: 12px; margin-top: 8px; }}
                .grid-container {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin-bottom: 24px; }}
                .folder-card {{ display: flex; align-items: center; padding: 12px 16px; background-color: #f7f9fc; border: 1px solid #e0e3e7; border-radius: 12px; cursor: pointer; transition: all 0.2s ease; }}
                .folder-card:hover {{ background-color: #eaeef4; }}
                .folder-card .material-icons-outlined {{ color: #444746; margin-right: 12px; }}
                .folder-name {{ font-size: 14px; font-weight: 500; color: #1f1f1f; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
                .file-card {{ background-color: #f7f9fc; border: 1px solid #e0e3e7; border-radius: 12px; overflow: hidden; cursor: pointer; transition: all 0.2s ease; display: flex; flex-direction: column; }}
                .file-card:hover {{ box-shadow: 0 2px 6px rgba(0,0,0,0.1); border-color: #c4c7c5; }}
                .file-preview {{ height: 120px; background-color: #ffffff; display: flex; align-items: center; justify-content: center; border-bottom: 1px solid #e0e3e7; }}
                .file-preview img {{ max-height: 100%; width: 100%; object-fit: cover; }}
                .file-info {{ padding: 12px; display: flex; align-items: center; gap: 10px; }}
                .file-icon {{ font-size: 20px; }}
                .file-icon.pdf {{ color: #ea4335; }}
                .file-icon.doc {{ color: #4285f4; }}
                .file-icon.sheet {{ color: #0f9d58; }}
                .file-icon.image {{ color: #ea4335; }}
                .file-details {{ overflow: hidden; }}
                .file-title {{ font-size: 13px; font-weight: 500; color: #1f1f1f; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
                .file-meta {{ font-size: 11px; color: #747775; margin-top: 2px; }}
                .modal-overlay {{ display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); z-index: 1000; align-items: center; justify-content: center; }}
                .modal-content {{ background: #fff; border-radius: 12px; width: 85%; max-width: 900px; height: 85%; display: flex; flex-direction: column; overflow: hidden; }}
                .modal-header {{ padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e0e3e7; }}
                .modal-body {{ flex-grow: 1; display: flex; align-items: center; justify-content: center; background: #f1f3f4; }}
                .modal-body iframe {{ width: 100%; height: 100%; border: none; }}
            </style>
        </head>
        <body>
        <div class="drive-container">
            <div class="top-bar">
                <div class="search-box">
                    <span class="material-icons-outlined">search</span>
                    <input type="text" id="searchInput" placeholder="Buscar en Drive" onkeyup="filterItems()">
                </div>
            </div>
            <div class="breadcrumb" id="breadcrumbContainer"></div>
            <div class="content-section">
                <div id="foldersSection">
                    <div class="section-title">Carpetas</div>
                    <div class="grid-container" id="foldersGrid"></div>
                </div>
                <div id="filesSection">
                    <div class="section-title">Archivos</div>
                    <div class="grid-container" id="filesGrid"></div>
                </div>
            </div>
        </div>

        <div class="modal-overlay" id="previewModal">
            <div class="modal-content">
                <div class="modal-header">
                    <span id="modalTitle" style="font-weight: 500;"></span>
                    <span class="material-icons-outlined" style="cursor:pointer;" onclick="closeModal()">close</span>
                </div>
                <div class="modal-body" id="modalBody"></div>
            </div>
        </div>

        <script>
            const driveData = {json.dumps(drive_json_data)};
            let currentPath = [driveData];

            function getCurrentFolder() {{ return currentPath[currentPath.length - 1]; }}

            function render() {{
                const currentFolder = getCurrentFolder();
                const breadcrumbEl = document.getElementById('breadcrumbContainer');
                breadcrumbEl.innerHTML = '';
                
                currentPath.forEach((folder, index) => {{
                    const item = document.createElement('span');
                    item.className = 'breadcrumb-item';
                    item.innerText = folder.name;
                    item.onclick = () => navigateToBreadcrumb(index);
                    breadcrumbEl.appendChild(item);

                    if (index < currentPath.length - 1) {{
                        const sep = document.createElement('span');
                        sep.className = 'material-icons-outlined breadcrumb-separator';
                        sep.innerText = 'chevron_right';
                        breadcrumbEl.appendChild(sep);
                    }}
                }});

                const foldersGrid = document.getElementById('foldersGrid');
                const foldersSection = document.getElementById('foldersSection');
                foldersGrid.innerHTML = '';
                
                if (currentFolder.folders && currentFolder.folders.length > 0) {{
                    foldersSection.style.display = 'block';
                    currentFolder.folders.forEach(folder => {{
                        const card = document.createElement('div');
                        card.className = 'folder-card';
                        card.onclick = () => openFolder(folder);
                        card.innerHTML = `<span class="material-icons-outlined">folder</span><span class="folder-name">${{folder.name}}</span>`;
                        foldersGrid.appendChild(card);
                    }});
                }} else {{
                    foldersSection.style.display = 'none';
                }}

                const filesGrid = document.getElementById('filesGrid');
                const filesSection = document.getElementById('filesSection');
                filesGrid.innerHTML = '';

                if (currentFolder.files && currentFolder.files.length > 0) {{
                    filesSection.style.display = 'block';
                    currentFolder.files.forEach(file => {{
                        const card = document.createElement('div');
                        card.className = 'file-card';
                        card.onclick = () => openFilePreview(file);
                        
                        const previewContent = file.previewImg 
                            ? `<img src="${{file.previewImg}}" alt="preview">` 
                            : `<span class="material-icons-outlined file-icon ${{file.type}}" style="font-size: 48px;">${{file.icon}}</span>`;

                        card.innerHTML = `
                            <div class="file-preview">${{previewContent}}</div>
                            <div class="file-info">
                                <span class="material-icons-outlined file-icon ${{file.type}}">${{file.icon}}</span>
                                <div class="file-details">
                                    <div class="file-title">${{file.name}}</div>
                                    <div class="file-meta">${{file.size}} • ${{file.date}}</div>
                                </div>
                            </div>
                        `;
                        filesGrid.appendChild(card);
                    }});
                }} else {{
                    filesSection.style.display = 'none';
                }}
            }}

            function openFolder(folder) {{ currentPath.push(folder); render(); }}
            function navigateToBreadcrumb(index) {{ currentPath = currentPath.slice(0, index + 1); render(); }}
            
            function openFilePreview(file) {{
                const modal = document.getElementById('previewModal');
                document.getElementById('modalTitle').innerText = file.name;
                const body = document.getElementById('modalBody');
                
                if (file.url) {{
                    body.innerHTML = `<iframe src="${{file.url}}" allow="autoplay"></iframe>`;
                }} else {{
                    body.innerHTML = `<div style="text-align:center; padding: 20px;"><p>No hay previsualización disponible.</p></div>`;
                }}
                modal.style.display = 'flex';
            }}

            function closeModal() {{ document.getElementById('previewModal').style.display = 'none'; }}
            function filterItems() {{
                const query = document.getElementById('searchInput').value.toLowerCase();
                document.querySelectorAll('.folder-card').forEach(el => {{
                    el.style.display = el.innerText.toLowerCase().includes(query) ? 'flex' : 'none';
                }});
                document.querySelectorAll('.file-card').forEach(el => {{
                    el.style.display = el.innerText.toLowerCase().includes(query) ? 'flex' : 'none';
                }});
            }}

            render();
        </script>
        </body>
        </html>
        """
        # El iframe se estira hasta el alto de la ventana del navegador.
        js_alto = (
            "function ajustarAlto() { try { const f = window.frameElement; "
            "if (f) f.style.height = Math.max(520, window.parent.innerHeight - 190) + 'px'; } catch (e) {} }\n"
            "ajustarAlto(); window.addEventListener('resize', ajustarAlto);\n"
        )
        html_code = html_code.replace("render();\n        </script>", "render();\n" + js_alto + "</script>", 1)
        components.html(html_code, height=760, scrolling=True)


    # ==============================================================================
    # EJECUCIÓN PRINCIPAL DE LA APP
    # ==============================================================================
    st.title("📁 Explorador de Google Drive")

    with st.spinner("Cargando estructura de Google Drive..."):
        datos_drive = construir_arbol_drive(FOLDER_ID_RAIZ)
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/Nora%20Garcia.jpeg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 12345678",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 2 (Gerente)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-100", "nombre": "Maria Jose Diaz", "puesto": "Auxiliar Administrativo",
                "departamento": "CDMX", "estado": "Inactivo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Maria%20Jose%20Diaz.jpeg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 30682627",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Auxiliar Admvo.)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-100", "nombre": "Renata Espitia", "puesto": "Auxiliar Administrativo",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Renata%20Espitia.jpeg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 30573454",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Auxiliar Admvo.)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-100", "nombre": "Monica Neira", "puesto": "Auxiliar Administrativo",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Monica%20Neira.jpeg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 14761951",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Auxiliar Admvo.)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1002", "nombre": "Alberto Torres Gutierrez", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://cdn.phototourl.com/member/2026-08-24-edca077c-9102-418c-a376-1c751ce6c889.jpg",
                "email": "alberto.at840@gmail.com", "telefono": "(+52) 55 31119554",
                "fecha_ingreso": "01-Febrero-2021", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 28 Unidades () ", "Central del Sur : 1 Unidades (Tlalpan)"],
                "habilidades": ["Docker", "Python", "Terraform"],
            },
            {
                "id": "USR-1003", "nombre": "Alejandro Gomez", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Alejandro%20Gomez.jpeg",
                "email": "pako.gomez.p@gmail.com", "telefono": "(+52) 5535377489",
                "fecha_ingreso": "10-Agosto-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 13 Unidades ()", "Secretaria de las Mujeres : 2 Unidades (Milpa Alta)"],
                "habilidades": ["Figma", "User Research", "Prototipado"],
            },
            {
                "id": "USR-1004", "nombre": "Amairani Ramirez", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Amairani%20Ramirez.jpeg",
                "email": "ramireztorresamairani@gmail.com", "telefono": "(+52) 5521756716",
                "fecha_ingreso": "01-Julio-2025", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["ATRAPI : 2 Unidades (Coyoacan)", "IMSS-Bienestar CDMX : 32 Unidades ()", "SPOTMET : 3 Unidades (Benito Juarez, Azcapozalco, Iztacalco)"],
                "habilidades": ["Penetration Testing", "SIEM", "Criptografía"],
            },
            {
                "id": "USR-1005", "nombre": "Anayeli Lazaro", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://cdn.phototourl.com/member/2026-08-24-d3b25557-e292-4617-b689-8a0bc4a0bad3.jpg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Armando%20Medina.jpeg",
                "email": "medina.971@outlook.com ", "telefono": "(+52) 5531042782",
                "fecha_ingreso": "20-Enero-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 20 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1007", "nombre": "Eduardo Valerdi", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Eduardo%20Valerdi.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Enrique%20Gonzalez.png",
                "email": "enriquegonzalezg1963@gmail.com", "telefono": "(+52) 5531411830",
                "fecha_ingreso": "10-Marzo-2023", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 18 Unidades ()", "Secretaria de las Mujeres : 3 Unidades (Tlahuac, Xochimilco)"],
                "habilidades": ["Gestión de Proyectos", "Comunicación Efectiva", "Liderazgo"],
            },
            {
                "id": "USR-1009", "nombre": "Erika Cristan", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Erika%20Cristan.jpeg",
                "email": "ceakire@gmail.com", "telefono": "(+52) 5534988267",
                "fecha_ingreso": "20-Enero-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinadora)",
                "proyectos": ["IMSS-Bienestar CDMX : 20 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1010", "nombre": "Fernando Dali", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "",
                "email": "Sin correo ", "telefono": "(+52) Sin numero",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IPN : 5 Unidades (Gustavo A. Madero, Miguel Hidalgo)"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1011", "nombre": "Fernando Valerdi", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Fernando%20Valerdi.jpeg",
                "email": "fernando.valerdi.rebollo@gmail.com", "telefono": "(+52) 5530830567",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 10 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1012", "nombre": "Francisco Garcia", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Francisco%20Garcia.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Gloria%20Hernandez.jpeg",
                "email": "gloriacoordi.08@gmail.com", "telefono": "(+52) 5531065274",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMMS-Bienestar CDMX : 30 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1014", "nombre": "Guadalupe Barbosa", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Guadalupe%20Barbosa.jpg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Jhon%20Ramos.jpeg?h=8192&max-h=8192&fit=clip",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Jose%20Luis%20Ruiz.jpeg",
                "email": "munejl14@hotmail.com ", "telefono": "(+52) 5527117537",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 12 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1017", "nombre": "Juan Pablo Cruz", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Juan%20Pablo%20Cruz.jpeg",
                "email": "so.ni1110@hotmail.com", "telefono": "(+52) 5521756417",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["FINABIEN : 2 Unidades ()", "IMSS-Bienestar CDMX : 24 Unidades ()", "ISSSTE : 11 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1018", "nombre": "Julio Barrientos", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Julio%20Cesar%20Barrientos.jpeg",
                "email": "julibarri589@gmail.com", "telefono": "(+52) 5521529515",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 19 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1019", "nombre": "Manuel Hernandez", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Manuel%20Hernandez.jpeg",
                "email": "mhernandez.p@youhoo.com", "telefono": "(+52) 5510589560",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 11 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1020", "nombre": "Maria Almanza", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Maria%20Almanza.jpeg",
                "email": "almanza93marii@gmail.com", "telefono": "(+52) 5530591633",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 1 Unidades ()", "ISSSTE : 9 Unidades ()", "PLAZA ARTZ : 1 Unidad ()", "PROFECO : 8 Unidades ()", "Salud Federal : 6 Unidades ()", "SHCP : 8 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1021", "nombre": "Marisol Meraz", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Marisol%20Meraz.jpeg",
                "email": "marimerlop8560@gmail.com", "telefono": "(+52) 5551956442",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 17 Unidades ()", "Salud Federal : 4 Unidades ()", "SEBIEN : 18 Unidades ()", "SEGIAGUA :  31 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1022", "nombre": "Michelle Carlon", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Michelle%20Carlon.jpeg",
                "email": "Sin datos", "telefono": "(+52) sin datos",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IPN : # Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1023", "nombre": "Oscar Lavadores", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Oscar%20Lavadores.jpeg",
                "email": "oscarlpineda0123@gmail.com", "telefono": "(+52) 5531337212",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 11 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1024", "nombre": "Roberto Reyes", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Roberto%20Reyes.jpeg",
                "email": "reyesz.robertojavier@gmail.com", "telefono": "(+52) 5526922378",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["ISSSTE : 21 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1025", "nombre": "Victor Munguia", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Victor%20Munguia.jpeg",
                "email": "brian_jes@hotmail.com", "telefono": "(+52) 5522404313",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 9 Unidades ()", "METROBUS : 1 Unidad ()", "SAPCI : 21 Unidades ()", "Secretaria de las Mujeres : 2 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1026", "nombre": "Victor Uzcanga", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Victor%20Uzcanga.jpeg",
                "email": "vic.uzcanga_chavez@hotmail.com", "telefono": "(+52) 5530785781",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 22 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1101", "nombre": "Pilar Hernandez", "puesto": "Gerente de Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Pilar%20Hernandez.jpeg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 72 22694403",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 2 (Gerente)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1102", "nombre": "Andrea Feliciano", "puesto": "Auxiliar Administrativo",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://cdn.phototourl.com/member/2026-08-24-90980387-a04e-4f41-a11f-1def4d2cd75f.jpg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 31186668",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel # (Auxiliar Admvo.)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1103", "nombre": "Alexandra Gomora", "puesto": "Auxiliar Administrativo",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://cdn.phototourl.com/member/2026-08-24-9281c913-aeca-4e8f-9546-d641ea106af7.jpg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 30787614",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel # (Auxiliar Admvo.)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1104", "nombre": "Maria Eugenia Alonso", "puesto": "Auxiliar Administrativo",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Maria%20Eugenia%20Alonso.jpeg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 31037494",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel # (Auxiliar Admvo.)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1105", "nombre": "Adriana Zarco", "puesto": "Coordinadora Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Adriana%20Zarco.jpeg",
                "email": "---", "telefono": "(+52) 55 30476909",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["ISEM : 49 Unidades", "Poder Judicial Edo. Mex : 11 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1106", "nombre": "Alejandro Giacomo", "puesto": "Coordinador Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Alejandro%20Giacomo.jpeg",
                "email": "---", "telefono": "(+52) 55 31200565",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 64 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1107", "nombre": "Carlos Zarco", "puesto": "Coordinador Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Carlos%20Zarco.jpeg",
                "email": "---", "telefono": "(+52) 55 31217189",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 59 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1108", "nombre": "Francisco Anzaldo", "puesto": "Coordinador Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Francisco%20Anzaldo.jpeg",
                "email": "---", "telefono": "(+52) 55 31318418",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 46 Unidades", "ISSSTE : 6 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1109", "nombre": "Humbert Campuzano", "puesto": "Coordinador Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://cdn.phototourl.com/member/2026-08-24-6401e903-3b49-4393-b827-34ac67346803.jpg",
                "email": "---", "telefono": "(+52) 55 30702088",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 47 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1110", "nombre": "Javier Salgado", "puesto": "Coordinador Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Javier%20Salgado.jpeg",
                "email": "---", "telefono": "(+52) 55 31037269",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["ISEM : 38 Unidades",  "ISSSTE : 14 Unidades", "Poder Judicial Edo. Mex : 14 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1111", "nombre": "Jonathan Mercado", "puesto": "Coordinador Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://cdn.phototourl.com/member/2026-08-24-92bb253f-c764-4312-ba8f-23ed2ccd324a.jpg",
                "email": "---", "telefono": "(+52) 55 31271396",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 53 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1112", "nombre": "Mauricio Rojas", "puesto": "Coordinador Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://cdn.phototourl.com/member/2026-08-24-31690df0-85ed-4d0d-bf55-40b4ef3d0148.jpg",
                "email": "---", "telefono": "(+52) 55 31347301",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 56 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1113", "nombre": "Nancy Giacomo", "puesto": "Coordinadora Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://cdn.phototourl.com/member/2026-08-24-52399856-e6e0-48ad-986d-58fe3e8f72c6.jpg",
                "email": "---", "telefono": "(+52) 55 30825691",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Toluca",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 60 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1114", "nombre": "Ulises Mociño", "puesto": "Coordinador Toluca",
                "departamento": "Toluca", "estado": "Activo",
                "foto": "https://cdn.phototourl.com/member/2026-08-24-edd3d8bb-f51a-4b2c-a290-c7cf0ce033fa.jpg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Adolfo%20Sanabria.jpeg",
                "email": "", "telefono": "(+52) 55 91678805",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 2 (Gerente)",
                "proyectos": ["Oficialia Mayor", "Poder Judicial"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1201", "nombre": "Miguel Alexis Martinez Martinez", "puesto": "Auxiliar Administrativo",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Alexis%20Martinez.jpeg",
                "email": "", "telefono": "(+52) 55 31057105",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Auxiliar Admvo.)",
                "proyectos": ["Oficialia Mayor", "Poder Judicial"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1202", "nombre": "José Luis Rivera", "puesto": "Auxiliar Administrativo",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Jose%20Luis%20Rivera.jpeg",
                "email": "", "telefono": "(+52) 55 31057105",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Auxiliar Admvo.)",
                "proyectos": ["Oficialia Mayor", "Poder Judicial"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1203", "nombre": "Carlos Cesar Serrano Ramirez", "puesto": "Coordinador Edo. México",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Cesar%20Serrano.jpeg",
                "email": "", "telefono": "(+52) 56 28213647",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Poder Judicial : 24 Unidades"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1204", "nombre": "Eduardo Ramírez López", "puesto": "Coordinador Edo. México",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Eduardo%20Ramirez.jpeg",
                "email": "", "telefono": "(+52) 56 37268956",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 47 Unidades"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1205", "nombre": "José Ascensión Arreola González", "puesto": "Coordinador Edo. México",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Jose%20Arreola.jpeg",
                "email": "", "telefono": "(+52) 56 27915122",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 55 Unidades"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1206", "nombre": "María Magdalena García Cruz", "puesto": "Coordinador Edo. México",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Magdalena%20Garcia.jpeg",
                "email": "", "telefono": "(+52) 56 17907344",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 22 Unidades"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1207", "nombre": "Mauro Araujo Gallegos", "puesto": "Coordinador Edo. México",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Mauro%20Araujo.jpeg",
                "email": "", "telefono": "(+52) 55 21969640",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 61 Unidades"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1208", "nombre": "Omar Terreros Mendoza", "puesto": "Coordinador Edo. México",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Omar%20Terreros.jpeg",
                "email": "", "telefono": "(+52) 55 71111709",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 51 Unidades"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1209", "nombre": "Samuel Rosas Canales", "puesto": "Coordinador Edo. México",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Samuel%20Rosas.jpeg",
                "email": "", "telefono": "(+52) 55 49593643",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almacén",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Oficialia Mayor : 32 Unidades"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1300", "nombre": "Berenice Bellacetin Peña", "puesto": " Gerente de Foráneos",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Bere%20Bellacetin.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Renata%20Pe%C3%B1a.jpeg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 21400127",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel # (Auxiliar Admvo.)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1302", "nombre": "Adan Elias Ceja", "puesto": "Coordinador Regional de Tabasco",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Elias%20Ceja.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/ALEJANDRA%20SANCHEZ.jpeg",
                "email": "---", "telefono": "(+52) 55 31136817",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Tabasco",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS - Bienestar Tabasco : 117 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1305", "nombre": "Alan Reyna", "puesto": "Coordinador de Proyecto",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Alan%20Reyna.jpg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Arturo%20Sanchez.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/EMILIANO%20MENDEZ.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/GABRIELA%20ROJAS.jpeg",
                "email": "---", "telefono": "(+52) 55 31213187",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Tabasco",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS - Bienestar Tabasco : 109 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1312", "nombre": "Iveth Broca", "puesto": "Coordinadora Tabasco",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Iveth%20Broca.jpeg",
                "email": "---", "telefono": "(+52) 55 31098614",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Tabasco",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS - Bienestar Tabasco : 125 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1313", "nombre": "Ivonne Garcia Martinez", "puesto": "Coordinadora Foranea",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Ivonne%20Garcia.jpeg",
                "email": "---", "telefono": "(+52) 55 30838497",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS - Bienestar Colima : 135 Unidades", " IPN Foraneo : 40 Unidades", "PRODECON : 8 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1314", "nombre": "Jair Estrada", "puesto": "Coordinador Foraneo",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Jair%20Estrada.jpeg",
                "email": "---", "telefono": "(+52) 55 30527704",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["INFONAVIT Foraneo : 26 Unidades", "CONAFE : 28 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1315", "nombre": "Jazmin Gomez", "puesto": "Coordinadora Tabasco",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/JAZMIN%20GOMEZ.jpeg",
                "email": "---", "telefono": "(+52) 55 30857671",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas Tabasco",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS - Bienestar Tabasco : 128 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1316", "nombre": "Jesus Salazar Hinojosa", "puesto": "Coordinador de Proyecto",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Jesus%20Salazar%20Hinojosa.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Fernandad%20Acevedo.jpeg",
                "email": "---", "telefono": "(+52) 55 29687664",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["Banjercito : 14 Unidades", "PRODECON : 9 Unidades"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1318", "nombre": "Melisa Martinez", "puesto": "Coordinadora Foranea",
                "departamento": "Foraneos", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/Melissa%20Martinez.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Viridiana%20Zu%C3%B1iga.jpeg",
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

    st.title("🪪 Coordinadores")
    st.caption("Tarjetas de identificación interactivas: ver QR, descargar credencial, editar, eliminar y administrar servicios como en Excel.")
    st.divider()

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

    with st.sidebar:
        st.header("🔍 Buscador y Filtros de Coordinadores")

        busqueda = st.text_input("Buscar por Nombre, Puesto o ID:", "", key="busqueda_coord")
        filtro_estado = st.multiselect(
            "Estado de Credencial:", ["Activo", "Pendiente", "Inactivo"],
            default=["Activo", "Pendiente", "Inactivo"], key="filtro_estado_coord",
        )
        columnas_grid = st.slider("Columnas de tarjetas:", min_value=1, max_value=5, value=5)

        if st.button("🔄 Restablecer filtros"):
            st.session_state.busqueda_coord = ""
            st.session_state.filtro_estado_coord = ["Activo", "Pendiente", "Inactivo"]
            st.rerun()

        st.divider()

        st.subheader("➕ Agregar Nueva Credencial")
        with st.expander("Formulario de registro"):
            with st.form("form_nuevo_usuario", clear_on_submit=True):
                nuevo_nombre = st.text_input("Nombre Completo")
                nuevo_puesto = st.selectbox("Puesto / Cargo:", ["Coordinador", "Coordinadora", "Gerente", "Administrativo"])
                nuevo_id = st.text_input("ID de Usuario*", value=f"USR-{len(st.session_state.usuarios) + 1001}")
                nuevo_depto = st.selectbox("Área geográfica", REGIONES)
                nuevo_estado = st.selectbox("Estado", ["Activo", "Pendiente", "Inactivo"])
                nuevo_email = st.text_input("Correo Electrónico")
                nuevo_tel = st.text_input("Teléfono")
                nuevo_nivel = st.selectbox("Nivel de Acceso", ["Nivel 1 (Coordinador)", "Nivel 2 (Gerente)", "Nivel 3 (Administrativo)", "Nivel 4 (Director)"])
                nueva_foto = st.file_uploader("Subir Foto de Perfil", type=["jpg", "jpeg", "png"])

                submitted = st.form_submit_button("Guardar Credencial")
                if submitted:
                    ids_existentes = {u["id"] for u in st.session_state.usuarios}
                    if not nuevo_nombre or not nuevo_id:
                        st.error("Por favor completa los campos obligatorios (*).")
                    elif nuevo_id in ids_existentes:
                        st.error(f"El ID '{nuevo_id}' ya existe. Usa un identificador distinto.")
                    else:
                        st.session_state.usuarios.append({
                            "id": nuevo_id, "nombre": nuevo_nombre, "puesto": nuevo_puesto,
                            "departamento": nuevo_depto, "estado": nuevo_estado,
                            "foto": None, "foto_bytes": nueva_foto.read() if nueva_foto else None,
                            "email": nuevo_email or f"{nuevo_nombre.lower().replace(' ', '.')}@empresa.com",
                            "telefono": nuevo_tel or "+52 (55) 0000-0000",
                            "fecha_ingreso": "Reciente", "ubicacion": "Por asignar",
                            "nivel_acceso": nuevo_nivel, "proyectos": [], "servicios": [],
                            "habilidades": ["Colaboración"],
                        })
                        st.success("¡Credencial agregada exitosamente!")
                        st.rerun()

    busqueda_lower = busqueda.lower().strip()
    usuarios_filtrados = [
        u for u in st.session_state.usuarios
        if (
            busqueda_lower in u["nombre"].lower()
            or busqueda_lower in u["id"].lower()
            or busqueda_lower in u["puesto"].lower()
        )
        and (not filtro_estado or u["estado"] in filtro_estado)
    ]

    st.markdown(f"Mostrando **{len(usuarios_filtrados)}** credencial(es) de **{len(st.session_state.usuarios)}** totales.")

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

    tab_cdmx, tab_toluca, tab_edomex, tab_foraneos = st.tabs(
        ["🏙️ CDMX", "🌆 Toluca", "🗺️ Estado de México", "📍 Foráneos"]
    )

    with tab_cdmx:
        renderizar_grid([u for u in usuarios_filtrados if u["departamento"] == "CDMX"], columnas_grid)
    with tab_toluca:
        renderizar_grid([u for u in usuarios_filtrados if u["departamento"] == "Toluca"], columnas_grid)
    with tab_edomex:
        renderizar_grid([u for u in usuarios_filtrados if u["departamento"] == "Estado de México"], columnas_grid)
    with tab_foraneos:
        renderizar_grid([u for u in usuarios_filtrados if u["departamento"] == "Foraneos"], columnas_grid)






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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Alofonso%20Acevedo.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Julio%20Ibarra.jpg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Cassandra%20Sosa.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Karla%20Ayala.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Rodrigo%20Rebolledo.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Abigail%20Pacheco.jpeg",
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
                "foto": "https://cdn.phototourl.com/member/2026-08-17-63c02bcd-f57e-4f9d-ad2a-ab7d56673746.jpg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Nicte%20Gonzalez.jpg",
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
                "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/Cristian Merino.jpeg",
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
                "puesto": "----",
                "departamento": "Operaciones",
                "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Alejandro%20Vazquez.png",
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
                "puesto": "Subdirectora de Auditoria",
                "departamento": "Auditoria",
                "estado": "Activo",
                "foto": "",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Daniel%20Vega.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Antonio%20Cadena.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Brianda%20Barr%C3%B3n.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Jessyca%20Mendoza.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Ana%20Leon.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Astrid%20Hernandez.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/David%20Hernandez.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Susana%20Ortiz.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Osvaldo%20Palomino.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Cristian%20Alvado.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Lorena%20Chavarria.jpeg",
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
                "foto": "",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Tania.jpeg",
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
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Fernando%20Rodriguez.jpg",
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
                "foto": "",
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

    st.title("💼 Administradores")
    st.caption("Gestión de credenciales de personal administrativo por departamento.")
    st.divider()

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

    tabs_admin = st.tabs(DEPARTAMENTOS_ADMIN)
    for i, depto in enumerate(DEPARTAMENTOS_ADMIN):
        with tabs_admin[i]:
            admins_depto = [a for a in st.session_state.administradores if a["departamento"] == depto]
            if admins_depto:
                cols_adm = st.columns(4)
                for idx_a, adm in enumerate(admins_depto):
                    with cols_adm[idx_a % 4]:
                        renderizar_tarjeta_admin(adm, idx_a)
            else:
                st.info(f"No hay personal asignado en la área de {depto}.")


# ==============================================================================
# PESTAÑA "Seguimiento de Facturación"
# ==============================================================================
with pestana_facturacion:
    st.title("📑 Seguimiento de Facturación")
    st.caption("Módulo para consulta de estatus presupuestal y cobranza.")




#===============================================================================
#PESATAÑA "Acuerdos y Convenios"
#===============================================================================
with pestana_acuerdos:
    st.title("🤝 Acuerdos y Convenios")
    st.caption("Módulo para consulta de acuerdos y convenios con clientes y/o proveedores.")