# Piloto de cancelamento de eco acústico local

## Objetivo
Tentar preservar a ordem de interrupção do usuário enquanto o assistente fala pelos alto-falantes, sem fones e sem serviço pago. Não substitui identificação de locutor.

## Implementação
Dependência opcional `pywebrtc-audio==0.2.0`, licença Apache 2.0, instalada no ambiente virtual do projeto. Modo padrão desligado (`AUDIO_AEC_ENABLED=false`). A ativação por variável de ambiente do processo não altera `.env` e é reversível reiniciando sem a variável.
`src/audio/duplex_aec.py` abre um único stream sounddevice de entrada/saída mono 16kHz em blocos de 10ms. A saída exata do callback é a referência do WebRTC; o microfone limpo é agregado em 80ms para os consumidores existentes. O som 24kHz do Gemini é reamostrado por interpolação linear no piloto. Sem arquivos de áudio ou envio a terceiros para AEC.
O atraso usa soma das latências reportadas pelo stream, ajustável por `AUDIO_AEC_DELAY_MS` (0–500ms). Essa é uma estimativa, não calibração acústica comprovada. AEC requer convergência e validação sob fala simultânea.
O stop esvazia a fila de saída sem aguardar escrita longa; pode restar a cauda já armazenada no driver. O streaming para o Gemini continua protegido durante reprodução, e o reconhecimento local recebe o áudio processado.

## Limitações
- Cancela somente o som do Aton roteado por este engine, não televisão ou áudio de outros aplicativos.
- Não garante separação perfeita, ausência de falsos positivos ou interrupção imediata.
- Falha de processamento não encaminha áudio cru silenciosamente: marca erro para recuperação coordenada.
- Mudança de dispositivos, volumes, distância e acústica pode exigir calibrar atraso e validar novamente.
- O modo legado fica intacto quando a opção está desligada. Não há fallback silencioso no meio da sessão.

## Validação
Testes simulados devem verificar referência exata, preservação de amostras, fila limitada e parada. Teste sintético de eco apenas avalia o processador, não prova efeito no hardware.
Teste real: iniciar modo piloto; verificar AEC_HEALTH sem erros; chamar o assistente; pedir resposta longa e emitir ordem curta enquanto a voz sai pelos alto-falantes. Correlacionar VOICE_STOP com reprodução e repouso. Repetir com frase de encerramento. Só considerar aprovado com confirmação do usuário e evidência dos registros.

## Ativação em hardware — 03/11/2026
89 testes automatizados revalidados. Processo iniciado em piloto com AUDIO_AEC_ENABLED=true e WAKE_DIRECTED_ENABLED=true, sem alterar .env. Stream compartilhado ativo a 16kHz/10ms; atraso estimado 120ms. Captura processada avançou de 790 para 2792 frames, sem erro do processador e com dois eventos de status iniciais sem crescimento na observação. Esses dados são de repouso, com referência de saída zero; não comprovam cancelamento de eco durante reprodução nem reconhecimento da ordem do usuário. Teste real durante história ainda pendente.

- 03/11/2026, ajuste de escuta simultânea no piloto: o modo AEC agora permite enviar captura processada ao Gemini durante reprodução somente com engine saudável e pelo menos 200 frames processados. Modo legado mantém bloqueio. Sinal server_content.interrupted limpa a reprodução local, preservando a captura do novo pedido e invalidando confirmação interrompida; ignora áudio anexado ao evento de interrupção. Mantém stop_listening para entrar em repouso e preserva confirmação de conclusão de fala para operações sensíveis. Teste real de interrupção ainda pendente.

## Revalidação da escuta simultânea
101 testes aprovados, incluindo execução real do loop principal com dependências simuladas: durante reprodução envia exatamente um bloco ao cliente no AEC saudável, nenhum no modo legado; evento de interrupção descarta saída antiga sem limpar captura do pedido. Processo piloto reiniciado em 03/11/2026 às 09:48 e retornou a ready, AEC sem erro em repouso. Próximo passo: teste real de ordem durante resposta longa. Não comprova resultado acústico final.

- Comparação real: primeiro teste teve VOICE_INTERRUPTED e VOICE_BARGE_IN antes do encerramento; segundo somente stop_listening posterior, sem interrupção de reprodução. AEC sem erro em ambos, o que não prova preservação da voz do usuário. Ajuste isolado no perfil de atividade Live para AEC: início HIGH explícito, prefixo20ms, silêncio200ms, START_OF_ACTIVITY_INTERRUPTS. Ativa transcrição de entrada sem salvar texto: apenas marcador booleano quando há pedido exato de parada. Não muda processamento NS/AEC para manter uma hipótese por teste. Perfil mais sensível requer observar ativações indevidas. Pendente novo teste real; não é correção comprovada.

- Diagnóstico acústico autorizado pelo usuário: opção explícita da bandeja grava por no máximo 30s, localmente, três canais PCM (microfone bruto, processado, referência de saída) em `data/diagnostics`. Padrão inativo; não inicia no boot e não envia o arquivo a serviços externos. Deve ser acionado durante conversa AEC saudável, sem mute. Exportação fora do callback, duração limitada por amostras e relógio; testes em `tests/test_local_audio_diagnostic.py`. Análise real pendente.

- Análise da gravação autorizada: atraso acústico observado ~212ms versus estimativa120ms; replay comparativo não melhorou o resultado com212ms, portanto120ms mantido. Reconhecimento dirigido de Pare na captura processada perto do fim não comprovou interrupção precoce, conforme observação do usuário. Novo piloto de pausa por início de fala local: VoiceDetector sobre áudio AEC, probabilidade>=0,65 e RMS>=100 sustentados por8frames10ms, guarda inicial500ms e um evento por reprodução. O evento somente limpa saída e preserva microfone; entrar em repouso ainda depende de comando local ou stop_listening. Limiares experimentais com risco de pausas indevidas; validar antes de adotar como padrão. Nenhuma gravação adicional iniciada.

- Pausa local também suprime áudio remanescente apenas do turno que ainda estava sendo gerado. server_turn_open distingue geração em andamento de áudio já recebido/enfileirado. A supressão termina no evento interrupted ou turn_complete e não bloqueia a captura nem uma resposta nova. Teste de latência/eficácia no hardware ainda pendente.

- Correção de falso encerramento em perguntas: registros mostraram VOICE_STOP accepted final=0 repetidas vezes. Hipóteses parciais locais deixam de autorizar repouso, mesmo estáveis; pausa rápida continua no gate de fala, sem fechar captura. Repouso local exige resultado final exato/validado, ou comando interpretado pela ferramenta stop_listening. Perfil AEC mantém início rápido20ms e amplia silêncio de fim de fala para700ms, permitindo pausas naturais. Validar tanto pergunta sobre APIs gratuitas/pagas quanto ordem explícita de parada.
