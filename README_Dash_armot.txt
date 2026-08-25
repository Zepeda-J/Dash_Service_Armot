DASHBOARD ARMOT - VERSION MEJORADA

1. Coloca en la misma carpeta:
   - Dash_armot_mejorado.py
   - Servicio.xlsx
   - Armot_Color.png

2. Instala dependencias:
   pip install -r requirements_Dash_armot.txt

3. Ejecuta:
   streamlit run Dash_armot_mejorado.py

4. IA Gemini (opcional):
   Crea .streamlit/secrets.toml:
   GEMINI_API_KEY = "TU_API_KEY"
   GEMINI_MODEL = "gemini-2.5-flash"

La versión mejorada conserva la estructura y los datos embebidos del archivo original, pero corrige rutas, normalización numérica, IDs duplicados, manejo de imágenes, filtros, fechas, búsquedas y configuración opcional de Gemini.
