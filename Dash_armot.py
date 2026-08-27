import io
import re
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import qrcode
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import hashlib

try:
    from google import genai
except ImportError:
    genai = None

BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "Armot_Color.png"
EXCEL_PATH = BASE_DIR / "Servicio.xlsx"

st.set_page_config(
    page_title="Dashboard Armot",
    layout="wide",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "📊",
)

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
# UTILIDADES PARA CREDENCIALES Y WHATSAPP
# =========================================================================
def generar_link_whatsapp(telefono: str) -> str:
    """Extrae únicamente los dígitos del teléfono y genera una URL de WhatsApp."""
    digitos = re.sub(r"\D", "", str(telefono or ""))
    if digitos:
        # Asume formato de México (+52) si no trae código de país largo
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
col_izq, col_centro, col_der = st.columns([1, 2, 1])
with col_centro:
    _, col_img, _ = st.columns([1, 1.5, 1])
    with col_img:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), use_container_width=True)
        else:
            st.markdown("# ARMOT")

st.markdown("---")
st.write("")
st.write("")


# ==============================================================================
# CARGA Y PROCESAMIENTO DE DATOS
# ==============================================================================
def normalizar_dataframe(df_in):
    if df_in.empty:
        return df_in
    df_in.columns = [str(c).strip() for c in df_in.columns]
    return df_in

@st.cache_data
def cargar_datos():
    try:
        return normalizar_dataframe(pd.read_excel(EXCEL_PATH, engine="openpyxl"))
    except Exception:
        return pd.DataFrame()


df = cargar_datos()

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
                st.error("⚠️ El archivo 'Servicio.xlsx' está vacío o no se pudo cargar.")
            else:
                with st.spinner("Pensando..."):
                    num_dep = df["Dependencia"].nunique() if "Dependencia" in df.columns else 0
                    tot_uni = df["N° de Unidades"].sum() if "N° de Unidades" in df.columns else 0
                    ele_min = df["Elementos minimos"].sum() if "Elementos minimos" in df.columns else 0
                    ele_max = df["Elementos máximos"].sum() if "Elementos máximos" in df.columns else 0
                    monto_min = f"${df['Monto mínimo con IVA'].sum():,.2f}" if "Monto mínimo con IVA" in df.columns else "$0.00"
                    monto_max = f"${df['Monto máximo con IVA'].sum():,.2f}" if "Monto máximo con IVA" in df.columns else "$0.00"

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

--- CONTEXTO DE DATOS DE LA EMPRESA (SERVICIO.XLSX) ---
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
    col_estado = "Estados" if "Estados" in df.columns else "Estado"
    col_dependencia = "Dependencias" if "Dependencias" in df.columns else "Dependencia"

    estados_disponibles = sorted(df[col_estado].dropna().unique().tolist())
    estado_seleccionado = st.sidebar.selectbox("Seleccionar Estado:", options=["Todos los Estados"] + estados_disponibles)

    df_filtrado_estado = df[df[col_estado] == estado_seleccionado] if estado_seleccionado != "Todos los Estados" else df.copy()

    dependencias_disponibles = sorted(df_filtrado_estado[col_dependencia].dropna().unique().tolist())
    dependencia_seleccionada = st.sidebar.selectbox("Seleccionar Dependencia:", options=["Todas las Dependencias"] + dependencias_disponibles)

    df = df_filtrado_estado[df_filtrado_estado[col_dependencia] == dependencia_seleccionada] if dependencia_seleccionada != "Todas las Dependencias" else df_filtrado_estado

if not df.empty:
    col_estado = "Estados" if "Estados" in df.columns else "Estado"
    Dependencias_unicas = df["Dependencia"].nunique() if "Dependencia" in df.columns else 0
    Total_unidades = df["N° de Unidades"].sum() if "N° de Unidades" in df.columns else 0
    Total_de_operarios_min_en_contrato = df["Elementos minimos"].sum() if "Elementos minimos" in df.columns else 0
    Total_de_operarios_maximos_en_contrato = df["Elementos máximos"].sum() if "Elementos máximos" in df.columns else 0
    Total_estados_presentes = df[col_estado].nunique() if col_estado in df.columns else 0
    Total_coordinadores = df["Coordinador"].nunique() if "Coordinador" in df.columns else 0

    Cantidad_formateada_min_sin_IVA = f"${df['Monto mínimo sin IVA'].sum():,.2f}" if "Monto mínimo sin IVA" in df.columns else "$0.00"
    Cantidad_formateada_min_con_IVA = f"${df['Monto mínimo con IVA'].sum():,.2f}" if "Monto mínimo con IVA" in df.columns else "$0.00"
    Cantidad_formateada_max_sin_IVA = f"${df['Monto máximo sin IVA'].sum():,.2f}" if "Monto máximo sin IVA" in df.columns else "$0.00"
    Cantidad_formateada_max_con_IVA = f"${df['Monto máximo con IVA'].sum():,.2f}" if "Monto máximo con IVA" in df.columns else "$0.00"
else:
    Dependencias_unicas = 0
    Total_unidades = 0
    Total_de_operarios_min_en_contrato = 0
    Total_de_operarios_maximos_en_contrato = 0
    Total_estados_presentes = 0
    Total_coordinadores = 0
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

st.markdown("<h1 style='text-align: center;'>Panel de Control</h1>", unsafe_allow_html=True)

pestana_resumen_global, pestana_coordinadores, pestana_administracion, pestana_facturacion = st.tabs(
    ["Resumen Global", "Coordinadores", "Administración", "Seguimiento de facturación"]
)

st.markdown("---")

# ==============================================================================
# PESTAÑA "Resumen Global"
# ==============================================================================
with pestana_resumen_global:
    st.subheader("Resumen Global")

    col1, col2, col3 = st.columns(3)
    col1.metric(label="Total de Servicios", value=f"{int(Dependencias_unicas)}")
    col2.metric(label="Presencia", value=f"{int(Total_estados_presentes)} Estados")
    col3.metric(label="Total de Unidades", value=f"{int(Total_unidades):,}")

    st.subheader("")
    col_1_1, col_2_2, col_3_3 = st.columns(3)
    col_1_1.metric(label="Elementos mínimos", value=f"{int(Total_de_operarios_min_en_contrato):,}")
    col_2_2.metric(label="Elementos máximos", value=f"{int(Total_de_operarios_maximos_en_contrato):,}")
    col_3_3.metric(label="Total de Coordinadores", value=f"{int(Total_coordinadores)}")

    st.subheader("")
    col_1, col_2, col_3, col_4 = st.columns(4)
    col_1.metric(label="Mínimo sin IVA", value=Cantidad_formateada_min_sin_IVA)
    col_2.metric(label="Mínimo con IVA", value=Cantidad_formateada_min_con_IVA)
    col_3.metric(label="Máximo sin IVA", value=Cantidad_formateada_max_sin_IVA)
    col_4.metric(label="Máximo con IVA", value=Cantidad_formateada_max_con_IVA)

    st.write("")
    st.write("")
    st.write("")
    st.markdown("---")

    st.subheader("Dispersion de Servicios Armot")
    if not df.empty and "Dependencia" in df.columns:
        df_agrupado = df.groupby("Dependencia").agg(
            {"N° de Unidades": "sum", "Monto máximo con IVA": "sum", "Elementos máximos": "sum"}
        ).reset_index()
        df_agrupado.columns = ["Dependencia", "Cantidad de unidades por dependencia", "Monto total por dependencia", "Operarios Máximos"]

        max_unidades = int(df_agrupado["Cantidad de unidades por dependencia"].max()) if not df_agrupado.empty else 0
        if max_unidades > 0:
            rango_unidades = st.slider(
                "Filtrar por rango de unidades (Eje X):", min_value=0, max_value=max_unidades,
                value=(0, max_unidades), step=1, key="slider_dispersion_x_original",
            )
            df_disp_filtrado = df_agrupado[
                (df_agrupado["Cantidad de unidades por dependencia"] >= rango_unidades[0])
                & (df_agrupado["Cantidad de unidades por dependencia"] <= rango_unidades[1])
            ]
        else:
            df_disp_filtrado = df_agrupado
            rango_unidades = (0, 0)

        if not df_disp_filtrado.empty:
            fig = px.scatter(
                df_disp_filtrado, x="Cantidad de unidades por dependencia", y="Monto total por dependencia",
                color="Dependencia", size="Operarios Máximos", size_max=100, hover_name="Dependencia",
                labels={"Cantidad de unidades por dependencia": "Número de Unidades", "Monto total por dependencia": "Monto Máximo con IVA ($MXN)"},
            )
            fig.update_layout(
                height=650, title="<b>Gráfica de Dispersión de Servicios 2026</b>", title_x=0.5, showlegend=True,
                legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5, title_text="<b>Dependencias:</b>", font=dict(size=11)),
                yaxis=dict(tickprefix="$", tickformat=",.2f"),
                xaxis=dict(range=[rango_unidades[0], rango_unidades[1]], fixedrange=True),
            )
            st.plotly_chart(fig, width="stretch", on_select="rerun")
        else:
            st.warning("No existen dependencias que coincidan con el rango de unidades seleccionado.")
    else:
        st.info("No hay datos disponibles para mostrar la gráfica de dispersión.")

    st.markdown("---")
    st.subheader("Vigencia de los Contratos")
    if not df.empty and set(["Inicio", "Fin", "Dependencia"]).issubset(df.columns):
        df_timeline = df.copy()
        df_timeline["Inicio"] = pd.to_datetime(df_timeline["Inicio"], errors="coerce")
        df_timeline["Fin"] = pd.to_datetime(df_timeline["Fin"], errors="coerce")
        df_timeline = df_timeline.dropna(subset=["Inicio", "Fin", "Dependencia"])
        fig = px.timeline(df_timeline, x_start="Inicio", x_end="Fin", y="Dependencia", color="Dependencia")
        fig.update_yaxes(categoryorder="category descending")
        fig.update_layout(
            height=500, title="<b>Vigencia de Contratos 2026</b>", title_x=0.5,
            xaxis_title="Meses de Contratación (2026)", yaxis_title="Dependencias", showlegend=False,
            xaxis=dict(tickformat="%b\n%Y", dtick="M1", ticklabelmode="period"),
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No hay datos de fechas disponibles para mostrar la vigencia.")

    st.markdown("---")
    st.subheader("📍 Desglose Geográfico por Estado")
    if not df.empty:
        col_estado = "Estados" if "Estados" in df.columns else "Estado"
        col_dependencia = "Dependencias" if "Dependencias" in df.columns else "Dependencia"
        if col_estado in df.columns and col_dependencia in df.columns and "N° de Unidades" in df.columns:
            tabla_estados = df.groupby(col_estado).agg({col_dependencia: "nunique", "N° de Unidades": "sum"}).reset_index()
            tabla_estados.columns = ["Estado", "Cantidad de Dependencias", "Cantidad de Unidades"]
            tabla_estados = tabla_estados.sort_values(by="Cantidad de Unidades", ascending=False).reset_index(drop=True)
            st.dataframe(tabla_estados, width="stretch", hide_index=True)
            st.caption(f"Mostrando un total de {len(tabla_estados)} entidades federativas con infraestructura asignada.")
        else:
            st.info("No existen las columnas necesarias para el desglose geográfico.")
    else:
        st.info("No hay datos disponibles para estructurar la tabla por Estados.")

    st.subheader("📋 Análisis Financiero por Dependencia")
    if not df.empty and set(["Dependencia", "Monto máximo con IVA"]).issubset(df.columns):
        Dependencias_montos = df.groupby("Dependencia")["Monto máximo con IVA"].sum().reset_index()
        monto_max_dep = float(Dependencias_montos["Monto máximo con IVA"].max()) if not Dependencias_montos.empty else 0.0
        limite_y_dep = st.slider(
            "Ajustar límite máximo del eje vertical (Presupuesto):", min_value=0.0,
            max_value=monto_max_dep if monto_max_dep > 0 else 1.0, value=monto_max_dep,
            step=100000.0, format="$%,.2f", key="slider_y_dep",
        )
        barras_por_dependencia = px.bar(
            Dependencias_montos, x="Dependencia", y="Monto máximo con IVA", color="Monto máximo con IVA",
            color_continuous_scale="RdBu", title="<b>Monto Máximo con IVA por Dependencia</b>",
            labels={"Monto máximo con IVA": "Monto Total ($MXN)", "Dependencia": "Dependencia"},
        )
        barras_por_dependencia.update_layout(
            title_x=0.5, height=550,
            yaxis=dict(tickprefix="$", tickformat=",.2f", range=[0, limite_y_dep], fixedrange=True),
            xaxis=dict(tickangle=-30, type="category", fixedrange=True),
        )
        st.plotly_chart(barras_por_dependencia, width="stretch")
    else:
        st.info("No hay datos disponibles para la gráfica de dependencias.")

    st.subheader("📍 Distribución de los montos de los contratos por Estado")
    if not df.empty:
        col_estado = "Estados" if "Estados" in df.columns else "Estado"
        if col_estado in df.columns and "Monto máximo con IVA" in df.columns:
            Estados_montos = df.groupby(col_estado)["Monto máximo con IVA"].sum().reset_index()
            Estados_montos.columns = ["Estado", "Monto Máximo con IVA"]
            Estados_montos = Estados_montos.sort_values(by="Monto Máximo con IVA", ascending=False)
            monto_max_est = float(Estados_montos["Monto Máximo con IVA"].max()) if not Estados_montos.empty else 0.0
            limite_y_est = st.slider(
                "Ajustar límite máximo del eje vertical (Presupuesto por Estado):", min_value=0.0,
                max_value=monto_max_est if monto_max_est > 0 else 1.0, value=monto_max_est,
                step=500000.0, format="$%,.2f", key="slider_y_est",
            )
            barras_por_estado = px.bar(
                Estados_montos, x="Estado", y="Monto Máximo con IVA", color="Monto Máximo con IVA",
                color_continuous_scale="Viridis", title="<b>Inversión Máxima con IVA por Estado</b>",
                labels={"Monto Máximo con IVA": "Monto Máximo con IVA ($MXN)"},
            )
            barras_por_estado.update_layout(
                title_x=0.5, height=550,
                yaxis=dict(tickprefix="$", tickformat=",.2f", range=[0, limite_y_est], fixedrange=True),
                xaxis=dict(tickangle=-45, type="category", fixedrange=True),
            )
            st.plotly_chart(barras_por_estado, width="stretch")
        else:
            st.info("Columnas incompletas para la gráfica por estado.")
    else:
        st.info("No hay datos disponibles para la gráfica de estados.")

    st.header("Distribución de empresas operando en los servicios")
    if not df.empty and set(["Empresa operando", "Dependencia"]).issubset(df.columns):
        empresas = df.groupby("Empresa operando", dropna=False)["Dependencia"].nunique().reset_index(name="Numero de dependencias")
        colores = px.colors.qualitative.Safe
        fig = go.Figure(data=[go.Pie(
            labels=empresas["Empresa operando"], values=empresas["Numero de dependencias"], hole=0.4,
            marker=dict(colors=colores), textinfo="percent+label", insidetextorientation="radial",
        )])
        fig.update_layout(
            showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
            margin=dict(t=20, b=20, l=20, r=20),
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No hay datos disponibles para mostrar las empresas operando.")


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
                "foto": "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=300&auto=format&fit=crop&q=80",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 12345678",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 2 (Gerente)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-100", "nombre": "Maria Jose Diaz", "puesto": "Auxiliar Administrativo",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Maria%20Jose%20Diaz.jpeg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 30682627",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas CDMX¿",
                "nivel_acceso": "Nivel # (Auxiliar Admvo.)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-100", "nombre": "Renata Espitia", "puesto": "Auxiliar Administrativo",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Renata%20Espitia.jpeg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 30573454",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas CDMX¿",
                "nivel_acceso": "Nivel # (Auxiliar Admvo.)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-100", "nombre": "Monica Neira", "puesto": "Auxiliar Administrativo",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://6a8cbbe897833836f658517e.imgix.net/sandbox/Monica%20Neira.jpeg",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 14761951",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas CDMX¿",
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
                "foto": "",
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
                "foto": "https://cdn.phototourl.com/member/2026-08-24-a63c0c4a-0cbe-447b-9803-f8cc36351551.jpg",
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
                "foto": "",
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
                "id": "USR-1200", "nombre": "Adolfo Sanabria Jiménez", "puesto": " Gerente del Estado de México",
                "departamento": "Estado de México", "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=300&auto=format&fit=crop&q=80",
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 12345678",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas Almamcen",
                "nivel_acceso": "Nivel 2 (Gerente)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
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
                "foto": "",
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
        columnas_grid = st.slider("Columnas de tarjetas:", min_value=1, max_value=5, value=4)

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
                    ["📧 Contacto", "🛡️ Resumen", "📊 Servicios (Excel)", "⭐ Perfil"]
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
                    st.markdown("**Habilidades Clave:**")
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
    "Finanzas",
    "Nomina",
    "Movimiento de Personal",
    "Recursos Humanos",
    "Juridico",
    "Almacen",
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
                "foto": "https://cdn.phototourl.com/member/2026-08-17-110813c4-4bdd-42f7-8e99-29054e3ba08d.jpg",
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
                "id": "ADM-4001",
                "nombre": "Nayeli",
                "puesto": "Directora de Finanzas",
                "departamento": "Finanzas",
                "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=300&auto=format&fit=crop&q=80",
                "email": "finanzas@empresa.com",
                "telefono": "(+52) 55 33445566",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 4 (Directivo)",
                "proyectos": ["Presupuesto Anual : 1 Unidad ()"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-5001",
                "nombre": "Norma Fuentes",
                "puesto": "Gerente de Nomina",
                "departamento": "Nomina",
                "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=300&auto=format&fit=crop&q=80",
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
                "foto": "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=300&auto=format&fit=crop&q=80",
                "email": "finanzas@empresa.com",
                "telefono": "(+52) 55 33445566",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 2 (Analista)",
                "proyectos": ["Presupuesto Anual : 1 Unidad ()"],
                "habilidades": ["Auditoría", "Facturación", "Excel Avanzado"],
            },
            {
                "id": "ADM-6001",
                "nombre": "Daniel Vega",
                "puesto": "Movimiento de Personal",
                "departamento": "Movimiento de Personal",
                "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=300&auto=format&fit=crop&q=80",
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
                "nombre": "Damaris",
                "puesto": "Gerente de Recursos Humanos",
                "departamento": "Recursos Humanos",
                "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=300&auto=format&fit=crop&q=80",
                "email": "finanzas@empresa.com",
                "telefono": "(+52) 55 33445566",
                "fecha_ingreso": "01-Septiembre-2021",
                "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 2 (Gerente)",
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
                "foto": "",
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
                "foto": "",
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
                cols_adm = st.columns(3)
                for idx_a, adm in enumerate(admins_depto):
                    with cols_adm[idx_a % 3]:
                        renderizar_tarjeta_admin(adm, idx_a)
            else:
                st.info(f"No hay personal asignado en la área de {depto}.")


# ==============================================================================
# PESTAÑA "Seguimiento de Facturación"
# ==============================================================================
with pestana_facturacion:
    st.title("📑 Seguimiento de Facturación")
    st.caption("Módulo para consulta de estatus presupuestal y cobranza.")
   