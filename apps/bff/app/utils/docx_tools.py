# app/utils/docx_tools.py
from __future__ import annotations

"""
Ferramentas para renderização e pós-processamento de arquivos DOCX.

Propósito
---------
- Detectar e listar placeholders Jinja2 em modelos `.docx`.
- Renderizar documentos via `docxtpl` quando houver placeholders.
- Renderizar documentos preservando timbre/cabeçalho quando não houver placeholders (fallback).
- Montar trechos XML (parágrafos, runs, tabelas) diretamente em WordprocessingML.
- Converter DOCX para PDF via LibreOffice (quando disponível).

Segurança / Efeitos colaterais
------------------------------
- Leitura e escrita em disco (modelos/arquivos temporários/saída).
- Execução de processo externo (`soffice`) quando conversão para PDF é solicitada.
- Manipulação direta do pacote DOCX (ZIP) e de seus XMLs internos.

Observações
-----------
- **Lógica original preservada integralmente**; apenas:
  - docstrings adicionadas/expandida em pt-BR;
  - comentários removidos/condensados em docstrings de funções e módulo;
  - referência de topo incluída.
"""

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

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_XML = "http://www.w3.org/XML/1998/namespace"
ET.register_namespace("w", NS_W)


def _w(tag: str) -> str:
    """
    Qualifica uma tag com o namespace WordprocessingML.

    Parâmetros
    ----------
    tag : str
        Nome local da tag (ex.: 'p', 'r', 't').

    Retorna
    -------
    str
        Tag qualificada no formato `{namespace}tag`.
    """
    return f"{{{NS_W}}}{tag}"


def get_docx_placeholders(template_path: str) -> List[str]:
    """
    Extrai variáveis Jinja presentes em um arquivo DOCX.

    Estratégia
    ----------
    1) Tenta utilizar `docxtpl` (`get_undeclared_template_variables`).
    2) Fallback: varre XMLs internos removendo tags e buscando padrões `{{ var }}`.

    Parâmetros
    ----------
    template_path : str
        Caminho do arquivo `.docx` de modelo.

    Retorna
    -------
    list[str]
        Lista ordenada de nomes de variáveis detectadas (pode conter sentinela `_block`).
    """
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


def _date_br(v) -> str:
    """
    Formata data para pt-BR no padrão DD/MM/AAAA.

    Parâmetros
    ----------
    v : datetime | str | Any
        Objeto datetime ou string ISO a ser formatado.

    Retorna
    -------
    str
        Data formatada; valor original como string em caso de falha.
    """
    try:
        if isinstance(v, datetime):
            dt = v
        else:
            dt = datetime.fromisoformat(str(v))
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str(v) if v is not None else ""


def _xml_escape(s: str) -> str:
    """
    Escapa caracteres especiais para uso seguro em XML.

    Parâmetros
    ----------
    s : str
        Texto de entrada.

    Retorna
    -------
    str
        Texto com `&`, `<` e `>` escapados.
    """
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_money(v) -> str:
    """
    Formata valores monetários no padrão pt-BR: `R$ 1.234,56`.

    Parâmetros
    ----------
    v : Any
        Valor numérico (int/float/str).

    Retorna
    -------
    str
        Representação formatada com separador de milhar e 2 casas decimais.
    """
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
    """
    Divide um texto em linhas preservando ordem.

    Parâmetros
    ----------
    text : str
        Texto de entrada (pode ser None ou vazio).

    Retorna
    -------
    list[str]
        Linhas resultantes; retorna `['']` quando vazio.
    """
    if not text:
        return [""]
    return str(text).splitlines() or [""]


def _num(v) -> float:
    """
    Converte para float com fallback em 0.0.

    Parâmetros
    ----------
    v : Any
        Valor a ser convertido.

    Retorna
    -------
    float
        Valor convertido ou 0.0 quando inválido.
    """
    try:
        return float(v)
    except Exception:
        return 0.0


def _mk_run(text: str, bold: bool = False, italic: bool = False) -> ET.Element:
    """
    Cria um elemento `<w:r>` com `<w:t>` e formatação opcional.

    Parâmetros
    ----------
    text : str
        Conteúdo textual do run.
    bold : bool
        Aplica negrito.
    italic : bool
        Aplica itálico.

    Retorna
    -------
    xml.etree.ElementTree.Element
        Elemento `<w:r>` pronto para inserção.
    """
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
    indent_level: int = 0,
    left_indent_level: int | None = None,
    first_line_indent_level: int = 0,
) -> ET.Element:
    """
    Cria `<w:p>` com suporte a múltiplos runs e indentação.

    Parâmetros
    ----------
    runs : list[tuple[str,bool,bool]] | None
        Lista de runs (texto, bold, italic). Se None, usa `text/bold/italic`.
    text : str | None
        Texto simples quando `runs` não for fornecido.
    bold : bool
        Negrito para `text` simples.
    italic : bool
        Itálico para `text` simples.
    indent_level : int
        Alias legado de `left_indent_level`.
    left_indent_level : int | None
        Recuo à esquerda em níveis (cada nível ≈ 360 twips).
    first_line_indent_level : int
        Recuo da primeira linha (cada nível ≈ 360 twips).

    Retorna
    -------
    Element
        Parágrafo `<w:p>` com formatação e runs inseridos.
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
            ind.set(_w("firstLine"), str(360 * first_line_indent_level))

    if runs is None:
        runs = [(text or "", bold, italic)]
    for s, b, i in runs:
        p.append(_mk_run(s, bold=b, italic=i))
    return p


def _mk_label_value(label: str, value: str, indent_level: int = 0) -> ET.Element:
    """
    Cria um parágrafo no formato 'Label: valor' (label em negrito).

    Parâmetros
    ----------
    label : str
        Rótulo exibido em negrito.
    value : str
        Valor exibido após o rótulo.
    indent_level : int
        Recuo à esquerda em níveis (≈ 360 twips por nível).

    Retorna
    -------
    Element
        Parágrafo `<w:p>` correspondente.
    """
    return _mk_p(
        runs=[(f"{label}: ", True, False), (value or "", False, False)],
        left_indent_level=indent_level
    )


def _tc(text: str, *, bold: bool = False, align: str | None = None, grid_span: int | None = None) -> ET.Element:
    """
    Cria uma célula `<w:tc>` com um único parágrafo e texto.

    Parâmetros
    ----------
    text : str
        Conteúdo textual da célula.
    bold : bool
        Negrito no conteúdo.
    align : {'left','center','right',None}
        Alinhamento horizontal do parágrafo.
    grid_span : int | None
        Mescla horizontal (gridSpan) para abarcar múltiplas colunas.

    Retorna
    -------
    Element
        Célula de tabela `<w:tc>`.
    """
    tc = ET.Element(_w("tc"))
    tcpr = ET.SubElement(tc, _w("tcPr"))
    if grid_span and grid_span > 1:
        gs = ET.SubElement(tcpr, _w("gridSpan"))
        gs.set(_w("val"), str(grid_span))
    p = ET.SubElement(tc, _w("p"))
    if align in ("left", "center", "right"):
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
    """
    Cria uma linha de tabela `<w:tr>` a partir de células.

    Parâmetros
    ----------
    cells : list[Element]
        Células `<w:tc>` da linha.

    Retorna
    -------
    Element
        Linha `<w:tr>`.
    """
    tr = ET.Element(_w("tr"))
    for c in cells:
        tr.append(c)
    return tr


def _tbl(rows: list[list[ET.Element]], *, borders: bool = True, col_widths: list[int] | None = None) -> ET.Element:
    """
    Cria uma tabela `<w:tbl>` simples.

    Parâmetros
    ----------
    rows : list[list[Element]]
        Linhas (cada uma com células `<w:tc>`).
    borders : bool
        Aplica bordas padrão.
    col_widths : list[int] | None
        Larguras das colunas em twips (opcional).

    Retorna
    -------
    Element
        Tabela `<w:tbl>` completa.
    """
    tbl = ET.Element(_w("tbl"))
    tblpr = ET.SubElement(tbl, _w("tblPr"))
    tblw = ET.SubElement(tblpr, _w("tblW"))
    tblw.set(_w("type"), "auto")
    tblw.set(_w("w"), "0")
    if borders:
        tb = ET.SubElement(tblpr, _w("tblBorders"))
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
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


_PRIORITY_OPTIONS = [
    "Alto, quando a impossibilidade de contratação provoca interrupção de processo crítico ou estratégico.",
    "Médio, quando a impossibilidade de contratação provoca atraso de processo crítico ou estratégico.",
    "Baixo, quando a impossibilidade de contratação provoca interrupção ou atraso de processo não crítico.",
    "Muito baixo, quando a continuidade do processo é possível mediante o emprego de uma solução de contorno.",
]


def _priority_block(selected: str | None) -> List[ET.Element]:
    """
    Renderiza lista de prioridade com marcação "(X)" na opção selecionada.

    Parâmetros
    ----------
    selected : str | None
        Opção exatamente igual a uma das alternativas de `_PRIORITY_OPTIONS`.

    Retorna
    -------
    list[Element]
        Sequência de parágrafos representando o bloco.
    """
    out: List[ET.Element] = []
    out.append(_mk_p(text="Grau de prioridade da aquisição/contratação:", bold=True))
    out.append(ET.Element(_w("p")))
    sel_norm = (selected or "").strip()
    for opt in _PRIORITY_OPTIONS:
        mark = "( X ) " if opt == sel_norm else "(   ) "
        out.append(_mk_p(text=mark + opt, left_indent_level=0, first_line_indent_level=1))
    return out


def _quantidade_valor_sentence(qtd: Any, um: str, vu: Any, vt: Any) -> str:
    """
    Frase padrão para quantidade e valores.

    Exemplo
    -------
    "A quantidade é de 10 (dez) unidades no valor de R$ 2.000,00 cada, totalizando R$ 20.000,00."

    Observações
    -----------
    - Não escreve números por extenso (apenas valores formatados).
    - Unidade é anexada somente se fornecida.

    Retorna
    -------
    str
        Frase composta.
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


def _append_body_sections_xml_et(
    document_xml_bytes: bytes,
    context: Dict[str, Any],
    intro_lines: List[str] | None = None,
) -> bytes:
    """
    Insere seções padronizadas no corpo do documento (`word/document.xml`).

    Estrutura
    ---------
    - Introdução
    - Diretoria demandante
    - Alinhamento com o PE (multilinha)
    - Justificativa da necessidade (GERAL)
    - Objeto (multilinha)
    - Tabela 1: Itens (Item | Descrição | Vínculo | Renovação)
    - Valores estimados + Tabela 2 (Item | Quantidade | Unidade | VU | VT + Total)
    - Prazos envolvidos
    - Consequências da não aquisição
    - Grau de prioridade
    - ASSINATURA

    Retorna
    -------
    bytes
        XML do documento atualizado (UTF-8, com declaração XML).

    Observações
    -----------
    Preserva `sectPr`; insere os elementos antes dele.
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

    if intro_lines:
        for line in intro_lines:
            elems.append(_mk_p(text=line))
        if intro_lines and intro_lines[-1].strip():
            elems.append(ET.Element(_w("p")))

    dire = str(context.get("diretoria_demandante") or "").strip()
    if dire:
        elems.append(_mk_label_value("Diretoria demandante", dire))
        elems.append(ET.Element(_w("p")))

    alin = str(context.get("alinhamento_pe") or "").strip()
    if alin:
        elems.append(_mk_p(text="Alinhamento com o Planejamento Estratégico", bold=True))
        elems.append(ET.Element(_w("p")))
        for line in _split_lines(alin):
            elems.append(_mk_p(text=line, left_indent_level=0, first_line_indent_level=1))
        elems.append(ET.Element(_w("p")))

    just_geral = str(context.get("justificativa_necessidade") or "").strip()
    if just_geral:
        elems.append(_mk_p(text="Justificativa da necessidade", bold=True))
        elems.append(ET.Element(_w("p")))
        for line in _split_lines(just_geral):
            elems.append(_mk_p(text=line, left_indent_level=0, first_line_indent_level=1))
        elems.append(ET.Element(_w("p")))

    obj = str(context.get("objeto") or "").strip()
    if obj:
        elems.append(_mk_p(text="Objeto", bold=True))
        elems.append(ET.Element(_w("p")))
        for line in _split_lines(obj):
            elems.append(_mk_p(text=line, left_indent_level=0, first_line_indent_level=1))
        elems.append(ET.Element(_w("p")))

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

        elems.append(_mk_p(text="Valores estimados:", bold=True))
        elems.append(ET.Element(_w("p")))
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
            um = (it.get("unidadeMedida") or "").strip()
            vu = it.get("valorUnitario")
            vt = it.get("valorTotal")
            try:
                total_geral += float(vt or 0.0)
            except Exception:
                pass
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
        v_rows.append([
            _tc("Total", bold=True, grid_span=4, align="left"),
            _tc(_fmt_money(total_geral), bold=True, align="right"),
        ])
        elems.append(_tbl(v_rows, borders=True))
        elems.append(ET.Element(_w("p")))

    prazos = str(context.get("prazos_envolvidos") or context.get("prazosEnvolvidos") or "").strip()
    consq = str(context.get("consequencia_nao_aquisicao") or context.get("consequenciaNaoAquisicao") or "").strip()
    grau = str(context.get("grau_prioridade") or context.get("grauPrioridade") or "").strip()

    if prazos or consq or grau:
        if prazos:
            elems.append(_mk_p(text="Prazos envolvidos (Data – mês e ano – em que o objeto precisa estar adquirido ou contratado)", bold=True))
            elems.append(ET.Element(_w("p")))
            elems.append(_mk_p(text=f"Até {prazos}.", left_indent_level=0, first_line_indent_level=1))
            elems.append(ET.Element(_w("p")))
        if consq:
            elems.append(_mk_p(text="Consequências da não aquisição/contratação do objeto", bold=True))
            elems.append(ET.Element(_w("p")))
            for line in _split_lines(consq):
                elems.append(_mk_p(text=line, left_indent_level=0, first_line_indent_level=1))
            elems.append(ET.Element(_w("p")))
        if grau:
            elems.extend(_priority_block(grau))
            elems.append(ET.Element(_w("p")))

    elems.append(_mk_p(text="ASSINATURA", bold=True))
    elems.append(ET.Element(_w("p")))

    for off, el in enumerate(elems):
        body.insert(insert_idx + off, el)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _patch_header_xml_text(xml: str, numero: str, assunto: str, data_fmt: str) -> str:
    """
    Atualiza placeholders no cabeçalho: data, número e assunto.

    Parâmetros
    ----------
    xml : str
        Conteúdo XML do header.
    numero : str
        Número do documento.
    assunto : str
        Assunto do documento.
    data_fmt : str
        Data já formatada (ex.: DD/MM/AAAA).

    Retorna
    -------
    str
        XML resultante com placeholders substituídos.
    """
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


def _render_fixed_timbre(template_path: str, context: Dict[str, Any], out_path: str) -> None:
    """
    Renderiza preservando timbre e cabeçalho quando não há placeholders Jinja.

    Passos
    ------
    - Copia o DOCX para um temporário.
    - Aplica patch nos headers (número/assunto/data).
    - Injeta seções do corpo conforme contexto (via ElementTree).

    Efeitos
    -------
    - Gera arquivo final em `out_path`.
    - Remove temporários ao final (best-effort).
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
                    continue

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


def render_docx_template(template_path: str, context: Dict[str, Any], out_path: str) -> None:
    """
    Renderiza um documento DOCX a partir de um template.

    Roteamento
    ----------
    - Se houver placeholders Jinja: usa `docxtpl` com filtro `date_br`.
    - Caso contrário: aplica pipeline de timbre fixo.

    Exceções
    --------
    FileNotFoundError
        Quando `template_path` não existir.
    """
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


def _soffice_bin() -> str | None:
    """
    Localiza o binário do LibreOffice/soffice no PATH.

    Retorna
    -------
    str | None
        Caminho do executável quando encontrado; caso contrário, None.
    """
    return shutil.which("soffice") or shutil.which("libreoffice")


def has_soffice() -> bool:
    """
    Indica se o LibreOffice está disponível para conversão.

    Retorna
    -------
    bool
        True quando o binário `soffice/libreoffice` está acessível.
    """
    return _soffice_bin() is not None


def convert_docx_to_pdf(docx_path: str, pdf_path: str) -> bool:
    """
    Converte um arquivo DOCX em PDF utilizando o LibreOffice em modo headless.

    Parâmetros
    ----------
    docx_path : str
        Caminho do arquivo DOCX de entrada.
    pdf_path : str
        Caminho de saída desejado para o PDF.

    Retorna
    -------
    bool
        True se o PDF foi gerado; False caso contrário (inclui ausência do LibreOffice).

    Observações
    -----------
    - A conversão roda no diretório do DOCX, com saída direcionada a `outdir` do PDF.
    - Em caso de erro de processo, registra log e retorna False.
    """
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
