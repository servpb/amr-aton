"""Voice tool contracts for persistent reminders."""
from datetime import datetime
from src.core.reminders import get_reminder_store

def declaration(name, description, properties, required=()):
    return {"name": name, "description": description, "parameters": {
        "type": "OBJECT", "properties": properties, "required": list(required)}}

REMINDER_DECLARATIONS = [
    declaration("create_timer", "Cria timer persistente. Converta minutos/horas em segundos. Avisa por som e notificação mesmo em repouso, somente com Aton e PC executando.", {
        "seconds": {"type": "NUMBER", "description": "Duração positiva em segundos."},
        "title": {"type": "STRING", "description": "Texto curto do aviso."}}, ("seconds", "title")),
    declaration("create_reminder", "Agenda aviso único com data ISO 8601 e fuso explícito. Pergunte quando data/horário forem ambíguos. Não cria compromisso no Google.", {
        "at": {"type": "STRING", "description": "Data e hora completas com offset, exemplo 2026-11-03T15:00:00-03:00."},
        "title": {"type": "STRING", "description": "Texto curto do aviso."}}, ("at", "title")),
    declaration("list_reminders", "Consulta timers/lembretes persistidos e quanto falta. Não confundir com tarefa de automação ou Google Tasks.", {
        "include_history": {"type": "BOOLEAN", "description": "Inclui avisos enviados e cancelados, se solicitado."}}),
    declaration("cancel_reminder", "Cancela um aviso pendente por ID retornado na consulta. Se houver ambiguidade, consulte e pergunte qual; nunca escolha arbitrariamente.", {
        "reminder_id": {"type": "STRING", "description": "ID exato retornado por list_reminders."}}, ("reminder_id",)),
]

def present(item):
    return {**item, "due_local": datetime.fromtimestamp(item['due_at']).astimezone().isoformat(),
            "remaining_seconds": max(0, round(item['due_at'] - get_reminder_store().clock()))}

def dispatch_reminder_tool(name, args):
    try:
        store = get_reminder_store()
        if name == "create_timer":
            item = store.create(args.get('title'), seconds=args.get('seconds'))
        elif name == "create_reminder":
            item = store.create(args.get('title'), at=args.get('at'))
        elif name == "list_reminders":
            items = [present(row) for row in store.list(args.get('include_history', False))]
            return {"status": "success", "reminders": items, "current_local_time": datetime.now().astimezone().isoformat(), "message": "Consulta concluída." if items else "Não há avisos nesta consulta."}
        elif name == "cancel_reminder":
            changed = store.cancel(args.get('reminder_id', ''))
            return {"status": "success" if changed else "not_cancelled", "message": "Aviso cancelado." if changed else "Não cancelado: aviso inexistente, já enviado/cancelado ou em processo de notificação. Consulte o estado atual."}
        else:
            raise ValueError("Ferramenta de lembrete desconhecida.")
        return {"status": "success", "reminder": present(item), "message": "Aviso salvo. Tocará um som e exibirá notificação; o Aton precisa estar executando e o PC ativo. Se estiverem indisponíveis, avisarei quando voltar."}
    except (ValueError, TypeError, OverflowError) as exc:
        return {"status": "error", "message": str(exc)}
    except Exception:
        return {"status": "error", "message": "Não consegui acessar os lembretes locais. O aviso não foi confirmado; consulte antes de tentar novamente."}
