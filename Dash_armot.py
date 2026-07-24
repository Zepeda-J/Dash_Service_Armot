import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# ==============================================================================
# 1. CONFIGURACIÓN INICIAL DE LA PÁGINA 
# ==============================================================================
st.set_page_config(
    page_title="Dashboard Armot", 
    layout="wide", 
    page_icon="Armot_Color.png" 
)

# ==============================================================================
# 2. INYECCIÓN DE ESTILOS CSS (Garantiza el centrado y la responsividad)
# ==============================================================================
st.html(
    """
    <style>
        /* Centrar texto de subtítulos */
        .stSubheader {
            text-align: center !important;
        }
        
        /* Centrar y ajustar las tarjetas de st.metric en cualquier dispositivo */
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

        /* Ajustes tipográficos adaptativos para pantallas pequeñas */
        @media (max-width: 640px) {
            [data-testid="stMetricValue"] {
                font-size: 1.8rem !important; /* Reduce el tamaño del número en celular para que no se corte */
            }
            .responsive-title {
                font-size: 24px !important;
                text-align: center !important;
            }
        }
    </style>
    """
)

# ==============================================================================
# 3. ENCABEZADO OPTIMIZADO (Cambia el diseño dinámicamente si es PC o Móvil)
# ==============================================================================
# Eliminamos las columnas fijas que causaban distorsión y usamos contenedores centrados
st.html(
    """
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; width: 100%;">
        <img src="app/static/Armot_Color.png" style="max-width: 160px; width: 100%; height: auto; margin-bottom: 10px;">
        <h1 class="responsive-title" style="margin: 0; padding: 0;">Servicios Armot 2026</h1>
    </div>
    """
)

st.markdown("---") 

# ==============================================================================
# 4. CARGA Y PROCESAMIENTO DE DATOS
# ==============================================================================
@st.cache_data
def cargar_datos():
    datasets = pd.read_excel("Servicio.xlsx", engine="openpyxl")
    return datasets

df = cargar_datos()

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

    # Conversión y formateo financiero seguro (f-strings)
    Monto_minimo_sin_IVA = df["Monto mínimo sin IVA"].sum()
    Cantidad_formateada_min_sin_IVA = f"${Monto_minimo_sin_IVA:,.2f}"

    Monto_minimo_con_IVA = df["Monto mínimo con IVA"].sum()
    Cantidad_formateada_min_con_IVA = f"${Monto_minimo_con_IVA:,.2f}"

    Monto_maximo_sin_IVA = df["Monto máximo sin IVA"].sum()
    Cantidad_formateada_max_sin_IVA = f"${Monto_maximo_sin_IVA:,.2f}"

    Monto_maximo_con_IVA = df["Monto máximo con IVA"].sum()
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

# ==============================================================================
# 5. SECCIÓN DE INDICADORES (MÉTRICAS QUE SE APILAN EN CELULARES)
# ==============================================================================
st.subheader("Resumen Global")
col1, col2, col3 = st.columns(3)
col1.metric(label="Total de Servicios", value=f"{int(Dependencias_unicas)}")
col2.metric(label="Presencia", value="32 Estados")
col3.metric(label="Total de Unidades", value=f"{int(Total_unidades):,}")

st.markdown("---")

st.subheader("Personal en Contrato")
col_1_1, col_2_2, col_3_3 = st.columns(3)
col_1_1.metric(label="Elementos mínimos", value=f"{int(Total_de_operarios_min_en_contrato):,}")
col_2_2.metric(label="Elementos máximos", value=f"{int(Total_de_operarios_maximos_en_contrato):,}")
col_3_3.metric(label="Total de Coordinadores", value=f"{int(Total_coordinadores)}")

st.markdown("---")

st.subheader("Montos Totales de los Contratos")
# Cambiado a 2 columnas en lugar de 4. En móvil se adaptará mucho mejor sin amontonar cifras
col_m1, col_m2 = st.columns(2)
with col_m1:
    st.metric(label="Mínimo sin IVA", value=Cantidad_formateada_min_sin_IVA)
    st.metric(label="Máximo sin IVA", value=Cantidad_formateada_max_sin_IVA)
with col_m2:
    st.metric(label="Mínimo con IVA", value=Cantidad_formateada_min_con_IVA)
    st.metric(label="Máximo con IVA", value=Cantidad_formateada_max_con_IVA)

st.markdown("---")

# ==============================================================================
# 6. SECCIÓN DE GRÁFICAS ADAPTATIVAS
# ==============================================================================
st.subheader("Análisis de Distribución por Dependencia")

if not df.empty:
    df_agrupado = df.groupby("Dependencia").agg({
        "N° de Unidades": "sum",
        "Monto máximo con IVA": "sum",
        "Elementos máximos": "sum"
    }).reset_index()

    df_agrupado.columns = [
        'Dependencia', 'Cantidad de unidades por dependencia', 
        'Monto total por dependencia', 'Operarios Máximos'
    ]

    fig = px.scatter(
        df_agrupado,
        x='Cantidad de unidades por dependencia',
        y='Monto total por dependencia',
        color='Dependencia',
        size='Operarios Máximos',  
        size_max=30,               
        hover_name='Dependencia',  
        labels={
            'Cantidad de unidades por dependencia': 'Número de Unidades',
            'Monto total por dependencia': 'Monto Máximo con IVA ($MXN)'
        }
    )

    fig.update_layout(
        height=500,
        title='<b>Gráfica de Dispersión de Servicios 2026</b>',
        title_x=0.5, 
        legend_title_text='Dependencias',
        yaxis=dict(tickprefix="$", tickformat=",.2f") 
    )

    st.plotly_chart(fig, use_container_width=True)
    
    # --------------------------------------------------------------------------
    # LINEA DE TIEMPO RESPONSIBA
    # --------------------------------------------------------------------------
    st.markdown("---")
    st.subheader("Vigencia de los Contratos")
    
    df["Inicio"] = pd.to_datetime(df["Inicio"], errors='coerce')
    df["Fin"] = pd.to_datetime(df["Fin"], errors='coerce')

    fig_tiempo = px.timeline(
        df, 
        x_start="Inicio",       
        x_end="Fin",           
        y="Dependencia",       
        color="Dependencia",   
    )

    fig_tiempo.update_yaxes(categoryorder="category descending") 
    fig_tiempo.update_layout(
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

    st.plotly_chart(fig_tiempo, use_container_width=True)
else:
    st.info("No hay registros en el DataFrame para graficar.")
