# app/utils/docx_tools.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple
from datetime import datetime
from docxtpl import DocxTemplate
import jinja2
import subprocess
import shutil
import zipfile
import logging
import os
import re
import tempfile
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

# Namespaces DOCX (WordprocessingML)
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_XML = "http://www.w3.org/XML/1998/namespace"
ET.register_namespace("w", NS_W)  # preserva prefixo w

def _w(tag: str) -> str:
    return f"{{{NS_W}}}{tag}"

# -------------------------------------------------------------------
# Placeholders utilitários / inspeção
# -------------------------------------------------------------------
def get_docx_placeholders(template_path: str) -> List[str]:
    """Extrai variáveis Jinja do DOCX."""
    if not os.path.exists(template_path):
        return []
    try:
        tpl = DocxTemplate(template_path)
        env = jinja2.Environment()
        vars_set = tpl.get_undeclared_template_variables(jinja_env=env)  # type: ignore
        out = sorted(vars_set)
        logger.info("[docx_tools] Placeholders(docxtpl): %s", out)
        return out
    except Exception as e:
        logger.info("[docx_tools] get_undeclared_template_variables falhou: %s", e)

    names: set[str] = set()
    try:
        with zipfile.ZipFile(template_path, "r") as z:
            for name in z.namelist():
                if not name.startswith("word/") or not name.endswith(".xml"):
                    continue
                xml = z.read(name).decode("utf-8", errors="ignore")
                flat = re.sub(r"<[^>]+>", "", xml)
                for m in re.finditer(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)", flat):
                    names.add(m.group(1))
                if "{%" in flat:
                    names.add("_block")
    except Exception as e:
        logger.warning("[docx_tools] Falha ao varrer XML: %s", e)
    out2 = sorted(names)
    logger.info("[docx_tools] Placeholders(fallback): %s", out2)
    return out2

# -------------------------------------------------------------------
# Helpers gerais
# -------------------------------------------------------------------
def _date_br(v) -> str:
    try:
        if isinstance(v, datetime):
            dt = v
        else:
            dt = datetime.fromisoformat(str(v))
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str(v) if v is not None else ""

def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _fmt_money(v) -> str:
    """Formata dinheiro em pt-BR: R$ 1.234,56."""
    try:
        n = float(v or 0.0)
    except Exception:
        n = 0.0
    inteiro, frac = f"{n:0.2f}".split(".")
    inteiro_grp = []
    while inteiro:
        inteiro_grp.append(inteiro[-3:])
        inteiro = inteiro[:-3]
    inteiro_fmt = ".".join(reversed(inteiro_grp))
    return f"R$ {inteiro_fmt},{frac}"

def _split_lines(text: str) -> List[str]:
    if not text:
        return [""]
    return str(text).splitlines() or [""]

def _num(v) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0

# -------------------------------------------------------------------
# Helpers XML (parágrafos, runs, estilos leves)
# -------------------------------------------------------------------
def _mk_run(text: str, bold: bool = False, italic: bool = False) -> ET.Element:
    r = ET.Element(_w("r"))
    if bold or italic:
        rpr = ET.SubElement(r, _w("rPr"))
        if bold:
            ET.SubElement(rpr, _w("b"))
        if italic:
            ET.SubElement(rpr, _w("i"))
    t = ET.SubElement(r, _w("t"))
    t.set(f"{{{NS_XML}}}space", "preserve")
    t.text = text
    return r

def _mk_p(
    runs: List[Tuple[str, bool, bool]] | None = None,
    *,
    text: str | None = None,
    bold: bool = False,
    italic: bool = False,
    # legado: indent_level continua aceito, mapeado para left_indent_level
    indent_level: int = 0,
    # novos: controle fino de recuos
    left_indent_level: int | None = None,
    first_line_indent_level: int = 0,
) -> ET.Element:
    """
    Cria <w:p> com suporte a múltiplos runs e indentação.
    - runs: lista de tuplas (texto, bold, italic) OU text/bold/italic simples
    - left_indent_level: níveis de recuo à ESQUERDA (cada nível ≈ 360 twips)
    - first_line_indent_level: recuo apenas da PRIMEIRA linha (cada nível ≈ 360 twips)
    - indent_level (legado): equivale a left_indent_level
    """
    if left_indent_level is None:
        left_indent_level = indent_level

    p = ET.Element(_w("p"))

    if (left_indent_level and left_indent_level > 0) or (first_line_indent_level and first_line_indent_level > 0):
        ppr = ET.SubElement(p, _w("pPr"))
        ind = ET.SubElement(ppr, _w("ind"))
        if left_indent_level and left_indent_level > 0:
            ind.set(_w("left"), str(360 * left_indent_level))
        if first_line_indent_level and first_line_indent_level > 0:
            # Recuo apenas da primeira linha
            ind.set(_w("firstLine"), str(360 * first_line_indent_level))

    if runs is None:
        runs = [(text or "", bold, italic)]
    for s, b, i in runs:
        p.append(_mk_run(s, bold=b, italic=i))
    return p

def _mk_label_value(label: str, value: str, indent_level: int = 0) -> ET.Element:
    """Parágrafo 'Label: valor' (label em negrito)."""
    return _mk_p(
        runs=[(f"{label}: ", True, False), (value or "", False, False)],
        left_indent_level=indent_level
    )

# -------------------------------------------------------------------
# Tabelas (WordprocessingML)
# -------------------------------------------------------------------
def _tc(text: str, *, bold: bool=False, align: str|None=None, grid_span: int|None=None) -> ET.Element:
    """
    Cria uma célula <w:tc> com um único parágrafo e texto.
    align: None | 'left' | 'center' | 'right'
    grid_span: número de colunas a mesclar (gridSpan)
    """
    tc = ET.Element(_w("tc"))
    tcpr = ET.SubElement(tc, _w("tcPr"))
    if grid_span and grid_span > 1:
        gs = ET.SubElement(tcpr, _w("gridSpan"))
        gs.set(_w("val"), str(grid_span))
    p = ET.SubElement(tc, _w("p"))
    if align in ("left","center","right"):
        ppr = ET.SubElement(p, _w("pPr"))
        jc = ET.SubElement(ppr, _w("jc"))
        jc.set(_w("val"), align)
    r = ET.SubElement(p, _w("r"))
    if bold:
        rpr = ET.SubElement(r, _w("rPr"))
        ET.SubElement(rpr, _w("b"))
    t = ET.SubElement(r, _w("t"))
    t.set(f"{{{NS_XML}}}space", "preserve")
    t.text = text
    return tc

def _tr(cells: list[ET.Element]) -> ET.Element:
    tr = ET.Element(_w("tr"))
    for c in cells:
        tr.append(c)
    return tr

def _tbl(rows: list[list[ET.Element]], *, borders: bool=True, col_widths: list[int]|None=None) -> ET.Element:
    """
    Cria <w:tbl> simples.
    col_widths: lista com larguras em twips (opcional).
    """
    tbl = ET.Element(_w("tbl"))
    tblpr = ET.SubElement(tbl, _w("tblPr"))
    tblw = ET.SubElement(tblpr, _w("tblW"))
    tblw.set(_w("type"), "auto")
    tblw.set(_w("w"), "0")
    if borders:
        tb = ET.SubElement(tblpr, _w("tblBorders"))
        for side in ("top","left","bottom","right","insideH","insideV"):
            b = ET.SubElement(tb, _w(side))
            b.set(_w("val"), "single")
            b.set(_w("sz"), "4")
            b.set(_w("space"), "0")
            b.set(_w("color"), "auto")
    if col_widths:
        grid = ET.SubElement(tbl, _w("tblGrid"))
        for w in col_widths:
            gc = ET.SubElement(grid, _w("gridCol"))
            gc.set(_w("w"), str(w))
    for r in rows:
        tbl.append(_tr(r))
    return tbl

# -------------------------------------------------------------------
# Blocos prontos (fraseados no estilo do DFD)
# -------------------------------------------------------------------
_PRIORITY_OPTIONS = [
    "Alto, quando a impossibilidade de contratação provoca interrupção de processo crítico ou estratégico.",
    "Médio, quando a impossibilidade de contratação provoca atraso de processo crítico ou estratégico.",
    "Baixo, quando a impossibilidade de contratação provoca interrupção ou atraso de processo não crítico.",
    "Muito baixo, quando a continuidade do processo é possível mediante o emprego de uma solução de contorno.",
]

def _priority_block(selected: str | None) -> List[ET.Element]:
    """Renderiza a lista de prioridade com (X) na opção selecionada (campo geral)."""
    out: List[ET.Element] = []
    out.append(_mk_p(text="Grau de prioridade da aquisição/contratação:", bold=True))
    # linha em branco após o enunciado
    out.append(ET.Element(_w("p")))
    sel_norm = (selected or "").strip()
    for opt in _PRIORITY_OPTIONS:
        mark = "( X ) " if opt == sel_norm else "(   ) "
        # recuo apenas da primeira linha; linhas seguintes voltam à margem do enunciado
        out.append(_mk_p(text=mark + opt, left_indent_level=0, first_line_indent_level=1))
    return out

def _quantidade_valor_sentence(qtd: Any, um: str, vu: Any, vt: Any) -> str:
    """
    Frase:
    'A quantidade é de 10 (dez) unidades no valor de R$ 2.000,00 cada, totalizando R$ 20.000,00.'
    (sem número por extenso; valores numéricos formatados)
    """
    try:
        qn = int(float(qtd))
    except Exception:
        qn = 0
    um_txt = (um or "").strip()
    vu_txt = _fmt_money(vu)
    vt_txt = _fmt_money(vt)
    s_um = f" {um_txt}" if um_txt else ""
    return f"A quantidade é de {qn}{s_um} no valor de {vu_txt} cada, totalizando {vt_txt}."

# -------------------------------------------------------------------
# Corpo do documento (sem placeholders Jinja)
# -------------------------------------------------------------------
def _append_body_sections_xml_et(
    document_xml_bytes: bytes,
    context: Dict[str, Any],
    intro_lines: List[str] | None = None,
) -> bytes:
    """
    Organização alinhada à NOVA UI e ao modelo de exemplo:
      - Introdução
      - Diretoria demandante
      - Alinhamento com o Planejamento Estratégico (multilinha)
      - Justificativa da necessidade (GERAL)
      - Objeto (multilinha)
      - Itens em TABELA 1: Item | Descrição | Vínculo | Renovação (tudo à ESQUERDA)
      - 'Valores estimados:' + TABELA 2: Item | Quantidade | Unidade | Valor Unitário | Valor Total
        (tudo à ESQUERDA, EXCETO 'Valor Total', que fica à DIREITA) + linha Total com valor à DIREITA
      - Prazos envolvidos
      - Consequências da não aquisição
      - Grau de prioridade
      - ASSINATURA
    """
    root = ET.fromstring(document_xml_bytes)
    body = root.find(_w("body"))
    if body is None:
        logger.warning("[docx_tools] <w:body> não encontrado.")
        return document_xml_bytes

    children = list(body)
    sectpr = next((c for c in children if c.tag == _w("sectPr")), None)
    insert_idx = children.index(sectpr) if sectpr is not None else len(children)

    elems: List[ET.Element] = []

    # 0) Introdução (se houver)
    if intro_lines:
        for line in intro_lines:
            elems.append(_mk_p(text=line))
        if intro_lines and intro_lines[-1].strip():
            elems.append(ET.Element(_w("p")))  # linha em branco

    # 1) Diretoria demandante
    dire = str(context.get("diretoria_demandante") or "").strip()
    if dire:
        elems.append(_mk_label_value("Diretoria demandante", dire))
        elems.append(ET.Element(_w("p")))
    
    # 2) Alinhamento com o Planejamento Estratégico
    alin = str(context.get("alinhamento_pe") or "").strip()
    if alin:
        elems.append(_mk_p(text="Alinhamento com o Planejamento Estratégico", bold=True))
        # linha em branco após o enunciado
        elems.append(ET.Element(_w("p")))
        for line in _split_lines(alin):
            # recuo somente na primeira linha; demais linhas voltam à margem do enunciado
            elems.append(_mk_p(text=line, left_indent_level=0, first_line_indent_level=1))
        elems.append(ET.Element(_w("p")))

    # 3) Justificativa da necessidade (GERAL)
    just_geral = str(context.get("justificativa_necessidade") or "").strip()
    if just_geral:
        elems.append(_mk_p(text="Justificativa da necessidade", bold=True))
        elems.append(ET.Element(_w("p")))  # branco após enunciado
        for line in _split_lines(just_geral):
            elems.append(_mk_p(text=line, left_indent_level=0, first_line_indent_level=1))
        elems.append(ET.Element(_w("p")))

    # 4) Objeto
    obj = str(context.get("objeto") or "").strip()
    if obj:
        elems.append(_mk_p(text="Objeto", bold=True))
        elems.append(ET.Element(_w("p")))  # branco após enunciado
        for line in _split_lines(obj):
            elems.append(_mk_p(text=line, left_indent_level=0, first_line_indent_level=1))
        elems.append(ET.Element(_w("p")))

    # 5) Tabela 1 — Itens: Item | Descrição | Vínculo | Renovação (tudo à ESQUERDA)
    itens = context.get("itens") or []
    if isinstance(itens, list) and itens:
        elems.append(ET.Element(_w("p")))
        header = [
            _tc("Item", bold=True, align="left"),
            _tc("Descrição", bold=True, align="left"),
            _tc("Vínculo", bold=True, align="left"),
            _tc("Renovação", bold=True, align="left"),
        ]
        rows = [header]
        for i, it in enumerate(itens, start=1):
            desc = (it.get("descricao") or "").strip()
            dep = (it.get("haDependencia") or "").strip()
            dep_qual = (it.get("dependenciaQual") or "").strip()
            # Se houver vínculo (Sim), exibir a descrição do vínculo; se 'Não', mostrar 'Não'
            vinculo_txt = dep_qual if dep == "Sim" and dep_qual else "Não"
            renov = (it.get("renovacaoContrato") or "").strip()
            rows.append([
                _tc(str(i), align="left"),
                _tc(desc, align="left"),
                _tc(vinculo_txt, align="left"),
                _tc(renov, align="left"),
            ])
        elems.append(_tbl(rows, borders=True))
        elems.append(ET.Element(_w("p")))

        # 6) Valores estimados — título + tabela 2
        elems.append(_mk_p(text="Valores estimados:", bold=True))
        elems.append(ET.Element(_w("p")))  # branco após enunciado
        v_header = [
            _tc("Item", bold=True, align="left"),
            _tc("Quantidade", bold=True, align="left"),
            _tc("Unidade", bold=True, align="left"),
            _tc("Valor Unitário", bold=True, align="left"),
            _tc("Valor Total", bold=True, align="right"),
        ]
        v_rows = [v_header]
        total_geral = 0.0
        for i, it in enumerate(itens, start=1):
            qtd = it.get("quantidade")
            um  = (it.get("unidadeMedida") or "").strip()
            vu  = it.get("valorUnitario")
            vt  = it.get("valorTotal")
            try:
                total_geral += float(vt or 0.0)
            except Exception:
                pass
            # normaliza quantidade para inteiro
            try:
                qtd_txt = str(int(float(qtd or 0)))
            except Exception:
                qtd_txt = "0"
            v_rows.append([
                _tc(str(i), align="left"),
                _tc(qtd_txt, align="left"),
                _tc(um, align="left"),
                _tc(_fmt_money(vu), align="left"),
                _tc(_fmt_money(vt), align="right"),
            ])
        # Linha Total (mescla 4 primeiras colunas); valor à direita
        v_rows.append([
            _tc("Total", bold=True, grid_span=4, align="left"),
            _tc(_fmt_money(total_geral), bold=True, align="right"),
        ])
        elems.append(_tbl(v_rows, borders=True))
        elems.append(ET.Element(_w("p")))

    # 7) Seção geral (após itens): prazos, consequência, prioridade
    prazos = str(context.get("prazos_envolvidos") or context.get("prazosEnvolvidos") or "").strip()
    consq = str(context.get("consequencia_nao_aquisicao") or context.get("consequenciaNaoAquisicao") or "").strip()
    grau = str(context.get("grau_prioridade") or context.get("grauPrioridade") or "").strip()

    if prazos or consq or grau:
        # Prazos envolvidos — texto igual ao exemplo
        if prazos:
            elems.append(_mk_p(text="Prazos envolvidos (Data – mês e ano – em que o objeto precisa estar adquirido ou contratado)", bold=True))
            elems.append(ET.Element(_w("p")))  # branco após enunciado
            elems.append(_mk_p(text=f"Até {prazos}.", left_indent_level=0, first_line_indent_level=1))
            elems.append(ET.Element(_w("p")))
        # Consequências
        if consq:
            elems.append(_mk_p(text="Consequências da não aquisição/contratação do objeto", bold=True))
            elems.append(ET.Element(_w("p")))  # branco após enunciado
            for line in _split_lines(consq):
                elems.append(_mk_p(text=line, left_indent_level=0, first_line_indent_level=1))
            elems.append(ET.Element(_w("p")))
        # Grau de prioridade (lista com marcação)
        if grau:
            elems.extend(_priority_block(grau))
            elems.append(ET.Element(_w("p")))

    # 8) ASSINATURA
    elems.append(_mk_p(text="ASSINATURA", bold=True))
    elems.append(ET.Element(_w("p")))

    # Inserção no corpo
    for off, el in enumerate(elems):
        body.insert(insert_idx + off, el)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)

# -------------------------------------------------------------------
# Patch do cabeçalho (preserva imagens)
# -------------------------------------------------------------------
def _patch_header_xml_text(xml: str, numero: str, assunto: str, data_fmt: str) -> str:
    xml = xml.replace("00/00/0000", _xml_escape(data_fmt))
    xml = re.sub(r"(?<!\d)0{4,}(?![\d/])", _xml_escape(numero), xml)
    repl = {
        "Xx": assunto,
        "xx": assunto,
        "[[NUMERO]]": numero,
        "[[ASSUNTO]]": assunto,
        "[[DATA]]": data_fmt,
    }
    for k, v in repl.items():
        xml = xml.replace(k, _xml_escape(v))
    return xml

# -------------------------------------------------------------------
# Renderização preservando timbre (fallback para DFD v2+)
# -------------------------------------------------------------------
def _render_fixed_timbre(template_path: str, context: Dict[str, Any], out_path: str) -> None:
    """
    Copia o DOCX e aplica:
      - patch nos headers (número/assunto/data),
      - injeção de INTRO + seções do DFD no corpo (formatação leve).
    """
    numero = str(context.get("numero") or "")
    assunto = str(context.get("assunto") or "Documento de Formalização de Demanda")
    data_fmt = _date_br(context.get("data") or datetime.utcnow().date().isoformat())
    ano_pca = str(context.get("pca_ano") or context.get("pcaAno") or "").strip()

    intro_lines = [
        "À Diretoria de Administrativo-Financeira",
        "",
        f"Encaminha-se o presente Documento de Formalização da Demanda – DFD, para fins de inclusão no Plano de Contratações Anual – PCA do exercício {ano_pca}, nos seguintes termos:",
    ]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        tmp_name = tmp.name

    try:
        with zipfile.ZipFile(template_path, "r") as zin, zipfile.ZipFile(tmp_name, "w", zipfile.ZIP_DEFLATED) as zout:
            doc_xml = None
            for name in zin.namelist():
                data = zin.read(name)

                if name.startswith("word/header") and name.endswith(".xml"):
                    try:
                        xml = data.decode("utf-8", errors="ignore")
                        data = _patch_header_xml_text(xml, numero, assunto, data_fmt).encode("utf-8")
                    except Exception as e:
                        logger.warning("[docx_tools] Falha patch header %s: %s", name, e)

                if name == "word/document.xml":
                    doc_xml = data
                    continue  # adia a escrita do corpo

                zout.writestr(name, data)

            if doc_xml is not None:
                doc_xml2 = _append_body_sections_xml_et(doc_xml, context, intro_lines=intro_lines)
                zout.writestr("word/document.xml", doc_xml2)

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        shutil.move(tmp_name, out_path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except Exception:
                pass

# -------------------------------------------------------------------
# API principal
# -------------------------------------------------------------------
def render_docx_template(template_path: str, context: Dict[str, Any], out_path: str) -> None:
    """Roteia entre:
       - docxtpl (quando o DOCX tem placeholders Jinja),
       - pipeline de timbre fixo (quando não tem placeholders)."""
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template não encontrado: {template_path}")

    vars_ = get_docx_placeholders(template_path)
    if vars_:
        env = jinja2.Environment(autoescape=False)
        env.filters["date_br"] = _date_br
        tpl = DocxTemplate(template_path)
        tpl.render(context, jinja_env=env)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        tpl.save(out_path)
        return

    _render_fixed_timbre(template_path, context, out_path)

# -------------------------------------------------------------------
# LibreOffice wrappers
# -------------------------------------------------------------------
def _soffice_bin() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")

def has_soffice() -> bool:
    return _soffice_bin() is not None

def convert_docx_to_pdf(docx_path: str, pdf_path: str) -> bool:
    """Converte DOCX em PDF usando LibreOffice headless (se disponível)."""
    soffice = _soffice_bin()
    if not soffice:
        logger.info("[docx_tools] soffice não encontrado; ficará em DOCX.")
        return False
    outdir = os.path.dirname(pdf_path)
    os.makedirs(outdir, exist_ok=True)
    cwd = os.path.dirname(docx_path)
    try:
        subprocess.check_call(
            [
                soffice, "--headless", "--norestore", "--invisible",
                "--convert-to", "pdf", os.path.basename(docx_path),
                "--outdir", outdir
            ],
            cwd=cwd
        )
    except subprocess.CalledProcessError as e:
        logger.error("[docx_tools] Erro LibreOffice: %s", e)
        return False
    return os.path.exists(pdf_path)
