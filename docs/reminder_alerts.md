# Avisos dinamicos de lembretes e timers

Implementado em05/11/2026. _notify_reminder abre janela Tk em processo isolado,
sem abrir Gemini ou executar texto do lembrete. Titulo/horario ficam visiveis ate fechar.
Concluir grava completed; Adiar10min recoloca o mesmo lembrete em pending com novo
horario persistido; Fechar apenas dispensa a janela (estado notified, nao completed).
Cliques validos em delivering/notified, uso unico; finish nao sobrescreve clique rapido.

Som: bipe Windows e titulo falado via SAPI offline, preferencia voz pt-BR instalada.
Texto literal com flag IsNotXML; sem PowerShell/shell, sem API ou dependencia nova.
Anuncia so em espera, sem mute e fora de horario silencioso/DND sonoro. Durante
conversa mostra janela sem som/fala; nao acumula anuncio falado para depois.
Durante anuncio a captura local descarta eco temporariamente; nao reconhece Aton
nesse intervalo (ate30s). Fechar interrompe anuncio. Falha SAPI preserva janela.
Agendador espera anuncio terminar fora do loop de audio, evitando anuncios simultaneos.

Nao Perturbe visual adia entrega por retentativa30s (nao marca como entregue).
Politica usa configuracao persistida proactive_calendar, inclusive silencio23h-07h.
Configuracoes de voz, microfone e quotas nao alteradas. Ate3 janelas simultaneas;
falha de janela/capacidade usa notificacao existente da bandeja quando disponivel.
Notificacao submetida nao comprova percepcao. Sem bandeja e falha de janela, retenta.
Popups abertos podem permanecer apos encerrar Aton; horarios adiados exigem Aton ativo.

Escopo: timers/lembretes locais ReminderStore. Avisos Google Agenda e tarefas Google
Tasks mantem entrega anterior; nao sao automaticamente convertidos neste modulo.
Nao altera schemas de ferramentas. UI nao altera tarefas de automacao em andamento.

Validacao:32 testes reminders/reminder_alert/proactive_calendar aprovados com mocks;
Tk inicializa e SAPI tem vozptBR neste Windows. Visualizacao, audicao e cliques reais
pendentes. Testar: Aton crie timer20s chamado Verificar orcamento; Pare. Deve mostrar
janela, bipe e titulo em espera. Adiar10min e reiniciar confirma persistencia;
Concluir aparece no historico como completed. Fechar nao conclui tarefa.
Nao cria teste de tarefa sem pedido do usuario; nao grava audio para validar.

Ajuste apos teste real: usuario confirmou aviso funcionando e pediu voz mais rapida. SAPI Rate=3 (padrao0; escala-10..10). Novas janelas carregam ajuste sem reiniciar Aton.

Ajuste teste2: estado conversing sozinho nao silencia mais. Avisos sonoros permitidos
tambem em escuta ativa, desde que player/turno do servidor nao estejam falando e
DND/mute/silencio permitam. Durante anuncio a captura para Gemini tambem descarta eco
(pausa breve da escuta); nao abre conversa nem executa texto. Marker REMINDER_ALERT
registra decisao sem titulo. Quando Aton estiver falando, permanece janela silenciosa.
