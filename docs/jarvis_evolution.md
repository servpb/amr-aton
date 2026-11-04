# Evolução do Aton — ordem aprovada

1. Voz confiável: em implementação; validação com voz real pendente.
2. Contexto de conversa: próxima etapa, após validar o ciclo de voz.
3. Execução de tarefas completas: planejar, executar, verificar e interromper com segurança.
4. Conhecimento do trabalho: relacionar clientes, projetos, arquivos e compromissos autorizados.
5. Iniciativa controlada: monitores opt-in com limites claros de ações e notificações.
6. Continuidade entre dispositivos: preservar contexto com autorização por dispositivo.

## Etapa 1 — melhorias implementadas
- Captura com fila limitada a 25 blocos; descarte de áudio com mais de 500ms desde o callback local.
- Contadores de entrada, processamento, tamanho de fila, idade e descartes a cada 10s sem transcrições ambientais.
- Variantes fonéticas ambíguas somente em resultado final exato; não se amplia o vocabulário.
- Respeito à taxa de amostragem configurada ao inicializar Vosk.
- Prontidão depende de callbacks reais do microfone, detector e carregamento.
- Limite absoluto padrão de conversa: 120s (`CONVERSATION_MAX_SECONDS`, 15 a 1800), independentemente do ruído e dos 12s de silêncio.
- Conexão limitada a 12s (`VOICE_CONNECT_TIMEOUT_SECONDS`); falha retorna ao repouso.
- Proteção contra abertura de segunda sessão já acordado.
- Diagnóstico de transcrições opt-in (`WAKE_DIAGNOSTICS`), somente nos primeiros 120s da instância; padrão desligado. Não remove registros históricos antigos.

O limite de conversa encerra a voz, mas não interrompe à força uma ferramenta em execução.
O limite reduz a exposição a som ambiente; não identifica locutor nem distingue usuário de TV. Falas da televisão ainda podem ser interpretadas durante uma sessão ativa. Biometria vocal não deve servir sozinha como autorização de ações sensíveis.
Idade de áudio mede a fila local após o callback, não a latência interna do driver ou microfone.

## Critérios de validação real
Após reiniciar somente o Aton mediante autorização: 5 chamadas em silêncio, medir acertos/tempo até retorno; repetir Pare → repouso → chamada; amostra com TV e falas negativas; verificar fim da sessão em até 120s mesmo com ruído. Conferir estado de erro sem áudio. Não afirmar voz confiável concluída antes desse teste.
Sem gravação de voz nem rede paga adicionada. Os testes simulados não provam sensibilidade ou rejeição real de televisão.

## Verificação da etapa 1
63 testes aprovados no conjunto de confiabilidade de voz, boot, configuração, lembretes, catálogo e bandeja. Outros 27 testes de wake word, boot, configuração e lembretes também passaram, com sobreposição entre conjuntos. Métrica T2_components_loaded_ms mede somente carga secundária; o registro VOICE_READINESS ready depende de captura e detector saudáveis. Processo do Aton não reiniciado; validação de hardware pendente.

## Teste de voz sob demanda
Menu da bandeja: Testar ativação por voz (60 segundos). Clique explícito autoriza uma janela de transcrição local de até 60s sem arquivo de áudio. A flag é processada no loop principal; se necessário encerra a conversa para testar o repouso. Se mudo, solicita desativar mute sem abrir o microfone silenciosamente. Após o teste, aguardar retorno ao repouso e repetir pelo menu se necessário.

## Experimento Vosk direcionado (somente comparação)
O teste de 60s da bandeja executa um segundo reconhecedor sobre os mesmos blocos de áudio. Gramática inclui variantes acústicas já conhecidas pelo léxico, palavras distratoras e [unk]. Rejeita parciais, exige frase final exata, evidência por palavra, confiança mínima 0,80 e duração de 0,18 a 3s. São limiares experimentais, não calibrados em hardware. O resultado é apenas candidato e nunca dispara a conversa. O detector principal e Pare continuam preservados. Nenhuma gravação de áudio ou API externa. Logs WAKE_COMPARE permitem comparar endpoints diferentes no mesmo período; não presumir que as fronteiras de locução coincidem. Adotar como ativador depende de teste positivo com voz real e amostra negativa com TV.

## Piloto de ativação direcionada autorizado
Após 2 candidatos positivos no teste guiado e 0 aceitos na janela negativa de 60s, ativação experimental por WAKE_DIRECTED_ENABLED=true somente no ambiente do processo de teste. Padrão de configuração permanece false até validação do ciclo real. Resultados finais exatos, confiança/duração e caminho [unk] preservados. Em modo direcionado, rejeição não é contornada pelo detector geral; falha interna volta explicitamente ao original. Pare continua usando o reconhecedor geral. Não registra transcrições fora da janela diagnóstica. Essa amostra não comprova taxa de falsos positivos de uso diário.

## Correção do comando de repouso
Reconhecedor Vosk geral separado para comandos curtos de parada; recebe todos os blocos de conversa, incluindo silêncio e durante reprodução, sem gates de RMS 2200/350. Não compartilha estado com wake ou confirmação. Aceita frases exatas; resultados parciais precisam permanecer estáveis por 240ms. Retira a aceitação da palavra dentro de discursos longos. Limpeza pós-eco preserva o stream de parada. Não equivale a cancelamento acústico de eco ou identificação do usuário: áudio externo contendo um comando exato ainda pode interromper. Teste real durante fala pendente.

- Parada via Gemini: ferramenta stop_listening agora exposta ao modelo e ligada ao handler existente de go_to_sleep; ordem direta encerra a sessão em vez de somente gerar fala. Fallback dependente da conexão, preservando detector local. Teste de integração verifica stop do player, desconexão, limpeza da captura e estado SLEEPING. Diagnóstico local de parada só transcreve durante janela de teste consentida. Validação real pendente.

- Interrupção durante reprodução em piloto: reconhecedor local de parada agora usa gramática direcionada com comandos de encerrar conversa, alternativas negativas e [unk]; final exige confiança mínima 0,80, parcial exato e estável permanece permitido exceto para a preposição para. Mantém bloqueio de eco no streaming ao Gemini. Não é AEC e ainda precisa de validação com usuário falando sobre a voz do assistente.
