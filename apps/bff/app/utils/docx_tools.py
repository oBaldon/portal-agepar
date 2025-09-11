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
    indent_level: int = 0
) -> ET.Element:
    """
    Cria <w:p> com suporte a múltiplos runs e indentação em níveis.
    - runs: lista de tuplas (texto, bold, italic)
    - ou text/bold/italic simples
    - indent_level: 0..N → aplica w:ind left ~ 360 twips por nível
    """
    p = ET.Element(_w("p"))
    if indent_level > 0:
        ppr = ET.SubElement(p, _w("pPr"))
        ind = ET.SubElement(ppr, _w("ind"))
        ind.set(_w("left"), str(360 * indent_level))
    if runs is None:
        runs = [(text or "", bold, italic)]
    for s, b, i in runs:
        p.append(_mk_run(s, bold=b, italic=i))
    return p

def _mk_label_value(label: str, value: str, indent_level: int = 0) -> ET.Element:
    """Parágrafo 'Label: valor' (label em negrito)."""
    return _mk_p(
        runs=[(f"{label}: ", True, False), (value or "", False, False)],
        indent_level=indent_level
    )

# -------------------------------------------------------------------
# Blocos prontos (fraseados no estilo do DFD antigo)
# -------------------------------------------------------------------
_PRIORITY_OPTIONS = [
    "Alto, quando a impossibilidade de contratação provoca interrupção de processo crítico ou estratégico.",
    "Médio, quando a impossibilidade de contratação provoca atraso de processo crítico ou estratégico.",
    "Baixo, quando a impossibilidade de contratação provoca interrupção ou atraso de processo não crítico.",
    "Muito baixo, quando a continuidade do processo é possível mediante o emprego de uma solução de contorno.",
]

def _priority_block(selected: str | None) -> List[ET.Element]:
    """Renderiza a lista de prioridade com (X) na opção selecionada."""
    out: List[ET.Element] = []
    out.append(_mk_p(text="Grau de prioridade da aquisição/contratação:", bold=True))
    sel_norm = (selected or "").strip()
    for opt in _PRIORITY_OPTIONS:
        mark = "( X ) " if opt == sel_norm else "(   ) "
        out.append(_mk_p(text=mark + opt, indent_level=1))
    return out

def _quantidade_valor_sentence(qtd: Any, um: str, vu: Any, vt: Any) -> str:
    """
    Frase nos moldes do exemplo antigo:
    'A quantidade é de 10 (dez) unidades no valor de R$ 2.000,00 cada, totalizando R$ 20.000,00.'
    (Não faremos número por extenso aqui — mantemos somente valores numéricos formatados)
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
# Manipulação do corpo (fallback DFD v2 lapidado)
# -------------------------------------------------------------------
def _append_body_sections_xml_et(
    document_xml_bytes: bytes,
    context: Dict[str, Any],
    intro_lines: List[str] | None = None,
) -> bytes:
    """
    Monta o corpo com a organização e o tom do DFD antigo, aplicado aos novos campos:
      - Introdução
      - Diretoria demandante
      - Alinhamento com o Planejamento Estratégico (multilinha)
      - Objeto (multilinha)
      - Itens (1..N) com sub-blocos:
          * Descrição sucinta do objeto
          * Justificativa da necessidade
          * Consequências da não contratação
          * Prazos envolvidos
          * Quantidade e Valor estimados
          * Unidade de medida (separado se fizer sentido)
          * Dependência (quando Sim)
          * Renovação de contrato (Sim/Não)
          * Grau de prioridade (lista com (X))
      - Total geral (soma dos itens)
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
        for line in _split_lines(alin):
            elems.append(_mk_p(text=line, indent_level=1))
        elems.append(ET.Element(_w("p")))

    # 3) Objeto
    obj = str(context.get("objeto") or "").strip()
    if obj:
        elems.append(_mk_p(text="Objeto", bold=True))
        for line in _split_lines(obj):
            elems.append(_mk_p(text=line, indent_level=1))
        elems.append(ET.Element(_w("p")))

    # 4) Itens
    itens = context.get("itens") or []
    if isinstance(itens, list) and itens:
        #elems.append(_mk_p(text="Itens", bold=True))
        elems.append(ET.Element(_w("p")))

        for i, it in enumerate(itens, start=1):
            desc = (it.get("descricao") or "").strip()
            just = (it.get("justificativa") or "").strip()
            um = (it.get("unidadeMedida") or "").strip()
            qtd = it.get("quantidade")
            vu = it.get("valorUnitario")
            vt = it.get("valorTotal")
            grau = (it.get("grauPrioridade") or "").strip()
            data = (it.get("dataPretendida") or "").strip()
            dep = (it.get("haDependencia") or "").strip()
            depq = (it.get("dependenciaQual") or "").strip()
            riscos = (it.get("riscosNaoContratacao") or "").strip()
            renov = (it.get("renovacaoContrato") or "").strip()

            # Cabeçalho do item
            elems.append(_mk_p(text=f"Item #{i}", bold=True))
            # Descrição
            if desc:
                elems.append(_mk_p(text="Descrição sucinta do objeto", bold=True, indent_level=1))
                for line in _split_lines(desc):
                    elems.append(_mk_p(text=line, indent_level=2))
            # Justificativa
            if just:
                elems.append(_mk_p(text="Justificativa da necessidade (Problema a ser resolvido)", bold=True, indent_level=1))
                for line in _split_lines(just):
                    elems.append(_mk_p(text=line, indent_level=2))
            # Consequências
            if riscos:
                elems.append(_mk_p(text="Consequências da não aquisição/contratação do objeto (Possíveis impactos se o problema não for resolvido)", bold=True, indent_level=1))
                for line in _split_lines(riscos):
                    elems.append(_mk_p(text=line, indent_level=2))
            # Prazos envolvidos
            if data:
                elems.append(_mk_p(text="Prazos envolvidos (Data – mês e ano – em que o objeto precisa estar adquirido ou contratado)", bold=True, indent_level=1))
                elems.append(_mk_p(text=f"Até {data}.", indent_level=2))
            # Quantidade e Valor
            if (qtd is not None) or (vu is not None) or (vt is not None):
                elems.append(_mk_p(text="Quantidade e Valor estimados", bold=True, indent_level=1))
                sent = _quantidade_valor_sentence(qtd, um, vu, vt)
                elems.append(_mk_p(text=sent, indent_level=2))
                # Unidade de medida (separadamente, caso deseje destacar)
                if um:
                    elems.append(_mk_label_value("Unidade de medida", um, indent_level=2))

            # Dependência
            if dep:
                elems.append(_mk_label_value("Há vínculo/dependência com outra contratação", dep, indent_level=1))
                if dep == "Sim" and depq:
                    elems.append(_mk_label_value("Se 'Sim', qual", depq, indent_level=2))

            # Renovação
            if renov:
                elems.append(_mk_label_value("Renovação de contrato", renov, indent_level=1))

            # Grau de prioridade
            elems.extend(_priority_block(grau))

            # Espaço entre itens
            elems.append(ET.Element(_w("p")))

    # 5) Total geral
    total_geral = context.get("total_geral", None)
    if total_geral is None and itens:
        total_geral = sum(_num((it or {}).get("valorTotal")) for it in itens if isinstance(it, dict))
    if itens:
        elems.append(_mk_p(text=f"Total geral da contratação (soma dos itens): {_fmt_money(total_geral)}", bold=True))
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
# Renderização preservando timbre (fallback para DFD v2)
# -------------------------------------------------------------------
def _render_fixed_timbre(template_path: str, context: Dict[str, Any], out_path: str) -> None:
    """
    Copia o DOCX e aplica:
      - patch nos headers (número/assunto/data),
      - injeção de INTRO + seções do DFD v2 no corpo (formatação lapidada).
    """
    numero = str(context.get("numero") or "")
    assunto = str(context.get("assunto") or "Documento de Formalização de Demanda")
    data_fmt = _date_br(context.get("data") or datetime.utcnow().date().isoformat())
    ano_pca = str(context.get("pca_ano") or context.get("pcaAno") or "").strip()

    intro_lines = [
        "À Diretoria de Administração-Financeira",
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
