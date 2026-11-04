# Piloto Groq por texto

## Estado
Conector preparado em 03/11/2026, sem ativacao no Aton e sem chamadas reais.
Modelo candidato fixo openai/gpt-oss-20b, endpoint HTTPS oficial fixo, sem redirects.
Biblioteca padrao apenas. Nenhuma ferramenta real e executada; nao conectado a voz.

## Configuracao local
GROQ_API_KEY e segredo local com repr desativado no Settings. Nunca enviar ao chat.
MULTI_LLM_ENABLED deve ser true e GROQ_FREE_PLAN_VERIFIED deve ser true somente apos
confirmar que a organizacao/chave utiliza o plano gratuito. Padroes false.
Nao alteramos .env. Atestacao nao verifica faturamento nem garante cobertura de quotas.
Documentacao oficial consultada em 03/11/2026:
https://console.groq.com/docs/rate-limits
https://console.groq.com/docs/openai

## Execucao opt-in, apos configurar
Na raiz do projeto, usar o Python da .venv:
python -m src.core.groq_pilot --case open_browser
python -m src.core.groq_pilot --case volume
python -m src.core.groq_pilot --case ambiguous
Cada execucao faz no maximo uma requisicao; modelo fixo, saida maxima512tokens,
timeout12s (limite por operacao de socket, nao prazo total rigido), resposta ate64KiB.
Nao aceita textos personalizados, historico, arquivos ou entrada de microfone.
Retorna proposta, correspondencia com resultado esperado e duracao, sem executar.
O tamanho de raciocinio do modelo pode esgotar512tokens; incomplete_response nao e sucesso.

## Protecoes e limites
Revalida a politica do roteador para os exemplos sinteticos internos. Dados pessoais
nao sao aceitos como entrada do piloto. Sem fallback, retries ou modelos pagos.
Erros sao sanitizados, sem corpo de erro/chave. HTTP429 impõe cooldown minimo60s,
respeitando Retry-After maior (segundos ou data). Outros pedidos no mesmo cliente
sao espacados3s. Cooldown e apenas por instancia/processo; nao substitui quota global.
As variaveis nao habilitam automaticamente o assistente nem criam conexao no boot.

## Validacao
python -m pytest tests/test_groq_pilot.py tests/test_model_router.py tests/test_config.py -q
34 testes aprovados com transporte simulado: bloqueios, payload sintetico, sem
execucao, respostas invalidas, segredo omitido, timeout/rede/auth,429 sem retry.
Nao houve comparacao real de velocidade/qualidade nem validacao da conta ou cobranca.
Proximo passo: configurar chave/plano localmente e rodar os tres exemplos; comparar
com Gemini antes de promover para pedidos reais. NVIDIA permanece fase posterior.
Retorno: manter flags false. Voz/Gemini nao foram alterados; nao requer reinicio.
