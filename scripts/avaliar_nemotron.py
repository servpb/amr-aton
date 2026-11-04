"""Script de avaliacao, diagnostico e benchmark do modelo NVIDIA Nemotron (via OpenRouter)."""
import argparse
import sys
import time
from pathlib import Path

# Configura encoding UTF-8 seguro para stdout no Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Adiciona a raiz do projeto ao sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import settings
from src.integrations.openrouter_client import (
    DEFAULT_NEMOTRON_MODEL,
    get_openrouter_client,
)
from src.tools.nemotron_service import check_nemotron_connection, planejar_tarefa_complexa
from src.tools.groq_service import query_groq_llm


def main():
    parser = argparse.ArgumentParser(description="Avaliacao da NVIDIA Nemotron via OpenRouter")
    parser.add_argument("--compare", action="store_true", help="Compara planejamento com a Groq LPU")
    args = parser.parse_args()

    print("=" * 65)
    print("[AMR / Aton] Diagnostico e Avaliacao - NVIDIA Nemotron (OpenRouter)")
    print("=" * 65)

    client = get_openrouter_client()
    key = client._key
    if not key:
        print("[ERRO] Nenhuma chave NVIDIA_API_KEY ou OPENROUTER_API_KEY configurada no arquivo .env.")
        print("Para NVIDIA NIM Direto (recomendado, 1.000 chamadas gratis):")
        print("  1. Crie uma conta em https://build.nvidia.com/")
        print("  2. Adicione no .env: NVIDIA_API_KEY=nvapi-...")
        print("Ou para OpenRouter (comunitario com :free):")
        print("  Adicione no .env: OPENROUTER_API_KEY=sk-or-v1-...")
        return 1

    provider_name = "NVIDIA NIM Oficial (build.nvidia.com)" if client.provider == "nvidia_nim" else "OpenRouter (:free)"
    masked_key = key[:10] + "..." + key[-4:] if len(key) > 16 else "***"
    print(f"[INFO] Provedor ativo: {provider_name}")
    print(f"[INFO] Endpoint: {client.endpoint}")
    print(f"[INFO] Chave detectada: {masked_key}")
    print(f"[INFO] Modelo Nemotron: {client.default_model}")
    print(f"[INFO] Timeout configurado: {client.timeout}s")
    print("-" * 65)

    # 1. Teste de Conexao (Ping)
    print(f"[INFO] 1. Testando conectividade com {provider_name}...")
    conn = check_nemotron_connection()
    if conn.get("status") == "connected":
        print(f"   [OK] Conexao ativa e operacional!")
        print(f"   [OK] Latencia de resposta: {conn.get('elapsed_ms')} ms")
        print(f"   [OK] Modelo respondente: {conn.get('model')}")
        print(f"   [OK] Provedor: {conn.get('provider')}")
    else:
        print(f"   [FALHA] Nao foi possivel conectar: {conn.get('message')}")
        if conn.get("code"):
            print(f"   Codigo HTTP: {conn.get('code')}")
        return 1

    print("-" * 65)

    # 2. Teste de Planejamento de Tarefa Complexa Ficticia
    tarefa_ficticia = (
        "Projetar uma rotina de contingencia para o assistente Aton caso a conexao com a internet caia: "
        "detectar a perda de rede, comutar comandos para o modelo offline local (Vosk/scripts locais), "
        "notificar o usuario por voz local e restabelecer a conexao automaticamente quando a rede voltar."
    )
    restricoes = "Utilizar exclusivamente bibliotecas nativas e scripts locais do Windows sem ferramentas pagas."

    print(f"[INFO] 2. Executando Planejamento Complexo com NVIDIA Nemotron...")
    print(f"   Objetivo: {tarefa_ficticia[:80]}...")

    start_plan = time.monotonic()
    res = planejar_tarefa_complexa(
        objetivo=tarefa_ficticia,
        restricoes=restricoes,
    )
    duration_nemotron = round((time.monotonic() - start_plan) * 1000)

    if res.get("status") == "success":
        print("\n" + "=" * 30 + " PLANO GERADO PELA NEMOTRON " + "=" * 30)
        print(res.get("plano"))
        print("=" * 65)
        usage = res.get("usage", {})
        print(f"[METRICAS NEMOTRON]:")
        print(f"   Tempo total: {res.get('elapsed_ms', duration_nemotron)} ms")
        print(f"   Tokens: {usage.get('prompt_tokens', 0)} prompt + {usage.get('completion_tokens', 0)} resposta = {usage.get('total_tokens', 0)} total")
    else:
        print(f"   [ERRO] Falha no planejamento: {res.get('message')}")
        return 1

    # 3. Comparativo Opcional com Groq LPU
    if args.compare:
        print("\n" + "-" * 65)
        print("[INFO] 3. Executando mesma tarefa na Groq LPU para comparacao...")
        start_groq = time.monotonic()
        prompt_groq = (
            f"Como modulo de planejamento, crie um plano estruturado para:\n{tarefa_ficticia}\nRestricoes: {restricoes}"
        )
        res_groq = query_groq_llm(prompt=prompt_groq)
        duration_groq = round((time.monotonic() - start_groq) * 1000)

        if res_groq.get("status") == "success":
            print("\n" + "=" * 30 + " RESPOSTA DA GROQ LPU " + "=" * 30)
            print(res_groq.get("content"))
            print("=" * 65)
            usage_g = res_groq.get("usage", {})
            print(f"[METRICAS COMPARATIVAS]:")
            print(f"   Groq LPU:     {res_groq.get('elapsed_ms', duration_groq)} ms (Tokens: {usage_g.get('total_tokens', 0)})")
            print(f"   Nemotron 70B: {res.get('elapsed_ms', duration_nemotron)} ms (Tokens: {usage.get('total_tokens', 0)})")

    print("\n" + "=" * 65)
    print("[SUCESSO] Avaliacao da NVIDIA Nemotron concluida com exito no Aton!")
    print("=" * 65)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

