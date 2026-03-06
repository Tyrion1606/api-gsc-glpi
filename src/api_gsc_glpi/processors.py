# processors.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET

NS = {"ns": "urn:GSC_RF010_FornecedorExterno_V401_WS"}


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _clean_b64(s: str) -> str:
    return re.sub(r"\s+", "", s or "").strip()


def _find_text_any_namespace(node, tag_name: str) -> str:
    if node is None:
        return ""
    for el in node.iter():
        if _local(el.tag) == tag_name:
            return (el.text or "").strip()
    return ""


def _fingerprint_reiteracao(no_req: str, no_wo: str, descricao: str, extra: str = "") -> str:
    base = f"{no_req}|{no_wo}|{descricao}|{extra}".encode("utf-8", errors="ignore")
    return hashlib.sha1(base).hexdigest()


# ======================================================
# GETLIST ABERTURA
# ======================================================
def extrair_chamados_abertura(xml: str):
    root = ET.fromstring(xml)
    chamados = []

    for item in root.findall(".//ns:getListValues", NS):
        no_req = item.findtext(".//ns:no_req", "", NS).strip()
        no_wo = item.findtext(".//ns:no_wo", "", NS).strip()
        nomereq = item.findtext(".//ns:nomereq", "Chamado CAIXA", NS).strip()
        prioridade = item.findtext(".//ns:prioridade", "", NS).strip()

        solicitante_nome = item.findtext(".//ns:contatonome", "", NS).strip()
        solicitante_matricula = item.findtext(".//ns:idsolicitante", "", NS).strip()
        solicitante_email = item.findtext(".//ns:contatoemail", "", NS).strip()
        solicitante_tel = item.findtext(".//ns:contatotelefone", "", NS).strip()

        cod_unidade = item.findtext(".//ns:codigounidade", "", NS).strip()
        sigla_unidade = item.findtext(".//ns:siglaunidade", "", NS).strip()
        nome_unidade = item.findtext(".//ns:nomeunidade", "", NS).strip()
        cidade = item.findtext(".//ns:cidadeunidade", "", NS).strip()
        uf = item.findtext(".//ns:ufunidade", "", NS).strip()

        detalhes_node = item.find(".//ns:solicitacao/ns:detalhes", NS)
        detalhes = []
        if detalhes_node is not None:
            for d in list(detalhes_node):
                if d.text:
                    detalhes.append(d.text.strip())

        anexos = []
        anexos_node = item.find(".//ns:anexos", NS)
        if anexos_node is not None:
            nomes = {}
            conteudos = {}

            for ch in list(anexos_node):
                lname = _local(ch.tag)
                txt = (ch.text or "").strip()

                m_nome = re.match(r"^nome_arquivo(\d+)$", lname)
                if m_nome:
                    nomes[int(m_nome.group(1))] = txt
                    continue

                m_idx = re.search(r"(\d+)$", lname)
                if m_idx:
                    idx = int(m_idx.group(1))
                    b64 = _clean_b64(txt)
                    if len(b64) > 50:
                        conteudos[idx] = b64

            for idx in sorted(nomes.keys()):
                b64 = conteudos.get(idx)
                if b64:
                    anexos.append({"nome": nomes[idx], "base64": b64})

        titulo = f"{no_req} / {no_wo} - {nomereq}".strip(" -/")

        descricao = f"""Solicitante
Nome: {solicitante_nome}
Matricula: {solicitante_matricula}
E-mail: {solicitante_email}
Telefone: {solicitante_tel}

Unidade
Codigo da unidade: {cod_unidade}
Sigla: {sigla_unidade}
Nome: {nome_unidade}
Cidade/UF: {cidade} / {uf}

Prioridade
Prioridade: {prioridade}

Detalhes da Solicitacao
{chr(10).join(detalhes)}

Origem: CAIXA Economica Federal
Fornecedor: PETACORP
""".strip()

        chamados.append(
            {
                "no_req": no_req,
                "no_wo": no_wo,
                "titulo": titulo,
                "descricao": descricao,
                "anexos": anexos,
            }
        )

    return chamados


# ======================================================
# GETLIST REITERACAO
# ======================================================
def extrair_reiteracoes(xml: str):
    root = ET.fromstring(xml)
    lista = []

    for item in root.iter():
        if _local(item.tag) != "getListValues":
            continue

        no_req = _find_text_any_namespace(item, "no_req").strip()
        no_wo = _find_text_any_namespace(item, "no_wo").strip()
        descricao = _find_text_any_namespace(item, "descricao").strip()
        chamado_fornecedor = _find_text_any_namespace(item, "chamado_fornecedor").strip()

        idarquivo = _find_text_any_namespace(item, "idarquivo").strip()
        datahora = _find_text_any_namespace(item, "datahorageracaoarquivo").strip()
        extra_id = idarquivo or datahora or ""

        if not descricao:
            descricao = "Reiteracao recebida da CAIXA (sem descricao)."

        anexos = []
        anexos_node = None
        for el in item.iter():
            if _local(el.tag) == "anexos":
                anexos_node = el
                break

        if anexos_node is not None:
            nomes = {}
            conteudos = {}

            for ch in list(anexos_node):
                lname = _local(ch.tag)
                txt = (ch.text or "").strip()

                m_nome = re.match(r"^nome_arquivo(\d+)$", lname)
                if m_nome:
                    nomes[int(m_nome.group(1))] = txt
                    continue

                m_idx = re.search(r"(\d+)$", lname)
                if m_idx:
                    idx = int(m_idx.group(1))
                    b64 = _clean_b64(txt)
                    if len(b64) > 50:
                        conteudos[idx] = b64

            for idx in sorted(nomes.keys()):
                b64 = conteudos.get(idx)
                if b64:
                    anexos.append({"nome": nomes[idx], "base64": b64})

        reit_id = _fingerprint_reiteracao(no_req, no_wo, descricao, extra_id)

        lista.append(
            {
                "no_req": no_req,
                "no_wo": no_wo,
                "descricao": descricao,
                "chamado_fornecedor": chamado_fornecedor,
                "anexos": anexos,
                "reit_id": reit_id,
            }
        )

    return lista
