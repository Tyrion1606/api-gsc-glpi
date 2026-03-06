# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import time

from api_gsc_glpi import caixa_client
from api_gsc_glpi import glpi_client
from api_gsc_glpi import glpi_updates
from api_gsc_glpi import processors
from api_gsc_glpi.anexos import extrair_anexos_do_xml

POLL_INTERVAL_SECONDS = 30
ENABLE_GLPI_ANEXOS_PARA_CAIXA = os.getenv("ENABLE_GLPI_ANEXOS_PARA_CAIXA", "0").strip() in ("1", "true", "True")


def _detectar_finalizacao_caixa(texto: str) -> str | None:
    s = (texto or "").lower()
    if "cancel" in s or "cancelado" in s or "cancelada" in s:
        return "CANCELADO"
    if "conclu" in s or "finaliz" in s or "encerr" in s or "fechad" in s:
        return "CONCLUIDO"
    return None


def executar_loop() -> None:
    glpi_client.init_session()
    print("Integracao CAIXA <-> GLPI iniciada")

    while True:
        try:
            # 1) ABERTURAS (CAIXA -> GLPI)
            print("Buscando aberturas na CAIXA...")
            xml_aberturas = caixa_client.buscar_aberturas(capturado=False)
            aberturas = processors.extrair_chamados_abertura(xml_aberturas)
            print(f"Aberturas retornadas pela CAIXA: {len(aberturas)}")

            for ch in aberturas:
                ticket_id = glpi_client.criar_ticket(ch["titulo"], ch["descricao"])
                print(f"Ticket criado no GLPI: {ticket_id}")

                glpi_updates.registrar_mapeamento_req_wo(ch["no_req"], ch["no_wo"], ticket_id)

                # Aceite automatico
                try:
                    caixa_client.set_aceite_recusa(
                        no_req=ch["no_req"],
                        no_wo=ch["no_wo"],
                        aceite=True,
                        chamado_fornecedor=f"GLPI-{ticket_id}",
                        descricao="Aceite automatico via GLPI",
                    )
                    print(f"Aceite automatico enviado para REQ={ch['no_req']} WO={ch['no_wo']}")
                except Exception as e:
                    print(f"WARN: Falha ao enviar aceite automatico REQ={ch['no_req']} WO={ch['no_wo']}: {e}")

                # Anexos da abertura (CAIXA -> GLPI)
                for ax in ch.get("anexos", []):
                    b64 = (ax.get("base64") or "").strip()
                    nome = (ax.get("nome") or "anexo.bin").strip()
                    if not b64:
                        continue
                    glpi_client.adicionar_followup_com_anexo(
                        ticket_id=ticket_id,
                        texto="Arquivo anexado automaticamente (origem: CAIXA)",
                        filename=nome,
                        base64_file=b64,
                    )

            # 2) REITERACOES (CAIXA -> GLPI)  <<< CORRIGIDO AQUI
            print("Buscando reiteracoes na CAIXA...")
            xml_reit = caixa_client.buscar_reiteracoes(capturado=False)  # <<< TEM QUE SER FALSE
            reiteracoes = processors.extrair_reiteracoes(xml_reit)
            print(f"Reiteracoes retornadas pela CAIXA: {len(reiteracoes)}")

            for r in reiteracoes:
                req = (r.get("no_req") or "").strip()
                wo = (r.get("no_wo") or "").strip()
                desc = (r.get("descricao") or "").strip()
                chamado_fornecedor = (r.get("chamado_fornecedor") or "").strip()
                reit_id = (r.get("reit_id") or "").strip()

                if not req or not wo:
                    continue
                if not reit_id:
                    # fallback seguro (n�o deveria acontecer porque processors gera)
                    reit_id = f"fallback_{hash(desc)}"

                # se ja foi aplicada, pula (AGORA POR ID)
                if glpi_updates.reiteracao_ja_processada(req, wo, reit_id):
                    continue

                # tenta achar ticket
                ticket_id = None
                if chamado_fornecedor.startswith("GLPI-"):
                    try:
                        ticket_id = int(chamado_fornecedor.replace("GLPI-", "").strip())
                    except Exception:
                        ticket_id = None

                if not ticket_id:
                    ticket_id = glpi_updates.buscar_ticket_por_req_wo(req, wo)

                if not ticket_id:
                    print(f"WARN: Ticket nao encontrado no GLPI para a reiteracao REQ={req} WO={wo}.")
                    glpi_updates.marcar_reiteracao_processada(req, wo, reit_id)
                    continue

                # followup publico com a nota da CAIXA (AGORA VAI ENTRAR TODAS)
                glpi_client.adicionar_followup_publico(
                    ticket_id,
                    f"Reiteracao recebida da CAIXA\n\n{desc or '(sem descricao)'}",
                )

                # anexos da reiteracao (CAIXA -> GLPI)
                anexos = extrair_anexos_do_xml(r) or []
                for ax in anexos:
                    b64 = (ax.get("base64") or "").strip()
                    fn = (ax.get("filename") or "anexo.bin").strip()
                    if not b64:
                        continue
                    glpi_client.adicionar_followup_com_anexo(
                        ticket_id=ticket_id,
                        texto="Arquivo recebido da CAIXA",
                        filename=fn,
                        base64_file=b64,
                    )

                # se indicar cancelado/concluido, bloqueia
                final = _detectar_finalizacao_caixa(desc)
                if final:
                    glpi_updates.bloquear_req_wo(req, wo, ticket_id, f"CAIXA informou {final}: {desc[:200]}")
                    try:
                        if final == "CONCLUIDO":
                            glpi_client.atualizar_status_ticket(ticket_id, 5)
                        else:
                            glpi_client.atualizar_status_ticket(ticket_id, 6)
                    except Exception:
                        pass

                    glpi_client.adicionar_followup_publico(
                        ticket_id,
                        f"Integracao: REQ/WO bloqueada porque a CAIXA informou {final}. A partir de agora nao enviaremos mais atualizacoes para a CAIXA.",
                    )

                glpi_updates.marcar_reiteracao_processada(req, wo, reit_id)
                print(f"Reiteracao aplicada no GLPI: REQ={req} WO={wo} id={reit_id}")

            # 3) GLPI -> CAIXA (FOLLOWUPS + STATUS + ANEXOS)
            print("Buscando tickets CAIXA no GLPI para enviar atualizacoes...")
            tickets = glpi_client.buscar_tickets_caixa_por_categoria(7)
            print(f"{len(tickets)} ticket(s) encontrados")

            for t in tickets:
                ticket_id = int(t["2"])

                mapeamento = glpi_updates.buscar_req_wo_por_ticket(ticket_id)
                if not mapeamento:
                    continue

                no_req = mapeamento["no_req"]
                no_wo = mapeamento["no_wo"]

                if glpi_updates.req_wo_esta_bloqueado(no_req, no_wo):
                    continue

                followups = glpi_client.listar_followups(ticket_id)

                for f in followups:
                    try:
                        fid = int(f["id"])
                    except Exception:
                        continue

                    if glpi_updates.followup_ja_enviado(ticket_id, fid):
                        continue

                    texto = (f.get("content") or "").strip()
                    if not texto:
                        glpi_updates.marcar_followup_enviado(ticket_id, fid)
                        continue

                    print(f"Enviando followup {fid} do ticket {ticket_id} para CAIXA")

                    try:
                        caixa_client.enviar_atualizacao(
                            no_req=no_req,
                            no_wo=no_wo,
                            descricao=texto,
                            chamado_fornecedor=f"GLPI-{ticket_id}",
                            tipo_retorno="1",
                        )
                        glpi_updates.marcar_followup_enviado(ticket_id, fid)

                    except caixa_client.CaixaFinalError as e:
                        print(f"FINAL: {e}")
                        glpi_updates.marcar_followup_enviado(ticket_id, fid)
                        glpi_updates.bloquear_req_wo(no_req, no_wo, ticket_id, str(e))
                        try:
                            glpi_client.atualizar_status_ticket(ticket_id, 5)
                        except Exception:
                            pass
                        glpi_client.adicionar_followup_publico(
                            ticket_id,
                            "Integracao: CAIXA retornou erro FINAL. REQ/WO bloqueada; nao enviaremos mais atualizacoes.",
                        )
                        break

                    except Exception as e:
                        print(f"Erro enviando followup {fid} do ticket {ticket_id}: {e}")

                if glpi_updates.req_wo_esta_bloqueado(no_req, no_wo):
                    continue

                if ENABLE_GLPI_ANEXOS_PARA_CAIXA:
                    docs_link = glpi_client.listar_documentos_ticket(ticket_id)

                    for link in docs_link:
                        doc_id = link.get("documents_id") or link.get("id") or link.get("document_id")
                        try:
                            doc_id = int(doc_id)
                        except Exception:
                            continue

                        if glpi_updates.documento_ja_enviado(ticket_id, doc_id):
                            continue

                        filename = f"documento_{doc_id}"

                        try:
                            b64 = glpi_client.baixar_documento_base64(doc_id)

                            caixa_client.enviar_atualizacao(
                                no_req=no_req,
                                no_wo=no_wo,
                                descricao=f"Anexo enviado pelo GLPI: {filename}",
                                chamado_fornecedor=f"GLPI-{ticket_id}",
                                tipo_retorno="1",
                                anexos=[{"nome": filename, "base64": b64}],
                            )
                            glpi_updates.marcar_documento_enviado(ticket_id, doc_id)

                        except caixa_client.CaixaFinalError as e:
                            print(f"FINAL: {e}")
                            glpi_updates.marcar_documento_enviado(ticket_id, doc_id)
                            glpi_updates.bloquear_req_wo(no_req, no_wo, ticket_id, str(e))
                            try:
                                glpi_client.atualizar_status_ticket(ticket_id, 5)
                            except Exception:
                                pass
                            glpi_client.adicionar_followup_publico(
                                ticket_id,
                                "Integracao: CAIXA retornou erro FINAL ao enviar anexo. REQ/WO bloqueada.",
                            )
                            break
                        except Exception as e:
                            print(f"Erro enviando anexo Document/{doc_id} do ticket {ticket_id}: {e}")

                if glpi_updates.req_wo_esta_bloqueado(no_req, no_wo):
                    continue

                status_glpi = glpi_client.buscar_status_ticket(ticket_id)
                if not status_glpi:
                    continue

                mapa_status = {
                    "solucionado": "CONCLUIDO",
                    "fechado": "CONCLUIDO",
                    "cancelado": "CANCELADO",
                    "pendente": "PENDENTE",
                }

                status_caixa = mapa_status.get(status_glpi.lower())
                if not status_caixa:
                    continue

                if glpi_updates.status_ja_enviado(ticket_id, status_caixa):
                    continue

                print(f"Enviando status {status_caixa} do ticket {ticket_id} para CAIXA")

                if status_caixa == "CONCLUIDO":
                    tipo_retorno = "5"
                    status_fornecedor = "CONCLUIDO"
                else:
                    tipo_retorno = "1"
                    status_fornecedor = None

                try:
                    caixa_client.enviar_atualizacao(
                        no_req=no_req,
                        no_wo=no_wo,
                        descricao=f"Status alterado para {status_caixa} no GLPI",
                        chamado_fornecedor=f"GLPI-{ticket_id}",
                        status_fornecedor=status_fornecedor,
                        tipo_retorno=tipo_retorno,
                    )
                    glpi_updates.marcar_status_enviado(ticket_id, status_caixa)

                except caixa_client.CaixaFinalError as e:
                    print(f"FINAL: {e}")
                    glpi_updates.marcar_status_enviado(ticket_id, status_caixa)
                    glpi_updates.bloquear_req_wo(no_req, no_wo, ticket_id, str(e))
                    try:
                        glpi_client.atualizar_status_ticket(ticket_id, 5)
                    except Exception:
                        pass
                    glpi_client.adicionar_followup_publico(
                        ticket_id,
                        "Integracao: CAIXA retornou erro FINAL no envio de status. REQ/WO bloqueada.",
                    )

                except Exception as e:
                    print(f"Erro enviando status do ticket {ticket_id}: {e}")

            print("Ciclo finalizado. Aguardando...")
            time.sleep(POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("Interrompido pelo usuario.")
            break
        except Exception as e:
            print(f"Erro no loop: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)

    glpi_client.kill_session()
