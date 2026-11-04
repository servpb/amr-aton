# Gateway Multi-LLM - fase zero

## Estado em 03/11/2026
Base offline implementada; nao conectada ao assistente em execucao. Nenhuma chamada
externa, biblioteca nova, chave nova ou alteracao no .env. Processo nao reiniciado.
Gemini Live e despacho de ferramentas existentes preservados.

## Diagnostico e integracao futura
src/core/live_client.py concentra o streaming Gemini. O assistant.py recebe tool calls
e encaminha ao dispatch_tool em src/tools/__init__.py. O gateway ainda nao participa
desse caminho. A futura integracao deve ocorrer no trabalho assincrono, sem bloquear
o loop de audio. Pare durante reproducao continua pendente e separado deste modulo.

## Contrato implementado
src/core/router.py contem ModelRouter, RouteRequest, RouteDecision, FreeEndpoint,
DataClass e TaskKind. Usa somente a biblioteca padrao, sem payload, rede, logs de texto
ou execucao de ferramentas. Por padrao enabled=False e endpoints vazio.

Pedidos publicos ou sinteticos podem produzir uma decisao candidata se o gateway
for habilitado explicitamente e houver endpoint atestado como gratuito pelo operador.
COMMAND seleciona groq; PLANNING seleciona openrouter. Endpoints OpenRouter exigem
sufixo :free adicionalmente a atestacao. Google pago nao e selecionado.
VOICE retorna existing_voice_path_only, sem tentar substituir o Gemini Live.
Dados pessoais, confidenciais, desconhecidos, metadados invalidos, pedidos cancelados
e acoes ja enviadas sao bloqueados. Sem endpoint elegivel ou com provedor indisponivel,
retorna bloqueio: nao ha fallback para outro papel ou para servico pago.

## Limites importantes
MULTI_LLM_ENABLED=false foi acrescentado ao Settings e ao .env.example. Nesta fase,
o parametro e preparatorio: nao instancia nem ativa o roteador no runtime.
O modulo nao classifica conteudo automaticamente: metadados devem vir de politica
local confiavel, nunca de alegacao do modelo. Ainda falta implementar e validar a
origem desses metadados, incluindo resultados de ferramentas e historico derivado.
A atestacao free_tier_verified nao consulta faturamento e nao garante custo zero.
Conectores futuros deverao validar conta, modelo, quota e politica antes de transmitir.
A protecao action_already_sent impede selecionar nova rota, mas nao implementa
idempotencia nem reconciliacao de ferramentas: isso fica para a etapa de execucao.
Esta base nao protege retroativamente audio/dados que o Gemini existente ja recebe.

## Dependencias e teste
Sem dependencias novas. Executar com o Python do ambiente do Aton:
python -m pytest tests/test_model_router.py tests/test_config.py -q
Resultado da fase zero: 17 testes aprovados. Cobrem bloqueios de dados e metadados,
selecao por papel, quota/indisponibilidade sinalizada, ausencia de fallback pago,
voz separada, cancelamento, acao previamente enviada e padrao desativado.
Nao foram testados conectividade, quotas reais, cobranca ou voz real nesta fase.

## Proximas etapas
1. Groq: confirmar modelo e plano gratuito da conta; conector com timeout/limites;
   configurar atestacao confiavel e realizar piloto sintetico por texto, sem ferramentas reais.
2. NVIDIA via OpenRouter: confirmar endpoint gratuito e termos de dados; conector e
   comparacao de planejamento com conteudo publico/sintetico, sem historico privado.
3. Integracao opt-in com voz somente apos aprovacao dos pilotos e validacao do Pare.
Google pago permanece fora do escopo. Nao ha credenciais de novos provedores nesta etapa.

## Retorno
Nenhum fluxo ativo foi substituido. Manter modulo sem instanciacao e flag false.
Se necessario, remover apenas o modulo e testes novos e o campo preparatorio,
sem reverter alteracoes anteriores do usuario. Registros existentes permanecem.

## Atualizacao Groq
Conector e CLI sintetico preparados; consultar docs/groq_text_pilot.md. Sem ativacao, credencial nova ou chamadas reais. Validacao conjunta34testes simulados; conta/latencia reais pendentes.
