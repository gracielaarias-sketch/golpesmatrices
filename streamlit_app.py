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

def get_match_key(pieza_str):
    """Corta los sufijos pares (ej: /748R) para agrupar golpes de producción en uno solo."""
    return pieza_str.split('/')[0].strip() if '/' in pieza_str else pieza_str

def extract_mantenimientos(url, tipo_mant):
    """Extrae mantenimientos diferenciando el estado 'Terminado'."""
    try:
        df = pd.read_csv(url)
        cols = [str(c).upper().strip() for c in df.columns]
        
        col_fecha = next((i for i, c in enumerate(cols) if 'FECHA' in c), None)
        # Buscar columna "TERMINADO"
        col_term = next((i for i, c in enumerate(cols) if 'TERMINADO' in c or 'TERMINO' in c), None)
        
        if col_fecha is None: return pd.DataFrame()

        registros = []
        for _, row in df.iterrows():
            fecha = pd.to_datetime(row.iloc[col_fecha], dayfirst=True, errors='coerce')
            if pd.isna(fecha): continue
            
            # Evaluar si está terminado
            estado_terminado = 'NO'
            if col_term is not None and pd.notna(row.iloc[col_term]):
                v_term = str(row.iloc[col_term]).strip().upper()
                if 'SI' in v_term or 'SÍ' in v_term:
                    estado_terminado = 'SI'

            for i, col_name in enumerate(cols):
                base_col = col_name.split('.')[0].strip()
                if base_col in VALID_PIEZA_COLS:
                    pieza_completa = clean_str(row.iloc[i])
                    if pieza_completa and pieza_completa not in ['NAN', 'NONE', '-', '0', 'N/A', 'NO APLICA', '']:
                        pieza_match = get_match_key(pieza_completa)
                        op = ""
                        for j in range(i+1, min(i+4, len(cols))):
                            next_col = cols[j].split('.')[0].strip()
                            if 'OPERACION' in next_col or 'OPERACIÓN' in next_col or 'OP' == next_col:
                                op = clean_str(row.iloc[j])
                                break
                        
                        registros.append({
                            'Fecha': fecha, 
                            'Pieza_Completa': pieza_completa, 
                            'Pieza_Match': pieza_match, 
                            'OP': op,
                            'Tipo_Mant': tipo_mant,
                            'Terminado': estado_terminado
                        })
        return pd.DataFrame(registros)
    except Exception as e:
        print(f"Error cargando mantenimiento: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_all_data():
    df_cat = pd.read_csv(URL_CATALOGO)
    df_cat.columns = df_cat.columns.astype(str).str.replace('\n', ' ').str.replace('\r', '').str.strip()
    df_cat.columns = df_cat.columns.str.replace(r'\s+', ' ', regex=True)
    
    col_activo = next((c for c in df_cat.columns if 'ACTIVO' in c.upper()), None)
    if col_activo:
        df_cat = df_cat[df_cat[col_activo].astype(str).str.strip().str.upper() == 'SI']

    df_prod = pd.read_csv(URL_PRODUCCION)
    df_prod.columns = df_prod.columns.astype(str).str.strip()
    
    col_fecha_prod = next((c for c in df_prod.columns if 'fecha' in c.lower() and 'inicio' not in c.lower()), None)
    if col_fecha_prod:
        df_prod['Fecha'] = pd.to_datetime(df_prod[col_fecha_prod], dayfirst=True, errors='coerce')
    else:
        df_prod['Fecha'] = pd.NaT
    
    col_buenas = next((c for c in df_prod.columns if 'buenas' in c.lower()), None)
    col_retrabajo = next((c for c in df_prod.columns if 'retrabajo' in c.lower()), None)
    
    df_prod['Buenas_Num'] = pd.to_numeric(df_prod[col_buenas].astype(str).str.replace('.', '').str.replace(',', '.'), errors='coerce').fillna(0) if col_buenas else 0
    df_prod['Retrabajo_Num'] = pd.to_numeric(df_prod[col_retrabajo].astype(str).str.replace('.', '').str.replace(',', '.'), errors='coerce').fillna(0) if col_retrabajo else 0
    df_prod['Golpes_Totales'] = df_prod['Buenas_Num'] + df_prod['Retrabajo_Num']
    
    col_pieza_prod = next((c for c in df_prod.columns if 'código producto' in c.lower() or 'codigo producto' in c.lower() or 'pieza' in c.lower()), None)
    if col_pieza_prod:
        df_prod['Pieza_Match'] = df_prod[col_pieza_prod].apply(lambda x: get_match_key(clean_str(x)))
    else:
        df_prod['Pieza_Match'] = "" 

    # Cargamos asignándole el tipo correspondiente
    df_prev = extract_mantenimientos(URL_PREV_FAMMA, "PREV")
    df_corr = extract_mantenimientos(URL_CORR_FAMMA, "CORR")
    df_mant_historico = pd.concat([df_prev, df_corr], ignore_index=True)
    
    return df_cat, df_prod, df_mant_historico

# ==========================================
# 4. MOTOR DE CRUCE Y CÁLCULO
# ==========================================
def procesar_estado_matrices(df_cat, df_prod, df_mant):
    resultados = []
    abiertos = []
    
    col_pieza = next((c for c in df_cat.columns if c.upper() == 'PIEZA'), None)
    col_op = next((c for c in df_cat.columns if c.upper() == 'OP'), None)
    col_cliente = next((c for c in df_cat.columns if 'CLIENTE' in c.upper()), None)
    col_tipo = next((c for c in df_cat.columns if 'TIPO' in c.upper()), None)
    col_limite = next((c for c in df_cat.columns if 'GOLPES PARA MANTENIMIENTO' in c.upper()), None)
    col_alerta = next((c for c in df_cat.columns if 'ALERTA' in c.upper()), None)
    col_prev = next((c for c in df_cat.columns if 'ULTIMO PREVENTIVO' in c.upper()), None)
    col_corr = next((c for c in df_cat.columns if 'ULTIMO CORRECTIVO' in c.upper()), None)
    
    if not col_pieza or not col_op:
        return pd.DataFrame(), pd.DataFrame()

    # Recorremos manteniendo el orden del catálogo
    for _, row in df_cat.iterrows():
        pieza_completa = clean_str(row.get(col_pieza, ''))
        op = clean_str(row.get(col_op, ''))
        cliente = clean_str(row.get(col_cliente, '-')) if col_cliente else '-'
        tipo = clean_str(row.get(col_tipo, '-')) if col_tipo else '-'
        
        if not pieza_completa or pieza_completa == 'NAN': continue
        
        pieza_match = get_match_key(pieza_completa)
        
        limite_mant = pd.to_numeric(row.get(col_limite, 0), errors='coerce') if col_limite else 0
        limite_alerta = pd.to_numeric(row.get(col_alerta, 0), errors='coerce') if col_alerta else 0
        if pd.isna(limite_mant) or limite_mant <= 0: limite_mant = 20000
        if pd.isna(limite_alerta) or limite_alerta <= 0: limite_alerta = limite_mant * 0.8
        
        fecha_base = pd.NaT
        tipo_ultimo = ""
        
        # A) Revisar fechas manuales en el catálogo
        if col_prev:
            d_prev = pd.to_datetime(row.get(col_prev), dayfirst=True, errors='coerce')
            if pd.notna(d_prev): 
                fecha_base = d_prev
                tipo_ultimo = "PREV"
            
        if col_corr:
            d_corr = pd.to_datetime(row.get(col_corr), dayfirst=True, errors='coerce')
            if pd.notna(d_corr) and (pd.isna(fecha_base) or d_corr > fecha_base): 
                fecha_base = d_corr
                tipo_ultimo = "CORR"
            
        # B) Revisar fechas en Google Forms (Mantenimientos Reales)
        tiene_abierto = False
        fecha_abierto = None
        tipo_abierto = ""

        if not df_mant.empty:
            mant_match = df_mant[(df_mant['Pieza_Match'] == pieza_match) & (df_mant['OP'] == op)]
            
            # --- 1. Buscar terminados para reiniciar contador ---
            mant_term = mant_match[mant_match['Terminado'] == 'SI']
            if not mant_term.empty:
                idx_max = mant_term['Fecha'].idxmax()
                max_form_date = mant_term.loc[idx_max, 'Fecha']
                
                # Si el formulario tiene un mantenimiento MÁS RECIENTE que el catálogo manual, gana el formulario
                if pd.isna(fecha_base) or max_form_date > fecha_base:
                    fecha_base = max_form_date
                    tipo_ultimo = mant_term.loc[idx_max, 'Tipo_Mant']
                    
            # --- 2. Buscar mantenimientos abiertos ---
            mant_abiertos = mant_match[mant_match['Terminado'] == 'NO']
            if not mant_abiertos.empty:
                tiene_abierto = True
                idx_max_ab = mant_abiertos['Fecha'].idxmax()
                fecha_abierto = mant_abiertos.loc[idx_max_ab, 'Fecha']
                tipo_abierto = mant_abiertos.loc[idx_max_ab, 'Tipo_Mant']

        # C) Sumar Producción post-mantenimiento
        prod_match = df_prod[df_prod['Pieza_Match'] == pieza_match]
        if pd.notna(fecha_base):
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
            
        # Construir string visual de fecha
        str_fecha_base = "Sin Registro"
        if pd.notna(fecha_base):
            str_fecha_base = f"{fecha_base.strftime('%d/%m/%y')} ({tipo_ultimo})"
            
        resultados.append({
            'CLIENTE': cliente,
            'PIEZA': pieza_completa,
            'OP': op,
            'TIPO': tipo,
            'ULT_MANTENIMIENTO': str_fecha_base,
            'GOLPES': int(golpes_acumulados),
            'LIMITE': int(limite_mant),
            'ESTADO': estado,
            'COLOR': color
        })
        
        if tiene_abierto:
            abiertos.append({
                'CLIENTE': cliente,
                'PIEZA': pieza_completa,
                'OP': op,
                'TIPO': tipo,
                'TIPO_MANT_ABIERTO': tipo_abierto,
                'FECHA_APERTURA': fecha_abierto.strftime('%d/%m/%Y')
            })
            
    df_resultados = pd.DataFrame(resultados)
    df_abiertos = pd.DataFrame(abiertos)
    
    # Retornamos sin ordenar para respetar el orden natural del catálogo (Gamas)
    return df_resultados, df_abiertos

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

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Pagina {self.page_no()}", 0, 0, "C")

def build_pdf_golpes(df_resultados, df_abiertos):
    pdf = PDFGolpes(orientation='L', unit='mm', format='A4') # Formato Apaisado
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    if df_resultados.empty:
        pdf.set_font("Arial", '', 10)
        pdf.cell(0, 10, "No se encontraron matrices activas para procesar.", align='C')
        temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        pdf.output(temp_pdf.name)
        with open(temp_pdf.name, "rb") as f: pdf_bytes = f.read()
        os.remove(temp_pdf.name)
        return pdf_bytes

    # --- TABLA PRINCIPAL ---
    pdf.set_font("Arial", 'B', 9)
    pdf.set_fill_color(31, 73, 125)
    pdf.set_text_color(255, 255, 255)
    
    # Encabezados (Suma Total 277mm)
    pdf.cell(18, 8, "Cliente", 1, 0, 'C', fill=True)
    pdf.cell(63, 8, "Codigo Pieza", 1, 0, 'C', fill=True)
    pdf.cell(12, 8, "OP", 1, 0, 'C', fill=True)
    pdf.cell(12, 8, "Tipo", 1, 0, 'C', fill=True)
    pdf.cell(35, 8, "Ult. Mant. Cerrado", 1, 0, 'C', fill=True)
    pdf.cell(27, 8, "Golpes Acum.", 1, 0, 'C', fill=True)
    pdf.cell(27, 8, "Limite Mant.", 1, 0, 'C', fill=True)
    pdf.cell(83, 8, "Estado / Accion", 1, 1, 'C', fill=True)
    
    pdf.set_font("Arial", '', 8)
    
    for _, row in df_resultados.iterrows():
        # Paleta de Semáforo
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
        pdf.cell(18, 7, str(row['CLIENTE']), 1, 0, 'C')
        pdf.cell(63, 7, pieza_str, 1, 0, 'L')
        pdf.cell(12, 7, str(row['OP']), 1, 0, 'C')
        pdf.cell(12, 7, str(row['TIPO']), 1, 0, 'C')
        pdf.cell(35, 7, str(row['ULT_MANTENIMIENTO']), 1, 0, 'C')
        
        pdf.set_fill_color(*bg_color)
        pdf.set_text_color(*txt_color)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(27, 7, f"{row['GOLPES']:,}", 1, 0, 'C', fill=True)
        
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", '', 8)
        pdf.cell(27, 7, f"{row['LIMITE']:,}", 1, 0, 'C')
        
        pdf.set_fill_color(*bg_color)
        pdf.set_text_color(*txt_color)
        pdf.set_font("Arial", 'B', 8)
        pdf.cell(83, 7, str(row['ESTADO']), 1, 1, 'C', fill=True)

    # --- ANEXO: MANTENIMIENTOS ABIERTOS ---
    if not df_abiertos.empty:
        pdf.add_page()
        pdf.set_font("Arial", 'B', 12)
        pdf.set_text_color(192, 0, 0) # Rojo oscuro
        pdf.cell(0, 8, "MANTENIMIENTOS ABIERTOS (Pendientes de Cierre)", ln=True)
        pdf.set_font("Arial", 'I', 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 5, "Las siguientes matrices tienen un registro de mantenimiento en proceso. Sus golpes no se reiniciaran hasta que se marquen como terminadas.", ln=True)
        pdf.ln(3)
        
        pdf.set_font("Arial", 'B', 9)
        pdf.set_fill_color(192, 0, 0)
        pdf.set_text_color(255, 255, 255)
        
        pdf.cell(25, 8, "Cliente", 1, 0, 'C', fill=True)
        pdf.cell(80, 8, "Codigo Pieza", 1, 0, 'C', fill=True)
        pdf.cell(15, 8, "OP", 1, 0, 'C', fill=True)
        pdf.cell(20, 8, "Tipo", 1, 0, 'C', fill=True)
        pdf.cell(35, 8, "Tipo Mant.", 1, 0, 'C', fill=True)
        pdf.cell(35, 8, "Fecha Apertura", 1, 1, 'C', fill=True)
        
        pdf.set_font("Arial", '', 8)
        pdf.set_text_color(0, 0, 0)
        for _, row_ab in df_abiertos.iterrows():
            pdf.cell(25, 7, str(row_ab['CLIENTE']), 1, 0, 'C')
            pdf.cell(80, 7, str(row_ab['PIEZA'])[:50], 1, 0, 'L')
            pdf.cell(15, 7, str(row_ab['OP']), 1, 0, 'C')
            pdf.cell(20, 7, str(row_ab['TIPO']), 1, 0, 'C')
            pdf.cell(35, 7, str(row_ab['TIPO_MANT_ABIERTO']), 1, 0, 'C')
            pdf.cell(35, 7, str(row_ab['FECHA_APERTURA']), 1, 1, 'C')

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
                df_res, df_abiertos = procesar_estado_matrices(df_cat_raw, df_prod_raw, df_mant_raw)
                
                if df_res.empty:
                    st.warning("No se encontraron datos que procesar. Revisa que el catalogo tenga matrices marcadas como 'SI' en la columna de Activos.")
                else:
                    rojos = len(df_res[df_res['COLOR'] == 'ROJO'])
                    amarillos = len(df_res[df_res['COLOR'] == 'AMARILLO'])
                    verdes = len(df_res[df_res['COLOR'] == 'VERDE'])
                    
                    st.write(f"**Resumen de Estado:** 🔴 {rojos} Críticas | 🟡 {amarillos} En Alerta | 🟢 {verdes} OK")
                    if not df_abiertos.empty:
                        st.caption(f"⚠️ *Atención: Existen {len(df_abiertos)} mantenimientos abiertos que impiden el reinicio de golpes para esas OP.*")
                    
                    pdf_data = build_pdf_golpes(df_res, df_abiertos)
                    
                    st.download_button(
                        label="📥 Descargar Reporte en PDF",
                        data=pdf_data,
                        file_name=f"Reporte_Golpes_Matrices_{datetime.now().strftime('%d%m%Y')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
