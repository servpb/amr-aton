"""Script de diagnóstico e teste em tempo real da API Groq LPU."""
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
from src.integrations.groq_client import (
    DEFAULT_GROQ_MODEL,
    FAST_GROQ_MODEL,
    get_groq_client,
)
from src.tools.groq_service import check_groq_connection, query_groq_llm


def main():
    print("=" * 60)
    print("[AMR / Aton] Diagnostico e Teste da API Groq LPU")
    print("=" * 60)

    key = settings.groq_api_key
    if not key:
        print("[ERRO] Nenhuma chave GROQ_API_KEY encontrada no arquivo .env.")
        print("Configure GROQ_API_KEY=gsk_... no .env antes de executar este teste.")
        return 1

    masked_key = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
    print(f"[INFO] Chave Groq detectada: {masked_key}")
    print(f"[INFO] Modelo padrao: {settings.groq_model or DEFAULT_GROQ_MODEL}")
    print(f"[INFO] Modelo ultra-rapido: {FAST_GROQ_MODEL}")
    print(f"[INFO] Timeout configurado: {settings.groq_timeout_seconds}s")
    print("-" * 60)

    # 1. Teste de Conexao (Ping)
    print("[INFO] 1. Testando conectividade e latencia com Groq API...")
    conn_result = check_groq_connection()
    if conn_result.get("status") == "connected":
        print(f"   [OK] Conexao estabelecida com sucesso!")
        print(f"   [OK] Latencia de resposta: {conn_result.get('elapsed_ms')} ms")
        print(f"   [OK] Modelo respondente: {conn_result.get('model')}")
    else:
        print(f"   [FALHA] Nao foi possivel conectar: {conn_result.get('message')}")
        if conn_result.get("code"):
            print(f"   Codigo HTTP: {conn_result.get('code')}")
        return 1

    print("-" * 60)

    # 2. Teste de Inferencia de Texto (Llama 3.3 70B)
    test_prompt = "Em uma frase curta e elegante, apresente o assistente Aton e destaque sua velocidade com Groq."
    print(f"[INFO] 2. Executando consulta de texto com {DEFAULT_GROQ_MODEL}...")
    print(f"   Pergunta: '{test_prompt}'")

    res = query_groq_llm(
        prompt=test_prompt,
        model=DEFAULT_GROQ_MODEL,
    )

    if res.get("status") == "success":
        print("\n[RESPOSTA DO ATON (via Groq)]:")
        print(f"\"{res.get('content')}\"")
        print(f"\n[METRICAS]:")
        print(f"   Tempo de processamento: {res.get('elapsed_ms')} ms")
        usage = res.get("usage", {})
        print(f"   Tokens: {usage.get('prompt_tokens', 0)} prompt + {usage.get('completion_tokens', 0)} resposta = {usage.get('total_tokens', 0)} total")
    else:
        print(f"   [ERRO] Falha na consulta: {res.get('message')}")
        return 1

    print("\n" + "=" * 60)
    print("[SUCESSO] Integracao Groq LPU operacional com sucesso no Aton!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
