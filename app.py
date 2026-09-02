import io
import re
from datetime import datetime
import pandas as pd
import pdfplumber
import streamlit as st
from xhtml2pdf import pisa

st.set_page_config(
    page_title="Conferência de Extratos Bancários",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Conferência Financeira - Extrato Completo")
st.subheader("Processador Automático de Créditos e Débitos")

arquivo_pdf = st.file_uploader("Arraste e solte o PDF do extrato bancário aqui", type=["pdf"])

def extrair_metadados_e_dados(pdf_bytes):
    creditos = []
    tarifas = []
    
    meta = {
        "cliente": "Não identificado",
        "periodo": "Não identificado",
        "conta": "Não identificada"
    }
    
    # Expressão regular para capturar linhas de movimentação bancária:
    # Formato esperado: DATA + HISTÓRICO + VALOR + C/D
    padrao_movimentacao = re.compile(r'^(\d{2}/\d{2}/\d{4}|\d{2}/\d{2}/\d{2})\s+(.*?)\s+([\d\.]+\,\d\d)\s+([CD])$')
    
    with pdfplumber.open(pdf_bytes) as pdf:
        # Extrai metadados da primeira página
        primeira_pagina = pdf.pages[0].extract_text() or ""
        
        match_cliente = re.search(r'Nome\s*:\s*([^\n]+)', primeira_pagina, re.IGNORECASE) or \
                        re.search(r'Cliente\s*:\s*([^\n]+)', primeira_pagina, re.IGNORECASE)
        if match_cliente:
            meta["cliente"] = match_cliente.group(1).strip()
            
        match_periodo = re.search(r'Período\s*:\s*([\d\/]+\s*a\s*[\d\/]+)', primeira_pagina, re.IGNORECASE)
        if match_periodo:
            meta["periodo"] = match_periodo.group(1).strip()
            
        match_conta = re.search(r'Conta\s*:\s*([\d\s\-\|]+)', primeira_pagina, re.IGNORECASE)
        if match_conta:
            meta["conta"] = match_conta.group(1).strip()

        # Varredura de movimentações em todas as páginas
        for page in pdf.pages:
            texto = page.extract_text()
            if not texto:
                continue
            
            linhas = texto.split('\n')
            for linha in linhas:
                linha_clean = linha.strip()
                
                # Ignora linhas de saldo anterior / atual ou cabeçalhos
                if 'SALDO' in linha_clean.upper() or linha_clean.startswith('000000'):
                    continue
                
                # Procura por linhas terminadas em C ou D com valores
                match_val = re.search(r'([\d\.]+,\d\d)\s+([CD])$', linha_clean)
                if match_val:
                    val_str = match_val.group(1)
                    tipo_mov = match_val.group(2)
                    val_float = float(val_str.replace('.', '').replace(',', '.'))
                    
                    # Extrai a data (primeiro elemento da linha) e o histórico (restante do texto)
                    partes = linha_clean.split()
                    data = partes[0] if re.match(r'^\d{2}/\d{2}', partes[0]) else ""
                    
                    # Extrai o texto do histórico removendo a data e o valor/tipo final
                    historico = re.sub(r'^\d{2}/\d{2}(/\d{2,4})?\s+', '', linha_clean)
                    historico = re.sub(r'\s+[\d\.]+,\d\d\s+[CD]$', '', historico).strip()
                    if not historico:
                        historico = "Lançamento Bancário"

                    if tipo_mov == 'C':
                        creditos.append({
                            'Data Mov.': data,
                            'Histórico': historico,
                            'Tipo': 'Crédito (C)',
                            'Valor (R$)': val_float,
                            'Valor Formatado': f"R$ {val_str}"
                        })
                    elif tipo_mov == 'D':
                        tarifas.append({
                            'Data Mov.': data,
                            'Histórico': historico,
                            'Tipo': 'Débito (D)',
                            'Valor (R$)': val_float,
                            'Valor Formatado': f"R$ {val_str}"
                        })
                            
    return meta, pd.DataFrame(creditos), pd.DataFrame(tarifas)

def fmt_brl(valor):
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def gerar_pdf_relatorio(meta, df_creditos, df_tarifas, total_creditos, total_tarifas):
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
            <td style="text-align: center;">{idx+1:02d}</td>
            <td style="text-align: center; font-weight: bold;">{row['Data Mov.']}</td>
            <td>{row['Histórico']}</td>
            <td style="text-align: center;"><span style="color: #991b1b; font-weight: bold;">DÉBITO (D)</span></td>
            <td style="text-align: right; font-weight: bold;">{row['Valor Formatado']}</td>
        </tr>
        """

    html_full = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            @page {{ size: a4; margin: 1cm; }}
            body {{ font-family: Helvetica, Arial, sans-serif; color: #1e293b; font-size: 8.5pt; }}
            .header {{ background-color: #1e3a8a; color: white; padding: 12px; margin-bottom: 12px; border-radius: 4px; }}
            .info-table {{ width: 100%; margin-bottom: 12px; background-color: #f8fafc; padding: 8px; border: 1px solid #e2e8f0; }}
            .cards-table {{ width: 100%; margin-bottom: 12px; text-align: center; }}
            .card {{ background-color: #f1f5f9; padding: 8px; border: 1px solid #cbd5e1; border-radius: 4px; }}
            .card-title {{ font-size: 7.5pt; font-weight: bold; color: #475569; text-transform: uppercase; }}
            .card-value {{ font-size: 10.5pt; font-weight: bold; margin-top: 3px; }}
            table.data-table {{ width: 100%; border-collapse: collapse; margin-bottom: 12px; }}
            table.data-table th {{ background-color: #f1f5f9; padding: 5px; text-align: left; font-size: 8pt; border-bottom: 2px solid #cbd5e1; }}
            table.data-table td {{ padding: 5px; border-bottom: 1px solid #f1f5f9; font-size: 8pt; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2 style="margin:0; font-size: 13pt;">Relatório Geral de Conferência Financeira</h2>
            <p style="margin:2px 0 0 0; font-size: 8.5pt;">Consolidado de Entradas (Créditos) e Saídas (Débitos)</p>
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
                <td width="24%" class="card">
                    <div class="card-title">Entradas (Créditos)</div>
                    <div class="card-value" style="color: #15803d;">{fmt_brl(total_creditos)}</div>
                    <div style="font-size: 7pt; color: #64748b;">{len(df_creditos)} lançamentos</div>
                </td>
                <td width="1%"></td>
                <td width="24%" class="card">
                    <div class="card-title">Saídas (Débitos)</div>
                    <div class="card-value" style="color: #b91c1c;">{fmt_brl(total_tarifas)}</div>
                    <div style="font-size: 7pt; color: #64748b;">{len(df_tarifas)} lançamentos</div>
                </td>
                <td width="1%"></td>
                <td width="24%" class="card">
                    <div class="card-title">Resultado do Período</div>
                    <div class="card-value" style="color: {'#15803d' if total_creditos - total_tarifas >= 0 else '#b91c1c'};">{fmt_brl(total_creditos - total_tarifas)}</div>
                    <div style="font-size: 7pt; color: #64748b;">Balanço Líquido</div>
                </td>
            </tr>
        </table>

        <h3 style="color: #1e3a8a; font-size: 9.5pt; margin-bottom: 4px;">1. Detalhamento dos Créditos (Entradas)</h3>
        <table class="data-table">
            <thead>
                <tr>
                    <th style="text-align: center;" width="6%">Item</th>
                    <th style="text-align: center;" width="14%">Data Mov.</th>
                    <th width="45%">Histórico</th>
                    <th style="text-align: center;" width="15%">Tipo</th>
                    <th style="text-align: right;" width="20%">Valor (R$)</th>
                </tr>
            </thead>
            <tbody>
                {html_items}
                <tr style="font-weight: bold; background-color: #f8fafc;">
                    <td colspan="4" style="text-align: right;">TOTAL DE CRÉDITOS:</td>
                    <td style="text-align: right; color: #15803d;">{fmt_brl(total_creditos)}</td>
                </tr>
            </tbody>
        </table>

        {"<h3 style='color: #1e3a8a; font-size: 9.5pt; margin-bottom: 4px;'>2. Detalhamento dos Débitos (Saídas)</h3>" if not df_tarifas.empty else ""}
        {"<table class='data-table'><thead><tr><th style='text-align: center;' width='6%'>Item</th><th style='text-align: center;' width='14%'>Data Mov.</th><th width='45%'>Histórico</th><th style='text-align: center;' width='15%'>Tipo</th><th style='text-align: right;' width='20%'>Valor (R$)</th></tr></thead><tbody>" + html_tarifas + "<tr style='font-weight: bold; background-color: #f8fafc;'><td colspan='4' style='text-align: right;'>TOTAL DE DÉBITOS:</td><td style='text-align: right; color: #b91c1c;'>" + fmt_brl(total_tarifas) + "</td></tr></tbody></table>" if not df_tarifas.empty else ""}

        <div style="margin-top: 10px; font-size: 7pt; color: #64748b;">
            <b>Observações para Conciliação:</b><br/>
            • Os lançamentos acima refletem a totalidade das movimentações financeiras de entrada e saída encontradas no extrato fornecido.<br/>
            • Relatório gerado automaticamente para auditoria e conciliação bancária.
        </div>
    </body>
    </html>
    """
    
    pdf_buffer = io.BytesIO()
    pisa.CreatePDF(io.StringIO(html_full), dest=pdf_buffer)
    return pdf_buffer.getvalue()

if arquivo_pdf is not None:
    meta, df_creditos, df_tarifas = extrair_metadados_e_dados(arquivo_pdf)
    
    total_cred = df_creditos['Valor (R$)'].sum() if not df_creditos.empty else 0.0
    total_tar = df_tarifas['Valor (R$)'].sum() if not df_tarifas.empty else 0.0
    
    st.info(f"**Cliente:** {meta['cliente']} | **Conta:** {meta['conta']} | **Período:** {meta['periodo']}")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Créditos", fmt_brl(total_cred), delta=f"{len(df_creditos)} lançamentos")
    col2.metric("Total de Débitos", fmt_brl(total_tar), delta=f"{len(df_tarifas)} lançamentos", delta_color="inverse")
    col3.metric("Balanço do Período", fmt_brl(total_cred - total_tar))
    
    st.divider()
    
    col_left, col_right = st.columns(2)
    with col_left:
        st.write("### 🟢 Entradas (Créditos)")
        if not df_creditos.empty:
            st.dataframe(df_creditos[['Data Mov.', 'Histórico', 'Tipo', 'Valor Formatado']], use_container_width=True)
        else:
            st.info("Nenhum crédito encontrado.")
            
    with col_right:
        st.write("### 🔴 Saídas (Débitos)")
        if not df_tarifas.empty:
            st.dataframe(df_tarifas[['Data Mov.', 'Histórico', 'Tipo', 'Valor Formatado']], use_container_width=True)
        else:
            st.info("Nenhum débito encontrado.")
        
    if not df_creditos.empty or not df_tarifas.empty:
        pdf_out = gerar_pdf_relatorio(meta, df_creditos, df_tarifas, total_cred, total_tar)
        
        st.download_button(
            label="📄 Baixar Relatório Completo em PDF",
            data=pdf_out,
            file_name="Relatorio_Conferencia_Geral.pdf",
            mime="application/pdf"
        )
