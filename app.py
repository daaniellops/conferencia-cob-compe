import io
import re
from datetime import datetime
import pandas as pd
import pdfplumber
import streamlit as st
from xhtml2pdf import pisa

st.set_page_config(
    page_title="Conferência de Extratos - COB COMPE",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Conferência Financeira - COB COMPE")
st.subheader("Processador Automático de Extratos Bancários")

arquivo_pdf = st.file_uploader("Arraste e solte o PDF do extrato bancário aqui", type=["pdf"])

def extrair_metadados_e_dados(pdf_bytes):
    creditos = []
    tarifas = []
    
    meta = {
        "cliente": "Não identificado",
        "periodo": "Não identificado",
        "conta": "Não identificada"
    }
    
    with pdfplumber.open(pdf_bytes) as pdf:
        # Extrai metadados da primeira página
        primeira_pagina = pdf.pages[0].extract_text() or ""
        
        # Busca Razão Social / Nome do Cliente
        match_cliente = re.search(r'Nome\s*:\s*([^\n]+)', primeira_pagina, re.IGNORECASE) or \
                        re.search(r'Cliente\s*:\s*([^\n]+)', primeira_pagina, re.IGNORECASE)
        if match_cliente:
            meta["cliente"] = match_cliente.group(1).strip()
            
        # Busca Período do Extrato
        match_periodo = re.search(r'Período\s*:\s*([\d\/]+\s*a\s*[\d\/]+)', primeira_pagina, re.IGNORECASE)
        if match_periodo:
            meta["periodo"] = match_periodo.group(1).strip()
            
        # Busca Agência e Conta
        match_conta = re.search(r'Conta\s*:\s*([\d\s\-\|]+)', primeira_pagina, re.IGNORECASE)
        if match_conta:
            meta["conta"] = match_conta.group(1).strip()

        # Extração de lançamentos em todas as páginas
        for page in pdf.pages:
            texto = page.extract_text()
            if not texto:
                continue
            
            linhas = texto.split('\n')
            for linha in linhas:
                if 'COB COMPE' in linha:
                    partes = linha.split()
                    data = partes[0] if len(partes) > 0 else ""
                    
                    # Captura complemento do histórico ex: (030826)
                    match_cod = re.search(r'COB COMPE\s*(\(\d+\))?', linha)
                    historico = "COB COMPE"
                    if match_cod and match_cod.group(1):
                        historico = f"COB COMPE {match_cod.group(1)}"
                    
                    # Filtra Créditos (C)
                    if linha.strip().endswith('C') and not linha.strip().startswith('000000'):
                        match_val = re.search(r'([\d\.]+,\d\d)\s+C', linha)
                        if match_val:
                            val_str = match_val.group(1)
                            val_float = float(val_str.replace('.', '').replace(',', '.'))
                            creditos.append({
                                'Data Mov.': data,
                                'Histórico': historico,
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
                                'Histórico': f"{historico} (Tarifa)",
                                'Tipo': 'Débito (D)',
                                'Valor (R$)': val_float,
                                'Valor Formatado': f"R$ {val_str}"
                            })
                            
    return meta, pd.DataFrame(creditos), pd.DataFrame(tarifas)

def fmt_brl(valor):
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def gerar_pdf_relatorio(meta, df_creditos, df_tarifas, total_creditos, total_tarifas):
    media_lanc = total_creditos / len(df_creditos) if len(df_creditos) > 0 else 0.0
    data_emissao = datetime.now().strftime("%d/%m/%Y")
    
    html_items = ""
    for idx, row in df_creditos.iterrows():
        html_items += f"""
        <tr>
            <td style="text-align: center;">{idx+1:02d}</td>
            <td style="text-align: center; font-weight: bold;">{row['Data Mov.']}</td>
            <td>{row['Histórico']}</td>
            <td style="text-align: center;"><span style="color: #166534; font-weight: bold;">CRÉDITO (C)</span></td>
            <td style="text-align: right; font-weight: bold;">{row['Valor Formatado']}</td>
        </tr>
        """
        
    html_tarifas = ""
    for idx, row in df_tarifas.iterrows():
        html_tarifas += f"""
        <tr>
            <td style="text-align: center;">{row['Data Mov.']}</td>
            <td>{row['Histórico']}</td>
            <td style="text-align: center;"><span style="color: #991b1b; font-weight: bold;">DÉBITO (D)</span></td>
            <td style="text-align: right;">{row['Valor Formatado']}</td>
        </tr>
        """

    html_full = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            @page {{ size: a4; margin: 1cm; }}
            body {{ font-family: Helvetica, Arial, sans-serif; color: #1e293b; font-size: 9pt; }}
            .header {{ background-color: #1e3a8a; color: white; padding: 12px; margin-bottom: 15px; border-radius: 4px; }}
            .info-table {{ width: 100%; margin-bottom: 15px; background-color: #f8fafc; padding: 8px; border: 1px solid #e2e8f0; }}
            .cards-table {{ width: 100%; margin-bottom: 15px; text-align: center; }}
            .card {{ background-color: #f1f5f9; padding: 10px; border: 1px solid #cbd5e1; border-radius: 4px; }}
            .card-title {{ font-size: 8pt; font-weight: bold; color: #475569; text-transform: uppercase; }}
            .card-value {{ font-size: 11pt; font-weight: bold; color: #1e3a8a; margin-top: 4px; }}
            table.data-table {{ width: 100%; border-collapse: collapse; margin-bottom: 15px; }}
            table.data-table th {{ background-color: #f1f5f9; padding: 6px; text-align: left; font-size: 8pt; border-bottom: 2px solid #cbd5e1; }}
            table.data-table td {{ padding: 6px; border-bottom: 1px solid #f1f5f9; font-size: 8.5pt; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2 style="margin:0; font-size: 14pt;">Relatório de Conferência Financeira</h2>
            <p style="margin:3px 0 0 0; font-size: 9pt;">Créditos de Cobrança Compensada (COB COMPE) - Extrato Caixa</p>
        </div>
        
        <table class="info-table">
            <tr>
                <td><b>Cliente:</b> {meta['cliente']}</td>
                <td><b>Período:</b> {meta['periodo']}</td>
            </tr>
            <tr>
                <td><b>Conta:</b> {meta['conta']}</td>
                <td><b>Data Emissão:</b> {data_emissao}</td>
            </tr>
        </table>

        <table class="cards-table">
            <tr>
                <td width="32%" class="card">
                    <div class="card-title">Qtd. Lançamentos (C)</div>
                    <div class="card-value">{len(df_creditos)} entradas</div>
                </td>
                <td width="2%"></td>
                <td width="32%" class="card">
                    <div class="card-title">Total Créditos COB COMPE</div>
                    <div class="card-value" style="color: #15803d;">{fmt_brl(total_creditos)}</div>
                </td>
                <td width="2%"></td>
                <td width="32%" class="card">
                    <div class="card-title">Média por Lançamento</div>
                    <div class="card-value">{fmt_brl(media_lanc)}</div>
                </td>
            </tr>
        </table>

        <h3 style="color: #1e3a8a; font-size: 10pt; margin-bottom: 5px;">Detalhamento dos Créditos (COB COMPE)</h3>
        <table class="data-table">
            <thead>
                <tr>
                    <th style="text-align: center;" width="8%">Item</th>
                    <th style="text-align: center;" width="15%">Data Mov.</th>
                    <th width="42%">Histórico</th>
                    <th style="text-align: center;" width="15%">Tipo</th>
                    <th style="text-align: right;" width="20%">Valor (R$)</th>
                </tr>
            </thead>
            <tbody>
                {html_items}
                <tr style="font-weight: bold; background-color: #f8fafc;">
                    <td colspan="4" style="text-align: right;">TOTAL DE CRÉDITOS COMPENSADOS:</td>
                    <td style="text-align: right; color: #15803d;">{fmt_brl(total_creditos)}</td>
                </tr>
            </tbody>
        </table>

        {"<h3 style='color: #1e3a8a; font-size: 10pt; margin-bottom: 5px;'>Informativo Complementar (Tarifas Associadas)</h3>" if not df_tarifas.empty else ""}
        {"<table class='data-table'><thead><tr><th style='text-align: center;'>Data Mov.</th><th>Histórico</th><th style='text-align: center;'>Tipo</th><th style='text-align: right;'>Valor (R$)</th></tr></thead><tbody>" + html_tarifas + "</tbody></table>" if not df_tarifas.empty else ""}

        <div style="margin-top: 15px; font-size: 7.5pt; color: #64748b;">
            <b>Observações para Conferência:</b><br/>
            • Os valores listados correspondem exclusivamente às entradas brutas de cobranças compensadas (créditos com sufixo 'C').<br/>
            • Relatório gerado automaticamente para auxílio de conferência e conciliação bancária.
        </div>
    </body>
    </html>
    """
    
    pdf_buffer = io.BytesIO()
    pisa.CreatePDF(io.StringIO(html_full), dest=pdf_buffer)
    return pdf_buffer.getvalue()

if arquivo_pdf is not None:
    meta, df_creditos, df_tarifas = extrair_metadados_e_dados(arquivo_pdf)
    
    if not df_creditos.empty:
        total_cred = df_creditos['Valor (R$)'].sum()
        total_tar = df_tarifas['Valor (R$)'].sum() if not df_tarifas.empty else 0.0
        
        st.info(f"**Cliente:** {meta['cliente']} | **Conta:** {meta['conta']} | **Período:** {meta['periodo']}")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Qtd. Créditos", len(df_creditos))
        col2.metric("Total Créditos", fmt_brl(total_cred))
        col3.metric("Média p/ Lançamento", fmt_brl(total_cred / len(df_creditos)))
        
        st.divider()
        st.write("### 🟢 Créditos Identificados")
        st.dataframe(df_creditos[['Data Mov.', 'Histórico', 'Tipo', 'Valor Formatado']], use_container_width=True)
        
        if not df_tarifas.empty:
            st.write("### 🔴 Tarifas Associadas")
            st.dataframe(df_tarifas[['Data Mov.', 'Histórico', 'Tipo', 'Valor Formatado']], use_container_width=True)
            
        pdf_out = gerar_pdf_relatorio(meta, df_creditos, df_tarifas, total_cred, total_tar)
        
        st.download_button(
            label="📄 Baixar Relatório Formatado em PDF",
            data=pdf_out,
            file_name="Relatorio_Conferencia_COB_COMPE.pdf",
            mime="application/pdf"
        )
    else:
        st.warning("Nenhum lançamento 'COB COMPE' de crédito foi encontrado no PDF enviado.")
