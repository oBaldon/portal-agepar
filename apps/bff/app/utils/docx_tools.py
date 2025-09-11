# app/utils/docx_tools.py
from __future__ import annotations
from typing import Dict, Any, List
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
    # separador milhar "." e decimal ","
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


# -------------------------------------------------------------------
# Manipulação do corpo do documento (fallback DFD v2)
# -------------------------------------------------------------------
def _mk_p(text: str) -> ET.Element:
    p = ET.Element(_w("p"))
    r = ET.SubElement(p, _w("r"))
    t = ET.SubElement(r, _w("t"))
    t.set(f"{{{NS_XML}}}space", "preserve")
    t.text = text
    return p


def _append_body_sections_xml_et(
    document_xml_bytes: bytes,
    context: Dict[str, Any],
    intro_lines: List[str] | None = None,
) -> bytes:
    """
    Acrescenta seções simples ao <w:body> para o DFD v2:
      - Introdução
      - Diretoria demandante
      - Objeto (multilinha)
      - Alinhamento com o Planejamento Estratégico (multilinha)
      - Itens (lista de itens com campos)
      - Total geral
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
            elems.append(_mk_p(line))
        if intro_lines and intro_lines[-1].strip():
            elems.append(ET.Element(_w("p")))  # linha em branco

    # 1) Diretoria demandante
    dire = str(context.get("diretoria_demandante") or "").strip()
    if dire:
        elems.append(_mk_p(f"Diretoria demandante: {dire}"))
        elems.append(ET.Element(_w("p")))

    # 2) Objeto
    obj = str(context.get("objeto") or "").strip()
    if obj:
        elems.append(_mk_p("Objeto:"))
        for line in _split_lines(obj):
            elems.append(_mk_p(f"  {line}"))
        elems.append(ET.Element(_w("p")))

    # 3) Alinhamento com o Planejamento Estratégico
    alin = str(context.get("alinhamento_pe") or "").strip()
    if alin:
        elems.append(_mk_p("Alinhamento com o Planejamento Estratégico:"))
        for line in _split_lines(alin):
            elems.append(_mk_p(f"  {line}"))
        elems.append(ET.Element(_w("p")))

    # 4) Itens
    itens = context.get("itens") or []
    if isinstance(itens, list) and itens:
        elems.append(_mk_p("Itens:"))
        elems.append(ET.Element(_w("p")))
        for i, it in enumerate(itens, start=1):
            elems.append(_mk_p(f"Item #{i}"))
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

            if desc:
                elems.append(_mk_p("  Descrição:"))
                for line in _split_lines(desc):
                    elems.append(_mk_p(f"    {line}"))
            if just:
                elems.append(_mk_p("  Justificativa:"))
                for line in _split_lines(just):
                    elems.append(_mk_p(f"    {line}"))

            if um:
                elems.append(_mk_p(f"  Unidade de medida: {um}"))
            if qtd is not None:
                elems.append(_mk_p(f"  Quantidade: {qtd}"))
            elems.append(_mk_p(f"  Valor unitário: {_fmt_money(vu)}"))
            elems.append(_mk_p(f"  Valor total: {_fmt_money(vt)}"))
            if grau:
                elems.append(_mk_p(f"  Grau de prioridade: {grau}"))
            if data:
                elems.append(_mk_p(f"  Data pretendida: {data}"))
            if dep:
                elems.append(_mk_p(f"  Há dependência: {dep}"))
                if dep == "Sim" and depq:
                    elems.append(_mk_p(f"  Dependência (qual): {depq}"))
            if riscos:
                elems.append(_mk_p("  Riscos da não contratação:"))
                for line in _split_lines(riscos):
                    elems.append(_mk_p(f"    {line}"))
            if renov:
                elems.append(_mk_p(f"  Renovação de contrato: {renov}"))
            elems.append(ET.Element(_w("p")))  # linha em branco entre itens

    # 5) Total geral
    if itens:
        total_geral = context.get("total_geral")
        elems.append(_mk_p(f"Total geral da contratação (soma dos itens): {_fmt_money(total_geral)}"))

    # Inserção no corpo
    for off, el in enumerate(elems):
        body.insert(insert_idx + off, el)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


# -------------------------------------------------------------------
# Patch do cabeçalho (preserva imagens)
# -------------------------------------------------------------------
def _patch_header_xml_text(xml: str, numero: str, assunto: str, data_fmt: str) -> str:
    xml = xml.replace("00/00/0000", _xml_escape(data_fmt))
    # substitui sequências de zeros (>=4) que não estão coladas a '/'
    xml = re.sub(r"(?<!\d)0{4,}(?![\d/])", _xml_escape(numero), xml)
    # sentinelas opcionais
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
    """Copia o DOCX e aplica:
       - patch nos headers (número/assunto/data),
       - injeção de INTRO + seções do DFD v2 no corpo."""
    numero = str(context.get("numero") or "")
    assunto = str(context.get("assunto") or "Documento de Formalização de Demanda")
    data_fmt = _date_br(context.get("data") or datetime.utcnow().date().isoformat())

    # Ano do PCA pode vir como pca_ano (interno) ou pcaAno (externo)
    ano_pca = str(context.get("pca_ano") or context.get("pcaAno") or "").strip()

    # Introdução solicitada
    intro_lines = [
        "À Diretoria de Administração-Financeira",
        "",  # linha em branco
        f"Encaminha-se, o presente Documento de Formalização de Demanda - DFD, para fins de inclusão no Plano de Contratação Anual - PCA do exercício {ano_pca}, nos seguintes termos:",
    ]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        tmp_name = tmp.name

    try:
        # 1) Copia tudo da origem, mas segura document.xml para alterar uma única vez
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

            # 2) Escreve o corpo uma única vez (INTRO + seções DFD v2)
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
