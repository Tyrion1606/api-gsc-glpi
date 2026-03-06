# glpi_client.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import json
import re
from io import BytesIO
from typing import Any, Dict, Optional, List

import requests

from config import (
    GLPI_API_URL,
    GLPI_APP_TOKEN,
    GLPI_USER_TOKEN,
    GLPI_ENTITIES_ID,
    GLPI_VERIFY_SSL,
)

SESSION_TOKEN: Optional[str] = None


def _headers() -> Dict[str, str]:
    return {
        "App-Token": GLPI_APP_TOKEN,
        "Authorization": f"user_token {GLPI_USER_TOKEN}",
        "Content-Type": "application/json",
    }


def init_session() -> str:
    global SESSION_TOKEN
    url = f"{GLPI_API_URL}/initSession"
    r = requests.get(url, headers=_headers(), verify=GLPI_VERIFY_SSL)
    r.raise_for_status()
    SESSION_TOKEN = r.json().get("session_token")
    if not SESSION_TOKEN:
        raise Exception("Nao foi possivel obter session_token do GLPI")
    return SESSION_TOKEN


def kill_session() -> None:
    global SESSION_TOKEN
    if not SESSION_TOKEN:
        return
    try:
        requests.get(
            f"{GLPI_API_URL}/killSession",
            headers={**_headers(), "Session-Token": SESSION_TOKEN},
            verify=GLPI_VERIFY_SSL,
        )
    except Exception:
        pass
    SESSION_TOKEN = None


def _auth_headers() -> Dict[str, str]:
    if not SESSION_TOKEN:
        init_session()
    h = _headers()
    h["Session-Token"] = SESSION_TOKEN
    return h


def criar_ticket(titulo: str, descricao: str) -> int:
    r = requests.post(
        f"{GLPI_API_URL}/Ticket",
        headers=_auth_headers(),
        verify=GLPI_VERIFY_SSL,
        json={
            "input": {
                "name": titulo,
                "content": descricao,
                "entities_id": GLPI_ENTITIES_ID,
            }
        },
    )
    r.raise_for_status()
    return int(r.json()["id"])


def buscar_tickets_caixa_por_categoria(itilcategories_id: int) -> List[Dict[str, Any]]:
    r = requests.get(
        f"{GLPI_API_URL}/search/Ticket",
        headers=_auth_headers(),
        verify=GLPI_VERIFY_SSL,
        params={
            "criteria[0][field]": 7,  # itilcategories_id
            "criteria[0][searchtype]": "equals",
            "criteria[0][value]": str(itilcategories_id),
            "forcedisplay[0]": "2",   # id
            "forcedisplay[1]": "12",  # status
            "range": "0-200",
        },
    )
    r.raise_for_status()
    return r.json().get("data", [])


def buscar_status_ticket(ticket_id: int) -> Optional[str]:
    r = requests.get(
        f"{GLPI_API_URL}/Ticket/{ticket_id}",
        headers=_auth_headers(),
        verify=GLPI_VERIFY_SSL,
    )
    if r.status_code != 200:
        return None

    status_id = r.json().get("status")
    mapa = {
        1: "Novo",
        2: "Em atendimento",
        3: "Planejado",
        4: "Pendente",
        5: "Solucionado",
        6: "Fechado",
    }
    return mapa.get(status_id)


def atualizar_status_ticket(ticket_id: int, status_id: int) -> None:
    r = requests.put(
        f"{GLPI_API_URL}/Ticket/{ticket_id}",
        headers=_auth_headers(),
        verify=GLPI_VERIFY_SSL,
        json={"input": {"id": ticket_id, "status": int(status_id)}},
    )
    # não quebra o loop por causa disso
    if r.status_code not in (200, 201):
        return


def adicionar_followup_publico(ticket_id: int, texto: str) -> int:
    r = requests.post(
        f"{GLPI_API_URL}/Ticket/{ticket_id}/ITILFollowup",
        headers=_auth_headers(),
        verify=GLPI_VERIFY_SSL,
        json={
            "input": {
                "itemtype": "Ticket",
                "items_id": ticket_id,
                "content": texto,
                "is_private": 0,
            }
        },
    )
    r.raise_for_status()
    return int(r.json()["id"])


def listar_followups(ticket_id: int) -> List[Dict[str, Any]]:
    r = requests.get(
        f"{GLPI_API_URL}/Ticket/{ticket_id}/ITILFollowup",
        headers=_auth_headers(),
        verify=GLPI_VERIFY_SSL,
    )
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else data.get("data", [])


def _clean_b64(s: str) -> str:
    return re.sub(r"\s+", "", s or "").strip()


def adicionar_followup_com_anexo(
    ticket_id: int,
    texto: str,
    filename: str,
    base64_file: str,
) -> int:
    """
    Followup + upload no mesmo request (arquivo fica no corpo/historico do chamado)

    Correção aplicada:
    - Índices coerentes entre "files" e "uploadManifest"
    - Base64 limpo (remove quebras/espacos)
    """
    if not SESSION_TOKEN:
        init_session()

    b64 = _clean_b64(base64_file)
    file_bytes = base64.b64decode(b64)

    # índice 0
    files = {
        "_filename[0]": (filename, BytesIO(file_bytes)),
    }

    data = {
        "input": json.dumps(
            {
                "itemtype": "Ticket",
                "items_id": ticket_id,
                "content": texto,
                "is_private": 0,
            }
        ),
        "uploadManifest": json.dumps(
            {
                "files": {
                    "0": {"name": filename}
                }
            }
        ),
    }

    r = requests.post(
        f"{GLPI_API_URL}/Ticket/{ticket_id}/ITILFollowup",
        headers={
            "App-Token": GLPI_APP_TOKEN,
            "Authorization": f"user_token {GLPI_USER_TOKEN}",
            "Session-Token": SESSION_TOKEN,
        },
        files=files,
        data=data,
        verify=GLPI_VERIFY_SSL,
    )
    r.raise_for_status()
    return int(r.json()["id"])


def listar_documentos_ticket(ticket_id: int) -> List[Dict[str, Any]]:
    r = requests.get(
        f"{GLPI_API_URL}/Ticket/{ticket_id}/Document_Item",
        headers=_auth_headers(),
        verify=GLPI_VERIFY_SSL,
    )
    if r.status_code != 200:
        return []
    data = r.json()
    return data if isinstance(data, list) else data.get("data", [])


def baixar_documento_base64(doc_id: int) -> str:
    """
    Baixa o binário do documento e retorna Base64.
    Tenta:
      1) /Document/{id}?alt=media
      2) /Document/{id}/download
    """
    h = _auth_headers()

    r = requests.get(
        f"{GLPI_API_URL}/Document/{doc_id}",
        headers=h,
        params={"alt": "media"},
        verify=GLPI_VERIFY_SSL,
        stream=True,
    )

    content_type = (r.headers.get("Content-Type") or "").lower()
    if r.status_code == 200 and "application/json" not in content_type:
        return base64.b64encode(r.content).decode("ascii")

    r2 = requests.get(
        f"{GLPI_API_URL}/Document/{doc_id}/download",
        headers=h,
        verify=GLPI_VERIFY_SSL,
        stream=True,
    )
    if r2.status_code == 200:
        return base64.b64encode(r2.content).decode("ascii")

    raise Exception(f"Falha ao baixar Document/{doc_id} (status {r.status_code}/{r2.status_code})")
