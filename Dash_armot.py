import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from PIL import Image
import io  
import locale as lc
import plotly.graph_objects as go
import plotly.figure_factory   as ff 

# Configuración inicial de la página
st.set_page_config(
    page_title="Dashboard Armot", 
    layout="wide", 
    page_icon="Armot_Color.png"  
)

# --- ENCABEZADO CENTRADO CON LOGO AJUSTADO ---
# Creamos 3 columnas. La del centro (proporción 2) contendrá el contenido.
col_izq, col_centro, col_der = st.columns([1, 2, 1])

with col_centro:
    # 1. Ajustar el tamaño del logo usando un contenedor de columnas internas
    # Al hacer la columna del logo más pequeña (1) respecto a las vacías (3), reducimos su tamaño
    _, col_img, _ = st.columns([1, 1.5, 1]) 
    with col_img:
        st.image("Armot_Color.png", use_container_width=True)
    
    # 2. Centrar el texto del título usando HTML integrado nativamente en Streamlit
    st.html("<h1 style='text-align: center; margin-top: 10px;'>Servicios Armot 2026</h1>")

st.markdown("---") # Línea divisoria estética
#Espacios (saltos de pagina)
st.write("")
st.write("")

# ==============================================================================
# 4. CARGA Y PROCESAMIENTO DE DATOS
# ==============================================================================
@st.cache_data
def cargar_datos():
    datasets = pd.read_excel("Servicio.xlsx", engine="openpyxl")
    return datasets

df = cargar_datos()

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
    # Calculamos las sumas
    Monto_minimo_sin_IVA = df["Monto mínimo sin IVA"].sum()
    Monto_minimo_con_IVA = df["Monto mínimo con IVA"].sum()
    Monto_maximo_sin_IVA = df["Monto máximo sin IVA"].sum()
    Monto_maximo_con_IVA = df["Monto máximo con IVA"].sum()

    # Formateamos usando f-strings: agrega '$', comas en miles y 2 decimales
    Cantidad_formateada_min_sin_IVA = f"${Monto_minimo_sin_IVA:,.2f}"
    Cantidad_formateada_min_con_IVA = f"${Monto_minimo_con_IVA:,.2f}"
    Cantidad_formateada_max_sin_IVA = f"${Monto_maximo_sin_IVA:,.2f}"
    Cantidad_formateada_max_con_IVA = f"${Monto_maximo_con_IVA:,.2f}"

else:
    # Valores por defecto si el Excel está vacío
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
        /* Centrar el texto de los subtítulos (subheaders) */
        .stSubheader {
            text-align: center !important;
        }
        
        /* Centrar todos los elementos internos del componente st.metric */
        [data-testid="stMetric"] {
            text-align: center !important;
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: center !important;
            width: 100% !important;
        }

        /* Forzar el centrado específico de las etiquetas y valores numéricos */
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
st.subheader("") # Reemplazado "" por un título descriptivo centrado

col_1_1, col_2_2, col_3_3 = st.columns(3)
col_1_1.metric(label="Elementos mínimos", value=f"{int(Total_de_operarios_min_en_contrato):,}")
col_2_2.metric(label="Elementos máximos", value=f"{int(Total_de_operarios_maximos_en_contrato):,}")
col_3_3.metric(label="Total de Coordinadores", value=f"{int(Total_coordinadores)}")

#Montos
st.subheader("")
col_1, col_2, col_3, col_4 = st.columns(4)
# CORREGIDO: Se eliminó el casteo int() de las variables que ya son cadenas de texto formateadas
col_1.metric(label="Mínimo sin IVA", value=Cantidad_formateada_min_sin_IVA)
col_2.metric(label="Mínimo con IVA", value=Cantidad_formateada_min_con_IVA)
col_3.metric(label="Máximo sin IVA", value=Cantidad_formateada_max_sin_IVA)
col_4.metric(label="Máximo con IVA", value=Cantidad_formateada_max_con_IVA)

st.write("")
st.write("")
st.write("")

st.markdown("---") # Línea divisoria estética

# --- SECCIÓN: GRÁFICA DE DISPERSIÓN ---
st.subheader("Dispersion de Servicios Armot")

if not df.empty:
    # 1. Agrupación unificada (Evita desalineación de datos y errores de escritura como 'Dependecia')
    # Agrupamos por 'Dependencia' y calculamos la suma de las tres métricas clave simultáneamente
    df_agrupado = df.groupby("Dependencia").agg({
        "N° de Unidades": "sum",
        "Monto máximo con IVA": "sum",
        "Elementos máximos": "sum"  # Obtenemos los operarios máximos para el tamaño de las burbujas
    }).reset_index()

    # Rediseño de nombres de columnas para claridad en el gráfico
    df_agrupado.columns = [
        'Dependencia', 
        'Cantidad de unidades por dependencia', 
        'Monto total por dependencia',
        'Operarios Máximos'
    ]

    # 2. Construcción de la Gráfica de Dispersión (Burbujas)
    fig = px.scatter(
        df_agrupado,
        x='Cantidad de unidades por dependencia',
        y='Monto total por dependencia',
        color='Dependencia',
        size='Operarios Máximos',  # El tamaño de la burbuja representará los operarios asignados
        size_max=150,               # Ajustado de 100 a 40 para evitar que las burbujas saturen el gráfico
        hover_name='Dependencia',  # Muestra el nombre arriba en la etiqueta flotante
        labels={
            'Cantidad de unidades por dependencia': 'Número de Unidades',
            'Monto total por dependencia': 'Monto Máximo con IVA ($MXN)'
        }
    )

    # 3. Personalización del diseño del gráfico
    fig.update_layout(
        height=600,
        title='<b>Gráfica de Dispersión de Servicios 2026</b>',
        title_x=0.5,
        legend_title_text='Dependencias',
        # Formatear el eje Y como moneda para que sea más legible
        yaxis=dict(tickprefix="$", tickformat=",.2f") 
    )

    # 4. Renderizado en Streamlit (Reemplaza fig.show() que abre pestañas locales del navegador)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No hay datos disponibles para mostrar la gráfica de dispersión.")


st.markdown("---") # Línea divisoria estética

# --- SECCIÓN: GRÁFICA DE TIEMPO (DIAGRAMA DE GANTT) ---
st.subheader("Vigencia de los Contratos")

if not df.empty:
    # 1. Asegurar que las columnas sean interpretadas como fechas por Pandas
    df["Inicio"] = pd.to_datetime(df["Inicio"], errors='coerce')
    df["Fin"] = pd.to_datetime(df["Fin"], errors='coerce')

    # 2. Crear el gráfico de línea de tiempo corregido
    fig = px.timeline(
        df, 
        x_start="Inicio",       
        x_end="Fin",           
        y="Dependencia",       
        color="Dependencia",   
    )

    # 3. Optimizar el diseño para que las fechas y etiquetas se lean correctamente
    fig.update_yaxes(categoryorder="category descending") 
    
    fig.update_layout(
        height=500,
        title='<b>Vigencia de Contratos 2026</b>',
        title_x=0.5,           
        xaxis_title="Meses de Contratación (2026)", 
        yaxis_title="Dependencias",
        showlegend=False,       
        
        # --- CONFIGURACIÓN PARA FORZAR EL EJE X POR MESES ---
        xaxis=dict(
            tickformat="%b\n%Y",     # %b muestra el nombre corto del mes (Ene, Feb...) y %Y el año
            dtick="M1",              # Forzar saltos de exactamente 1 mes ("M1")
            ticklabelmode="period"   # Centra la etiqueta del mes en el bloque correspondiente
        )
    )

    # 4. Renderizar el gráfico interactivo nativamente en Streamlit
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No hay datos de fechas disponibles para mostrar la vigencia.")



st.markdown("---")

# --- SECCIÓN: TABLA DE UNIDADES Y DEPENDENCIAS POR ESTADO ---
st.subheader("📍 Desglose Geográfico por Estado")

if not df.empty:
    # 1. Agrupación unificada y segura (Garantiza consistencia y alineación por Estado)
    # Nota: Asegúrate de que en tu Excel la columna se llame "Estados" o "Estado".
    col_estado = "Estados" if "Estados" in df.columns else "Estado"
    col_dependencia = "Dependencias" if "Dependencias" in df.columns else "Dependencia"
    
    tabla_estados = df.groupby(col_estado).agg({
        col_dependencia: "nunique",
        "N° de Unidades": "sum"
    }).reset_index()

    # 2. Renombrar columnas para la visualización final
    tabla_estados.columns = ["Estado", "Cantidad de Dependencias", "Cantidad de Unidades"]

    # 3. Ordenar la tabla de mayor a menor número de unidades
    tabla_estados = tabla_estados.sort_values(by="Cantidad de Unidades", ascending=False).reset_index(drop=True)

    # 4. Mostrar la tabla interactiva y estilizada en Streamlit
    st.dataframe(
        tabla_estados, 
        use_container_width=True, 
        hide_index=True
    )
    
    # Opcional: Un pequeño resumen de texto dinámico debajo de la tabla
    st.caption(f"Mostrando un total de {len(tabla_estados)} entidades federativas con infraestructura asignada.")

else:
    st.info("No hay datos disponibles para estructurar la tabla por Estados.")

#Grafica de barras-Desglose de montos por contrato
# 1. Agrupamos y reseteamos el índice para que Plotly reconozca las columnas
Dependencias_montos = df.groupby("Dependencia")["Monto máximo con IVA"].sum().reset_index()

# 2. Creamos la gráfica de barras
barras_por_dependencia = px.bar(
    Dependencias_montos,
    x="Dependencia",
    y="Monto máximo con IVA",
    color="Monto máximo con IVA",
    color_continuous_scale="Blues",
    title="<b>Monto Máximo con IVA por Dependencia</b>",
    labels={"Monto máximo con IVA": "Monto Total ($MXN)", "Dependencia": "Dependencia"}
)

# 3. Formateamos el diseño (Eje Y como moneda y título centrado)
barras_por_dependencia.update_layout(
    title_x=0.5,
    yaxis=dict(tickprefix="$", tickformat=",.2f")
)

# 4. Mostrar en Streamlit
st.plotly_chart(barras_por_dependencia, use_container_width=True)

#Grafica de Montos por Estado
# 1. Identificar columna de estado de forma segura
col_estado = "Estados" if "Estados" in df.columns else "Estado"

# 2. Agrupar montos por Estado
Estados_montos = df.groupby(col_estado)["Monto máximo con IVA"].sum().reset_index()
Estados_montos.columns = ["Estado", "Monto Máximo con IVA"]
Estados_montos = Estados_montos.sort_values(by="Monto Máximo con IVA", ascending=False)

# 3. Crear la gráfica de barras por Estado
barras_por_estado = px.bar(
    Estados_montos,
    x="Estado",
    y="Monto Máximo con IVA",
    color="Monto Máximo con IVA",
    color_continuous_scale="Viridis",
    title="<b>Inversión Máxima con IVA por Estado</b>"
)

# 4. Ajustar formato de moneda y centrar título
barras_por_estado.update_layout(
    title_x=0.5,
    yaxis=dict(tickprefix="$", tickformat=",.2f")
)

# 5. Mostrar en Streamlit
st.plotly_chart(barras_por_estado, use_container_width=True)
