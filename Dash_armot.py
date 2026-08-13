# Requiere además de lo ya instalado:
#   pip install qrcode[pil] openpyxl
#
# CAMBIOS EN ESTA VERSIÓN
# ------------------------
# 1) Se corrigió la pestaña "Coordinadores": el bloque que pegaste tenía
#    indentación rota (los `with st.title(...)` de Toluca / Edo. México /
#    Foráneos estaban sueltos dentro de un `if` sin `with` que los contuviera,
#    lo que provocaba IndentationError y no dejaba correr la app).
# 2) La pestaña Coordinadores ahora usa 4 sub-pestañas (CDMX, Toluca,
#    Estado de México, Foráneos) que filtran automáticamente por el campo
#    "departamento" de cada credencial — ya no hay bloques repetidos y rotos
#    por región, hay una sola función que dibuja las tarjetas y se reutiliza.
# 3) NUEVO: cada credencial tiene una pestaña "📊 Servicios (Excel)" dentro de
#    su menú desplegable con una tabla editable (st.data_editor) donde se
#    puede modificar/añadir/eliminar los servicios asignados (Dependencia,
#    Unidades, Ubicación) como si fuera Excel. También se puede:
#      - Descargar esos servicios como archivo .xlsx real
#      - Subir un .xlsx editado para reemplazar los servicios de golpe
# 4) Los "proyectos" (texto libre tipo "IMSS-Bienestar CDMX : 28 Unidades
#    (Tlahuac)") se parsean automáticamente a filas estructuradas
#    (Dependencia / Unidades / Ubicación) la primera vez que se cargan.

import io
import re

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.figure_factory as ff
import plotly.graph_objects as go
import qrcode
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

import google.generativeai as genai

st.set_page_config(
    page_title="Dashboard Armot", layout="wide", page_icon="Armot_Color.png"
)

# =========================================================================
# CONFIGURACIÓN DE IA SEGURA (PARA LOCAL Y GITHUB)
# =========================================================================
if "GEMINI_API_KEY" in st.secrets:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"].strip()
    genai.configure(api_key=GEMINI_API_KEY)
else:
    st.error("⚠️ No se encontró la clave GEMINI_API_KEY en los secretos de Streamlit.")
    GEMINI_API_KEY = None


def obtener_modelo_gemini():
    if not GEMINI_API_KEY:
        return None
    try:
        return genai.GenerativeModel("gemini-1.5-flash")
    except Exception as e:
        st.error(f"Error al inicializar Gemini: {e}")
        return None


model_gemini = obtener_modelo_gemini()


# =========================================================================
# UTILIDADES PARA CREDENCIALES
# =========================================================================
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
    iniciales = "".join([p[0].upper() for p in nombre.split() if p][:2]) or "?"
    paleta = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#0891b2", "#ea580c"]
    color = paleta[abs(hash(nombre)) % len(paleta)]

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
        return Image.open(io.BytesIO(foto_bytes)).convert("RGB")
    if isinstance(foto, str) and foto:
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
    draw.text((x_texto, 150), usuario.get("nombre", ""), fill="black", font=font_nombre)
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


# --- NUEVO: parseo de "proyectos" (texto libre) a filas de servicios (tabla editable) ---
_PATRON_SERVICIO = re.compile(r"^(.*?)\s*:\s*(\d+)\s*Unidad(?:es)?\s*\(?([^)]*)\)?\s*$")


def parsear_servicio_texto(texto):
    m = _PATRON_SERVICIO.match(texto.strip())
    if m:
        return {
            "Dependencia": m.group(1).strip(),
            "Unidades": int(m.group(2)),
            "Ubicación": m.group(3).strip(),
        }
    return {"Dependencia": texto.strip(), "Unidades": 0, "Ubicación": ""}


def asegurar_servicios_estructurados(usuario):
    """La primera vez que se ve a un usuario, convierte su lista de texto
    'proyectos' en filas estructuradas 'servicios' (Dependencia/Unidades/
    Ubicación) editables tipo Excel."""
    if "servicios" not in usuario:
        usuario["servicios"] = [parsear_servicio_texto(p) for p in usuario.get("proyectos", [])]
    return usuario["servicios"]


def exportar_servicios_excel(usuario) -> bytes:
    df_serv = pd.DataFrame(usuario.get("servicios", []) or [{"Dependencia": "", "Unidades": 0, "Ubicación": ""}])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_serv.to_excel(writer, index=False, sheet_name="Servicios")
    return buf.getvalue()


# --- ENCABEZADO CENTRADO CON LOGO AJUSTADO ---
col_izq, col_centro, col_der = st.columns([1, 2, 1])
with col_centro:
    _, col_img, _ = st.columns([1, 1.5, 1])
    with col_img:
        st.image("Armot_Color.png", use_container_width=True)

st.markdown("---")
st.write("")
st.write("")


# ==============================================================================
# CARGA Y PROCESAMIENTO DE DATOS
# ==============================================================================
@st.cache_data
def cargar_datos():
    try:
        return pd.read_excel("Servicio.xlsx", engine="openpyxl")
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
            if model_gemini is None:
                st.error("⚠️ El modelo de Gemini no está inicializado correctamente. Revisa tu API Key.")
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
                            lambda x: x.str.lower().str.contains("|".join(palabras_clave))
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
                        "preguntas del usuario basándote estrictamente en el resumen de métricas y la tabla provista. "
                        "Sé ejecutivo, claro, preciso y responde siempre en español. No inventes datos fuera del contexto dado."
                    )

                    bloque_contenido = [
                        f"--- INSTRUCCIONES DEL SISTEMA ---\n{instrucciones_sistema}\n\n"
                        f"--- CONTEXTO DE DATOS DE LA EMPRESA (SERVICIO.XLSX) ---\n"
                        f"- Número de Dependencias Únicas: {num_dep}\n"
                        f"- Total de Unidades: {tot_uni}\n"
                        f"- Elementos Mínimos de Seguridad: {ele_min}\n"
                        f"- Elementos Máximos de Seguridad: {ele_max}\n"
                        f"- Monto Mínimo con IVA Global de la empresa: {monto_min}\n"
                        f"- Monto Máximo con IVA Global de la empresa: {monto_max}\n"
                        f"{nota_contexto}\n\n"
                        f"--- MUESTRA DE FILAS DEL DATAFRAME ---\n"
                        f"{muestra_tabla}\n\n"
                        f"--- PREGUNTA A RESPONDER ---\n"
                        f"Pregunta del usuario: {prompt_ia}"
                    ]

                    try:
                        respuesta = model_gemini.generate_content(
                            contents=bloque_contenido, generation_config={"temperature": 0.2}
                        )
                        if respuesta and respuesta.text:
                            st.markdown(respuesta.text)
                            st.session_state.chat_history.append({"role": "assistant", "content": respuesta.text})
                        else:
                            st.warning("La IA recibió los datos pero no generó texto. Intenta reformular tu pregunta.")
                    except Exception as e:
                        st.error(f"Ocurrió un problema al procesar la respuesta: {e}")


# ==============================================================================
# FILTROS GLOBALES EN CASCADA (para el Excel de servicios)
# ==============================================================================
st.sidebar.header("🔍 Filtros Globales")

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
    Dependencias_unicas = df["Dependencia"].nunique()
    Total_unidades = df["N° de Unidades"].sum()
    Total_de_operarios_min_en_contrato = df["Elementos minimos"].sum()
    Total_de_operarios_maximos_en_contrato = df["Elementos máximos"].sum()
    Total_estados_presentes = df[col_estado].nunique()
    Total_coordinadores = df["Coordinador"].nunique() if "Coordinador" in df.columns else 0

    Cantidad_formateada_min_sin_IVA = f"${df['Monto mínimo sin IVA'].sum():,.2f}"
    Cantidad_formateada_min_con_IVA = f"${df['Monto mínimo con IVA'].sum():,.2f}"
    Cantidad_formateada_max_sin_IVA = f"${df['Monto máximo sin IVA'].sum():,.2f}"
    Cantidad_formateada_max_con_IVA = f"${df['Monto máximo con IVA'].sum():,.2f}"
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
    </style>
    """
)

st.markdown("<h1 style='text-align: center;'>Panel de Control</h1>", unsafe_allow_html=True)

pestana_resumen_global, pestana_coordinadores, pestana_administradores = st.tabs(
    ["Resumen Global", "Coordinadores", "Administradores"]
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
    if not df.empty:
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
            st.plotly_chart(fig, use_container_width=True, on_select="rerun")
        else:
            st.warning("No existen dependencias que coincidan con el rango de unidades seleccionado.")
    else:
        st.info("No hay datos disponibles para mostrar la gráfica de dispersión.")

    st.markdown("---")
    st.subheader("Vigencia de los Contratos")
    if not df.empty:
        df["Inicio"] = pd.to_datetime(df["Inicio"], errors="coerce")
        df["Fin"] = pd.to_datetime(df["Fin"], errors="coerce")
        fig = px.timeline(df, x_start="Inicio", x_end="Fin", y="Dependencia", color="Dependencia")
        fig.update_yaxes(categoryorder="category descending")
        fig.update_layout(
            height=500, title="<b>Vigencia de Contratos 2026</b>", title_x=0.5,
            xaxis_title="Meses de Contratación (2026)", yaxis_title="Dependencias", showlegend=False,
            xaxis=dict(tickformat="%b\n%Y", dtick="M1", ticklabelmode="period"),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay datos de fechas disponibles para mostrar la vigencia.")

    st.markdown("---")
    st.subheader("📍 Desglose Geográfico por Estado")
    if not df.empty:
        col_estado = "Estados" if "Estados" in df.columns else "Estado"
        col_dependencia = "Dependencias" if "Dependencias" in df.columns else "Dependencia"
        tabla_estados = df.groupby(col_estado).agg({col_dependencia: "nunique", "N° de Unidades": "sum"}).reset_index()
        tabla_estados.columns = ["Estado", "Cantidad de Dependencias", "Cantidad de Unidades"]
        tabla_estados = tabla_estados.sort_values(by="Cantidad de Unidades", ascending=False).reset_index(drop=True)
        st.dataframe(tabla_estados, use_container_width=True, hide_index=True)
        st.caption(f"Mostrando un total de {len(tabla_estados)} entidades federativas con infraestructura asignada.")
    else:
        st.info("No hay datos disponibles para estructurar la tabla por Estados.")

    st.subheader("📋 Análisis Financiero por Dependencia")
    if not df.empty:
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
        st.plotly_chart(barras_por_dependencia, use_container_width=True)
    else:
        st.info("No hay datos disponibles para la gráfica de dependencias.")

    st.subheader("📍 Distribución de los montos de los contratos por Estado")
    if not df.empty:
        col_estado = "Estados" if "Estados" in df.columns else "Estado"
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
        st.plotly_chart(barras_por_estado, use_container_width=True)
    else:
        st.info("No hay datos disponibles para la gráfica de estados.")

    st.header("Distribución de empresas operando en los servicios")
    if not df.empty:
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
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay datos disponibles para mostrar las empresas operando.")


# ==============================================================================
# PESTAÑA "Coordinadores" — CREDENCIALES INTERACTIVAS POR REGIÓN
# ==============================================================================
REGIONES = ["CDMX", "Toluca", "Estado de México", "Foraneos"]

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
                "email": "elena.rostova@empresa.com", "telefono": "(+52) 55 ",
                "fecha_ingreso": "15-Marzo-2019", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 2 (Gerente)",
                "proyectos": ["Proyecto Quantum", "IA Biomédica"],
                "habilidades": ["Liderazgo", "Machine Learning", "Genómica"],
            },
            {
                "id": "USR-1002", "nombre": "Alberto Torres Gutierrez", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1560250097-0b93528c311a?w=300&auto=format&fit=crop&q=80",
                "email": "alberto.at840@gmail.com", "telefono": "(+52) 55 31119554",
                "fecha_ingreso": "01-Febrero-2021", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 28 Unidades () ", "Central del Sur : 1 Unidades (Tlalpan)"],
                "habilidades": ["Docker", "Python", "Terraform"],
            },
            {
                "id": "USR-1003", "nombre": "Alejandro Gomez ", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=300&auto=format&fit=crop&q=80",
                "email": "pako.gomez.p@gmail.com", "telefono": "(+52) 5535377489",
                "fecha_ingreso": "10-Agosto-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 13 Unidades ()", "Secretaria de las Mujeres : 2 Unidades (Milpa Alta)"],
                "habilidades": ["Figma", "User Research", "Prototipado"],
            },
            {
                "id": "USR-1004", "nombre": "Amairani Ramirez", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=300&auto=format&fit=crop&q=80",
                "email": "ramireztorresamairani@gmail.com", "telefono": "(+52) 5521756716",
                "fecha_ingreso": "01-Julio-2025", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["ATRAPI : 2 Unidades (Coyoacan)", "IMSS-Bienestar CDMX : 32 Unidades ()", "SPOTMET : 3 Unidades (Benito Juarez, Azcapozalco, Iztacalco)"],
                "habilidades": ["Penetration Testing", "SIEM", "Criptografía"],
            },
            {
                "id": "USR-1005", "nombre": "Anayeli Lazaro", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=300&auto=format&fit=crop&q=80",
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
                "foto": "https://images.unsplash.com/photo-1560250097-0b93528c311a?w=300&auto=format&fit=crop&q=80",
                "email": "medina.971@outlook.com ", "telefono": "(+52) 5531042782",
                "fecha_ingreso": "20-Enero-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 20 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1007", "nombre": "Eduardo Valerdi", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=300&auto=format&fit=crop&q=80",
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
                "foto": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=300&auto=format&fit=crop&q=80",
                "email": "enriquegonzalezg1963@gmail.com", "telefono": "(+52) 5531411830",
                "fecha_ingreso": "10-Marzo-2023", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 18 Unidades ()", "Secretaria de las Mujeres : 3 Unidades (Tlahuac, Xochimilco)"],
                "habilidades": ["Gestión de Proyectos", "Comunicación Efectiva", "Liderazgo"],
            },
            {
                "id": "USR-1009", "nombre": "Erika Cristan", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=300&auto=format&fit=crop&q=80",
                "email": "ceakire@gmail.com", "telefono": "(+52) 5534988267",
                "fecha_ingreso": "20-Enero-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinadora)",
                "proyectos": ["IMSS-Bienestar CDMX : 20 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1010", "nombre": "Fernando Dali", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=300&auto=format&fit=crop&q=80",
                "email": "Sin correo ", "telefono": "(+52) Sin numero",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IPN : 5 Unidades (Gustavo A. Madero, Miguel Hidalgo)"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1011", "nombre": "Fernando Valerdi", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=300&auto=format&fit=crop&q=80",
                "email": "fernando.valerdi.rebollo@gmail.com", "telefono": "(+52) 5530830567",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 10 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1012", "nombre": "Francisco Garcia", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=300&auto=format&fit=crop&q=80",
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
                "foto": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=300&auto=format&fit=crop&q=80",
                "email": "gloriacoordi.08@gmail.com", "telefono": "(+52) 5531065274",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMMS-Bienestar CDMX : 30 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
            {
                "id": "USR-1014", "nombre": "Guadalupe Barbosa", "puesto": "Coordinadora CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=300&auto=format&fit=crop&q=80",
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
                "id": "USR-1015", "nombre": "Jhon Boris", "puesto": "Coordinador CDMX",
                "departamento": "CDMX", "estado": "Activo",
                "foto": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=300&auto=format&fit=crop&q=80",
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
                "foto": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=300&auto=format&fit=crop&q=80",
                "email": "munejl14@hotmail.com ", "telefono": "(+52) 5527117537",
                "fecha_ingreso": "15-Marzo-2022", "ubicacion": "Oficinas CDMX",
                "nivel_acceso": "Nivel 1 (Coordinador)",
                "proyectos": ["IMSS-Bienestar CDMX : 12 Unidades ()"],
                "habilidades": ["Administración de Sistemas", "Redes", "Seguridad Informática"],
            },
        ]

    if "confirmar_borrado" not in st.session_state:
        st.session_state.confirmar_borrado = None

    st.title("🪪 Coordinadores")
    st.caption("Tarjetas de identificación interactivas: ver QR, descargar credencial, editar, eliminar y administrar servicios como en Excel.")
    st.divider()

    # --- Diálogo modal de edición de datos de la credencial ---
    @st.dialog("✏️ Editar credencial")
    def dialogo_editar(usuario_id):
        usuario = next(u for u in st.session_state.usuarios if u["id"] == usuario_id)
        with st.form(f"form_editar_{usuario_id}"):
            nombre_e = st.text_input("Nombre completo", value=usuario["nombre"])
            puesto_e = st.text_input("Puesto / Cargo", value=usuario["puesto"])
            depto_e = st.selectbox(
                "Área geográfica", REGIONES,
                index=REGIONES.index(usuario["departamento"]) if usuario["departamento"] in REGIONES else 0,
            )
            estado_e = st.selectbox("Estado", ["Activo", "Pendiente", "Inactivo"], index=["Activo", "Pendiente", "Inactivo"].index(usuario["estado"]))
            email_e = st.text_input("Correo electrónico", value=usuario["email"])
            tel_e = st.text_input("Teléfono", value=usuario["telefono"])
            nivel_e = st.text_input("Nivel de acceso", value=usuario["nivel_acceso"])
            foto_nueva = st.file_uploader("Reemplazar foto (opcional)", type=["jpg", "jpeg", "png"])

            col_a, col_b = st.columns(2)
            guardar = col_a.form_submit_button("💾 Guardar cambios", use_container_width=True)
            cancelar = col_b.form_submit_button("Cancelar", use_container_width=True)

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

    # --- Sidebar: búsqueda, filtros y alta de credenciales ---
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

    # --- Filtro por búsqueda + estado (el departamento lo deciden las sub-pestañas) ---
    busqueda_lower = busqueda.lower().strip()
    usuarios_filtrados = [
        u for u in st.session_state.usuarios
        if (
            busqueda_lower in u["nombre"].lower()
            or busqueda_lower in u["id"].lower()
            or busqueda_lower in u["puesto"].lower()
        )
        and u["estado"] in filtro_estado
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
                st.image(obtener_imagen_usuario(usuario), use_container_width=True)
            with c_datos:
                st.markdown(f"### {usuario['nombre']}")
                st.markdown(f"**💼 Puesto:** {usuario['puesto']}")
                st.markdown(f"**🏢 Zona:** `{usuario['departamento']}`")

            st.divider()

            with st.expander("📂 Menú de Información Completa", expanded=False):
                tab_contacto, tab_servicios, tab_excel, tab_skills = st.tabs(
                    ["📧 Contacto", "🛡️ Resumen", "📊 Servicios (Excel)", "⭐ Perfil"]
                )

                with tab_contacto:
                    st.markdown(f"**Email:** [{usuario['email']}](mailto:{usuario['email']})")
                    st.markdown(f"**Teléfono:** {usuario['telefono']}")
                    st.markdown(f"**Ubicación:** {usuario['ubicacion']}")
                    st.markdown(f"**Nivel de Acceso:** {usuario['nivel_acceso']}")
                    st.markdown(f"**Ingreso:** {usuario['fecha_ingreso']}")

                with tab_servicios:
                    servicios = asegurar_servicios_estructurados(usuario)
                    if servicios:
                        total_unidades_usuario = sum(s.get("Unidades", 0) for s in servicios)
                        st.metric("Total de unidades asignadas", total_unidades_usuario)
                        for s in servicios:
                            ubic = f" — {s['Ubicación']}" if s.get("Ubicación") else ""
                            st.markdown(f"- **{s['Dependencia']}**: {s['Unidades']} unidad(es){ubic}")
                    else:
                        st.caption("Sin servicios asignados todavía.")

                with tab_excel:
                    st.caption("Edita la tabla como si fuera Excel: agrega, borra o modifica filas y se guarda al vuelo.")
                    servicios = asegurar_servicios_estructurados(usuario)
                    df_servicios = pd.DataFrame(servicios) if servicios else pd.DataFrame(
                        columns=["Dependencia", "Unidades", "Ubicación"]
                    )
                    df_editado = st.data_editor(
                        df_servicios,
                        num_rows="dynamic",
                        use_container_width=True,
                        key=f"editor_servicios_{usuario['id']}_{idx}",
                        column_config={
                            "Dependencia": st.column_config.TextColumn("Dependencia", required=True),
                            "Unidades": st.column_config.NumberColumn("Unidades", min_value=0, step=1),
                            "Ubicación": st.column_config.TextColumn("Ubicación / Municipios"),
                        },
                    )
                    # Se guarda de inmediato en session_state para que quede persistido en la sesión
                    usuario["servicios"] = df_editado.fillna({"Dependencia": "", "Unidades": 0, "Ubicación": ""}).to_dict("records")

                    col_x1, col_x2 = st.columns(2)
                    with col_x1:
                        st.download_button(
                            "⬇️ Descargar Excel",
                            data=exportar_servicios_excel(usuario),
                            file_name=f"servicios_{usuario['id']}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"xlsx_dl_{usuario['id']}_{idx}",
                            use_container_width=True,
                        )
                    with col_x2:
                        excel_subido = st.file_uploader(
                            "⬆️ Reemplazar desde Excel", type=["xlsx"],
                            key=f"xlsx_up_{usuario['id']}_{idx}", label_visibility="collapsed",
                        )
                        if excel_subido is not None:
                            try:
                                df_nuevo = pd.read_excel(excel_subido, engine="openpyxl")
                                columnas_ok = {"Dependencia", "Unidades", "Ubicación"}.issubset(df_nuevo.columns)
                                if columnas_ok:
                                    usuario["servicios"] = df_nuevo.fillna(
                                        {"Dependencia": "", "Unidades": 0, "Ubicación": ""}
                                    ).to_dict("records")
                                    st.success("Servicios actualizados desde el Excel subido.")
                                    st.rerun()
                                else:
                                    st.error("El Excel debe tener las columnas: Dependencia, Unidades, Ubicación.")
                            except Exception as e:
                                st.error(f"No se pudo leer el archivo: {e}")

                with tab_skills:
                    st.markdown("**Habilidades Clave:**")
                    st.write(", ".join([f"`{h}`" for h in usuario["habilidades"]]))

                st.markdown("---")

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    with st.popover("📱 Ver QR", use_container_width=True):
                        qr_data = f"ID:{usuario['id']};Nombre:{usuario['nombre']};Puesto:{usuario['puesto']}"
                        st.image(generar_qr(qr_data), width=180)
                        st.caption("Escanea para verificar la identidad del portador.")
                with col_btn2:
                    png_bytes = generar_credencial_png(usuario)
                    st.download_button(
                        "🖨️ Descargar", data=png_bytes, file_name=f"credencial_{usuario['id']}.png",
                        mime="image/png", key=f"download_{usuario['id']}_{idx}", use_container_width=True,
                    )

                col_btn3, col_btn4 = st.columns(2)
                with col_btn3:
                    if st.button("✏️ Editar", key=f"edit_{usuario['id']}_{idx}", use_container_width=True):
                        dialogo_editar(usuario["id"])
                with col_btn4:
                    if st.session_state.confirmar_borrado == usuario["id"]:
                        if st.button("⚠️ Confirmar", key=f"confirm_del_{usuario['id']}_{idx}", use_container_width=True, type="primary"):
                            st.session_state.usuarios = [u for u in st.session_state.usuarios if u["id"] != usuario["id"]]
                            st.session_state.confirmar_borrado = None
                            st.toast(f"Credencial {usuario['id']} eliminada.")
                            st.rerun()
                    else:
                        if st.button("🗑️ Eliminar", key=f"del_{usuario['id']}_{idx}", use_container_width=True):
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
with pestana_administradores:
    st.subheader("Área de Operaciones")
    st.info("Esta sección está pendiente de contenido.")
    st.subheader("Oficinas CDMX")