import re
import pandas as pd
import pdfplumber
import streamlit as st
from weasyprint import HTML

# Configuração da página
st.set_page_config(
    page_title="Conferência de Extratos - COB COMPE",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Conferência Financeira - COB COMPE")
st.subheader("Processador Automático de Extratos Bancários")

# Upload do arquivo PDF
arquivo_pdf = st.file_uploader("Arraste e solte o PDF do extrato bancário aqui", type=["pdf"])

def processar_pdf(pdf_bytes):
    creditos = []
    tarifas = []
    
    with pdfplumber.open(pdf_bytes) as pdf:
        for page in pdf.pages:
            texto = page.extract_text()
            if not texto:
                continue
            
            linhas = texto.split('\n')
            for linha in linhas:
                if 'COB COMPE' in linha:
                    partes = linha.split()
                    data = partes[0] if len(partes) > 0 else ""
                    
                    # Filtra Créditos (C)
                    if linha.strip().endswith('C') and not linha.strip().startswith('000000'):
                        match_val = re.search(r'([\d\.]+,\d\d)\s+C', linha)
                        if match_val:
                            val_str = match_val.group(1)
                            val_float = float(val_str.replace('.', '').replace(',', '.'))
                            creditos.append({
                                'Data Mov.': data,
                                'Histórico': 'COB COMPE',
                                'Tipo': 'Crédito (C)',
                                'Valor (R$)': val_float,
                                'Valor Formatado': f"R$ {val_str}"
                            })
                            
                    # Filtra Débitos de Tarifas (D)
                    elif linha.strip().endswith('D'):
                        match_val = re.search(r'([\d\.]+,\d\d)\s+D', linha)
                        if match_val:
                            val_str = match_val.group(1)
                            val_float = float(val_str.replace('.', '').replace(',', '.'))
                            tarifas.append({
                                'Data Mov.': data,
                                'Histórico': 'COB COMPE (Tarifa)',
                                'Tipo': 'Débito (D)',
                                'Valor (R$)': val_float,
                                'Valor Formatado': f"R$ {val_str}"
                            })
                            
    return pd.DataFrame(creditos), pd.DataFrame(tarifas)

def gerar_pdf_relatorio(df_creditos, df_tarifas, total_creditos, total_tarifas):
    html_items = ""
    for idx, row in df_creditos.iterrows():
        html_items += f"""
        <tr>
            <td style="text-align: center;">{idx+1:02d}</td>
            <td style="text-align: center; font-weight: bold;">{row['Data Mov.']}</td>
            <td>{row['Histórico']}</td>
            <td style="text-align: center;"><span style="background-color: #dcfce7; color: #166534; padding: 3px 8px; border-radius: 12px; font-weight: bold;">CRÉDITO (C)</span></td>
            <td style="text-align: right; font-weight: bold;">{row['Valor Formatado']}</td>
        </tr>
        """
        
    html_tarifas = ""
    for idx, row in df_tarifas.iterrows():
        html_tarifas += f"""
        <tr>
            <td style="text-align: center;">{row['Data Mov.']}</td>
            <td>{row['Histórico']}</td>
            <td style="text-align: center;"><span style="background-color: #fee2e2; color: #991b1b; padding: 3px 8px; border-radius: 12px; font-weight: bold;">DÉBITO (D)</span></td>
            <td style="text-align: right;">{row['Valor Formatado']}</td>
        </tr>
        """

    html_full = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            @page {{ size: A4; margin: 15mm; }}
            body {{ font-family: Arial, sans-serif; color: #1e293b; font-size: 10pt; }}
            .header {{ background-color: #1e3a8a; color: white; padding: 15px; margin-bottom: 20px; border-radius: 4px; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
            th {{ background-color: #f1f5f9; padding: 8px; text-align: left; font-size: 9pt; border-bottom: 2px solid #cbd5e1; }}
            td {{ padding: 8px; border-bottom: 1px solid #f1f5f9; font-size: 9pt; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2 style="margin:0;">Relatório de Conferência - COB COMPE</h2>
            <p style="margin:5px 0 0 0; font-size: 9pt;">Extrato Consolidado</p>
        </div>
        
        <h3>Entradas de Crédito (COB COMPE)</h3>
        <table>
            <thead>
                <tr>
                    <th style="text-align: center;">Item</th>
                    <th style="text-align: center;">Data Mov.</th>
                    <th>Histórico</th>
                    <th style="text-align: center;">Tipo</th>
                    <th style="text-align: right;">Valor</th>
                </tr>
            </thead>
            <tbody>
                {html_items}
                <tr style="font-weight: bold; background-color: #f8fafc;">
                    <td colspan="4" style="text-align: right;">TOTAL DE CRÉDITOS:</td>
                    <td style="text-align: right; color: #15803d;">R$ {total_creditos:,.2f}</td>
                </tr>
            </tbody>
        </table>

        <h3>Tarifas Associadas (Débitos)</h3>
        <table>
            <thead>
                <tr>
                    <th style="text-align: center;">Data Mov.</th>
                    <th>Histórico</th>
                    <th style="text-align: center;">Tipo</th>
                    <th style="text-align: right;">Valor</th>
                </tr>
            </thead>
            <tbody>
                {html_tarifas}
            </tbody>
        </table>
    </body>
    </html>
    """
    
    return HTML(string=html_full).write_pdf()

if arquivo_pdf is not None:
    df_creditos, df_tarifas = processar_pdf(arquivo_pdf)
    
    if not df_creditos.empty:
        total_cred = df_creditos['Valor (R$)'].sum()
        total_tar = df_tarifas['Valor (R$)'].sum() if not df_tarifas.empty else 0.0
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Qtd. Créditos", len(df_creditos))
        col2.metric("Total Créditos (COB COMPE)", f"R$ {total_cred:,.2f}")
        col3.metric("Total Tarifas (Débitos)", f"R$ {total_tar:,.2f}")
        
        st.divider()
        
        st.write("### 🟢 Créditos Identificados")
        st.dataframe(df_creditos[['Data Mov.', 'Histórico', 'Tipo', 'Valor Formatado']], use_container_width=True)
        
        if not df_tarifas.empty:
            st.write("### 🔴 Tarifas Associadas")
            st.dataframe(df_tarifas[['Data Mov.', 'Histórico', 'Tipo', 'Valor Formatado']], use_container_width=True)
            
        pdf_out = gerar_pdf_relatorio(df_creditos, df_tarifas, total_cred, total_tar)
        
        st.download_button(
            label="📄 Baixar Relatório Formatado em PDF",
            data=pdf_out,
            file_name="Relatorio_Conferencia_COB_COMPE.pdf",
            mime="application/pdf"
        )
    else:
        st.warning("Nenhum lançamento 'COB COMPE' de crédito foi encontrado no PDF enviado.")
