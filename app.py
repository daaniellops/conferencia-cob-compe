import io
import re
from datetime import datetime
import pandas as pd
import pdfplumber
import streamlit as st
from xhtml2pdf import pisa

st.set_page_config(
    page_title="Conferência Financeira - Extrato Completo",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Relatório Completo de Créditos e Débitos")
st.subheader("Separação Total de Entradas (C) e Saídas (D)")

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
                
                if 'SALDO ANTERIOR' in linha_clean.upper() or 'DATA MOV.' in linha_clean.upper():
                    continue
                
                # Captura apenas o valor da coluna 'Valor' (primeiro match C/D da linha)
                matches = re.findall(r'([\d\.]+,\d\d)\s+([CD])', linha_clean)
                
                if matches:
                    val_str, tipo_mov = matches[0]
                    val_float = float(val_str.replace('.', '').replace(',', '.'))
                    
                    if val_float == 0.0:
                        continue
                        
                    partes = linha_clean.split()
                    data = partes[0] if re.match(r'^\d{2}/\d{2}', partes[0]) else ""
                    
                    num_doc = "-"
                    if len(partes) > 1 and re.match(r'^\d+$', partes[1]):
                        num_doc = partes[1]
                        
                    historico = linha_clean
                    if data:
                        historico = re.sub(r'^\d{2}/\d{2}(/\d{2,4})?\s+', '', historico)
                    if num_doc != "-" and historico.startswith(num_doc):
                        historico = re.sub(r'^\d+\s+', '', historico)
                    historico = re.sub(r'\s+[\d\.]+,\d\d\s+[CD].*$', '', historico).strip()
                    
                    if not historico:
                        historico = "Lançamento Bancário"

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
                        'Tipo': 'Crédito' if tipo_mov == 'C' else 'Débito',
                        'Indicador': tipo_mov,
                        'Categoria': categoria,
                        'Valor (R$)': val_float,
                        'Valor Formatado': f"R$ {val_str}"
                    })
                            
    return meta, pd.DataFrame(movimentacoes)

def fmt_brl(valor):
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def gerar_tabela_categoria_html(df_sub, categoria_nome, cor_tema):
    if df_sub.empty:
        return ""
    
    linhas = ""
    for idx, row in df_sub.reset_index(drop=True).iterrows():
        linhas += f"""
        <tr>
            <td style="text-align: center;">{idx+1:02d}</td>
            <td style="text-align: center; font-weight: bold;">{row['Data Mov.']}</td>
            <td style="text-align: center;">{row['Nº Doc.']}</td>
            <td>{row['Histórico']}</td>
            <td style="text-align: right; font-weight: bold; color: {cor_tema};">{row['Valor Formatado']}</td>
        </tr>
        """
    
    total_cat = df_sub['Valor (R$)'].sum()
    
    return f"""
    <div style="margin-top: 8px; margin-bottom: 4px; font-weight: bold; color: {cor_tema}; font-size: 8.5pt;">
        ▪ Tópico: {categoria_nome}
    </div>
    <table class="data-table">
        <thead>
            <tr>
                <th style="text-align: center;" width="6%">Item</th>
                <th style="text-align: center;" width="14%">Data Mov.</th>
                <th style="text-align: center;" width="14%">Nº Doc.</th>
                <th width="46%">Histórico</th>
                <th style="text-align: right;" width="20%">Valor</th>
            </tr>
        </thead>
        <tbody>
            {linhas}
            <tr style="font-weight: bold; background-color: #f8fafc;">
                <td colspan="4" style="text-align: right;">SUBTOTAL ({categoria_nome}):</td>
                <td style="text-align: right; color: {cor_tema};">{fmt_brl(total_cat)}</td>
            </tr>
        </tbody>
    </table>
    """

def gerar_pdf_relatorio(meta, df_mov):
    data_emissao = datetime.now().strftime("%d/%m/%Y")
    
    df_creditos = df_mov[df_mov['Indicador'] == 'C']
    df_debitos = df_mov[df_mov['Indicador'] == 'D']
    
    total_creditos = df_creditos['Valor (R$)'].sum()
    total_debitos = df_debitos['Valor (R$)'].sum()

    # Função interna para montar o bloco de Crédito ou Débito completo por tópicos
    def montar_bloco_tipo(df_tipo, tipo_indicador, titulo_bloco, cor_tema):
        if df_tipo.empty:
            return f"<p style='color: #64748b; font-style: italic; font-size: 8.5pt;'>Nenhum lançamento de {titulo_bloco.lower()} no extrato.</p>"
        
        df_cob = df_tipo[df_tipo['Categoria'] == 'COB COMPE']
        df_resg = df_tipo[df_tipo['Categoria'] == 'RESG AUT / APLICAÇÃO']
        df_outros = df_tipo[df_tipo['Categoria'] == 'OUTRAS MOVIMENTAÇÕES']
        
        html_bloco = f"""
        <div class="section-main-title" style="background-color: {cor_tema}; color: white; padding: 6px 10px; margin-top: 14px; margin-bottom: 8px; font-weight: bold; border-radius: 3px; font-size: 10pt;">
            {titulo_bloco} — TOTAL: {fmt_brl(df_tipo['Valor (R$)'].sum())}
        </div>
        """
        html_bloco += gerar_tabela_categoria_html(df_cob, "COB COMPE", cor_tema)
        html_bloco += gerar_tabela_categoria_html(df_resg, "RESG AUT / APLICAÇÃO", cor_tema)
        html_bloco += gerar_tabela_categoria_html(df_outros, "OUTRAS MOVIMENTAÇÕES", cor_tema)
        
        return html_bloco

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
            table.data-table {{ width: 100%; border-collapse: collapse; margin-bottom: 8px; }}
            table.data-table th {{ background-color: #f1f5f9; padding: 5px; text-align: left; font-size: 8pt; border-bottom: 2px solid #cbd5e1; }}
            table.data-table td {{ padding: 5px; border-bottom: 1px solid #f1f5f9; font-size: 8pt; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2 style="margin:0; font-size: 13pt;">Relatório de Conferência Financeira</h2>
            <p style="margin:2px 0 0 0; font-size: 8.5pt;">Relatório Consolidado de Créditos e Débitos por Tópicos</p>
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
                    <div class="card-title">Total Créditos (Entradas)</div>
                    <div class="card-value" style="color: #15803d;">{fmt_brl(total_creditos)}</div>
                </td>
                <td width="2%"></td>
                <td width="32%" class="card">
                    <div class="card-title">Total Débitos (Saídas)</div>
                    <div class="card-value" style="color: #b91c1c;">{fmt_brl(total_debitos)}</div>
                </td>
                <td width="2%"></td>
                <td width="32%" class="card">
                    <div class="card-title">Resultado do Período</div>
                    <div class="card-value" style="color: {'#15803d' if total_creditos - total_debitos >= 0 else '#b91c1c'};">{fmt_brl(total_creditos - total_debitos)}</div>
                </td>
            </tr>
        </table>

        {montar_bloco_tipo(df_creditos, 'C', '1. TODOS OS CRÉDITOS (ENTRADAS)', '#166534')}
        
        {montar_bloco_tipo(df_debitos, 'D', '2. TODOS OS DÉBITOS (SAÍDAS)', '#991b1b')}

        <div style="margin-top: 15px; font-size: 7pt; color: #64748b;">
            <b>Nota:</b> A coluna de saldo foi totalmente desconsiderada dos cálculos do relatório.
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
        df_creditos = df_mov[df_mov['Indicador'] == 'C']
        df_debitos = df_mov[df_mov['Indicador'] == 'D']
        
        total_cred = df_creditos['Valor (R$)'].sum()
        total_deb = df_debitos['Valor (R$)'].sum()
        
        st.info(f"**Cliente:** {meta['cliente']} | **Conta:** {meta['conta']} | **Período:** {meta['periodo']}")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Créditos (Entradas)", fmt_brl(total_cred))
        col2.metric("Total Débitos (Saídas)", fmt_brl(total_deb), delta_color="inverse")
        col3.metric("Resultado das Movimentações", fmt_brl(total_cred - total_deb))
        
        st.divider()
        
        tab_c, tab_d = st.tabs(["🟢 TODOS OS CRÉDITOS (ENTRADAS)", "🔴 TODOS OS DÉBITOS (SAÍDAS)"])
        
        def renderizar_telas_por_categoria(df_grupo):
            if df_grupo.empty:
                st.info("Nenhum lançamento encontrado para esta seção.")
                return
            
            for cat in ["COB COMPE", "RESG AUT / APLICAÇÃO", "OUTRAS MOVIMENTAÇÕES"]:
                sub = df_grupo[df_grupo['Categoria'] == cat]
                if not sub.empty:
                    st.markdown(f"##### 📌 {cat}")
                    st.dataframe(sub[['Data Mov.', 'Nº Doc.', 'Histórico', 'Valor Formatado']], use_container_width=True)

        with tab_c:
            renderizar_telas_por_categoria(df_creditos)
            
        with tab_d:
            renderizar_telas_por_categoria(df_debitos)
            
        pdf_out = gerar_pdf_relatorio(meta, df_mov)
        
        st.download_button(
            label="📄 Baixar Relatório Completo em PDF",
            data=pdf_out,
            file_name="Relatorio_Creditos_e_Debitos_Separados.pdf",
            mime="application/pdf"
        )
    else:
        st.warning("Nenhuma movimentação de crédito ou débito foi encontrada no arquivo enviado.")
