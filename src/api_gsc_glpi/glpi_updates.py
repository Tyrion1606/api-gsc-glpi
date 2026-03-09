# glpi_updates.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
from typing import Dict, Any, Optional

STATE_FILE = "state.json"

def _default_state() -> Dict[str, Any]:
    return {
        "mapeamentos": {},
        "reiteracoes_processadas": [],
        "followups_enviados": {},
        "status_enviados": {},
        "req_wo_bloqueados": {},
        "documentos_enviados": {},
    }

def _load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        print("Arquivo [state.json] não encontrado!!!")
        return _default_state()

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            base = _default_state()
            if isinstance(data, dict):
                base.update(data)
            return base
    except Exception:
        return _default_state()


def _save_state(state: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _key_req_wo(no_req: str, no_wo: str) -> str:
    return f"{no_req}|{no_wo}"


def _key_reit(no_req: str, no_wo: str, reit_id: str) -> str:
    return f"{no_req}|{no_wo}|{reit_id}"


# ============================
# MAPEAMENTO REQ/WO
# ============================

def registrar_mapeamento_req_wo(no_req: str, no_wo: str, ticket_id: int) -> None:
    state = _load_state()
    state["mapeamentos"][_key_req_wo(no_req, no_wo)] = int(ticket_id)
    _save_state(state)


def buscar_ticket_por_req_wo(no_req: str, no_wo: str) -> Optional[int]:
    state = _load_state()
    v = state["mapeamentos"].get(_key_req_wo(no_req, no_wo))
    return int(v) if v is not None else None


def buscar_req_wo_por_ticket(ticket_id: int) -> Optional[Dict[str, str]]:
    state = _load_state()
    for k, v in state["mapeamentos"].items():
        try:
            if int(v) == int(ticket_id):
                no_req, no_wo = k.split("|", 1)
                return {"no_req": no_req, "no_wo": no_wo}
        except Exception:
            continue
    return None


# ============================
# BLOQUEIO DEFINITIVO REQ/WO
# ============================

def bloquear_req_wo(no_req: str, no_wo: str, ticket_id: int, motivo: str) -> None:
    state = _load_state()
    state["req_wo_bloqueados"][_key_req_wo(no_req, no_wo)] = {
        "ticket_id": int(ticket_id),
        "motivo": str(motivo),
    }
    _save_state(state)


def req_wo_esta_bloqueado(no_req: str, no_wo: str) -> bool:
    state = _load_state()
    return _key_req_wo(no_req, no_wo) in state.get("req_wo_bloqueados", {})


# ============================
# REITERACOES (POR ID)
# ============================

def reiteracao_ja_processada(no_req: str, no_wo: str, reit_id: str) -> bool:
    state = _load_state()
    old_key = _key_req_wo(no_req, no_wo)
    new_key = _key_reit(no_req, no_wo, reit_id)
    lst = state.get("reiteracoes_processadas", [])
    return (old_key in lst) or (new_key in lst)


def marcar_reiteracao_processada(no_req: str, no_wo: str, reit_id: str) -> None:
    state = _load_state()
    key = _key_reit(no_req, no_wo, reit_id)
    state.setdefault("reiteracoes_processadas", [])
    if key not in state["reiteracoes_processadas"]:
        state["reiteracoes_processadas"].append(key)
    _save_state(state)


# ============================
# FOLLOWUPS
# ============================

def followup_ja_enviado(ticket_id: int, followup_id: int) -> bool:
    state = _load_state()
    enviados = state["followups_enviados"].get(str(ticket_id), [])
    return int(followup_id) in [int(x) for x in enviados if str(x).isdigit()]


def marcar_followup_enviado(ticket_id: int, followup_id: int) -> None:
    state = _load_state()
    tid = str(ticket_id)
    state["followups_enviados"].setdefault(tid, [])
    if int(followup_id) not in state["followups_enviados"][tid]:
        state["followups_enviados"][tid].append(int(followup_id))
    _save_state(state)


# ============================
# STATUS
# ============================

def status_ja_enviado(ticket_id: int, status: str) -> bool:
    state = _load_state()
    return state["status_enviados"].get(str(ticket_id)) == status


def marcar_status_enviado(ticket_id: int, status: str) -> None:
    state = _load_state()
    state["status_enviados"][str(ticket_id)] = status
    _save_state(state)


# ============================
# DOCUMENTOS
# ============================

def documento_ja_enviado(ticket_id: int, doc_id: int) -> bool:
    state = _load_state()
    enviados = state["documentos_enviados"].get(str(ticket_id), [])
    return int(doc_id) in [int(x) for x in enviados if str(x).isdigit()]


def marcar_documento_enviado(ticket_id: int, doc_id: int) -> None:
    state = _load_state()
    tid = str(ticket_id)
    state["documentos_enviados"].setdefault(tid, [])
    if int(doc_id) not in state["documentos_enviados"][tid]:
        state["documentos_enviados"][tid].append(int(doc_id))
    _save_state(state)
