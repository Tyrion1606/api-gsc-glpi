# utils.py
from __future__ import annotations

import re


def limpar_texto_xml(texto: str) -> str:
    """
    - Remove caracteres de controle proibidos em XML 1.0 (exceto tab, CR, LF)
    - Faz escapes básicos (& < > " ')
    """
    if texto is None:
        return ""

    texto = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", str(texto))

    texto = (
        texto.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )

    return texto.strip()


def limpar_html_glpi(texto: str) -> str:
    """
    Remove tags HTML que o GLPI costuma gravar em followups (<p>, <br>, etc).
    """
    if not texto:
        return ""

    s = str(texto)

    # troca <br> por \n antes de remover tags, para não "colar" linhas
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)

    # remove tags
    s = re.sub(r"<[^>]+>", "", s)

    # normaliza espaços/linhas
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()
