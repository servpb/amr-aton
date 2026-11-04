# Documentação: Motor de Avisos Proativos da Agenda (`proactive_calendar.py`)

## 1. Visão Geral
O **Motor de Avisos Proativos da Agenda** ([`src/core/proactive_calendar.py`](file:///c:/xampp/htdocs/amr/src/core/proactive_calendar.py) e [`src/tools/proactive_tools.py`](file:///c:/xampp/htdocs/amr/src/tools/proactive_tools.py)) adiciona iniciativa controlada ao **Aton**: ele monitora silenciosamente os próximos compromissos da conta autenticada no Google Agenda a cada **60 segundos** e alerta o usuário automaticamente quando faltam **até 15 minutos** para um evento começar.

---

## 2. Os 6 Pilares de Confiabilidade Implementados

1. **Persistência em SQLite (`data/reminders.sqlite3`):**
   - As ocorrências já notificadas ficam salvas na tabela `proactive_calendar_notified` e o histórico detalhado em `proactive_calendar_alerts_log`.
   - Reiniciar o Aton ou o Windows **nunca provoca avisos duplicados** para o mesmo compromisso.
2. **Identificação Individual de Eventos Recorrentes e Reagendados:**
   - Cada ocorrência recebe uma chave composta única (`occurrence_key = rec::<recurringEventId>::<instanceId>::<start_utc>` ou `evt::<eventId>::<start_utc>`).
   - Uma reunião semanal gera um aviso a cada semana normalmente, e se um compromisso for reagendado para outro horário, o novo horário gera um novo aviso.
3. **Janela Tolerante de 15 Minutos (`0 < tempo_restante <= lead_minutes`):**
   - O ciclo de 60 segundos dispara o aviso sempre que faltar até 15 minutos (`lead_minutes=15`), sem exigir que o relógio coincida com o segundo exato `15:00`.
4. **Modo Não Perturbe Persistido com Controle Separado de Som e Visual:**
   - A tabela `proactive_calendar_settings` no SQLite mantém a configuração mesmo após reiniciar o programa:
     - `dnd_mute_sound`: bloqueia apenas o bipe sonoro, mantendo a notificação visual silenciosa na bandeja do Windows.
     - `dnd_block_visual`: bloqueia também a notificação visual na bandeja.
     - **Horário de Silêncio Automático (`23:00` às `07:00`):** silencia automaticamente o bipe sonoro durante a noite/madrugada.
5. **Limite de 3 Avisos por Hora com Agrupamento em Resumo:**
   - Para evitar excesso de interrupções sem perder nenhum compromisso importante, quando há múltiplos eventos próximos ou o orçamento de 3 avisos/hora é atingido, os eventos excedentes são **agrupados em uma única notificação resumida**.
6. **Resistência a Falhas (Isolamento Total):**
   - Quedas temporárias de internet, expiração de token OAuth ou indisponibilidade da API Google Calendar são tratadas silenciosamente em segundo plano sem jamais interromper a sessão de voz do Gemini Live.

---

## 3. Ferramentas de Voz Disponíveis

- **`explicar_ultimo_aviso()`:**
  - Acionada quando o usuário pergunta *"Aton, por que você me avisou isso?"* ou *"O que apitou agora?"*.
  - Retorna a explicação falada do último alerta disparado, os eventos incluídos e o horário.
- **`configurar_avisos_proativos(ativado?, minutos_antecedencia?, silenciar_som?, bloquear_notificacao_visual?)`:**
  - Permite ligar/desligar os avisos, ajustar os minutos de antecedência (ex.: 15 ou 20 minutos) ou ativar/desativar o Modo Não Perturbe (som e/ou visual) por voz.

---

## 4. Como Testar Automatizadamente

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_proactive_calendar.py -v
```

