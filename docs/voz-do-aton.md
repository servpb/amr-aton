# Voz do Aton

Registro consolidado em **05/11/2026** das alterações, testes acompanhados e limitações
tratadas nesta conversa. Este documento distingue o comportamento atual dos pilotos
anteriores; testes simulados não equivalem a validação completa no hardware.

## 1. Comportamento atual aprovado

- O aplicativo permanece residente enquanto o Windows estiver ativo e o Aton executando.
- Em espera, o microfone alimenta o reconhecimento local da palavra **Aton**.
- A conversa Gemini Live é aberta após a palavra-chave ou ativação manual.
- **Pare** interrompe a reprodução, desconecta a conversa e retorna silenciosamente à
  espera local. Não encerra o processo, o agendador ou os lembretes persistentes.
- Uma pergunta dita depois de Pare, sem Aton, não deve iniciar resposta.
- Avisos agendados são exceção: podem aparecer e anunciar o título sem nova chamada.
- Não existe identificação confiável do locutor: televisão, áudio deste chat ou outra
  pessoa pronunciando a palavra-chave também podem ativar o assistente.

O usuário confirmou o ciclo: história → Pare → pergunta sem palavra-chave ignorada →
Aton → resposta correta. A detecção durante fala sobreposta continua sujeita a falhas.

## 2. Ativação local, inicialização e áudio

A investigação anterior identificou transcrições diferentes para Aton no Vosk em
português. Foi criado reconhecedor direcionado, inicialmente comparativo, com
vocabulário existente no modelo, distratores, [unk] e critérios de confiança.
Não se trata de treinamento automático de uma palavra nova nem identificação pessoal.

Componentes relevantes:
- src/audio/wake_word.py: detector de ativação e reconhecedor local de parada.
- src/audio/wake_comparison.py: comparação e piloto direcionado.
- src/audio/stop_commands.py: vocabulário de encerramento e distratores.
- src/audio/recorder.py: captura limitada, descarte de backlog e indicadores de idade.
- src/core/assistant.py: estados, processamento de áudio e callbacks.
- src/integrations/system_tray.py: prontidão, erro e testes sob demanda.

A bandeja distingue inicialização, escuta local, prontidão e falhas. As métricas de
boot/áudio ajudam a separar carregamento, reconhecimento e conexão.

### Piloto de cancelamento de eco

Backend opcional em src/audio/duplex_aec.py com pywebrtc-audio0.2.0: stream duplex
mono16kHz, frames10ms e referência da saída. No equipamento foi usado atraso estimado
120ms. Uma comparação offline com212ms não mostrou melhora, portanto não foi adotada.
O detector de início de fala em src/audio/barge_in.py pausa saída preservando entrada;
isso sozinho não confirma reconhecimento de Pare nem encerra a conversa.

Nos reinícios de teste foram usados WAKE_DIRECTED_ENABLED=true e AUDIO_AEC_ENABLED=true
somente no ambiente do processo. **Não foram persistidos no .env nesta conversa.**
Logo, o boot normal pode carregar valores diferentes: verificar antes de afirmar que
um piloto está ativo após reiniciar o Windows.

## 3. Histórias cortadas e mudanças de comportamento

Foi encontrado limite local máximo de120s que podia encerrar a sessão durante fala.
A condição foi protegida para não disparar durante reprodução, turno aberto do
servidor ou ferramenta ativa. A mesma proteção foi aplicada ao timeout de silêncio.

Houve um piloto com CONTINUOUS_CONVERSATION_ENABLED=true e Pare mantendo sessão.
O usuário relatou falta de resposta depois da parada. Foi adicionada liberação da
supressão de áudio interrompido após nova fala transcrita.

**Esse piloto não é a preferência final.** O usuário definiu posteriormente que
Pare deve voltar à palavra-chave. O padrão atual é
CONTINUOUS_CONVERSATION_ENABLED=false; nova conversa exige Aton. A função interna
_stop_speaking e callbacks de retomada não substituem essa semântica pública.

Também foi observada desconexão do Gemini com aviso GoAway/limite de sessão, seguida
de retorno à espera. Não foi implementada renovação transparente da sessão. O
aplicativo residente não significa conexão de nuvem ilimitada. Quotas/internet se aplicam.

## 4. Continuidade da história entre chamadas

Criado src/core/story_context.py e integrado ao GeminiLiveClient:
- Último pedido de história até1500 caracteres e trecho gerado até2500 caracteres.
- Apenas RAM, validade15min; desaparece ao reiniciar o processo.
- Usa transcrição de entrada e saída do próprio Gemini, sem nova gravação local de
  áudio ou envio desse contexto aos auxiliares Groq/OpenRouter.
- Novo pedido de história substitui referência anterior.
- Pergunta de matemática não substitui o assunto nem seu trecho narrativo.
- Contexto é tratado como dados; não autoriza ferramentas ou reativa confirmações.
- Não retoma automaticamente ao despertar. Pedido ambíguo deve gerar esclarecimento.

O usuário confirmou que a história do **carro** foi retomada corretamente. Isso
valida esse caso, não todos os formatos de narrativa. A captura depende da transcrição
e do reconhecimento textual de pedidos com a palavra história. O trecho gerado pode
não ter sido ouvido integralmente; não existe posição exata de reprodução persistida.

### Pendência importante

“Aton, quanto é sete mais cinco?” dito de uma vez pode perder o pedido durante o
carregamento/conexão. O usuário precisou chamar Aton, esperar e então perguntar.
Preservar o áudio após a palavra-chave **ainda não foi implementado**. Não confundir
essa falha com a continuidade da história, que funcionou no caso descrito.

## 5. Avisos dinâmicos de timers e lembretes locais

Criado src/integrations/reminder_alert.py e integrado a _notify_reminder:
- Janela Tk em processo separado, com título e horário previsto.
- **Concluir:** marca o aviso local como completed.
- **Adiar10min:** mantém o mesmo aviso, com novo horário e estado pending persistidos.
- **Fechar:** dispensa a janela; não equivale a concluir a tarefa.
- Persistência em data/reminders.sqlite3, incluindo proteção de clique antes de finish.
- Até3 janelas; falha/capacidade pode usar a notificação anterior da bandeja.

Som: sinal Windows e leitura literal do título via SAPI offline, com vozptBR
verificada no computador. Velocidade ajustada para **Rate=3** após relato de lentidão.
Não há chamada de API paga para esse anúncio. Título não é executado como código/SSML.

O primeiro teste real foi confirmado pelo usuário. No segundo, um timer10s venceu
com sessão ativa e a regra antiga suprimiu o áudio. Ajustado: som permitido em espera
ou escuta ativa, desde que o player/turno do servidor não estejam falando.
Se estiver falando, aparece janela silenciosa, sem anúncio falado adiado.

Respeita DND sonoro/visual, mute e horário silencioso configurado (padrão23h–07h).
Bloqueio visual adia a entrega por retentativas. A fala local tem limite30s e o
processamento do microfone descarta eco durante esse anúncio; há pausa breve de
escuta, sem abrir conversa. Fechar interrompe o anúncio. Falha SAPI preserva janela.

Não garante aviso com PC desligado/suspenso ou Aton encerrado. Vencidos são tratados
quando o aplicativo/PC voltam. Notificação enviada não comprova que foi percebida.

## 6. Tarefas do Google com horário

Diagnóstico real: create_task recebia horário só no título/notas e due_date=hoje.
Não existia lembrete local correspondente. A API Google Tasks guarda dia e descarta
hora no campo due:
https://developers.google.com/workspace/tasks/reference/rest/v1/tasks

Ajustado create_task em src/tools/google_tasks.py:
- Campo reminder_at ISO8601 com data/hora/fuso, validado antes da criação remota.
- Depois do sucesso Google, cria aviso persistente local com janela/som/voz.
- Retorna task_created, reminder_scheduled e reminder_id separadamente.
- Horário explícito no título/notas sem campo adequado exige esclarecimento.
- Falha de aviso após criar tarefa retorna partial_success: não repetir criação Google.
- Apenas due_date não agenda aviso; resposta informa isso.
- Prompt orienta extrair o horário e não prometer aviso sem confirmação de agendamento.

Limitações: não existe transação atômica Google/SQLite nem sincronização bidirecional.
Concluir/adiar na janela afeta o aviso local, não a tarefa Google. Concluir/excluir
no Google não cancela automaticamente o aviso local. Tarefas antigas não foram
migradas ou reagendadas, especialmente quando horário já passou ou é ambíguo.

Consulta local feita para **06/11/2026**: nenhum aviso local encontrado naquele
momento. Isso não é consulta de todas as tarefas remotas nem previsão do estado futuro.
A capacidade de agendar data futura existe; entrega real de tarefa recém-criada com
reminder_at ainda requer confirmação no equipamento.

## 7. Testes e evidências

Execuções relevantes ao longo das mudanças (sobrepostas, não somar contagens):
-60 testes simulados após piloto inicial de conversa contínua.
-22 após liberação de resposta na próxima fala transcrita.
-62 após preferência Pare retornando à palavra-chave.
-27 para contexto narrativo e regressões de voz.
-32 para janelas, transições persistentes e políticas DND.
-40 após permitir anúncio em escuta ativa.
-40 para integração tarefa/aviso e regressões relacionadas.

São resultados das execuções registradas, não contagem da suíte inteira atual.
Testes de rede foram simulados; event loop Windows exigiu execução com sockets locais.
Tk inicializou e SAPI apresentou vozptBR instalada. Aparência, percepção e latência
são confirmadas somente pelos testes reais relatados. Não declarar correção completa
apenas porque existem logs de áudio ou retorno ao repouso.

Arquivos de testes: test_continuous_voice.py, test_voice_reliability.py,
test_aec_interruptions.py, test_story_context.py, test_reminder_alert.py,
test_reminders.py, test_proactive_calendar.py, test_task_reminder_link.py,
test_google_tasks.py (todos em tests/).

## 8. Roteiro de validação

1. Silenciar TV e outros assistentes durante o teste, sem exigir compra de fones.
2. Chamar Aton, esperar prontidão e pedir história. Dizer Pare durante a fala.
3. Perguntar sem Aton: deve ficar em espera. Chamar Aton e depois perguntar7+5.
4. Retomar a história mais recente. Repetir com novo tema e verificar substituição.
5. Criar timer30s, dizer Pare e aguardar janela/som/título. Testar Fechar, Concluir e
   Adiar separadamente; confirmar persistência após reinício.
6. Criar tarefa futura com horário e aviso. Conferir confirmação de agendamento,
   entrar em espera e aguardar. Verificar DND antes de interpretar silêncio como falha.
7. Após boot Windows, verificar flags reais e prontidão antes de comparar comportamento.

Marcadores úteis em logs/aton.log: VOICE_WAKE, VOICE_STOP, VOICE_BARGE_IN,
VOICE_INTERRUPTED, VOICE_RESUME, VOICE_SESSION, VOICE_READINESS, AEC_HEALTH,
AUDIO_LOOP_JITTER e REMINDER_ALERT. Não expor credenciais, tokens ou .env ao diagnosticar.

## 9. Documentação relacionada

- [Ciclo de voz](continuous_voice.md)
- [Contexto de histórias](story_context.md)
- [Piloto acústico](acoustic_echo_pilot.md)
- [Timers persistentes](timers_and_reminders.md)
- [Avisos dinâmicos](reminder_alerts.md)
- [Tarefas e avisos locais](task_reminder_link.md)

Este registro consolida o trabalho de voz/avisos. O planejamento Multi-LLM possui
registro próprio; não substitui testes nem corrige automaticamente áudio e palavra-chave.
