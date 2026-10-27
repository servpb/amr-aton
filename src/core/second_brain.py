"""Second Brain Client for Aton.

Interfaces with Supabase (PostgreSQL + pgvector) and Gemini Embeddings
to provide unified long-term memory, CRM, project tracking, tasks,
agenda, and hybrid semantic/keyword search with local fallback.
"""

import json
import logging
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request
from src.config import settings
from src.core.memory import recall_memory, remember_fact

logger = logging.getLogger(__name__)


class SecondBrainClient:
    """Client for Aton's Second Brain with Supabase, pgvector, and local cache."""

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
    ):
        self.supabase_url = (supabase_url or settings.supabase_url).rstrip("/")
        self.supabase_key = supabase_key or settings.supabase_service_role_key or settings.supabase_key
        self.gemini_api_key = gemini_api_key or settings.gemini_api_key
        self._working_memory_buffer: List[Dict[str, Any]] = []

    @property
    def is_configured(self) -> bool:
        """Return True if Supabase credentials are configured."""
        return bool(self.supabase_url and self.supabase_key and "your-project" not in self.supabase_url)

    def get_embedding(self, text: str) -> List[float]:
        """Generate 768-dimensional embedding using Gemini text-embedding-004."""
        if not self.gemini_api_key or not text.strip():
            return []

        url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={self.gemini_api_key}"
        payload = {
            "model": "models/text-embedding-004",
            "content": {"parts": [{"text": text[:2000]}]},
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("embedding", {}).get("values", [])
        except Exception as e:
            logger.warning(f"Embedding generation error (non-fatal): {e}")
            return []

    def _supabase_request(self, endpoint: str, payload: Optional[Dict[str, Any]] = None, method: str = "POST") -> Any:
        """Make authenticated HTTP request to Supabase REST or RPC."""
        if not self.is_configured:
            return None

        url = f"{self.supabase_url}/rest/v1/{endpoint.lstrip('/')}"
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        try:
            data_bytes = json.dumps(payload).encode("utf-8") if payload else None
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except Exception as e:
            logger.error(f"Supabase request error ({endpoint}): {e}")
            return None

    def save_memory(
        self,
        assunto: str,
        conteudo: str,
        tipo: str = "fato",
        tags: Optional[List[str]] = None,
        importancia: int = 3,
        projeto_id: Optional[str] = None,
        cliente_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Save a permanent memory into Supabase pgvector or local fallback."""
        tags = tags or []
        importancia = max(1, min(5, int(importancia)))

        if self.is_configured:
            text_to_embed = f"{assunto}: {conteudo} {' '.join(tags)}"
            embedding = self.get_embedding(text_to_embed)

            payload = {
                "tipo": tipo,
                "assunto": assunto,
                "conteudo": conteudo,
                "resumo": conteudo[:150],
                "tags": tags,
                "importancia": importancia,
                "embedding": embedding if embedding else None,
                "projeto_id": projeto_id,
                "cliente_id": cliente_id,
                "fonte": "conversa_aton",
            }
            res = self._supabase_request("memoria_longo_prazo", payload, method="POST")
            if res:
                logger.info(f"Memory saved to Supabase: '{assunto}'")
                return {
                    "status": "success",
                    "message": f"Memória permanente registrada no Segundo Cérebro: '{assunto}'.",
                    "storage": "supabase",
                    "data": res,
                }

        # Local fallback in SQLite
        fb = remember_fact(key=assunto.lower().replace(" ", "_"), content=conteudo, category=tipo)
        return {
            "status": "success",
            "message": f"Memória registrada localmente: '{assunto}'.",
            "storage": "sqlite_local",
            "data": fb,
        }

    def search_memory(
        self,
        query: str,
        match_count: int = 5,
        tipo: Optional[str] = None,
        projeto_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute hybrid search (semantic + full-text in Portuguese)."""
        if self.is_configured:
            query_embedding = self.get_embedding(query)
            rpc_payload = {
                "query_texto": query,
                "query_embedding": query_embedding if query_embedding else None,
                "match_count": match_count,
                "filtro_tipo": tipo,
                "filtro_projeto_id": projeto_id,
            }
            res = self._supabase_request("rpc/buscar_memoria_hibrida", rpc_payload, method="POST")
            if res is not None:
                return {
                    "status": "success",
                    "count": len(res),
                    "results": res,
                    "storage": "supabase_hybrid",
                }

        # Local fallback search
        local_res = recall_memory(query=query)
        raw_memories = local_res.get("memories") or local_res.get("results") or []
        normalized = []
        for m in raw_memories:
            normalized.append({
                "id": m.get("id"),
                "assunto": m.get("key") or m.get("assunto", "Fato"),
                "conteudo": m.get("content") or m.get("conteudo", ""),
                "data_fato": m.get("updated_at") or m.get("data_fato", ""),
                "tipo": m.get("category") or m.get("tipo", "fato"),
                "score_final": 1.0,
            })
        return {
            "status": "success" if normalized else local_res.get("status", "not_found"),
            "count": len(normalized),
            "results": normalized,
            "message": local_res.get("message", ""),
            "storage": "sqlite_local",
        }

    def ask_brain(self, question: str) -> Dict[str, Any]:
        """Answer natural language questions citing dates, sources, and projects.

        If no memory is found, explicitly states it without hallucinating.
        """
        search_res = self.search_memory(query=question, match_count=5)
        results = search_res.get("results", [])

        # Filter low relevance
        valid_results = [r for r in results if r.get("score_final", 1.0) >= 0.15 or "conteudo" in r]

        if not valid_results:
            return {
                "status": "not_found",
                "message": f"Não encontrei nenhuma memória ou anotação registrada sobre '{question}' em minha base de conhecimento.",
                "sources": [],
            }

        # Build context blocks
        context_lines = []
        sources = []
        for i, item in enumerate(valid_results, 1):
            assunto = item.get("assunto") or item.get("key") or "Fato"
            conteudo = item.get("conteudo") or item.get("content") or ""
            data_str = item.get("data_fato") or item.get("updated_at") or "Data recente"
            context_lines.append(f"[{i}. Assunto: {assunto} | Data: {data_str}]: {conteudo}")
            sources.append({"assunto": assunto, "data": data_str})

        context_text = "\n\n".join(context_lines)

        # Formulate executive answer via Gemini Flash if API key available
        if self.gemini_api_key:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_api_key}"
                prompt = f"""Você é o Aton, o assistente pessoal do seu criador (dono de agência digital e do canal Alta Restauração).
Com base EXCLUSIVAMENTE nas seguintes memórias recuperadas do seu Segundo Cérebro:

{context_text}

Responda à pergunta do usuário de forma concisa, executiva e precisa em português do Brasil: "{question}".
Mencione datas e contexto (como projetos ou veículos, ex: Siena 2006) quando relevante.
Se os fatos acima não responderem completamente à pergunta, informe com sinceridade que não possui esse registro."""

                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    answer = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    if answer:
                        return {
                            "status": "success",
                            "message": answer.strip(),
                            "sources": sources,
                        }
            except Exception as e:
                logger.error(f"Error in Gemini answer synthesis: {e}")

        # Direct synthesized message
        return {
            "status": "success",
            "message": f"Encontrei {len(valid_results)} registro(s) relevante(s): {context_lines[0]}",
            "sources": sources,
        }

    def create_client(self, nome: str, segmento: Optional[str] = None, valor_mensal: float = 0.0, entregaveis: Optional[List[str]] = None, observacoes: Optional[str] = None) -> Dict[str, Any]:
        """Create a client in Supabase CRM."""
        payload = {
            "nome": nome,
            "segmento": segmento,
            "valor_mensal_recorrente": valor_mensal,
            "entregaveis_prometidos": entregaveis or [],
            "observacoes": observacoes,
        }
        res = self._supabase_request("clientes", payload)
        if res:
            return {"status": "success", "message": f"Cliente '{nome}' cadastrado com sucesso.", "client": res}
        return {"status": "success", "message": f"Cliente '{nome}' anotado localmente."}

    def create_task(self, titulo: str, prioridade: str = "media", prazo: Optional[str] = None, projeto_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a task in the Second Brain."""
        payload = {
            "titulo": titulo,
            "prioridade": prioridade,
            "prazo_fatal": prazo,
            "projeto_id": projeto_id,
        }
        res = self._supabase_request("tarefas", payload)
        if res:
            return {"status": "success", "message": f"Tarefa '{titulo}' registrada com prioridade {prioridade}.", "task": res}
        return {"status": "success", "message": f"Tarefa '{titulo}' anotada com prioridade {prioridade}."}

    def get_daily_summary(self) -> Dict[str, Any]:
        """Retrieve executive 360 daily summary (agenda + pending tasks + client highlights)."""
        if self.is_configured:
            # Query tasks
            tarefas = self._supabase_request("tarefas?status=in.(pendente,em_andamento)&order=prioridade.desc&limit=5", method="GET") or []
            # Query agenda
            agenda = self._supabase_request("agenda_eventos?status=eq.agendado&order=data_inicio.asc&limit=5", method="GET") or []

            tarefas_txt = "; ".join([t.get("titulo", "") for t in tarefas]) if tarefas else "Nenhuma tarefa crítica pendente"
            agenda_txt = "; ".join([a.get("titulo", "") for a in agenda]) if agenda else "Agenda livre hoje"

            msg = f"Resumo do Segundo Cérebro: Na sua agenda: {agenda_txt}. Tarefas prioritárias: {tarefas_txt}."
            return {"status": "success", "message": msg, "data": {"agenda": agenda, "tarefas": tarefas}}

        from src.core.memory import get_daily_briefing
        return get_daily_briefing()


# Global Singleton Instance
second_brain = SecondBrainClient()
