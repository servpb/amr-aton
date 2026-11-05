# Tarefas Google e avisos locais

Diagnostico05/11/2026: tarefas tinham horario somente no titulo/notas. A API Tasks
persiste dia, descartando hora em due; nao havia ReminderStore para esses pedidos.
Referencia https://developers.google.com/workspace/tasks/reference/rest/v1/tasks

create_task aceita reminder_at ISO8601 com data/hora/fuso. Valida futuro ate366dias
e titulo ate200 antes do envio Google. Apos sucesso remoto, cria lembrete local
persistente e retorna reminder_scheduled e reminder_id. Horario explicito no titulo
sem reminder_at gera esclarecimento antes de escrever. Modelo deve extrair horario
pedido para campo, nunca inventar; sem hora pergunta. due_date sozinho nao cria som.
Falha local apos criacao Google e partial_success: nunca repetir criacao remota,
reparar apenas aviso. Nao existe transacao atomica entre Google e SQLite.

Nao altera tarefas antigas, cujos horarios podem ser ambiguos/vencidos. Nao consulta
remotamente para reconstruir horarios. Confirmar data/hora antes de reagendar.
Concluir/adiar janela afeta aviso local; nao altera tarefa Google. Conclusao/exclusao
Google nao cancela automaticamente aviso local nesta etapa. IDs retornados permitem
cancel_reminder. Sem sincronizacao de duas vias ou deduplicacao remota garantida.
Aviso exige Aton executando e PC ativo. Usa janela/som/voz e politicas existentes.
Testes mockados em test_task_reminder_link.py. Nenhuma tarefa remota criada no teste.
Validacao real pendente: criar tarefa futura com horario, conferir confirmacao do
aviso, dizer Pare e aguardar janela. Nao usar horario ja passado.
