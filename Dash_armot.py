import io
import locale as lc
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.figure_factory as ff
import plotly.graph_objects as go
from PIL import Image
import streamlit as st

# IMPORTACIÓN DE LA LIBRERÍA CLÁSICA
import google.generativeai as genai

# Configuración inicial de la página
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
    st.error(
        "⚠️ No se encontró la clave GEMINI_API_KEY en los secretos de Streamlit."
    )
    GEMINI_API_KEY = None


def obtener_modelo_gemini():
    if not GEMINI_API_KEY:
        return None
    try:
        # Usamos el nombre oficial del modelo recomendado para texto y análisis rápido
        return genai.GenerativeModel("gemini-1.5-flash")
    except Exception as e:
        st.error(f"Error al inicializar Gemini: {e}")
        print(f"Error al inicializar Gemini: {e}")
        return None


model_gemini = obtener_modelo_gemini()





# --- ENCABEZADO CENTRADO CON LOGO AJUSTADO ---
col_izq, col_centro, col_der = st.columns([1, 2, 1])

with col_centro:
    _, col_img, _ = st.columns([1, 1.5, 1])
    with col_img:
        st.image("Armot_Color.png", use_container_width=True)

    st.html(
        "<h1 style='text-align: center; margin-top: 10px;'>Servicios Armot 2026</h1>"
    )

st.markdown("---")
st.write("")
st.write("")

# ==============================================================================
# 4. CARGA Y PROCESAMIENTO DE DATOS
# ==============================================================================
@st.cache_data
def cargar_datos():
    try:
        datasets = pd.read_excel("Servicio.xlsx", engine="openpyxl")
        return datasets
    except Exception:
        return pd.DataFrame()  # Retorna DF vacío si no encuentra el archivo

df = cargar_datos()

# --- INTEGRACIÓN DEL ASISTENTE DE IA EN LA BARRA LATERAL ---
with st.sidebar:
    st.header("🤖 Asistente de IA Armot")
    st.write("Pregúntame estadísticas o dudas sobre el reporte de servicios.")

    # Inicializar el historial si no existe
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Mostrar los mensajes anteriores del historial en la pantalla
    for chat in st.session_state.chat_history:
        with st.chat_message(chat["role"]):
            st.markdown(chat["content"])

    # Capturar la pregunta del usuario
    if prompt_ia := st.chat_input("¿Qué deseas saber de los datos?"):
        # 1. Mostrar inmediatamente el mensaje del usuario en la interfaz
        st.chat_message("user").markdown(prompt_ia)
        st.session_state.chat_history.append(
            {"role": "user", "content": prompt_ia}
        )

        # 2. Generar la respuesta del asistente
        with st.chat_message("assistant"):
            if model_gemini is None:
                mensaje_error = "⚠️ El modelo de Gemini no está inicializado correctamente. Revisa tu API Key."
                st.error(mensaje_error)
            elif df is None or df.empty:
                mensaje_error = "⚠️ El archivo 'Servicio.xlsx' está vacío o no se pudo cargar."
                st.error(mensaje_error)
            else:
                with st.spinner("Pensando..."):
                    # 📊 EXTRACCIÓN EN TIEMPO REAL: Calculamos las variables del Excel
                    num_dep = (
                        df["Dependencia"].nunique()
                        if "Dependencia" in df.columns
                        else 0
                    )
                    tot_uni = (
                        df["N° de Unidades"].sum()
                        if "N° de Unidades" in df.columns
                        else 0
                    )
                    ele_min = (
                        df["Elementos minimos"].sum()
                        if "Elementos minimos" in df.columns
                        else 0
                    )
                    ele_max = (
                        df["Elementos máximos"].sum()
                        if "Elementos máximos" in df.columns
                        else 0
                    )

                    monto_min = (
                        f"${df['Monto mínimo con IVA'].sum():,.2f}"
                        if "Monto mínimo con IVA" in df.columns
                        else "$0.00"
                    )
                    monto_max = (
                        f"${df['Monto máximo con IVA'].sum():,.2f}"
                        if "Monto máximo con IVA" in df.columns
                        else "$0.00"
                    )

                    # 🔍 MOTOR DE CONTEXTO DINÁMICO (Optimizado para conjuntos grandes)
                    # Si el usuario pregunta por un término específico, filtramos el DataFrame para mandar solo lo relevante
                    palabras_clave = [p.strip().lower() for p in prompt_ia.split() if len(p) > 3]
                    
                    df_filtrado = pd.DataFrame()
                    if palabras_clave:
                        # Busca coincidencias de texto en cualquier columna del DataFrame
                        mascara = df.astype(str).apply(lambda x: x.str.lower().str.contains('|'.join(palabras_clave))).any(axis=1)
                        df_filtrado = df[mascara]

                    # Si el filtro encuentra coincidencias, envía hasta 25 filas relevantes; si no, envía las primeras 15 por defecto
                    if not df_filtrado.empty:
                        muestra_datos = df_filtrado.head(25)
                        nota_contexto = "Nota: Se han extraído las filas del reporte que coinciden dinámicamente con la búsqueda del usuario."
                    else:
                        muestra_datos = df.head(15)
                        nota_contexto = "Nota: Mostrando una vista previa general de las primeras filas del reporte debido a falta de palabras clave explícitas."

                    muestra_tabla = muestra_datos.to_markdown() if hasattr(muestra_datos, 'to_markdown') else muestra_datos.to_string()

                    # Estructuramos las directrices del sistema de forma explícita
                    instrucciones_sistema = (
                        "Eres un asistente analítico experto de la empresa Armot. Tu objetivo único es responder "
                        "preguntas del usuario basándote estrictamente en el resumen de métricas y la tabla provista. "
                        "Sé ejecutivo, claro, preciso y responde siempre en español. No inventes datos fuera del contexto dado."
                    )

                    # Creamos el bloque de contenido estructurado que obliga a Gemini a leer el contexto antes de la pregunta
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
                        # 🔄 ENTRADA MEJORADA: Enviamos las instrucciones del sistema separadas del contenido analítico
                        respuesta = model_gemini.generate_content(
                            contents=bloque_contenido,
                            generation_config={"temperature": 0.2} # Temperatura baja evita respuestas genéricas o alucinaciones
                        )

                        if respuesta and respuesta.text:
                            st.markdown(respuesta.text)
                            st.session_state.chat_history.append(
                                {
                                    "role": "assistant",
                                    "content": respuesta.text,
                                }
                            )
                        else:
                            st.warning(
                                "La IA recibió los datos pero no generó texto. Intenta reformular tu pregunta."
                            )

                    except Exception as e:
                        st.error(
                            f"Ocurrió un problema al procesar la respuesta: {e}"
                        )


# ==============================================================================
# SECCIÓN DE FILTROS LIGADOS (EN CASCADA)
# ==============================================================================
st.sidebar.header("🔍 Filtros Globales")

if not df.empty:
    # Asegurar nombres de columnas estándar
    col_estado = "Estados" if "Estados" in df.columns else "Estado"
    col_dependencia = "Dependencias" if "Dependencias" in df.columns else "Dependencia"
    
    # 1. FILTRO PADRE: Estado
    # Obtenemos la lista única de estados ordenados alfabéticamente
    estados_disponibles = sorted(df[col_estado].dropna().unique().tolist())
    estado_seleccionado = st.sidebar.selectbox(
        "Seleccionar Estado:",
        options=["Todos los Estados"] + estados_disponibles
    )
    
    # Filtrar el DataFrame según el estado seleccionado
    if estado_seleccionado != "Todos los Estados":
        df_filtrado_estado = df[df[col_estado] == estado_seleccionado]
    else:
        df_filtrado_estado = df.copy()

    # 2. FILTRO HIJO: Dependencia (Ligado al Estado seleccionado)
    # Solo muestra las dependencias que existen dentro del estado elegido previamente
    dependencias_disponibles = sorted(df_filtrado_estado[col_dependencia].dropna().unique().tolist())
    dependencia_seleccionada = st.sidebar.selectbox(
        "Seleccionar Dependencia:",
        options=["Todas las Dependencias"] + dependencias_disponibles
    )

    # Aplicar ambos filtros al DataFrame principal que usará todo el tablero
    if dependencia_seleccionada != "Todas las Dependencias":
        df = df_filtrado_estado[df_filtrado_estado[col_dependencia] == dependencia_seleccionada]
    else:
        df = df_filtrado_estado

# ==============================================================================
# A PARTIR DE AQUÍ SE MANTIENE TU LÓGICA CON EL DATAFRAME FILTRADO (df)
# ==============================================================================

# --- REEMPLAZO DE LOCALE POR FORMATEO NATIVO (A PRUEBA DE ERRORES EN LA NUBE) ---
if not df.empty:
    # Totales numéricos globales
    Dependencias_unicas = df["Dependencia"].nunique()
    Total_unidades = df["N° de Unidades"].sum()
    Total_de_operarios_min_en_contrato = df["Elementos minimos"].sum()
    Total_de_operarios_maximos_en_contrato = df["Elementos máximos"].sum()
    
    if "Coordinador" in df.columns:
        Total_coordinadores = df["Coordinador"].nunique()
    else:
        Total_coordinadores = 0

    # --- NUEVO FORMATEO FINANCIERO SEGURO ---
    Monto_minimo_sin_IVA = df["Monto mínimo sin IVA"].sum()
    Monto_minimo_con_IVA = df["Monto mínimo con IVA"].sum()
    Monto_maximo_sin_IVA = df["Monto máximo sin IVA"].sum()
    Monto_maximo_con_IVA = df["Monto máximo con IVA"].sum()

    Cantidad_formateada_min_sin_IVA = f"${Monto_minimo_sin_IVA:,.2f}"
    Cantidad_formateada_min_con_IVA = f"${Monto_minimo_con_IVA:,.2f}"
    Cantidad_formateada_max_sin_IVA = f"${Monto_maximo_sin_IVA:,.2f}"
    Cantidad_formateada_max_con_IVA = f"${Monto_maximo_con_IVA:,.2f}"

else:
    Dependencias_unicas = 0
    Total_unidades = 0
    Total_de_operarios_min_en_contrato = 0
    Total_de_operarios_maximos_en_contrato = 0
    Total_coordinadores = 0
    Cantidad_formateada_min_sin_IVA = "$0.00"
    Cantidad_formateada_min_con_IVA = "$0.00"
    Cantidad_formateada_max_sin_IVA = "$0.00"
    Cantidad_formateada_max_con_IVA = "$0.00"

# --- INYECCIÓN DE ESTILOS CSS PARA CENTRAR TODA LA INFORMACIÓN DE LAS MÉTRICAS ---
st.html(
    """
    <style>
        .stSubheader {
            text-align: center !important;
        }
        [data-testid="stMetric"] {
            text-align: center !important;
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: center !important;
            width: 100% !important;
        }
        [data-testid="stMetricLabel"], [data-testid="stMetricValue"] {
            text-align: center !important;
            justify-content: center !important;
            display: flex !important;
            width: 100% !important;
        }
    </style>
    """
)

# --- SECCIÓN DE MÉTRICAS RÁPIDAS (KPIs) ---
st.subheader("Resumen Global")

col1, col2, col3 = st.columns(3)
col1.metric(label="Total de Servicios", value=f"{int(Dependencias_unicas)}")
col2.metric(label="Presencia", value="32 Estados")
col3.metric(label="Total de Unidades", value=f"{int(Total_unidades):,}")

# --- SECCIÓN: OPERARIOS ---
st.subheader("")

col_1_1, col_2_2, col_3_3 = st.columns(3)
col_1_1.metric(label="Elementos mínimos", value=f"{int(Total_de_operarios_min_en_contrato):,}")
col_2_2.metric(label="Elementos máximos", value=f"{int(Total_de_operarios_maximos_en_contrato):,}")
col_3_3.metric(label="Total de Coordinadores", value=f"{int(Total_coordinadores)}")

#Montos
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

# --- SECCIÓN: GRÁFICA DE DISPERSIÓN ---
st.subheader("Dispersion de Servicios Armot")

if not df.empty:
    df_agrupado = df.groupby("Dependencia").agg({
        "N° de Unidades": "sum",
        "Monto máximo con IVA": "sum",
        "Elementos máximos": "sum"  
    }).reset_index()

    df_agrupado.columns = [
        'Dependencia', 
        'Cantidad de unidades por dependencia', 
        'Monto total por dependencia',
        'Operarios Máximos'
    ]

    max_unidades = int(df_agrupado["Cantidad de unidades por dependencia"].max()) if not df_agrupado.empty else 0
    
    if max_unidades > 0:
        rango_unidades = st.slider(
            "Filtrar por rango de unidades (Eje X):",
            min_value=0,
            max_value=max_unidades,
            value=(0, max_unidades),  
            step=1,
            key="slider_dispersion_x_original"
        )

        df_filtrado = df_agrupado[
            (df_agrupado["Cantidad de unidades por dependencia"] >= rango_unidades[0]) & 
            (df_agrupado["Cantidad de unidades por dependencia"] <= rango_unidades[1])
        ]
    else:
        df_filtrado = df_agrupado
        rango_unidades = (0, 0)

    if not df_filtrado.empty:
        fig = px.scatter(
            df_filtrado,  
            x='Cantidad de unidades por dependencia',
            y='Monto total por dependencia',
            color='Dependencia',
            size='Operarios Máximos',  
            size_max=100,              
            hover_name='Dependencia',  
            labels={
                'Cantidad de unidades por dependencia': 'Número de Unidades',
                'Monto total por dependencia': 'Monto Máximo con IVA ($MXN)'
            }
            
        )

        fig.update_layout(
            height=650,
            title='<b>Gráfica de Dispersión de Servicios 2026</b>',
            title_x=0.5,
            showlegend=True,
            legend=dict(
                orientation="h",        
                yanchor="top",
                y=-0.2,                    
                xanchor="center",
                x=0.5,                      
                title_text='<b>Dependencias:</b>',
                font=dict(size=11)      
            ),
            yaxis=dict(tickprefix="$", tickformat=",.2f"),
            xaxis=dict(range=[rango_unidades[0], rango_unidades[1]], fixedrange=True)
        )
        st.plotly_chart(fig, use_container_width=True, on_select = "rerun")
    else:
        st.warning("No existen dependencias que coincidan con el rango de unidades seleccionado.")
else:
    st.info("No hay datos disponibles para mostrar la gráfica de dispersión.")

st.markdown("---")

# --- SECCIÓN: GRÁFICA DE TIEMPO (DIAGRAMA DE GANTT) ---
st.subheader("Vigencia de los Contratos")

if not df.empty:
    df["Inicio"] = pd.to_datetime(df["Inicio"], errors='coerce')
    df["Fin"] = pd.to_datetime(df["Fin"], errors='coerce')

    fig = px.timeline(
        df, 
        x_start="Inicio",      
        x_end="Fin",          
        y="Dependencia",      
        color="Dependencia",   
    )

    fig.update_yaxes(categoryorder="category descending") 
    
    fig.update_layout(
        height=500,
        title='<b>Vigencia de Contratos 2026</b>',
        title_x=0.5,             
        xaxis_title="Meses de Contratación (2026)", 
        yaxis_title="Dependencias",
        showlegend=False,      
        xaxis=dict(
            tickformat="%b\n%Y",    
            dtick="M1",                    
            ticklabelmode="period"   
        )
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No hay datos de fechas disponibles para mostrar la vigencia.")

st.markdown("---")

# --- SECCIÓN: TABLA DE UNIDADES Y DEPENDENCIAS POR ESTADO ---
st.subheader("📍 Desglose Geográfico por Estado")

if not df.empty:
    col_estado = "Estados" if "Estados" in df.columns else "Estado"
    col_dependencia = "Dependencias" if "Dependencias" in df.columns else "Dependencia"
    
    tabla_estados = df.groupby(col_estado).agg({
        col_dependencia: "nunique",
        "N° de Unidades": "sum"
    }).reset_index()

    tabla_estados.columns = ["Estado", "Cantidad de Dependencias", "Cantidad de Unidades"]
    tabla_estados = tabla_estados.sort_values(by="Cantidad de Unidades", ascending=False).reset_index(drop=True)

    st.dataframe(tabla_estados, use_container_width=True, hide_index=True)
    st.caption(f"Mostrando un total de {len(tabla_estados)} entidades federativas con infraestructura asignada.")
else:
    st.info("No hay datos disponibles para estructurar la tabla por Estados.")

# ==============================================================================
# GRAFICA 1: DESGLOSE DE MONTOS POR CONTRATO
# ==============================================================================
st.subheader("📋 Análisis Financiero por Dependencia")

if not df.empty:
    Dependencias_montos = df.groupby("Dependencia")["Monto máximo con IVA"].sum().reset_index()

    monto_max_dep = float(Dependencias_montos["Monto máximo con IVA"].max()) if not Dependencias_montos.empty else 0.0
    
    limite_y_dep = st.slider(
        "Ajustar límite máximo del eje vertical (Presupuesto):",
        min_value=0.0,
        max_value=monto_max_dep if monto_max_dep > 0 else 1.0,
        value=monto_max_dep,  
        step=100000.0,
        format="$%,.2f",
        key="slider_y_dep"
    )

    barras_por_dependencia = px.bar(
        Dependencias_montos,
        x="Dependencia",
        y="Monto máximo con IVA",
        color="Monto máximo con IVA",
        color_continuous_scale="RdBu",
        title="<b>Monto Máximo con IVA por Dependencia</b>",
        labels={"Monto máximo con IVA": "Monto Total ($MXN)", "Dependencia": "Dependencia"}
    )

    barras_por_dependencia.update_layout(
        title_x=0.5,
        height=550,  
        yaxis=dict(
            tickprefix="$", 
            tickformat=",.2f",
            range=[0, limite_y_dep],  
            fixedrange=True
        ),
        xaxis=dict(
            tickangle=-30,
            type="category",
            fixedrange=True
        )
    )
    st.plotly_chart(barras_por_dependencia, use_container_width=True)
else:
    st.info("No hay datos disponibles para la gráfica de dependencias.")

# ==============================================================================
# GRAFICA 2: MONTOS POR ESTADO
# ==============================================================================
st.subheader("📍 Distribución de los montos de los contratos por Estado")

if not df.empty:
    col_estado = "Estados" if "Estados" in df.columns else "Estado"

    Estados_montos = df.groupby(col_estado)["Monto máximo con IVA"].sum().reset_index()
    Estados_montos.columns = ["Estado", "Monto Máximo con IVA"]
    Estados_montos = Estados_montos.sort_values(by="Monto Máximo con IVA", ascending=False)

    monto_max_est = float(Estados_montos["Monto Máximo con IVA"].max()) if not Estados_montos.empty else 0.0
    
    limite_y_est = st.slider(
        "Ajustar límite máximo del eje vertical (Presupuesto por Estado):",
        min_value=0.0,
        max_value=monto_max_est if monto_max_est > 0 else 1.0,
        value=monto_max_est,  
        step=500000.0,
        format="$%,.2f",
        key="slider_y_est"
    )

    barras_por_estado = px.bar(
        Estados_montos,
        x="Estado",
        y="Monto Máximo con IVA",
        color="Monto Máximo con IVA",
        color_continuous_scale="Viridis",
        title="<b>Inversión Máxima con IVA por Estado</b>",
        labels={"Monto Máximo con IVA": "Monto Máximo con IVA ($MXN)"}
    )

    barras_por_estado.update_layout(
        title_x=0.5,
        height=550,  
        yaxis=dict(
            tickprefix="$", 
            tickformat=",.2f",
            range=[0, limite_y_est],  
            fixedrange=True
        ),
        xaxis=dict(
            tickangle=-45,
            type="category",
            fixedrange=True
        )
    )
    st.plotly_chart(barras_por_estado, use_container_width=True)
else:
    st.info("No hay datos disponibles para la gráfica de estados.")

# ==============================================================================
# EMPRESAS OPERANDO EN LOS SERVICIOS
# ==============================================================================
st.header("Distribución de empresas operando en los servicios")

if not df.empty:
    empresas = (
        df.groupby("Empresa operando", dropna=False)["Dependencia"]
        .nunique()
        .reset_index(name="Numero de dependencias")
    )

    colores = px.colors.qualitative.Safe

    fig = go.Figure(
        data=[
            go.Pie(
                labels=empresas["Empresa operando"],
                values=empresas["Numero de dependencias"],
                hole=0.4,  
                marker=dict(colors=colores),  
                textinfo="percent+label",  
                insidetextorientation="radial",
            )
        ]
    )

    fig.update_layout(
        showlegend=True,  
        legend=dict(
            orientation="h",  
            yanchor="bottom",
            y=-0.2,  
            xanchor="center",
            x=0.5,
        ),
        margin=dict(t=20, b=20, l=20, r=20),  
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No hay datos disponibles para mostrar las empresas operando.")







     