import streamlit as st
import pandas as pd
from datetime import datetime
import tempfile
import os
from fpdf import FPDF

# ==========================================
# 1. CONFIGURACIÓN Y ESTILOS
# ==========================================
st.set_page_config(page_title="Control de Golpes de Matrices", layout="wide", page_icon="⚙️")

st.markdown("""
<style>
    .header-style { font-size: 26px; font-weight: bold; margin-bottom: 5px; color: #1F2937; text-align: center; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="header-style">⚙️ Reporte Auxiliar: Control de Golpes de Matrices (FAMMA)</div>', unsafe_allow_html=True)
st.write("<p style='text-align: center;'>Cruce automático de Catálogo, Producción y Mantenimiento.</p>", unsafe_allow_html=True)
st.divider()

# ==========================================
# 2. ENLACES DE GOOGLE SHEETS
# ==========================================
URL_CATALOGO = "https://docs.google.com/spreadsheets/d/1feaeFLl2UslCsO4mzldUVFuhY1bdnUiQPatRM2m0sW0/export?format=csv&gid=1862158700"
URL_PRODUCCION = "https://docs.google.com/spreadsheets/d/1TdQ3yNxx29SgQ7u8oexxlnL80rAcXQuP118wQVBd9ew/export?format=csv&gid=315437448"

# Formularios de Mantenimiento FAMMA
URL_PREV_FAMMA = "https://docs.google.com/spreadsheets/d/1MptnOuRfyOAr1EgzNJVygTtNziOSdzXJn-PZDX0pNzc/export?format=csv&gid=324842888"
URL_CORR_FAMMA = "https://docs.google.com/spreadsheets/d/1A-0mngZdgvZGbqzWjA_awhrwfvca0K4aGqp5NBAoFAY/export?format=csv&gid=238711679"

VALID_PIEZA_COLS = [
    'PIEZAS RENAULT', 'PIEZAS FAURECIA', 'PIEZAS FIAT', 'PIEZAS DENSO', 
    'PIEZAS PEUGEOT', 'PIEZA FIAT', 'PIEZA NISSAN', 'PIEZA RENAULT', 'NUMERO DE PIEZA'
]

# ==========================================
# 3. FUNCIONES DE LIMPIEZA Y CARGA
# ==========================================
def clean_str(val):
    """Limpia strings para que el cruce sea exacto (Ej: '20.0' -> '20')"""
    if pd.isna(val): return ""
    v = str(val).strip().upper()
    if v.endswith('.0'): v = v[:-2]
    return v

def get_match_key(pieza_str):
    """Si la pieza tiene '/', toma solo la primera parte para evitar duplicar piezas pares (Izq/Der)."""
    return pieza_str.split('/')[0].strip() if '/' in pieza_str else pieza_str

def extract_mantenimientos(url):
    """Extrae Fecha, Matriz y la Operacion correcta de los formularios de mantenimiento."""
    try:
        df = pd.read_csv(url)
        cols = [str(c).upper().strip() for c in df.columns]
        
        col_fecha = next((i for i, c in enumerate(cols) if 'FECHA' in c), None)
        if col_fecha is None: return pd.DataFrame()

        registros = []
        for _, row in df.iterrows():
            fecha = pd.to_datetime(row.iloc[col_fecha], dayfirst=True, errors='coerce')
            if pd.isna(fecha): continue
            
            # Buscar columnas de PIEZA (FIAT, RENAULT, NISSAN)
            for i, col_name in enumerate(cols):
                base_col = col_name.split('.')[0].strip()
                
                if base_col in VALID_PIEZA_COLS:
                    pieza_completa = clean_str(row.iloc[i])
                    if pieza_completa and pieza_completa not in ['NAN', 'NONE', '-', '0', 'N/A', 'NO APLICA', '']:
                        pieza_match = get_match_key(pieza_completa)
                        op = ""
                        
                        # Buscar la columna "OPERACION" inmediatamente a la derecha
                        for j in range(i+1, min(i+4, len(cols))):
                            next_col = cols[j].split('.')[0].strip()
                            if 'OPERACION' in next_col or 'OPERACIÓN' in next_col or 'OP' == next_col:
                                op = clean_str(row.iloc[j])
                                break
                        
                        registros.append({
                            'Fecha': fecha, 
                            'Pieza_Completa': pieza_completa, 
                            'Pieza_Match': pieza_match, 
                            'OP': op
                        })
        return pd.DataFrame(registros)
    except Exception as e:
        print(f"Error cargando mantenimiento: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_all_data():
    # --- 1. CARGAR CATÁLOGO MAESTRO ---
    df_cat = pd.read_csv(URL_CATALOGO)
    df_cat.columns = df_cat.columns.astype(str).str.replace('\n', ' ').str.replace('\r', '').str.strip()
    df_cat.columns = df_cat.columns.str.replace(r'\s+', ' ', regex=True)
    
    col_activo = next((c for c in df_cat.columns if 'ACTIVO' in c.upper()), None)
    if col_activo:
        df_cat = df_cat[df_cat[col_activo].astype(str).str.strip().str.upper() == 'SI']

    # --- 2. CARGAR PRODUCCIÓN ---
    df_prod = pd.read_csv(URL_PRODUCCION)
    df_prod.columns = df_prod.columns.astype(str).str.strip()
    
    col_fecha_prod = next((c for c in df_prod.columns if 'fecha' in c.lower() and 'inicio' not in c.lower()), None)
    if col_fecha_prod:
        df_prod['Fecha'] = pd.to_datetime(df_prod[col_fecha_prod], dayfirst=True, errors='coerce')
    else:
        df_prod['Fecha'] = pd.NaT
    
    # Calcular golpes (Buenas + Retrabajo)
    col_buenas = next((c for c in df_prod.columns if 'buenas' in c.lower()), None)
    col_retrabajo = next((c for c in df_prod.columns if 'retrabajo' in c.lower()), None)
    
    df_prod['Buenas_Num'] = pd.to_numeric(df_prod[col_buenas].astype(str).str.replace('.', '').str.replace(',', '.'), errors='coerce').fillna(0) if col_buenas else 0
    df_prod['Retrabajo_Num'] = pd.to_numeric(df_prod[col_retrabajo].astype(str).str.replace('.', '').str.replace(',', '.'), errors='coerce').fillna(0) if col_retrabajo else 0
    df_prod['Golpes_Totales'] = df_prod['Buenas_Num'] + df_prod['Retrabajo_Num']
    
    # Extraer código de pieza y aplicar llave de anti-duplicación
    col_pieza_prod = next((c for c in df_prod.columns if 'código producto' in c.lower() or 'codigo producto' in c.lower() or 'pieza' in c.lower()), None)
    if col_pieza_prod:
        df_prod['Pieza_Match'] = df_prod[col_pieza_prod].apply(lambda x: get_match_key(clean_str(x)))
    else:
        df_prod['Pieza_Match'] = "" 
        
    # Nota: Ya no buscamos OP en Producción, todas las OP de la matriz suman los mismos golpes

    # --- 3. CARGAR FORMULARIOS DE MANTENIMIENTO ---
    df_prev = extract_mantenimientos(URL_PREV_FAMMA)
    df_corr = extract_mantenimientos(URL_CORR_FAMMA)
    df_mant_historico = pd.concat([df_prev, df_corr], ignore_index=True)
    
    return df_cat, df_prod, df_mant_historico

# ==========================================
# 4. MOTOR DE CRUCE Y CÁLCULO
# ==========================================
def procesar_estado_matrices(df_cat, df_prod, df_mant):
    resultados = []
    
    # Búsqueda de las columnas en el Catálogo
    col_pieza = next((c for c in df_cat.columns if c.upper() == 'PIEZA'), None)
    col_op = next((c for c in df_cat.columns if c.upper() == 'OP'), None)
    col_cliente = next((c for c in df_cat.columns if 'CLIENTE' in c.upper()), None)
    col_tipo = next((c for c in df_cat.columns if 'TIPO' in c.upper()), None)
    col_limite = next((c for c in df_cat.columns if 'GOLPES PARA MANTENIMIENTO' in c.upper()), None)
    col_alerta = next((c for c in df_cat.columns if 'ALERTA' in c.upper()), None)
    col_prev = next((c for c in df_cat.columns if 'ULTIMO PREVENTIVO' in c.upper()), None)
    col_corr = next((c for c in df_cat.columns if 'ULTIMO CORRECTIVO' in c.upper()), None)
    
    if not col_pieza or not col_op:
        return pd.DataFrame()

    for _, row in df_cat.iterrows():
        pieza_completa = clean_str(row.get(col_pieza, ''))
        op = clean_str(row.get(col_op, ''))
        cliente = clean_str(row.get(col_cliente, '-')) if col_cliente else '-'
        tipo = clean_str(row.get(col_tipo, '-')) if col_tipo else '-'
        
        if not pieza_completa or pieza_completa == 'NAN': continue
        
        # Generar llave única (ignorar L/R si aplica)
        pieza_match = get_match_key(pieza_completa)
        
        # Límites
        limite_mant = pd.to_numeric(row.get(col_limite, 0), errors='coerce') if col_limite else 0
        limite_alerta = pd.to_numeric(row.get(col_alerta, 0), errors='coerce') if col_alerta else 0
        if pd.isna(limite_mant) or limite_mant <= 0: limite_mant = 20000
        if pd.isna(limite_alerta) or limite_alerta <= 0: limite_alerta = limite_mant * 0.8
        
        fecha_base = pd.NaT
        
        # A) Revisar fechas manuales en el catálogo
        if col_prev:
            d_prev = pd.to_datetime(row.get(col_prev), dayfirst=True, errors='coerce')
            if pd.notna(d_prev): fecha_base = d_prev
            
        if col_corr:
            d_corr = pd.to_datetime(row.get(col_corr), dayfirst=True, errors='coerce')
            if pd.notna(d_corr) and (pd.isna(fecha_base) or d_corr > fecha_base): 
                fecha_base = d_corr
            
        # B) Revisar fechas en Google Forms (Mantenimiento). 
        # Comparamos usando pieza_match y OP específica
        if not df_mant.empty:
            mant_match = df_mant[(df_mant['Pieza_Match'] == pieza_match) & (df_mant['OP'] == op)]
            if not mant_match.empty:
                max_form_date = mant_match['Fecha'].max()
                if pd.isna(fecha_base) or max_form_date > fecha_base:
                    fecha_base = max_form_date

        # C) Sumar Producción de la pieza
        prod_match = df_prod[df_prod['Pieza_Match'] == pieza_match]
        if pd.notna(fecha_base):
            # Solo suma los golpes fabricados DESPUÉS del mantenimiento de ESTA OP particular
            prod_match = prod_match[prod_match['Fecha'] >= fecha_base]
            
        golpes_acumulados = prod_match['Golpes_Totales'].sum()
        
        # D) Determinar estado (Semáforo)
        estado = "OK"
        color = "VERDE"
        
        if golpes_acumulados >= limite_mant:
            estado = "MANT. REQUERIDO"
            color = "ROJO"
        elif golpes_acumulados >= limite_alerta:
            estado = "ALERTA PREVENTIVO"
            color = "AMARILLO"
            
        resultados.append({
            'CLIENTE': cliente,
            'PIEZA': pieza_completa, # Mostramos el nombre real completo
            'OP': op,
            'TIPO': tipo,
            'ULT_MANTENIMIENTO': fecha_base.strftime('%d/%m/%Y') if pd.notna(fecha_base) else "Sin Registro",
            'GOLPES': int(golpes_acumulados),
            'LIMITE': int(limite_mant),
            'ALERTA': int(limite_alerta),
            'ESTADO': estado,
            'COLOR': color
        })
        
    df_resultados = pd.DataFrame(resultados)
    
    if df_resultados.empty:
        return pd.DataFrame(columns=['CLIENTE', 'PIEZA', 'OP', 'TIPO', 'ULT_MANTENIMIENTO', 'GOLPES', 'LIMITE', 'ALERTA', 'ESTADO', 'COLOR'])
        
    return df_resultados.sort_values(by=['COLOR', 'GOLPES'], ascending=[False, False])

# ==========================================
# 5. GENERACIÓN DEL PDF (FPDF)
# ==========================================
class PDFGolpes(FPDF):
    def header(self):
        self.set_font("Arial", 'B', 15)
        self.set_text_color(31, 73, 125)
        self.cell(0, 10, "Control de Golpes de Matrices (Mantenimiento)", border=0, ln=True, align='C')
        
        self.set_font("Arial", 'I', 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, f"Calculo generado el: {datetime.now().strftime('%d/%m/%Y %H:%M')}", border=0, ln=True, align='C')
        self.ln(3)

        self.set_font("Arial", 'B', 9)
        self.set_fill_color(31, 73, 125)
        self.set_text_color(255, 255, 255)
        
        # Anchos adaptados (Total 277mm)
        self.cell(20, 8, "Cliente", 1, 0, 'C', fill=True)
        self.cell(65, 8, "Codigo Pieza", 1, 0, 'C', fill=True)
        self.cell(15, 8, "OP", 1, 0, 'C', fill=True)
        self.cell(12, 8, "Tipo", 1, 0, 'C', fill=True)
        self.cell(30, 8, "Ult. Mant.", 1, 0, 'C', fill=True)
        self.cell(30, 8, "Golpes Acum.", 1, 0, 'C', fill=True)
        self.cell(30, 8, "Limite Mant.", 1, 0, 'C', fill=True)
        self.cell(70, 8, "Estado / Accion", 1, 1, 'C', fill=True)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Pagina {self.page_no()}", 0, 0, "C")

def build_pdf_golpes(df_resultados):
    pdf = PDFGolpes(orientation='L', unit='mm', format='A4') # Formato Apaisado
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", '', 8)
    
    if df_resultados.empty:
        pdf.cell(0, 10, "No se encontraron matrices activas para procesar.", align='C')
        temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        pdf.output(temp_pdf.name)
        with open(temp_pdf.name, "rb") as f: pdf_bytes = f.read()
        os.remove(temp_pdf.name)
        return pdf_bytes

    for _, row in df_resultados.iterrows():
        # Paleta de colores suave para lectura clara
        if row['COLOR'] == "ROJO":
            bg_color = (255, 180, 180)
            txt_color = (180, 0, 0)
        elif row['COLOR'] == "AMARILLO":
            bg_color = (255, 240, 180)
            txt_color = (150, 100, 0)
        else:
            bg_color = (198, 239, 206)
            txt_color = (0, 100, 0)
            
        pieza_str = str(row['PIEZA'])[:40] 
        
        pdf.set_text_color(0, 0, 0)
        pdf.cell(20, 7, str(row['CLIENTE']), 1, 0, 'C')
        pdf.cell(65, 7, pieza_str, 1, 0, 'L')
        pdf.cell(15, 7, str(row['OP']), 1, 0, 'C')
        pdf.cell(12, 7, str(row['TIPO']), 1, 0, 'C')
        pdf.cell(30, 7, str(row['ULT_MANTENIMIENTO']), 1, 0, 'C')
        
        pdf.set_fill_color(*bg_color)
        pdf.set_text_color(*txt_color)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(30, 7, f"{row['GOLPES']:,}", 1, 0, 'C', fill=True)
        
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", '', 8)
        pdf.cell(30, 7, f"{row['LIMITE']:,}", 1, 0, 'C')
        
        pdf.set_fill_color(*bg_color)
        pdf.set_text_color(*txt_color)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(70, 7, str(row['ESTADO']), 1, 1, 'C', fill=True)

    temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(temp_pdf.name)
    with open(temp_pdf.name, "rb") as f:
        pdf_bytes = f.read()
    os.remove(temp_pdf.name)
    return pdf_bytes

# ==========================================
# 6. INTERFAZ DE STREAMLIT
# ==========================================
with st.spinner("Conectando y descargando bases de datos..."):
    try:
        df_cat_raw, df_prod_raw, df_mant_raw = load_all_data()
        datos_listos = True
    except Exception as e:
        st.error(f"Error critico conectando con Google Sheets: {e}")
        datos_listos = False

if datos_listos:
    st.success("Bases de datos sincronizadas exitosamente.")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.info("Este reporte cruza la **Producción Oficial**, el **Catálogo Maestro** y los **Mantenimientos Prev/Corr** para calcular el estado actual de las matrices activas en FAMMA.")
    with col2:
        if st.button("🚀 Procesar y Generar PDF de Golpes", use_container_width=True, type="primary"):
            with st.spinner("Calculando estado de matrices..."):
                df_resultados = procesar_estado_matrices(df_cat_raw, df_prod_raw, df_mant_raw)
                
                if df_resultados.empty:
                    st.warning("No se encontraron datos que procesar. Revisa que el catalogo tenga matrices marcadas como 'SI' en la columna de Activos.")
                else:
                    rojos = len(df_resultados[df_resultados['COLOR'] == 'ROJO'])
                    amarillos = len(df_resultados[df_resultados['COLOR'] == 'AMARILLO'])
                    verdes = len(df_resultados[df_resultados['COLOR'] == 'VERDE'])
                    
                    st.write(f"**Resumen de Estado:** 🔴 {rojos} Críticas | 🟡 {amarillos} En Alerta | 🟢 {verdes} OK")
                    
                    pdf_data = build_pdf_golpes(df_resultados)
                    
                    st.download_button(
                        label="📥 Descargar Reporte en PDF",
                        data=pdf_data,
                        file_name=f"Reporte_Golpes_Matrices_{datetime.now().strftime('%d%m%Y')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
