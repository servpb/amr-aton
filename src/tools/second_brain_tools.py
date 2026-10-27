"""Second Brain Tools for Aton.

Provides Gemini Live API tool declarations and dispatcher for
long-term hybrid memory, Q&A (perguntar_ao_cerebro), CRM, and tasks.
"""

import logging
from typing import Any, Dict, List, Optional
from src.core.second_brain import second_brain

logger = logging.getLogger(__name__)


def salvar_memoria(
    assunto: str,
    conteudo: str,
    tipo: str = "fato",
    tags: Optional[List[str]] = None,
    importancia: int = 3,
) -> Dict[str, Any]:
    """Save a memory into the Second Brain."""
    return second_brain.save_memory(
        assunto=assunto,
        conteudo=conteudo,
        tipo=tipo,
        tags=tags or [],
        importancia=importancia,
    )


def buscar_memoria(query: str, tipo: Optional[str] = None) -> Dict[str, Any]:
    """Search the Second Brain using hybrid search."""
    return second_brain.search_memory(query=query, tipo=tipo)


def perguntar_ao_cerebro(pergunta: str) -> Dict[str, Any]:
    """Ask a question to the Second Brain citing dates, sources, and projects."""
    return second_brain.ask_brain(question=pergunta)


def criar_cliente_cerebro(
    nome: str,
    segmento: Optional[str] = None,
    valor_mensal: float = 0.0,
) -> Dict[str, Any]:
    """Register a new client in the Second Brain CRM."""
    return second_brain.create_client(nome=nome, segmento=segmento, valor_mensal=valor_mensal)


def criar_tarefa_cerebro(
    titulo: str,
    prioridade: str = "media",
    prazo: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a task in the Second Brain."""
    return second_brain.create_task(titulo=titulo, prioridade=prioridade, prazo=prazo)


def resumo_geral_cerebro() -> Dict[str, Any]:
    """Get executive daily summary of agenda, tasks, and client status."""
    return second_brain.get_daily_summary()


def esquecer_memoria_cerebro(id: str) -> Dict[str, Any]:
    """Soft delete a memory from the Second Brain (archives without physical deletion)."""
    return second_brain.soft_delete_memory(memory_id=id)


def atualizar_memoria_cerebro(
    id: str,
    novo_conteudo: str,
    novo_assunto: Optional[str] = None,
) -> Dict[str, Any]:
    """Append-only update of an existing memory (creates new version and marks previous as substituted)."""
    return second_brain.update_memory(
        origem_id=id,
        novo_conteudo=novo_conteudo,
        novo_assunto=novo_assunto,
    )


def consultar_autoconhecimento(pergunta: str, categoria: Optional[str] = None) -> Dict[str, Any]:
    """Consult Aton's verified self-knowledge base (identity, creator, architecture, tools, limitations, etc.)."""
    return second_brain.consultar_autoconhecimento(pergunta=pergunta, categoria=categoria)


# Declarations for Gemini Live API
SECOND_BRAIN_FUNCTION_DECLARATIONS = [
    {
        "name": "consultar_autoconhecimento",
        "description": "Consulta a base verificada de autoconhecimento do Aton sobre sua própria identidade, criador (dono de agência digital e canal Alta Restauração), arquitetura em três camadas, tecnologias reais (Python, Gemini Live, Supabase, pgvector), lista completa de ferramentas ativas, limitações reais e changelog. Responde com sinceridade e nunca expõe senhas ou chaves.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "pergunta": {
                    "type": "STRING",
                    "description": "A pergunta sobre o próprio Aton (ex: 'quem é seu criador?', 'quais ferramentas você tem?', 'qual sua arquitetura?', 'o que você não faz?').",
                },
                "categoria": {
                    "type": "STRING",
                    "description": "Categoria opcional: 'identidade', 'tecnologia', 'arquitetura', 'capacidade', 'limitacao', 'roadmap', 'historico'.",
                },
            },
            "required": ["pergunta"],
        },
    },
    {
        "name": "salvar_memoria",
        "description": "Salva uma informação, fato permanente, preferência ou detalhe de projeto no Segundo Cérebro do Aton.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "assunto": {
                    "type": "STRING",
                    "description": "Título curto do assunto (ex: 'Siena 2006 Multimídia', 'Cliente Agência XPTO').",
                },
                "conteudo": {
                    "type": "STRING",
                    "description": "Descrição completa e detalhada da informação a ser guardada.",
                },
                "tipo": {
                    "type": "STRING",
                    "description": "Tipo da memória: 'fato', 'regra', 'projeto', 'cliente', 'preferencia'.",
                },
                "importancia": {
                    "type": "INTEGER",
                    "description": "Nível de importância de 1 (baixo) a 5 (crítico). Padrão é 3.",
                },
            },
            "required": ["assunto", "conteudo"],
        },
    },
    {
        "name": "buscar_memoria",
        "description": "Realiza busca híbrida (semântica vetorial + texto exato) nas memórias permanentes do Segundo Cérebro.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Termo de busca ou dúvida a pesquisar no cérebro.",
                },
                "tipo": {
                    "type": "STRING",
                    "description": "Filtro opcional por tipo: 'fato', 'projeto', 'cliente', 'preferencia'.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "perguntar_ao_cerebro",
        "description": "Consulta o Segundo Cérebro em linguagem natural para responder dúvidas sobre projetos (ex: Alta Restauração / Siena 2006), clientes ou fatos passados, citando fontes e datas. Se não souber, informa que não possui o registro sem inventar.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "pergunta": {
                    "type": "STRING",
                    "description": "A pergunta que você quer fazer à memória permanente (ex: 'o que eu falei sobre a central multimídia do Siena?', 'quais entregas combinamos para o cliente X?').",
                },
            },
            "required": ["pergunta"],
        },
    },
    {
        "name": "criar_cliente_cerebro",
        "description": "Cadastra um novo cliente na base CRM do Segundo Cérebro.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "nome": {"type": "STRING", "description": "Nome do cliente ou empresa."},
                "segmento": {"type": "STRING", "description": "Ramo de atuação do cliente."},
                "valor_mensal": {"type": "NUMBER", "description": "Valor do contrato mensal recorrente."},
            },
            "required": ["nome"],
        },
    },
    {
        "name": "criar_tarefa_cerebro",
        "description": "Registra uma nova tarefa operacional com prioridade no Segundo Cérebro.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "titulo": {"type": "STRING", "description": "Título da tarefa."},
                "prioridade": {
                    "type": "STRING",
                    "description": "Prioridade: 'baixa', 'media', 'alta', 'urgente'.",
                },
                "prazo": {"type": "STRING", "description": "Data ou prazo previsto."},
            },
            "required": ["titulo"],
        },
    },
    {
        "name": "resumo_geral_cerebro",
        "description": "Gera um resumo executivo matinal 360 graus agregando a agenda, tarefas prioritárias e pendências de clientes.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "esquecer_memoria_cerebro",
        "description": "Arquiva uma memória do Segundo Cérebro (soft delete). A informação deixa de aparecer nas buscas, mas é preservada no histórico.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "id": {"type": "STRING", "description": "ID UUID da memória a ser arquivada."},
            },
            "required": ["id"],
        },
    },
    {
        "name": "atualizar_memoria_cerebro",
        "description": "Atualiza uma memória existente de forma aditiva (cria uma nova versão e preserva a anterior como histórico substituído).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "id": {"type": "STRING", "description": "ID UUID da memória original."},
                "novo_conteudo": {"type": "STRING", "description": "Novo conteúdo atualizado da memória."},
                "novo_assunto": {"type": "STRING", "description": "Novo título ou assunto opcional."},
            },
            "required": ["id", "novo_conteudo"],
        },
    },
]


def dispatch_second_brain_tool(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch Second Brain tools."""
    if tool_name == "salvar_memoria":
        return salvar_memoria(
            assunto=tool_args.get("assunto", ""),
            conteudo=tool_args.get("conteudo", ""),
            tipo=tool_args.get("tipo", "fato"),
            tags=tool_args.get("tags"),
            importancia=tool_args.get("importancia", 3),
        )
    elif tool_name == "buscar_memoria":
        return buscar_memoria(
            query=tool_args.get("query", ""),
            tipo=tool_args.get("tipo"),
        )
    elif tool_name == "perguntar_ao_cerebro":
        return perguntar_ao_cerebro(pergunta=tool_args.get("pergunta", ""))
    elif tool_name == "criar_cliente_cerebro":
        return criar_cliente_cerebro(
            nome=tool_args.get("nome", ""),
            segmento=tool_args.get("segmento"),
            valor_mensal=float(tool_args.get("valor_mensal", 0.0)),
        )
    elif tool_name == "criar_tarefa_cerebro":
        return criar_tarefa_cerebro(
            titulo=tool_args.get("titulo", ""),
            prioridade=tool_args.get("prioridade", "media"),
            prazo=tool_args.get("prazo"),
        )
    elif tool_name == "resumo_geral_cerebro":
        return resumo_geral_cerebro()
    elif tool_name == "esquecer_memoria_cerebro":
        return esquecer_memoria_cerebro(id=tool_args.get("id", ""))
    elif tool_name == "atualizar_memoria_cerebro":
        return atualizar_memoria_cerebro(
            id=tool_args.get("id", ""),
            novo_conteudo=tool_args.get("novo_conteudo", ""),
            novo_assunto=tool_args.get("novo_assunto"),
        )
    elif tool_name == "consultar_autoconhecimento":
        return consultar_autoconhecimento(
            pergunta=tool_args.get("pergunta", ""),
            categoria=tool_args.get("categoria"),
        )

    return {
        "status": "error",
        "message": f"Ferramenta do Segundo Cérebro desconhecida '{tool_name}'.",
    }
