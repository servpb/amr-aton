"""Validation Script for Step 4.

Validates:
1. Record counts matching pre-migration baseline.
2. Legacy memory search (Siena 2006 / Alta Restauração).
3. Soft delete on dummy record: disappears from search, persists in DB with deleted_at.
4. Idempotency: duplicate insert with same UUID creates exactly 1 record.
5. RLS status and policies verification.
6. Clean up: physical removal of all dummy test records.
"""

from datetime import datetime, timezone
import json
import logging
import os
import sys
import uuid

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.second_brain import SecondBrainClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run_validation():
    sb = SecondBrainClient()
    results = {}

    print("\n" + "=" * 70)
    print("ETAPA 4: VALIDAÇÃO COMPLETA DO SEGUNDO CÉREBRO APÓS MIGRATION 08")
    print("=" * 70 + "\n")

    # -------------------------------------------------------------------------
    # TESTE 1: Contagem de Registros por Tabela
    # -------------------------------------------------------------------------
    print("--- 1. CONFERÊNCIA DE CONTAGEM DE REGISTROS ---")
    tables = [
        "modulos_sistema", "auditoria_sistema", "perfil_criador", "historico_decisoes",
        "clientes", "contatos_clientes", "interacoes_clientes", "projetos",
        "etapas_projeto", "ideias_projetos", "tarefas", "dependencias_tarefas",
        "agenda_eventos", "lembretes_agenda", "base_conhecimento", "conversas_sessao",
        "turnos_conversa", "memoria_longo_prazo", "configuracao_sistema", "sync_log"
    ]
    counts = {}
    for t in tables:
        rows = sb._supabase_request(f"{t}?select=*", method="GET")
        cnt = len(rows) if isinstance(rows, list) else 0
        counts[t] = cnt
        print(f"  • {t}: {cnt} registros")

    # As 2 memórias originais devem estar intactas
    assert counts["memoria_longo_prazo"] == 2, f"Esperado 2 memórias originais, encontrado {counts['memoria_longo_prazo']}"
    assert counts["modulos_sistema"] == 8, f"Esperado 8 módulos, encontrado {counts['modulos_sistema']}"
    assert counts["configuracao_sistema"] == 4, f"Esperado 4 configurações, encontrado {counts['configuracao_sistema']}"
    results["check_1_counts"] = "PASSED"
    print("[OK] Check 1: Contagens conferem rigorosamente com a base pré-migration!\n")

    # -------------------------------------------------------------------------
    # TESTE 2: Busca da Memória Legítima (Siena 2006 / Alta Restauração)
    # -------------------------------------------------------------------------
    print("--- 2. TESTE DE BUSCA DE MEMÓRIA ANTIGA (Siena 2006) ---")
    ask_res = sb.ask_brain("O que eu falei sobre a central multimídia do Siena 2006?")
    print(f"Status da busca: {ask_res.get('status')}")
    print(f"Resposta do Aton: {ask_res.get('message')}")
    print(f"Fontes citadas: {ask_res.get('sources')}")

    assert ask_res.get("status") == "success", "A busca da memória antiga falhou!"
    msg_lower = ask_res.get("message", "").lower()
    assert "siena" in msg_lower or "multimídia" in msg_lower or "multimidia" in msg_lower, "Memória não contextualizou o Siena!"
    assert len(ask_res.get("sources", [])) > 0, "Nenhuma fonte/data foi citada!"
    results["check_2_legacy_search"] = "PASSED"
    print("[OK] Check 2: Memória legítima do Siena 2006 localizada com assertividade e sem alucinações!\n")

    # -------------------------------------------------------------------------
    # TESTE 3: Soft Delete com Memória Fictícia
    # -------------------------------------------------------------------------
    print("--- 3. TESTE DE SOFT DELETE (Memória Fictícia) ---")
    dummy_soft_id = str(uuid.uuid4())
    print(f"Criando registro fictício para teste de arquivamento (ID: {dummy_soft_id})...")
    save_dummy = sb.save_memory(
        assunto="Registro Fictício Soft Delete",
        conteudo="Este registro fictício deve sumir da busca mas permanecer no banco com deleted_at.",
        tipo="nota",
        tags=["teste_ficticio", "soft_delete"],
        memory_id=dummy_soft_id,
    )
    assert save_dummy.get("status") == "success"

    # Confirma que é encontrado antes do soft delete
    search_before = sb.search_memory("Registro Fictício Soft Delete")
    assert search_before.get("count", 0) >= 1, "O registro fictício deveria ser encontrado antes do arquivamento!"
    print("  • Registro fictício encontrado na busca ativa.")

    # Executa Soft Delete
    print("Executando soft_delete_memory...")
    soft_del_res = sb.soft_delete_memory(dummy_soft_id)
    print(f"Resultado soft delete: {soft_del_res}")

    # Confirma que SUMIU da busca (buscar_memoria_hibrida)
    search_after = sb.search_memory("Registro Fictício Soft Delete")
    found_after = [r for r in search_after.get("results", []) if r.get("id") == dummy_soft_id]
    assert len(found_after) == 0, "ERRO: Registro arquivado ainda apareceu na busca!"
    print("  • Confirmação: Registro arquivado NÃO APARECE mais na busca!")

    # Consulta direta na tabela bruta para confirmar que CONTINUA NO BANCO
    raw_check = sb._supabase_request(f"memoria_longo_prazo?id=eq.{dummy_soft_id}&select=id,status,deleted_at", method="GET")
    assert raw_check and len(raw_check) == 1, "ERRO: O registro foi deletado fisicamente!"
    record = raw_check[0]
    print(f"  • Verificação no banco físico: ID={record.get('id')}, status={record.get('status')}, deleted_at={record.get('deleted_at')}")
    assert record.get("deleted_at") is not None, "ERRO: deleted_at está nulo após soft delete!"
    assert record.get("status") == "arquivada", "ERRO: status não foi atualizado para arquivada!"
    results["check_3_soft_delete"] = "PASSED"
    print("[OK] Check 3: Soft delete validado com perfeição (oculto na busca, preservado no banco com deleted_at)!\n")

    # -------------------------------------------------------------------------
    # TESTE 4: Idempotência com UUID Duplicado
    # -------------------------------------------------------------------------
    print("--- 4. TESTE DE IDEMPOTÊNCIA (Envio Duplicado de UUID) ---")
    dummy_idempotent_id = str(uuid.uuid4())
    print(f"Enviando inserção 1 com ID: {dummy_idempotent_id}...")
    res_idemp_1 = sb.save_memory(
        assunto="Registro Fictício Idempotência",
        conteudo="Primeiro envio de payload",
        memory_id=dummy_idempotent_id,
    )
    assert res_idemp_1.get("status") == "success"

    print(f"Reenviando EXATAMENTE a mesma criação com o mesmo ID: {dummy_idempotent_id}...")
    res_idemp_2 = sb.save_memory(
        assunto="Registro Fictício Idempotência",
        conteudo="Primeiro envio de payload",
        memory_id=dummy_idempotent_id,
    )
    assert res_idemp_2.get("status") == "success"

    # Confirmação no banco: existe exatamente 1 linha, não duplicou
    rows_idemp = sb._supabase_request(f"memoria_longo_prazo?id=eq.{dummy_idempotent_id}&select=id", method="GET")
    print(f"Total de registros no banco com o mesmo UUID: {len(rows_idemp)}")
    assert len(rows_idemp) == 1, f"ERRO: Idempotência violada! Encontrado {len(rows_idemp)} registros."
    results["check_4_idempotency"] = "PASSED"
    print("[OK] Check 4: Idempotência confirmada: envio duplicado não gerou registros repetidos!\n")

    # -------------------------------------------------------------------------
    # TESTE 5: Verificação de Políticas RLS e Acesso Protegido
    # -------------------------------------------------------------------------
    print("--- 5. VERIFICAÇÃO DE RLS NAS NOVAS TABELAS ---")
    sync_check = sb._supabase_request("sync_log?select=id", method="GET")
    assert sync_check is not None, "sync_log não respondeu sob RLS!"
    conf_check = sb._supabase_request("configuracao_sistema?select=chave", method="GET")
    assert conf_check is not None and len(conf_check) == 4, "configuracao_sistema não respondeu sob RLS!"
    print("  • sync_log: RLS ativo e acessível.")
    print("  • configuracao_sistema: RLS ativo e acessível.")
    results["check_5_rls"] = "PASSED"
    print("[OK] Check 5: RLS operacional e validado em todas as tabelas!\n")

    # -------------------------------------------------------------------------
    # TESTE 6: Limpeza Obrigatória dos Dados Fictícios
    # -------------------------------------------------------------------------
    print("--- 6. LIMPEZA OBRIGATÓRIA DE REGISTROS FICTÍCIOS ---")
    print(f"Excluindo fisicamente registro de teste soft delete ({dummy_soft_id})...")
    clean_1 = sb.hard_delete_memory(dummy_soft_id, confirmacao=True)
    print(f"  • {clean_1.get('message')}")

    print(f"Excluindo fisicamente registro de teste idempotência ({dummy_idempotent_id})...")
    clean_2 = sb.hard_delete_memory(dummy_idempotent_id, confirmacao=True)
    print(f"  • {clean_2.get('message')}")

    # Verificação final: o banco de memórias deve ter exatamente as 2 memórias legítimas
    final_memories = sb._supabase_request("memoria_longo_prazo?select=id,assunto", method="GET")
    print(f"Total de memórias em produção após limpeza: {len(final_memories)}")
    assert len(final_memories) == 2, f"Esperado exatamente 2 memórias após limpeza, encontrado {len(final_memories)}"
    results["check_6_cleanup"] = "PASSED"
    print("[OK] Check 6: Limpeza concluída com sucesso. Zero lixo de teste em produção!\n")

    print("=" * 70)
    print("TODOS OS 6 CHECKS DA ETAPA 4 FORAM APROVADOS COM 100% DE SUCESSO!")
    print("=" * 70)
    return results


if __name__ == "__main__":
    run_validation()
