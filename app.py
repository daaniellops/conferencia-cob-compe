import io
import re
from datetime import datetime
import pandas as pd
import pdfplumber
import streamlit as st
from xhtml2pdf import pisa

st.set_page_config(
    page_title="Conferência Financeira de Extratos",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Conferência Financeira - Extrato Completo")
st.subheader("Processamento de Lançamentos (Exclusão Estrita de Saldos)")

arquivo_pdf = st.file_uploader("Arraste e solte o PDF do extrato bancário aqui", type=["pdf"])

def extrair_metadados_e_dados(pdf_bytes):
    movimentacoes = []
    
    meta = {
        "cliente": "Não identificado",
        "periodo": "Não identificado",
        "conta": "Não identificada"
    }
    
    with pdfplumber.open(pdf_bytes) as pdf:
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

        for page in pdf.pages:
            texto = page.extract_text()
            if not texto:
                continue
            
            linhas = texto.split('\n')
            for linha in linhas:
                linha_clean = linha.strip()
                
                # 1. ELIMINAÇÃO TOTAL DE QUALQUER TIPO DE SALDO
                if re.search(r'\bSALDO\b', linha_clean, re.IGNORECASE):
                    continue
                
                # 2. CAPTURA APENAS LINHAS DE MOVIMENTAÇÃO QUE TERMINAM EM 'C' OU 'D'
                match_val = re.search(r'([\d\.]+,\d\d)\s+([CD])$', linha_clean)
                if match_val:
                    val_str = match_val.group(1)
                    tipo_mov = match_val.group(2)
                    val_float = float(val_str.replace('.', '').replace(',', '.'))
                    
                    partes = linha_clean.split()
                    
                    # Extrai Data
                    data = partes[0] if re.match(r'^\d{2}/\d{2}', partes[0]) else ""
                    
                    # Extrai Número do Documento (normalmente o 2º elemento se for numérico)
                    num_doc = "-"
                    if len(partes) > 1 and re.match(r'^\d+$', partes[1]):
                        num_doc = partes[1]
                        
                    # Extrai Histórico Limpo
                    historico = linha_clean
                    if data:
                        historico = re.sub(r'^\d{2}/\d{2}(/\d{2,4})?\s+', '', historico)
                    if num_doc != "-" and historico.startswith(num_doc):
                        historico = re.sub(r'^\d+\s+', '', historico)
                    historico = re.sub(r'\s+[\d\.]+,\d\d\s+[CD]$', '', historico).strip()
                    
                    if not historico:
                        historico = "Lançamento Bancário"

                    # Classificação por Categoria para os Tópicos
                    if 'COB COMPE' in historico.upper():
                        categoria = 'COB COMPE'
                    elif 'RESG' in historico.upper() or 'APLIC' in historico.upper():
                        categoria = 'RESG AUT / APLICAÇÃO'
                    else:
                        categoria = 'OUTRAS MOVIMENTAÇÕES'

                    movimentacoes.append({
                        'Data Mov.': data,
                        'Nº Doc.': num_doc,
                        'Histórico': historico,
                        'Tipo': 'Crédito (C)' if tipo_mov == 'C' else 'Débito (D)',
                        'Indicador': tipo_mov,
                        'Categoria': categoria,
                        'Valor (R$)': val_float,
                        'Valor Formatado': f"R$ {val_str}"
                    })
                            
    return meta, pd.DataFrame(movimentacoes)

def fmt_brl(valor):
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def gerar_tabela_html(df_sub):
    if df_sub.empty:
        return "<p style='color: #64748b; font-style: italic;'>Nenhum lançamento nesta categoria.</p>"
    
    linhas = ""
    for idx, row in df_sub.reset_index(drop=True).iterrows():
        cor_tipo = "#166534" if row['Indicador'] == 'C' else "#991b1b"
        linhas += f"""
        <tr>
            <td style="text-align: center;">{idx+1:02d}</td>
            <td style="text-align: center; font-weight: bold;">{row['Data Mov.']}</td>
            <td style="text-align: center;">{row['Nº Doc.']}</td>
            <td>{row['Histórico']}</td>
            <td style="text-align: center;"><span style="color: {cor_tipo}; font-weight: bold;">{row['Tipo']}</span></td>
            <td style="text-align: right; font-weight: bold;">{row['Valor Formatado']}</td>
        </tr>
        """
    
    total_c = df_sub[df_sub['Indicador'] == 'C']['Valor (R$)'].sum()
    total_d = df_sub[df_sub['Indicador'] == 'D']['Valor (R$)'].sum()
    
    resumo_totais = f"Créditos (C): {fmt_brl(total_c)} | Débitos (D): {fmt_brl(total_d)}"
    
    return f"""
    <table class="data-table">
        <thead>
            <tr>
                <th style="text-align: center;" width="5%">Item</th>
                <th style="text-align: center;" width="12%">Data Mov.</th>
                <th style="text-align: center;" width="12%">Nº Doc.</th>
                <th width="41%">Histórico</th>
                <th style="text-align: center;" width="12%">Tipo</th>
                <th style="text-align: right;" width="18%">Valor</th>
            </tr>
        </thead>
        <tbody>
            {linhas}
            <tr style="font-weight: bold; background-color: #f8fafc;">
                <td colspan="4" style="text-align: right;">TOTAL DA CATEGORIA:</td>
                <td colspan="2" style="text-align: right; color: #1e3a8a;">{resumo_totais}</td>
            </tr>
        </tbody>
    </table>
    """

def gerar_pdf_relatorio(meta, df_mov):
    data_emissao = datetime.now().strftime("%d/%m/%Y")
    
    df_cob = df_mov[df_mov['Categoria'] == 'COB COMPE']
    df_resg = df_mov[df_mov['Categoria'] == 'RESG AUT / APLICAÇÃO']
    df_outros = df_mov[df_mov['Categoria'] == 'OUTRAS MOVIMENTAÇÕES']
    
    total_creditos = df_mov[df_mov['Indicador'] == 'C']['Valor (R$)'].sum()
    total_debitos = df_mov[df_mov['Indicador'] == 'D']['Valor (R$)'].sum()

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
            table.data-table {{ width: 100%; border-collapse: collapse; margin-bottom: 15px; }}
            table.data-table th {{ background-color: #f1f5f9; padding: 5px; text-align: left; font-size: 8pt; border-bottom: 2px solid #cbd5e1; }}
            table.data-table td {{ padding: 5px; border-bottom: 1px solid #f1f5f9; font-size: 8pt; }}
            .section-title {{ color: #1e3a8a; font-size: 10pt; margin-top: 10px; margin-bottom: 6px; border-bottom: 1px solid #cbd5e1; padding-bottom: 3px; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2 style="margin:0; font-size: 13pt;">Relatório de Conferência Financeira</h2>
            <p style="margin:2px 0 0 0; font-size: 8.5pt;">Análise de Entradas (C) e Saídas (D) - Exclusão de Saldos</p>
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
                    <div class="card-title">Total Créditos (C)</div>
                    <div class="card-value" style="color: #15803d;">{fmt_brl(total_creditos)}</div>
                </td>
                <td width="2%"></td>
                <td width="32%" class="card">
                    <div class="card-title">Total Débitos (D)</div>
                    <div class="card-value" style="color: #b91c1c;">{fmt_brl(total_debitos)}</div>
                </td>
                <td width="2%"></td>
                <td width="32%" class="card">
                    <div class="card-title">Balanço das Movimentações</div>
                    <div class="card-value" style="color: {'#15803d' if total_creditos - total_debitos >= 0 else '#b91c1c'};">{fmt_brl(total_creditos - total_debitos)}</div>
                </td>
            </tr>
        </table>

        <div class="section-title">1. COB COMPE</div>
        {gerar_tabela_html(df_cob)}

        <div class="section-title">2. RESG AUT / APLICAÇÃO</div>
        {gerar_tabela_html(df_resg)}

        {"<div class='section-title'>3. OUTRAS MOVIMENTAÇÕES</div>" + gerar_tabela_html(df_outros) if not df_outros.empty else ""}

        <div style="margin-top: 10px; font-size: 7pt; color: #64748b;">
            <b>Nota:</b> Linhas referentes a saldos anteriores ou saldos diários foram desconsideradas para evitar duplicação de dados.
        </div>
    </body>
    </html>
    """
    
    pdf_buffer = io.BytesIO()
    pisa.CreatePDF(io.StringIO(html_full), dest=pdf_buffer)
    return pdf_buffer.getvalue()

if arquivo_pdf is not None:
    meta, df_mov = extrair_metadados_e_dados(arquivo_pdf)
    
    if not df_mov.empty:
        total_cred = df_mov[df_mov['Indicador'] == 'C']['Valor (R$)'].sum()
        total_deb = df_mov[df_mov['Indicador'] == 'D']['Valor (R$)'].sum()
        
        st.info(f"**Cliente:** {meta['cliente']} | **Conta:** {meta['conta']} | **Período:** {meta['periodo']}")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Créditos (C)", fmt_brl(total_cred))
        col2.metric("Total Débitos (D)", fmt_brl(total_deb), delta_color="inverse")
        col3.metric("Fluxo Líquido das Movimentações", fmt_brl(total_cred - total_deb))
        
        st.divider()
        
        tab1, tab2, tab3 = st.tabs(["📌 COB COMPE", "🔄 RESG AUT / APLICAÇÃO", "📋 OUTRAS MOVIMENTAÇÕES"])
        
        with tab1:
            df_cob = df_mov[df_mov['Categoria'] == 'COB COMPE']
            st.dataframe(df_cob[['Data Mov.', 'Nº Doc.', 'Histórico', 'Tipo', 'Valor Formatado']], use_container_width=True)
            
        with tab2:
            df_resg = df_mov[df_mov['Categoria'] == 'RESG AUT / APLICAÇÃO']
            st.dataframe(df_resg[['Data Mov.', 'Nº Doc.', 'Histórico', 'Tipo', 'Valor Formatado']], use_container_width=True)
            
        with tab3:
            df_outros = df_mov[df_mov['Categoria'] == 'OUTRAS MOVIMENTAÇÕES']
            st.dataframe(df_outros[['Data Mov.', 'Nº Doc.', 'Histórico', 'Tipo', 'Valor Formatado']], use_container_width=True)
            
        pdf_out = gerar_pdf_relatorio(meta, df_mov)
        
        st.download_button(
            label="📄 Baixar Relatório de Conferência em PDF",
            data=pdf_out,
            file_name="Relatorio_Conferencia_Sem_Saldos.pdf",
            mime="application/pdf"
        )
    else:
        st.warning("Nenhuma movimentação de crédito ou débito foi encontrada no arquivo enviado.")
