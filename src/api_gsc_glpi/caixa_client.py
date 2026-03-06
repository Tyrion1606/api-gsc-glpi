# caixa_client.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional, List, Dict

import requests

from config import (
    CAIXA_ENDPOINT,
    CAIXA_USER,
    CAIXA_PASSWORD,
    CAIXA_TOKEN,
    CAIXA_QUALIFICATION,
    CAIXA_TIMEOUT_SECONDS,
    CAIXA_ID_FORNECEDOR,
    CAIXA_NOME_FORNECEDOR,
)

from utils import limpar_texto_xml

MAX_RETRIES = 3
BACKOFF_SECONDS = [5, 15, 45]
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)


def bool_tf(v: bool) -> str:
    return "true" if v else "false"


SOAP_ACTION = {
    "GetList_Abertura": "urn:GSC_RF010_FornecedorExterno_V401_WS/GetList_Abertura",
    "GetList_Reiteracao": "urn:GSC_RF010_FornecedorExterno_V401_WS/GetList_Reiteracao",
    "SetAceiteRecusa": "urn:GSC_RF010_FornecedorExterno_V401_WS/SetAceiteRecusa",
    "SetAtualizacao": "urn:GSC_RF010_FornecedorExterno_V401_WS/SetAtualizacao",
}

STATUS_FORNECEDOR = {
    "CONCLUIDO": "5",
}


class CaixaSoapFault(Exception):
    def __init__(self, http_status: int, fault_code: str, fault_string: str):
        self.http_status = http_status
        self.fault_code = fault_code
        self.fault_string = fault_string
        super().__init__(f"HTTP {http_status} - CAIXA rejeitou: {fault_code} - {fault_string}")


class CaixaFinalError(Exception):
    """Erro final (sem retry): ex. ERROR (10000) chamado cancelado/finalizado na CAIXA."""


def _extract_fault(resp_text: str) -> Optional[tuple[str, str]]:
    try:
        root = ET.fromstring(resp_text)
    except Exception:
        return None

    fault = root.find(".//{*}Fault")
    if fault is None:
        return None

    fc_el = fault.find(".//faultcode")
    fs_el = fault.find(".//faultstring")

    fault_code = (fc_el.text or "").strip() if fc_el is not None else ""
    fault_string = (fs_el.text or "").strip() if fs_el is not None else ""

    if not fault_code and not fault_string:
        return None

    return fault_code, fault_string


def _is_final_fault(fault_string: str) -> bool:
    s = (fault_string or "").lower()

    if "error (10000)" in s:
        return True
    if "chamado esta cancelado" in s:
        return True
    if "nao permite atualizacao" in s and "cancel" in s:
        return True
    if "finalizado" in s and "nao permite" in s:
        return True

    return False


def _save_req_resp(metodo: str, req_xml: str, resp_text: str, http_status: int) -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    req_path = os.path.join(LOG_DIR, f"{ts}_{metodo}_{http_status}_{uid}_req.xml")
    resp_path = os.path.join(LOG_DIR, f"{ts}_{metodo}_{http_status}_{uid}_resp.xml")

    with open(req_path, "w", encoding="utf-8") as f:
        f.write(req_xml)

    with open(resp_path, "w", encoding="utf-8") as f:
        f.write(resp_text)


def _log_retorno(soap_response_xml: str) -> None:
    try:
        root = ET.fromstring(soap_response_xml)
    except Exception:
        print("WARN: retorno CAIXA nao e XML valido (nao foi possivel parsear).")
        return

    def _find_text(tag_name: str) -> Optional[str]:
        el = root.find(f".//{{*}}{tag_name}")
        if el is not None and el.text:
            return el.text.strip()
        return None

    processado = _find_text("processado")
    if processado is not None:
        if processado.lower() == "true":
            print("Retorno CAIXA OK (processado=true).")
        else:
            print(f"Retorno CAIXA NAO OK (processado={processado}).")

    motivos = []
    for motivo in root.findall(".//{*}motivo"):
        codigo_el = motivo.find(".//{*}codigo")
        desc_el = motivo.find(".//{*}descricao")
        codigo = (codigo_el.text or "").strip() if codigo_el is not None and codigo_el.text else ""
        desc = (desc_el.text or "").strip() if desc_el is not None and desc_el.text else ""
        if codigo or desc:
            motivos.append((codigo, desc))

    for codigo, desc in motivos:
        print(f"CAIXA motivo: codigo={codigo} descricao={desc}")


def _post_soap(xml: str, metodo: str) -> str:
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": SOAP_ACTION.get(metodo, metodo),
    }

    last_exc: Optional[Exception] = None

    for tentativa in range(MAX_RETRIES):
        try:
            r = requests.post(
                CAIXA_ENDPOINT,
                data=xml.encode("utf-8"),
                headers=headers,
                timeout=CAIXA_TIMEOUT_SECONDS,
                verify=False,
            )

            resp_text = r.text or ""
            _save_req_resp(metodo, xml, resp_text, r.status_code)

            if r.status_code >= 400:
                fault = _extract_fault(resp_text)
                if fault:
                    fault_code, fault_string = fault
                    if _is_final_fault(fault_string):
                        raise CaixaFinalError(
                            f"HTTP {r.status_code} - CAIXA final: {fault_code} - {fault_string}"
                        )
                    raise CaixaSoapFault(r.status_code, fault_code, fault_string)
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)

            fault = _extract_fault(resp_text)
            if fault:
                fault_code, fault_string = fault
                if _is_final_fault(fault_string):
                    raise CaixaFinalError(
                        f"HTTP {r.status_code} - CAIXA final: {fault_code} - {fault_string}"
                    )
                raise CaixaSoapFault(r.status_code, fault_code, fault_string)

            return resp_text

        except CaixaFinalError:
            raise
        except Exception as e:
            last_exc = e
            print(f"CAIXA {metodo} erro ({tentativa+1}/{MAX_RETRIES}).")

            if tentativa < MAX_RETRIES - 1:
                time.sleep(BACKOFF_SECONDS[tentativa])
            else:
                break

    if last_exc:
        raise last_exc
    raise Exception("Erro inesperado no _post_soap")


def buscar_aberturas(capturado: bool = False) -> str:
    xml = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:urn="urn:GSC_RF010_FornecedorExterno_V401_WS">
      <soapenv:Header>
        <urn:AuthenticationInfo>
          <urn:userName>{CAIXA_USER}</urn:userName>
          <urn:password>{CAIXA_PASSWORD}</urn:password>
        </urn:AuthenticationInfo>
      </soapenv:Header>
      <soapenv:Body>
        <urn:GetList_Abertura>
          <urn:Qualification>{CAIXA_QUALIFICATION}</urn:Qualification>
          <urn:Token>{CAIXA_TOKEN}</urn:Token>
          <urn:Capturado>{bool_tf(capturado)}</urn:Capturado>
          <urn:startRecord>0</urn:startRecord>
          <urn:maxLimit>100</urn:maxLimit>
        </urn:GetList_Abertura>
      </soapenv:Body>
    </soapenv:Envelope>"""

    print("Enviando XML para CAIXA (GetList_Abertura)...")
    return _post_soap(xml, "GetList_Abertura")


def buscar_reiteracoes(capturado: bool = False) -> str:
    xml = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:urn="urn:GSC_RF010_FornecedorExterno_V401_WS">
      <soapenv:Header>
        <urn:AuthenticationInfo>
          <urn:userName>{CAIXA_USER}</urn:userName>
          <urn:password>{CAIXA_PASSWORD}</urn:password>
        </urn:AuthenticationInfo>
      </soapenv:Header>
      <soapenv:Body>
        <urn:GetList_Reiteracao>
          <urn:Qualification>{CAIXA_QUALIFICATION}</urn:Qualification>
          <urn:Token>{CAIXA_TOKEN}</urn:Token>
          <urn:Capturado>{bool_tf(capturado)}</urn:Capturado>
        </urn:GetList_Reiteracao>
      </soapenv:Body>
    </soapenv:Envelope>"""

    print("Enviando XML para CAIXA (GetList_Reiteracao)...")
    return _post_soap(xml, "GetList_Reiteracao")


def set_aceite_recusa(
    no_req: str,
    no_wo: str,
    aceite: bool,
    chamado_fornecedor: str,
    descricao: str = "Aceite automatico via GLPI",
) -> str:
    """
    CORREÇÃO:
    - adiciona info_fornecedor (obrigatório)
    - usa campos compatíveis com o WSDL (tipo_retorno etc.)
    Obs.: aqui tratamos "aceite" como tipo_retorno=4 (padrão de aceite/recusa).
          Se a CAIXA exigir valor diferente, troque AQUI sem mexer no resto.
    """
    agora = datetime.now().strftime("%Y%m%d%H%M%S")
    id_arquivo = uuid.uuid4().hex.upper()

    # convenção: 4 = aceite/recusa (ajuste se necessário)
    tipo_retorno = "4"
    sufixo = "ACEITE" if aceite else "RECUSA"
    descricao_envio = f"{descricao} ({sufixo})"

    xml = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:urn="urn:GSC_RF010_FornecedorExterno_V401_WS">
      <soapenv:Header>
        <urn:AuthenticationInfo>
          <urn:userName>{CAIXA_USER}</urn:userName>
          <urn:password>{CAIXA_PASSWORD}</urn:password>
        </urn:AuthenticationInfo>
      </soapenv:Header>
      <soapenv:Body>
        <urn:SetAceiteRecusa>
          <urn:arquivoxml>

            <urn:info_arquivo>
              <urn:tipoarquivo>2</urn:tipoarquivo>
              <urn:idarquivo>{id_arquivo}</urn:idarquivo>
              <urn:datahorageracaoarquivo>{agora}</urn:datahorageracaoarquivo>
              <urn:comunicacao>2</urn:comunicacao>
            </urn:info_arquivo>

            <urn:info_fornecedor>
              <urn:idfornecedor>{CAIXA_ID_FORNECEDOR}</urn:idfornecedor>
              <urn:nomefornecedor>{CAIXA_NOME_FORNECEDOR}</urn:nomefornecedor>
            </urn:info_fornecedor>

            <urn:retorno>
              <urn:codigodobanco>104</urn:codigodobanco>
              <urn:chamado_caixa>
                <urn:no_req>{limpar_texto_xml(no_req)}</urn:no_req>
                <urn:no_wo>{limpar_texto_xml(no_wo)}</urn:no_wo>
                <urn:no_inc></urn:no_inc>
                <urn:no_crq></urn:no_crq>
              </urn:chamado_caixa>

              <urn:tipo_retorno>{tipo_retorno}</urn:tipo_retorno>
              <urn:chamado_fornecedor>{limpar_texto_xml(chamado_fornecedor)}</urn:chamado_fornecedor>
              <urn:previsaoatendimento></urn:previsaoatendimento>
              <urn:responsavelatendimento></urn:responsavelatendimento>
              <urn:descricao>{limpar_texto_xml(descricao_envio)}</urn:descricao>
            </urn:retorno>

          </urn:arquivoxml>
        </urn:SetAceiteRecusa>
      </soapenv:Body>
    </soapenv:Envelope>"""

    print(f"Enviando XML para CAIXA (SetAceiteRecusa) aceite={aceite} idarquivo={id_arquivo}...")
    resp = _post_soap(xml, "SetAceiteRecusa")
    _log_retorno(resp)
    return resp


def _build_anexos_xml(anexos: Optional[List[Dict[str, str]]]) -> str:
    if not anexos:
        return ""

    anexos = [a for a in anexos if (a.get("nome") and a.get("base64"))]
    if not anexos:
        return ""

    anexos = anexos[:3]

    parts = ["<urn:anexos>"]
    for i, ax in enumerate(anexos, start=1):
        nome = limpar_texto_xml(ax.get("nome", f"arquivo_{i}.bin"))
        b64 = (ax.get("base64") or "").strip()
        b64 = "".join(b64.split())
        parts.append(f"<urn:nome_arquivo{i}>{nome}</urn:nome_arquivo{i}>")
        parts.append(f"<urn:anexo{i}>{b64}</urn:anexo{i}>")
    parts.append("</urn:anexos>")
    return "\n".join(parts)


def enviar_atualizacao(
    no_req: str,
    no_wo: str,
    descricao: str,
    chamado_fornecedor: str,
    status_fornecedor: str | None = None,
    tipo_retorno: str | None = None,
    atendimento_inicio: str | None = None,
    atendimento_fim: str | None = None,
    anexos: Optional[List[Dict[str, str]]] = None,
) -> str:
    descricao = limpar_texto_xml(descricao)
    agora = datetime.now().strftime("%Y%m%d%H%M%S")
    id_arquivo = uuid.uuid4().hex.upper()
    tipoarquivo = "3"

    status_fornecedor_xml = ""
    status_fornecedor_norm = None

    if status_fornecedor:
        status_fornecedor_norm = STATUS_FORNECEDOR.get(status_fornecedor, status_fornecedor)
        status_fornecedor_xml = (
            f"<urn:status_fornecedor>{limpar_texto_xml(status_fornecedor_norm)}</urn:status_fornecedor>"
        )

    if tipo_retorno is None:
        tipo_retorno = "5" if status_fornecedor_norm == "5" else "1"

    if tipo_retorno == "5":
        atendimento_inicio = atendimento_inicio or agora
        atendimento_fim = atendimento_fim or agora
    else:
        atendimento_inicio = atendimento_inicio or ""
        atendimento_fim = atendimento_fim or ""

    anexos_xml = _build_anexos_xml(anexos)

    xml = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:urn="urn:GSC_RF010_FornecedorExterno_V401_WS">
      <soapenv:Header>
        <urn:AuthenticationInfo>
          <urn:userName>{CAIXA_USER}</urn:userName>
          <urn:password>{CAIXA_PASSWORD}</urn:password>
        </urn:AuthenticationInfo>
      </soapenv:Header>
      <soapenv:Body>
        <urn:SetAtualizacao>
          <urn:arquivoxml>

            <urn:info_arquivo>
              <urn:tipoarquivo>{tipoarquivo}</urn:tipoarquivo>
              <urn:idarquivo>{id_arquivo}</urn:idarquivo>
              <urn:datahorageracaoarquivo>{agora}</urn:datahorageracaoarquivo>
              <urn:comunicacao>2</urn:comunicacao>
            </urn:info_arquivo>

            <urn:info_fornecedor>
              <urn:idfornecedor>{CAIXA_ID_FORNECEDOR}</urn:idfornecedor>
              <urn:nomefornecedor>{CAIXA_NOME_FORNECEDOR}</urn:nomefornecedor>
            </urn:info_fornecedor>

            <urn:retorno>
              <urn:codigodobanco>104</urn:codigodobanco>
              <urn:chamado_caixa>
                <urn:no_req>{limpar_texto_xml(no_req)}</urn:no_req>
                <urn:no_wo>{limpar_texto_xml(no_wo)}</urn:no_wo>
                <urn:no_inc></urn:no_inc>
                <urn:no_crq></urn:no_crq>
              </urn:chamado_caixa>

              <urn:tipo_retorno>{limpar_texto_xml(tipo_retorno)}</urn:tipo_retorno>
              <urn:descricao>{descricao}</urn:descricao>
              <urn:chamado_fornecedor>{limpar_texto_xml(chamado_fornecedor)}</urn:chamado_fornecedor>
              {status_fornecedor_xml}
            </urn:retorno>

            <urn:agendamento>
              <urn:data></urn:data>
              <urn:contato></urn:contato>
              <urn:telefone></urn:telefone>
            </urn:agendamento>

            <urn:atendimento>
              <urn:data_inicio>{limpar_texto_xml(atendimento_inicio)}</urn:data_inicio>
              <urn:data_fim>{limpar_texto_xml(atendimento_fim)}</urn:data_fim>
              <urn:rat></urn:rat>
              <urn:tecnicoresponsavel></urn:tecnicoresponsavel>
              <urn:numero_serie></urn:numero_serie>
              <urn:previsaoatendimento></urn:previsaoatendimento>
            </urn:atendimento>

            <urn:servicos></urn:servicos>

            {anexos_xml}

          </urn:arquivoxml>
        </urn:SetAtualizacao>
      </soapenv:Body>
    </soapenv:Envelope>"""

    print(
        f"Enviando XML para CAIXA (SetAtualizacao) idarquivo={id_arquivo} "
        f"tipo_retorno={tipo_retorno} status={status_fornecedor_norm or ''} anexos={len(anexos or [])}..."
    )
    resp = _post_soap(xml, "SetAtualizacao")
    _log_retorno(resp)
    return resp
