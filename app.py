from flask import Flask, request, jsonify, send_file
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
import io
import os
import uuid
import threading
import time
from datetime import datetime

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import reportlab as _rl

app = Flask(__name__)

# =================== FONTES COM SUPORTE A PORTUGUÊS ===================
_FONTS_DIR = os.path.join(os.path.dirname(_rl.__file__), 'fonts')
pdfmetrics.registerFont(TTFont("LiberationSans", os.path.join(_FONTS_DIR, "Vera.ttf")))
pdfmetrics.registerFont(TTFont("LiberationSans-Bold", os.path.join(_FONTS_DIR, "VeraBd.ttf")))
pdfmetrics.registerFont(TTFont("LiberationSans-Italic", os.path.join(_FONTS_DIR, "VeraIt.ttf")))

# =================== CORES OREN IA ===================
NAVY = colors.HexColor('#0A1F44')
BLUE = colors.HexColor('#2563EB')
GREEN = colors.HexColor('#16A34A')
RED = colors.HexColor('#DC2626')
LIGHT_GRAY = colors.HexColor('#F8FAFC')
GRAY = colors.HexColor('#6B7280')
DARK_GRAY = colors.HexColor('#1F2937')
WHITE = colors.white
BORDER_COLOR = colors.HexColor('#E5E7EB')

W, H = A4  # 595 x 842 pts
MARGIN = 15*mm
CONTENT_W = W - 2*MARGIN

# =================== STORAGE TEMPORÁRIO ===================

TMP_DIR = '/tmp/oren_pdfs'
os.makedirs(TMP_DIR, exist_ok=True)

def salvar_pdf_tmp(buffer, nome_base):
    """Salva PDF em /tmp e retorna o filename único"""
    filename = f"{nome_base}_{uuid.uuid4().hex[:8]}.pdf"
    path = os.path.join(TMP_DIR, filename)
    with open(path, 'wb') as f:
        f.write(buffer.getvalue())
    return filename

def limpar_pdfs_antigos():
    """Remove PDFs com mais de 1 hora"""
    while True:
        try:
            agora = time.time()
            for fname in os.listdir(TMP_DIR):
                fpath = os.path.join(TMP_DIR, fname)
                if agora - os.path.getmtime(fpath) > 3600:
                    os.remove(fpath)
        except:
            pass
        time.sleep(600)

# Inicia limpeza em background
threading.Thread(target=limpar_pdfs_antigos, daemon=True).start()

def get_base_url():
    """Retorna a URL base do serviço"""
    return os.environ.get('BASE_URL', request.host_url.rstrip('/'))

# =================== HELPERS ===================

def draw_header(c, estabelecimento, titulo, subtitulo='', periodo=''):
    HEADER_H = 28*mm
    c.setFillColor(NAVY)
    c.rect(0, H - HEADER_H, W, HEADER_H, fill=1, stroke=0)

    logo_y = H - HEADER_H/2
    c.setFillColor(WHITE)
    c.setFont('LiberationSans-Bold', 15)
    c.drawString(MARGIN, logo_y + 1*mm, 'Oren')
    c.setFillColor(BLUE)
    w_oren = c.stringWidth('Oren', 'LiberationSans-Bold', 15)
    c.drawString(MARGIN + w_oren, logo_y + 1*mm, ' IA')
    c.setFillColor(WHITE)
    c.setFont('LiberationSans', 6)
    c.drawString(MARGIN, logo_y - 5*mm, 'GESTÃO QUE ENTENDE VOCÊ.')

    c.setFillColor(WHITE)
    c.setFont('LiberationSans-Bold', 17)
    tw = c.stringWidth(titulo, 'LiberationSans-Bold', 17)
    c.drawString((W - tw) / 2, logo_y + 1*mm, titulo)

    if subtitulo:
        c.setFont('LiberationSans', 9)
        c.setFillColor(BLUE)
        sw = c.stringWidth(subtitulo, 'LiberationSans', 9)
        c.drawString((W - sw) / 2, logo_y - 6*mm, subtitulo)

    c.setFont('LiberationSans', 7)
    c.setFillColor(WHITE)
    right_x = W - MARGIN

    if periodo:
        c.drawRightString(right_x, logo_y + 3*mm, 'Período:')
        c.setFont('LiberationSans-Bold', 7)
        c.drawRightString(right_x, logo_y - 2*mm, periodo)
        c.setFont('LiberationSans', 7)
        c.drawRightString(right_x, logo_y - 8*mm, 'Estabelecimento:')
        c.setFont('LiberationSans-Bold', 7)
        c.drawRightString(right_x, logo_y - 13*mm, estabelecimento)
    else:
        c.drawRightString(right_x, logo_y + 2*mm, 'Estabelecimento:')
        c.setFont('LiberationSans-Bold', 7)
        c.drawRightString(right_x, logo_y - 4*mm, estabelecimento)

    return H - HEADER_H - 8*mm

def draw_footer(c, page_num=1):
    c.setStrokeColor(BLUE)
    c.setLineWidth(0.5)
    c.line(MARGIN, 18*mm, W - MARGIN, 18*mm)
    c.setFillColor(BLUE)
    c.setFont('LiberationSans-Bold', 8)
    c.drawString(MARGIN, 12*mm, 'Gerado por Oren IA — Fin')
    c.setFillColor(GRAY)
    c.setFont('LiberationSans', 8)
    data_hoje = datetime.now().strftime('%d/%m/%Y às %H:%M')
    c.drawCentredString(W/2, 12*mm, f'Data de geração: {data_hoje}')
    c.drawRightString(W - MARGIN, 12*mm, f'Página {page_num} de 1')

def draw_section_header(c, y, texto):
    BAR_H = 8*mm
    c.setFillColor(NAVY)
    c.rect(MARGIN, y - BAR_H, CONTENT_W, BAR_H, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont('LiberationSans-Bold', 9)
    c.drawString(MARGIN + 3*mm, y - BAR_H/2 - 1.5*mm, texto)
    return y - BAR_H - 2*mm

def format_brl(valor):
    try:
        v = float(valor)
        return f'R$ {v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    except:
        return f'R$ {valor}'

def draw_metric_card(c, x, y, w, h, titulo, valor, cor_fundo):
    c.setFillColor(cor_fundo)
    c.roundRect(x, y, w, h, 3*mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont('LiberationSans', 7)
    c.drawString(x + 4*mm, y + h - 7*mm, titulo.upper())
    c.setFont('LiberationSans-Bold', 13)
    c.drawString(x + 4*mm, y + h/2 - 2*mm, valor)

def draw_table_header(c, y, headers, col_widths, row_h=6*mm):
    c.setFillColor(LIGHT_GRAY)
    c.rect(MARGIN, y - row_h, CONTENT_W, row_h, fill=1, stroke=0)
    c.setFillColor(DARK_GRAY)
    c.setFont('LiberationSans-Bold', 8)
    x = MARGIN
    for i, (h_text, cw) in enumerate(zip(headers, col_widths)):
        if i == len(headers) - 1:
            c.drawRightString(x + cw - 2*mm, y - row_h/2 - 1.5*mm, h_text)
        else:
            c.drawString(x + 2*mm, y - row_h/2 - 1.5*mm, h_text)
        x += cw
    return y - row_h

def draw_table_row(c, y, vals, col_widths, row_h=6*mm, idx=0, last_col_color=None):
    bg = LIGHT_GRAY if idx % 2 == 0 else WHITE
    c.setFillColor(bg)
    c.rect(MARGIN, y - row_h, CONTENT_W, row_h, fill=1, stroke=0)
    c.setFont('LiberationSans', 8)
    x = MARGIN
    for i, (val, cw) in enumerate(zip(vals, col_widths)):
        if i == len(vals) - 1:
            cor = last_col_color if last_col_color else DARK_GRAY
            c.setFillColor(cor)
            c.setFont('LiberationSans-Bold', 8)
            c.drawRightString(x + cw - 2*mm, y - row_h/2 - 1.5*mm, str(val))
            c.setFont('LiberationSans', 8)
        else:
            c.setFillColor(DARK_GRAY)
            c.drawString(x + 2*mm, y - row_h/2 - 1.5*mm, str(val)[:35])
        x += cw
    return y - row_h

# =================== RELATÓRIO 1: RESUMO DO DIA ===================

def gerar_resumo_dia(dados):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    estabelecimento = dados.get('estabelecimento', 'Estabelecimento')
    data_ref = dados.get('data', datetime.now().strftime('%d/%m/%Y'))
    entradas = float(dados.get('entradas', 0))
    saidas = float(dados.get('saidas', 0))
    saldo = entradas - saidas
    lancamentos = dados.get('lancamentos', [])

    y = draw_header(c, estabelecimento, 'Resumo do Dia', subtitulo=data_ref)
    draw_footer(c)

    GAP = 3*mm
    card_w = (CONTENT_W - 2*GAP) / 3
    card_h = 26*mm
    card_y = y - card_h

    draw_metric_card(c, MARGIN, card_y, card_w, card_h, 'Entradas', format_brl(entradas), GREEN)
    draw_metric_card(c, MARGIN + card_w + GAP, card_y, card_w, card_h, 'Saidas', format_brl(saidas), RED)
    draw_metric_card(c, MARGIN + (card_w + GAP)*2, card_y, card_w, card_h, 'Saldo do Dia', format_brl(saldo), NAVY)

    y = card_y - 8*mm
    y = draw_section_header(c, y, 'MOVIMENTAÇÕES DE HOJE')
    col_widths = [22*mm, 80*mm, 47*mm, 31*mm]
    y = draw_table_header(c, y, ['HORÁRIO', 'DESCRIÇÃO', 'CATEGORIA', 'VALOR'], col_widths)

    for idx, item in enumerate(lancamentos[:15]):
        tipo = item.get('tipo', 'receita')
        valor = float(item.get('valor', 0))
        cor_val = GREEN if tipo == 'receita' else RED
        sinal = '' if tipo == 'receita' else '-'
        vals = [
            item.get('horario', ''),
            item.get('descricao', ''),
            item.get('categoria', ''),
            f'{sinal}{format_brl(valor)}'
        ]
        y = draw_table_row(c, y, vals, col_widths, idx=idx, last_col_color=cor_val)

    y -= 5*mm
    saldo_str = format_brl(saldo)
    c.setFillColor(LIGHT_GRAY)
    c.roundRect(MARGIN, y - 14*mm, CONTENT_W, 14*mm, 3*mm, fill=1, stroke=0)
    c.setFillColor(DARK_GRAY)
    c.setFont('LiberationSans-Bold', 9)
    c.drawString(MARGIN + 4*mm, y - 6*mm, f'Você terminou o dia com saldo de {saldo_str}.')
    c.setFillColor(GRAY)
    c.setFont('LiberationSans', 8)
    c.drawString(MARGIN + 4*mm, y - 11*mm, 'Continue assim!')

    c.save()
    buffer.seek(0)
    return buffer

# =================== RELATÓRIO 2: RESUMO MENSAL ===================

def gerar_resumo_mensal(dados):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    estabelecimento = dados.get('estabelecimento', 'Estabelecimento')
    periodo = dados.get('periodo', datetime.now().strftime('%m/%Y'))
    receita = float(dados.get('receita_total', 0))
    despesas = float(dados.get('despesas_totais', 0))
    lucro = float(dados.get('lucro_liquido', 0))
    categorias = dados.get('categorias', [])

    y = draw_header(c, estabelecimento, 'Resumo do Mês', periodo=periodo)
    draw_footer(c)

    GAP = 3*mm
    card_w = (CONTENT_W - 2*GAP) / 3
    card_h = 28*mm
    card_y = y - card_h

    draw_metric_card(c, MARGIN, card_y, card_w, card_h, 'Receita Total', format_brl(receita), NAVY)
    draw_metric_card(c, MARGIN + card_w + GAP, card_y, card_w, card_h, 'Despesas Totais', format_brl(despesas), RED)
    draw_metric_card(c, MARGIN + (card_w + GAP)*2, card_y, card_w, card_h, 'Lucro Líquido', format_brl(lucro), GREEN)

    y = card_y - 8*mm
    y = draw_section_header(c, y, 'DETALHAMENTO POR CATEGORIA')

    for idx, cat in enumerate(categorias):
        bg = LIGHT_GRAY if idx % 2 == 0 else WHITE
        c.setFillColor(bg)
        c.rect(MARGIN, y - 12*mm, CONTENT_W, 12*mm, fill=1, stroke=0)
        c.setFillColor(DARK_GRAY)
        c.setFont('LiberationSans-Bold', 9)
        c.drawString(MARGIN + 4*mm, y - 5*mm, cat.get('nome', ''))
        c.setFillColor(GRAY)
        c.setFont('LiberationSans', 7)
        c.drawString(MARGIN + 4*mm, y - 10*mm, cat.get('descricao', ''))
        valor = float(cat.get('valor', 0))
        c.setFillColor(RED if valor < 0 else DARK_GRAY)
        c.setFont('LiberationSans-Bold', 10)
        c.drawRightString(W - MARGIN - 2*mm, y - 7*mm, format_brl(valor))
        y -= 12*mm

    c.setFillColor(NAVY)
    c.rect(MARGIN, y - 8*mm, CONTENT_W, 8*mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont('LiberationSans-Bold', 9)
    c.drawString(MARGIN + 4*mm, y - 5.5*mm, 'LUCRO LÍQUIDO')
    c.setFillColor(GREEN if lucro >= 0 else RED)
    c.drawRightString(W - MARGIN - 2*mm, y - 5.5*mm, format_brl(lucro))

    c.save()
    buffer.seek(0)
    return buffer

# =================== RELATÓRIO 3: DRE ===================

def gerar_dre(dados):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    estabelecimento = dados.get('estabelecimento', 'Estabelecimento')
    periodo = dados.get('periodo', '')
    itens = dados.get('itens', {})

    y = draw_header(c, estabelecimento, 'DRE — Demonstração do Resultado', periodo=periodo)
    draw_footer(c)

    secoes = [
        ('RECEITA BRUTA', itens.get('receita_bruta', []), itens.get('total_receita_bruta', 0), False, itens.get('total_receita_bruta', 0), 'TOTAL RECEITA BRUTA'),
        ('(-) DEDUÇÕES E TAXAS', itens.get('deducoes', []), itens.get('total_deducoes', 0), True, itens.get('receita_liquida', 0), '(=) RECEITA LÍQUIDA'),
        ('(-) CMV', itens.get('cmv', []), itens.get('total_cmv', 0), True, itens.get('lucro_bruto', 0), '(=) LUCRO BRUTO'),
        ('(-) DESPESAS OPERACIONAIS', itens.get('despesas_op', []), itens.get('total_despesas_op', 0), True, itens.get('lucro_liquido', 0), '(=) LUCRO LÍQUIDO'),
    ]

    col_w = [CONTENT_W - 35*mm, 35*mm]

    for secao_nome, linhas, total_sec, negativo, resultado, resultado_label in secoes:
        y = draw_section_header(c, y, secao_nome)
        for idx, linha in enumerate(linhas):
            bg = LIGHT_GRAY if idx % 2 == 0 else WHITE
            c.setFillColor(bg)
            c.rect(MARGIN, y - 6*mm, CONTENT_W, 6*mm, fill=1, stroke=0)
            c.setFillColor(DARK_GRAY)
            c.setFont('LiberationSans', 8)
            c.drawString(MARGIN + 4*mm, y - 4*mm, linha.get('nome', ''))
            v = float(linha.get('valor', 0))
            c.setFillColor(RED if negativo else DARK_GRAY)
            c.drawRightString(W - MARGIN - 2*mm, y - 4*mm, f'{"-" if negativo and v > 0 else ""}{format_brl(abs(v))}')
            y -= 6*mm

        c.setFillColor(LIGHT_GRAY)
        c.rect(MARGIN, y - 6*mm, CONTENT_W, 6*mm, fill=1, stroke=0)
        c.setFillColor(DARK_GRAY)
        c.setFont('LiberationSans-Bold', 8)
        c.drawString(MARGIN + 4*mm, y - 4*mm, 'TOTAL')
        v = float(total_sec)
        c.setFillColor(RED if negativo else DARK_GRAY)
        c.drawRightString(W - MARGIN - 2*mm, y - 4*mm, f'{"-" if negativo and v > 0 else ""}{format_brl(abs(v))}')
        y -= 8*mm

        c.setFillColor(BLUE)
        c.rect(MARGIN, y - 7*mm, CONTENT_W, 7*mm, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont('LiberationSans-Bold', 9)
        c.drawString(MARGIN + 4*mm, y - 5*mm, resultado_label)
        c.drawRightString(W - MARGIN - 2*mm, y - 5*mm, format_brl(float(resultado)))
        y -= 12*mm

    c.save()
    buffer.seek(0)
    return buffer

# =================== RELATÓRIO 4: CONTÁBIL DETALHADO ===================

def gerar_contabil_detalhado(dados):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    estabelecimento = dados.get('estabelecimento', 'Estabelecimento')
    periodo = dados.get('periodo', '')
    cnpj = dados.get('cnpj', '')
    receitas = dados.get('receitas', [])
    despesas_lista = dados.get('despesas', [])
    resumo = dados.get('resumo', {})

    y = draw_header(c, estabelecimento, 'Relatório Contábil Detalhado', periodo=periodo)
    draw_footer(c)

    if cnpj:
        c.setFont('LiberationSans', 8)
        c.setFillColor(GRAY)
        c.drawString(MARGIN, y, f'CNPJ: {cnpj}')
        y -= 6*mm

    GAP = 2*mm
    card_w = (CONTENT_W - 3*GAP) / 4
    card_h = 20*mm
    metricas = [
        ('Receita Total', resumo.get('receita_total', 0), BLUE),
        ('Despesas Totais', resumo.get('despesas_totais', 0), RED),
        ('Lucro Líquido', resumo.get('lucro_liquido', 0), GREEN),
        ('Margem Líquida', resumo.get('margem', '0%'), NAVY),
    ]
    for i, (nome, val, cor) in enumerate(metricas):
        x = MARGIN + i * (card_w + GAP)
        c.setFillColor(cor)
        c.roundRect(x, y - card_h, card_w, card_h, 2*mm, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont('LiberationSans', 6)
        c.drawString(x + 2*mm, y - 5*mm, nome.upper())
        c.setFont('LiberationSans-Bold', 10)
        valor_str = val if isinstance(val, str) else format_brl(float(val))
        c.drawString(x + 2*mm, y - 14*mm, valor_str)
    y = y - card_h - 6*mm

    y = draw_section_header(c, y, 'RECEITAS')
    col_w = [18*mm, 50*mm, 28*mm, 26*mm, 22*mm, 14*mm, 22*mm]
    y = draw_table_header(c, y, ['Data', 'Descricao', 'Categoria', 'Forma Pagto', 'Bruto', 'Taxa', 'Liquido'], col_w, row_h=5*mm)
    for idx, r in enumerate(receitas[:10]):
        vals = [r.get('data',''), r.get('descricao','')[:22], r.get('categoria','')[:14],
                r.get('forma_pagamento','')[:12], format_brl(float(r.get('bruto',0))),
                format_brl(float(r.get('taxa',0))), format_brl(float(r.get('liquido',0)))]
        y = draw_table_row(c, y, vals, col_w, row_h=5*mm, idx=idx)

    y -= 4*mm
    y = draw_section_header(c, y, 'DESPESAS')
    y = draw_table_header(c, y, ['Data', 'Descricao', 'Categoria', 'Forma Pagto', 'Bruto', 'Taxa', 'Liquido'], col_w, row_h=5*mm)
    for idx, r in enumerate(despesas_lista[:10]):
        vals = [r.get('data',''), r.get('descricao','')[:22], r.get('categoria','')[:14],
                r.get('forma_pagamento','')[:12], format_brl(float(r.get('bruto',0))),
                format_brl(float(r.get('taxa',0))), format_brl(float(r.get('liquido',0)))]
        y = draw_table_row(c, y, vals, col_w, row_h=5*mm, idx=idx)

    c.save()
    buffer.seek(0)
    return buffer

# =================== RELATÓRIO 5: COMPARATIVO ===================

def gerar_comparativo(dados):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    estabelecimento = dados.get('estabelecimento', 'Estabelecimento')
    periodo1 = dados.get('periodo1', 'Período 1')
    periodo2 = dados.get('periodo2', 'Período 2')
    metricas = dados.get('metricas', [])

    y = draw_header(c, estabelecimento, 'Comparativo de Períodos')
    draw_footer(c)

    box_w = CONTENT_W/2 - 8*mm
    box_h = 12*mm

    c.setStrokeColor(BORDER_COLOR)
    c.setLineWidth(0.5)
    c.roundRect(MARGIN, y - box_h, box_w, box_h, 2*mm, fill=0, stroke=1)
    c.setFillColor(GRAY)
    c.setFont('LiberationSans', 7)
    c.drawString(MARGIN + 3*mm, y - 5*mm, 'Período 1 (Anterior)')
    c.setFillColor(NAVY)
    c.setFont('LiberationSans-Bold', 9)
    c.drawString(MARGIN + 3*mm, y - 10*mm, periodo1)

    c.setFillColor(BLUE)
    c.circle(W/2, y - box_h/2, 4*mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont('LiberationSans-Bold', 7)
    c.drawCentredString(W/2, y - box_h/2 - 2*mm, 'VS')

    c.setStrokeColor(BORDER_COLOR)
    c.roundRect(W/2 + 8*mm, y - box_h, box_w, box_h, 2*mm, fill=0, stroke=1)
    c.setFillColor(GRAY)
    c.setFont('LiberationSans', 7)
    c.drawString(W/2 + 11*mm, y - 5*mm, 'Período 2 (Atual)')
    c.setFillColor(NAVY)
    c.setFont('LiberationSans-Bold', 9)
    c.drawString(W/2 + 11*mm, y - 10*mm, periodo2)

    y -= box_h + 6*mm

    col_w = [45*mm, 42*mm, 42*mm, 36*mm]
    y = draw_section_header(c, y, 'COMPARATIVO DE MÉTRICAS')

    c.setFillColor(NAVY)
    c.rect(MARGIN, y - 6*mm, CONTENT_W, 6*mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont('LiberationSans-Bold', 8)
    x = MARGIN
    for lbl, cw in zip(['Métrica', 'Período 1', 'Período 2', 'Variação'], col_w):
        c.drawCentredString(x + cw/2, y - 4*mm, lbl)
        x += cw
    y -= 6*mm

    for idx, m in enumerate(metricas):
        bg = LIGHT_GRAY if idx % 2 == 0 else WHITE
        c.setFillColor(bg)
        c.rect(MARGIN, y - 6*mm, CONTENT_W, 6*mm, fill=1, stroke=0)
        variacao = m.get('variacao', '0%')
        positivo = not str(variacao).startswith('-')
        c.setFillColor(DARK_GRAY)
        c.setFont('LiberationSans-Bold', 8)
        c.drawString(MARGIN + 2*mm, y - 4*mm, m.get('nome', ''))
        c.setFont('LiberationSans', 8)
        c.drawCentredString(MARGIN + col_w[0] + col_w[1]/2, y - 4*mm, format_brl(float(m.get('valor1', 0))))
        c.drawCentredString(MARGIN + col_w[0] + col_w[1] + col_w[2]/2, y - 4*mm, format_brl(float(m.get('valor2', 0))))
        c.setFillColor(GREEN if positivo else RED)
        c.setFont('LiberationSans-Bold', 8)
        seta = '+' if positivo else '-'
        c.drawCentredString(MARGIN + col_w[0] + col_w[1] + col_w[2] + col_w[3]/2, y - 4*mm, f'{seta} {variacao}')
        y -= 6*mm

    c.save()
    buffer.seek(0)
    return buffer

# =================== RELATÓRIO 6: RANKING ===================

def gerar_ranking_servicos(dados):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    estabelecimento = dados.get('estabelecimento', 'Estabelecimento')
    periodo = dados.get('periodo', '')
    servicos = dados.get('servicos', [])

    y = draw_header(c, estabelecimento, 'Ranking de Serviços', periodo=periodo)
    draw_footer(c)

    y = draw_section_header(c, y, 'RECEITA POR SERVIÇO — Total faturado no período')
    max_val = max([float(s.get('receita', 0)) for s in servicos] + [1])
    bar_max = CONTENT_W - 75*mm

    for idx, s in enumerate(servicos[:10]):
        receita = float(s.get('receita', 0))
        bw = (receita/max_val)*bar_max
        c.setFillColor(DARK_GRAY)
        c.setFont('LiberationSans-Bold', 8)
        c.drawString(MARGIN + 2*mm, y - 4*mm, str(idx+1))
        c.setFont('LiberationSans', 8)
        c.drawString(MARGIN + 8*mm, y - 4*mm, s.get('nome', '')[:28])
        c.setFillColor(BLUE)
        c.rect(MARGIN + 68*mm, y - 5*mm, max(bw, 1*mm), 4*mm, fill=1, stroke=0)
        c.setFillColor(DARK_GRAY)
        c.setFont('LiberationSans-Bold', 8)
        c.drawRightString(W - MARGIN, y - 3*mm, format_brl(receita))
        y -= 7*mm

    y -= 4*mm
    col_w = [12*mm, 60*mm, 16*mm, 35*mm, 30*mm, 22*mm]
    y = draw_section_header(c, y, 'DETALHAMENTO POR SERVIÇO')
    y = draw_table_header(c, y, ['Pos.', 'Serviço', 'Qtd', 'Receita Total', 'Ticket Médio', '% Fat.'], col_w)

    total_receita = sum([float(s.get('receita', 0)) for s in servicos])
    for idx, s in enumerate(servicos[:10]):
        receita = float(s.get('receita', 0))
        qtd = int(s.get('quantidade', 0))
        ticket = receita/qtd if qtd > 0 else 0
        pct = (receita/total_receita*100) if total_receita > 0 else 0
        vals = [str(idx+1), s.get('nome','')[:28], str(qtd), format_brl(receita), format_brl(ticket), f'{pct:.2f}%']
        y = draw_table_row(c, y, vals, col_w, idx=idx)

    c.setFillColor(NAVY)
    c.rect(MARGIN, y - 6*mm, CONTENT_W, 6*mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont('LiberationSans-Bold', 8)
    c.drawString(MARGIN + 2*mm, y - 4*mm, 'TOTAL')
    c.drawRightString(W - MARGIN, y - 4*mm, '100,00%')

    c.save()
    buffer.seek(0)
    return buffer

# =================== RELATÓRIO 7: PERSONALIZADO ===================

def gerar_personalizado(dados):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    estabelecimento = dados.get('estabelecimento', 'Estabelecimento')
    titulo = dados.get('titulo', 'Relatório Personalizado')
    subtitulo = dados.get('subtitulo', '')
    secoes = dados.get('secoes', [])

    y = draw_header(c, estabelecimento, titulo, subtitulo=subtitulo)
    draw_footer(c)

    for secao in secoes:
        tipo = secao.get('tipo', 'tabela')
        nome = secao.get('nome', '')
        y = draw_section_header(c, y, nome.upper())

        if tipo == 'tabela':
            colunas = secao.get('colunas', [])
            linhas = secao.get('linhas', [])
            if colunas:
                col_w_unit = CONTENT_W / len(colunas)
                col_ws = [col_w_unit] * len(colunas)
                y = draw_table_header(c, y, colunas, col_ws)
                for idx, linha in enumerate(linhas):
                    y = draw_table_row(c, y, linha, col_ws, idx=idx)

        elif tipo == 'texto':
            texto = secao.get('texto', '')
            c.setFillColor(LIGHT_GRAY)
            c.roundRect(MARGIN, y - 18*mm, CONTENT_W, 18*mm, 2*mm, fill=1, stroke=0)
            c.setFillColor(DARK_GRAY)
            c.setFont('LiberationSans', 8)
            words = texto.split()
            line = ''
            line_y = y - 6*mm
            for word in words:
                test = line + word + ' '
                if c.stringWidth(test, 'LiberationSans', 8) > CONTENT_W - 8*mm:
                    c.drawString(MARGIN + 4*mm, line_y, line.strip())
                    line = word + ' '
                    line_y -= 5*mm
                else:
                    line = test
            if line:
                c.drawString(MARGIN + 4*mm, line_y, line.strip())
            y -= 22*mm

        y -= 5*mm

    c.save()
    buffer.seek(0)
    return buffer

# =================== ROTAS ===================

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'Oren IA PDF Service'})

@app.route('/pdf/download/<filename>', methods=['GET'])
def download_pdf(filename):
    """Serve o PDF salvo em /tmp"""
    path = os.path.join(TMP_DIR, filename)
    if not os.path.exists(path):
        return jsonify({'erro': 'Arquivo nao encontrado ou expirado'}), 404
    return send_file(path, mimetype='application/pdf', as_attachment=True, download_name=filename)

def responder_com_url(buffer, nome_base):
    """Helper: salva PDF e retorna JSON com URL de download"""
    filename = salvar_pdf_tmp(buffer, nome_base)
    base_url = get_base_url()
    url = f"{base_url}/pdf/download/{filename}"
    return jsonify({'url': url, 'filename': filename})

@app.route('/pdf/resumo-dia', methods=['POST'])
def pdf_resumo_dia():
    buffer = gerar_resumo_dia(request.get_json())
    return responder_com_url(buffer, 'resumo_dia')

@app.route('/pdf/resumo-mensal', methods=['POST'])
def pdf_resumo_mensal():
    buffer = gerar_resumo_mensal(request.get_json())
    return responder_com_url(buffer, 'resumo_mensal')

@app.route('/pdf/dre', methods=['POST'])
def pdf_dre():
    buffer = gerar_dre(request.get_json())
    return responder_com_url(buffer, 'dre')

@app.route('/pdf/contabil-detalhado', methods=['POST'])
def pdf_contabil():
    buffer = gerar_contabil_detalhado(request.get_json())
    return responder_com_url(buffer, 'relatorio_contabil')

@app.route('/pdf/comparativo', methods=['POST'])
def pdf_comparativo():
    buffer = gerar_comparativo(request.get_json())
    return responder_com_url(buffer, 'comparativo')

@app.route('/pdf/ranking-servicos', methods=['POST'])
def pdf_ranking():
    buffer = gerar_ranking_servicos(request.get_json())
    return responder_com_url(buffer, 'ranking_servicos')

@app.route('/pdf/personalizado', methods=['POST'])
def pdf_personalizado():
    buffer = gerar_personalizado(request.get_json())
    return responder_com_url(buffer, 'relatorio_personalizado')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
