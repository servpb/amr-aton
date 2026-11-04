# Timers e lembretes persistentes

## Objetivo e comandos
Avisos únicos locais por som e notificação do Windows, independentes da conversa.
- “Me avise daqui a um minuto para fazer uma pausa.” → create_timer(seconds=60, title=...).
- “Me lembre amanhã às 15 horas de ligar para o cliente.” → consultar horário atual com list_reminders, resolver data e fuso e usar create_reminder(at=ISO 8601 com offset, title=...). Perguntar em caso de ambiguidade.
- “Quais são meus lembretes?” → list_reminders(include_history=False).
- “Cancele o lembrete da pausa.” → consultar e cancelar pelo ID real; esclarecer se houver vários.

## Persistência e ciclo de vida
SQLite em data/reminders.sqlite3. Não usa Google Tasks, Calendar ou API paga.
IDs únicos, texto de 1 a 200 caracteres e duração/data futura até 366 dias.
Estados: pending, delivering, notified, cancelled. notified significa solicitação de notificação aceita pelo mecanismo local, não leitura/escuta comprovada.
O worker consulta a cada segundo em segundo plano sem abrir sessão Gemini. Cada processamento usa conexão SQLite própria e transação para evitar dupla captura.
Avisos sobrevivem ao encerramento/reinício do Aton. Windows desligado/suspenso ou aplicativo encerrado não pode notificar; vencidos são apresentados na próxima execução/retomada, em ordem de horário, um por ciclo.
Falha de notificação mantém o aviso pendente com nova tentativa após 30s. Entrega interrompida é recuperada após lease de 60s. Uma queda entre envio ao Windows e confirmação no banco pode gerar repetição: não há garantia de entrega exatamente uma vez.
Cancelamento vale somente para pending. Se já estiver delivering, não promete impedir uma notificação em curso. Histórico limitado aos primeiros 100 registros ordenados por vencimento.

## Avisos e limitações
Notificação textual na bandeja e bipe local quando em repouso; sem fala sintetizada, aviso por celular ou despertar do computador. Durante conversa usa a notificação do Windows sem misturar outro bipe ao player.
Foco/Não perturbe, volume, saída de áudio e preferências do Windows podem ocultar ou silenciar o aviso. Aton não pode comprovar percepção.
Sem bandeja disponível, a entrega é retentada. “Pare” e cancelar tarefa de automação não removem lembretes.
Por 0,8s após enfileirar o bipe em repouso, o detector é limpo para reduzir eco. Validar no equipamento real.
Textos são armazenados localmente sem criptografia adicional; não colocar segredos nos títulos.
Não inclui recorrência, adiar/soneca ou alteração de aviso: cancelar e criar outro.

## Validação
Automatizados: tests/test_reminders.py cobre reinício, vencidos, cancelamento, concorrência, lease, falhas e contratos das ferramentas.
Manual (após reinício autorizado apenas do Aton):
1. Criar timer de 60s, consultar e dizer Pare; verificar som/notificação sem despertar conversa.
2. Criar dois avisos, cancelar um e verificar que apenas o outro chega.
3. Criar timer, encerrar e iniciar Aton depois do vencimento; verificar aviso atrasado e histórico.
4. Testar suspensão/retomada e aviso durante conversa.
5. Verificar estado de prontidão, comando Pare e ativação por voz preservados.
Os testes automatizados não comprovam entrega audível/visível no Windows real.

## Resultado da verificação automatizada
37 testes aprovados: lembretes, catálogo de módulos, bandeja e ciclo de boot. O teste assíncrono precisou executar fora da restrição de rede do ambiente de testes porque o loop de eventos do Windows cria um socket local internamente. Nenhuma conexão Gemini foi aberta e o Aton em execução não foi reiniciado. Entrega real na bandeja, áudio e chamadas por voz continuam pendentes de teste manual.
