# Escuta continua e Pare

Implementado em 05/11/2026 a pedido do usuario. CONTINUOUS_CONVERSATION_ENABLED
padrao true: apos despertar nao aplica timeout local de silencio ou teto de120s.
Em modo legado false, os limites locais nao encerram durante reproducao, turno do
servidor aberto ou ferramenta ativa. Nao remove limites de sessao/quota do provedor.

Pare local ou ferramenta stop_listening sem argumentos interrompe a reproducao,
reseta o reconhecedor e preserva captura e sessao. Supressao do restante do turno
segue mecanismo de interrupcao existente. Ordem explicita encerrar conversa/pare de
escutar usa end_conversation=true e retorna a escuta local por palavra-chave.
Encerrar a sessao nao encerra aplicativo, timers ou notificacoes.

Nao ha identificacao do locutor: TV e outras vozes podem interferir. AEC e reconhecimento
local ainda sao pilotos; reconhecer Pare durante fala sobreposta nao esta comprovado.
Nao grava audio nem ativa automaticamente AEC. Gemini recebe audio enquanto sessao
conectada e respeita quotas do provedor; desconexao retorna ao detector local atual.
Nao ha promessa de conexao infinita ou reconexao automatica sem palavra-chave.

Testes simulados:60 aprovados em continuous_voice,voice_reliability,aec_interruptions.
Validacao real: pedir historia longa (>2min), dizer Pare durante a fala, verificar
interrupcao, fazer nova pergunta sem Aton; testar aviso agendado durante escuta.
Nao confundir ausencia de resposta com fim de sessao: correlacionar logs VOICE_STOP,
VOICE_SESSION e desconexao. Ainda depende de carregar versao e testar hardware.

Ajuste apos teste real: nova fala transcrita libera supressao de turno interrompido antes de reproduzir resposta nova. Nao depende apenas de turn_complete/interrupted. 22 testes simulados aprovados; causalidade e retomada no hardware ainda pendentes. Marcador VOICE_RESUME sem texto da fala.

## Preferencia atual (substitui comportamento anterior)
Usuario autorizou Pare retornando a espera local. Handler e detector local encerram
a sessao sem bipe; processo, microfone local e trabalhadores de avisos permanecem.
Padrao continuous_conversation_enabled=false, mantendo protecao de timeout durante
reproducao/turno aberto/ferramentas. Nova conversa exige Aton. Sem identificacao de
locutor: TV que pronuncie palavra-chave pode ativar. Validacao real pendente.
