import streamlit as st
import pandas as pd
from datetime import datetime
import tempfile
import os
import re
from fpdf import FPDF

# ==========================================
# 1. CONFIGURACIÓN Y ESTILOS
# ==========================================
st.set_page_config(page_title="Control de Golpes de Matrices", layout="wide", page_icon="⚙️")

st.markdown("""
<style>
    .header-style { font-size: 26px; font-weight: bold; margin-bottom: 5px; color: #1F2937; text-align: center; }
    .metric-container { display: flex; justify-content: space-around; background-color: #f8f9fa; padding: 10px; border-radius: 5px; }
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
    if pd.isna(val): return ""
    v = str(val).strip().upper()
    if v.endswith('.0'): v = v[:-2]
    return v

def extract_mantenimientos(url):
    """Extrae Fecha, Matriz y OP de los formularios de mantenimiento."""
    try:
        df = pd.read_csv(url)
        df.columns = df.columns.astype(str).str.upper().str.strip()
        
        # Buscar columna de fecha
        col_fecha = next((c for c in df.columns if 'FECHA' in c), None)
        if not col_fecha: return pd.DataFrame()

        registros = []
        for _, row in df.iterrows():
            fecha = pd.to_datetime(row[col_fecha], dayfirst=True, errors='coerce')
            if pd.isna(fecha): continue
            
            # Buscar piezas y operaciones
            for i, col_name in enumerate(df.columns):
                base_col = col_name.split('.')[0].strip()
                if base_col in VALID_PIEZA_COLS:
                    pieza = clean_str(row.iloc[i])
                    if pieza and pieza not in ['NAN', 'NONE', '-', '0', 'N/A', 'NO APLICA']:
                        op = ""
                        # Buscar la OP en las columnas siguientes
                        for j in range(i+1, min(i+4, len(df.columns))):
                            if 'OPERACION' in df.columns[j] or 'OPERACIÓN' in df.columns[j]:
                                op = clean_str(row.iloc[j])
                                break
                        registros.append({'Fecha': fecha, 'Pieza': pieza, 'OP': op})
        return pd.DataFrame(registros)
    except Exception as e:
        print(f"Error cargando mant: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_all_data():
    # 1. Cargar Catálogo (Filtrado por FAMMA ACTIVO? == SI)
    df_cat = pd.read_csv(URL_CATALOGO, skiprows=1) # Saltamos la primera fila que suele tener super-encabezados
    # Limpiamos nombres de columnas
    df_cat.columns = df_cat.columns.astype(str).str.strip().str.replace('\n', '')
    
    col_activo = next((c for c in df_cat.columns if 'FAMMA' in c.upper() and 'ACTIVO' in c.upper()), None)
    if col_activo:
        df_cat = df_cat[df_cat[col_activo].astype(str).str.strip().str.upper() == 'SI']

    # 2. Cargar Producción
    df_prod = pd.read_csv(URL_PRODUCCION)
    col_fecha_prod = next((c for c in df_prod.columns if 'fecha' in c.lower() and 'inicio' not in c.lower()), None)
    df_prod['Fecha'] = pd.to_datetime(df_prod[col_fecha_prod], dayfirst=True, errors='coerce')
    
    # Calcular golpes totales (Buenas + Retrabajo)
    col_buenas = next((c for c in df_prod.columns if 'buenas' in c.lower()), 'Buenas')
    col_retrabajo = next((c for c in df_prod.columns if 'retrabajo' in c.lower()), 'Retrabajo')
    
    df_prod['Buenas_Num'] = pd.to_numeric(df_prod[col_buenas].astype(str).str.replace('.', '').str.replace(',', '.'), errors='coerce').fillna(0)
    df_prod['Retrabajo_Num'] = pd.to_numeric(df_prod[col_retrabajo].astype(str).str.replace('.', '').str.replace(',', '.'), errors='coerce').fillna(0)
    df_prod['Golpes_Totales'] = df_prod['Buenas_Num'] + df_prod['Retrabajo_Num']
    
    df_prod['Pieza_Clean'] = df_prod['Pieza'].apply(clean_str)
    df_prod['OP_Clean'] = df_prod['OP'].apply(clean_str)

    # 3. Cargar Mantenimientos
    df_prev = extract_mantenimientos(URL_PREV_FAMMA)
    df_corr = extract_mantenimientos(URL_CORR_FAMMA)
    df_mant_historico = pd.concat([df_prev, df_corr], ignore_index=True)
    
    return df_cat, df_prod, df_mant_historico

# ==========================================
# 4. MOTOR DE CRUCE Y CÁLCULO
# ==========================================
def procesar_estado_matrices(df_cat, df_prod, df_mant):
    resultados = []
    
    for _, row in df_cat.iterrows():
        pieza = clean_str(row.get('PIEZA', ''))
        op = clean_str(row.get('OP', ''))
        cliente = clean_str(row.get('CLIENTE', '-'))
        tipo = clean_str(row.get('TIPO', '-'))
        
        if not pieza: continue
        
        limite_mant = pd.to_numeric(row.get('GOLPES PARA MANTENIMIENTO', 0), errors='coerce')
        limite_alerta = pd.to_numeric(row.get('ALERTA', 0), errors='coerce')
        if pd.isna(limite_mant) or limite_mant <= 0: limite_mant = 20000 # Valor fallback
        if pd.isna(limite_alerta) or limite_alerta <= 0: limite_alerta = limite_mant * 0.8
        
        # Determinar la fecha base (la más reciente entre el catálogo y los formularios)
        fecha_base = pd.NaT
        
        # A) Fecha desde el catálogo (Ultimo Preventivo o Correctivo)
        d_prev = pd.to_datetime(row.get('Ultimo Preventivo'), dayfirst=True, errors='coerce')
        d_corr = pd.to_datetime(row.get('Ultimo Correctivo'), dayfirst=True, errors='coerce')
        if pd.notna(d_prev): fecha_base = d_prev
        if pd.notna(d_corr) and (pd.isna(fecha_base) or d_corr > fecha_base): fecha_base = d_corr
            
        # B) Fecha desde los registros reales de formularios
        if not df_mant.empty:
            mant_match = df_mant[(df_mant['Pieza'] == pieza) & (df_mant['OP'] == op)]
            if not mant_match.empty:
                max_form_date = mant_match['Fecha'].max()
                if pd.isna(fecha_base) or max_form_date > fecha_base:
                    fecha_base = max_form_date

        # C) Sumar Producción posterior a la fecha base
        prod_match = df_prod[(df_prod['Pieza_Clean'] == pieza) & (df_prod['OP_Clean'] == op)]
        if pd.notna(fecha_base):
            prod_match = prod_match[prod_match['Fecha'] >= fecha_base]
            
        golpes_acumulados = prod_match['Golpes_Totales'].sum()
        
        # D) Lógica de Semáforo
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
            'PIEZA': pieza,
            'OP': op,
            'TIPO': tipo,
            'ULT_MANTENIMIENTO': fecha_base.strftime('%d/%m/%Y') if pd.notna(fecha_base) else "Sin Registro",
            'GOLPES': int(golpes_acumulados),
            'LIMITE': int(limite_mant),
            'ALERTA': int(limite_alerta),
            'ESTADO': estado,
            'COLOR': color
        })
        
    return pd.DataFrame(resultados).sort_values(by=['COLOR', 'GOLPES'], ascending=[False, False])

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
        self.cell(0, 5, f"Cálculo generado el: {datetime.now().strftime('%d/%m/%Y %H:%M')}", border=0, ln=True, align='C')
        self.ln(3)

        # Encabezados de tabla (Ancho Total: 277mm para Landscape)
        self.set_font("Arial", 'B', 9)
        self.set_fill_color(31, 73, 125)
        self.set_text_color(255, 255, 255)
        
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
    pdf = PDFGolpes(orientation='L', unit='mm', format='A4') # Landscape
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", '', 8)
    
    for _, row in df_resultados.iterrows():
        # Lógica de Color para la celda de Golpes y Estado
        if row['COLOR'] == "ROJO":
            bg_color = (255, 180, 180) # Rojo pastel
            txt_color = (180, 0, 0)
        elif row['COLOR'] == "AMARILLO":
            bg_color = (255, 240, 180) # Amarillo pastel
            txt_color = (150, 100, 0)
        else:
            bg_color = (198, 239, 206) # Verde pastel
            txt_color = (0, 100, 0)
            
        pieza_str = str(row['PIEZA'])[:40] 
        
        pdf.set_text_color(0, 0, 0)
        pdf.cell(20, 7, str(row['CLIENTE']), 1, 0, 'C')
        pdf.cell(65, 7, pieza_str, 1, 0, 'L')
        pdf.cell(15, 7, str(row['OP']), 1, 0, 'C')
        pdf.cell(12, 7, str(row['TIPO']), 1, 0, 'C')
        pdf.cell(30, 7, str(row['ULT_MANTENIMIENTO']), 1, 0, 'C')
        
        # Celda de Golpes con Semáforo
        pdf.set_fill_color(*bg_color)
        pdf.set_text_color(*txt_color)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(30, 7, f"{row['GOLPES']:,}", 1, 0, 'C', fill=True)
        
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", '', 8)
        pdf.cell(30, 7, f"{row['LIMITE']:,}", 1, 0, 'C')
        
        # Celda de Estado con Semáforo
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
        st.error(f"Error crítico conectando con Google Sheets: {e}")
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
                
                # Resumen Rápido en pantalla
                rojos = len(df_resultados[df_resultados['COLOR'] == 'ROJO'])
                amarillos = len(df_resultados[df_resultados['COLOR'] == 'AMARILLO'])
                verdes = len(df_resultados[df_resultados['COLOR'] == 'VERDE'])
                
                st.write(f"**Resumen:** 🔴 {rojos} Críticas | 🟡 {amarillos} En Alerta | 🟢 {verdes} OK")
                
                # Construir PDF
                pdf_data = build_pdf_golpes(df_resultados)
                
                st.download_button(
                    label="📥 Descargar Reporte en PDF",
                    data=pdf_data,
                    file_name=f"Reporte_Golpes_Matrices_{datetime.now().strftime('%d%m%Y')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
