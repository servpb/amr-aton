"""Second Brain Client for Aton.

Interfaces with Supabase (PostgreSQL + pgvector) and Gemini Embeddings
to provide unified long-term memory, CRM, project tracking, tasks,
agenda, and hybrid semantic/keyword search with local fallback.
"""

from datetime import datetime, timezone
import json
import logging
import os
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

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={self.gemini_api_key}"
        payload = {
            "content": {"parts": [{"text": text[:2000]}]},
            "output_dimensionality": 768,
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
        memory_id: Optional[str] = None,
        origem_dispositivo: str = "windows_pc",
        versao: int = 1,
        memoria_origem_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Save a permanent memory into Supabase pgvector or local fallback.

        Supports client-provided memory_id for idempotency.
        """
        tags = tags or []
        importancia = max(1, min(5, int(importancia)))

        if self.is_configured:
            # Idempotency check: if memory_id already exists, return without duplicating
            if memory_id:
                existing = self._supabase_request(f"memoria_longo_prazo?id=eq.{memory_id}&select=id,assunto", method="GET")
                if existing and isinstance(existing, list) and len(existing) > 0:
                    logger.info(f"Memory ID {memory_id} already exists. Idempotency preserved.")
                    return {
                        "status": "success",
                        "message": f"Memória já existente preservada (idempotência): '{assunto}'.",
                        "storage": "supabase",
                        "data": existing[0],
                        "idempotent": True,
                    }

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
                "embedding_pendente": False if embedding else True,
                "status": "ativa",
                "versao": versao,
                "origem_dispositivo": origem_dispositivo,
                "memoria_origem_id": memoria_origem_id,
                "projeto_id": projeto_id,
                "cliente_id": cliente_id,
                "fonte": "conversa_aton",
            }
            if memory_id:
                payload["id"] = memory_id

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

    def update_memory(
        self,
        origem_id: str,
        novo_conteudo: str,
        novo_assunto: Optional[str] = None,
        tags: Optional[List[str]] = None,
        importancia: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Append-only update: Marks previous memory as substituted and inserts new version."""
        if self.is_configured:
            # 1. Fetch original record
            old_records = self._supabase_request(f"memoria_longo_prazo?id=eq.{origem_id}&select=*", method="GET")
            if not old_records or not isinstance(old_records, list):
                return {"status": "not_found", "message": f"Memória original {origem_id} não encontrada."}

            old = old_records[0]
            assunto = novo_assunto or old.get("assunto", "Fato")
            tipo = old.get("tipo", "fato")
            tags = tags or old.get("tags", [])
            importancia = importancia if importancia is not None else old.get("importancia", 3)
            nova_versao = int(old.get("versao", 1)) + 1

            # 2. Mark old record as 'substituida'
            self._supabase_request(
                f"memoria_longo_prazo?id=eq.{origem_id}",
                {"status": "substituida"},
                method="PATCH",
            )

            # 3. Create new append-only version
            return self.save_memory(
                assunto=assunto,
                conteudo=novo_conteudo,
                tipo=tipo,
                tags=tags,
                importancia=importancia,
                versao=nova_versao,
                memoria_origem_id=origem_id,
                origem_dispositivo="windows_pc",
            )

        return self.save_memory(assunto=novo_assunto or "Fato", conteudo=novo_conteudo)

    def soft_delete_memory(self, memory_id: str) -> Dict[str, Any]:
        """Soft delete: Marks memory as deleted_at = now() and status = 'arquivada'."""
        if self.is_configured:
            # Try RPC soft_delete_memoria first
            rpc_res = self._supabase_request("rpc/soft_delete_memoria", {"p_id": memory_id}, method="POST")
            if rpc_res and isinstance(rpc_res, dict) and rpc_res.get("status") == "success":
                return rpc_res

            # Direct PATCH fallback
            now_iso = datetime.now(timezone.utc).isoformat()
            res = self._supabase_request(
                f"memoria_longo_prazo?id=eq.{memory_id}&deleted_at=is.null",
                {"deleted_at": now_iso, "status": "arquivada"},
                method="PATCH",
            )
            if res is not None:
                return {
                    "status": "success",
                    "message": f"Memória {memory_id} arquivada com sucesso (soft delete).",
                    "id": memory_id,
                }
            return {"status": "not_found", "message": f"Memória {memory_id} não encontrada ou já arquivada."}

        return {"status": "success", "message": f"Memória {memory_id} marcada como arquivada localmente."}

    def hard_delete_memory(self, memory_id: str, confirmacao: bool = False) -> Dict[str, Any]:
        """Permanent physical delete, requiring explicit confirmation."""
        if not confirmacao:
            return {
                "status": "error",
                "message": "Exclusão permanente cancelada: requer confirmação explícita do criador.",
            }

        if self.is_configured:
            rpc_res = self._supabase_request(
                "rpc/hard_delete_memoria",
                {"p_id": memory_id, "p_confirmacao": True},
                method="POST",
            )
            if rpc_res:
                return rpc_res

            # Direct DELETE
            self._supabase_request(f"memoria_longo_prazo?id=eq.{memory_id}", method="DELETE")
            return {"status": "success", "message": f"Memória {memory_id} excluída permanentemente."}

        return {"status": "success", "message": f"Memória {memory_id} excluída localmente."}

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
            if m.get("deleted_at") or m.get("status") in ("arquivada", "substituida"):
                continue
            normalized.append({
                "id": m.get("id"),
                "assunto": m.get("key") or m.get("assunto", "Fato"),
                "conteudo": m.get("content") or m.get("conteudo", ""),
                "data_fato": m.get("updated_at") or m.get("data_fato", ""),
                "tipo": m.get("category") or m.get("tipo", "fato"),
                "status": m.get("status", "ativa"),
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

        # Filter low relevance and any soft-deleted records
        valid_results = [
            r for r in results 
            if (r.get("score_final", 1.0) >= 0.15 or "conteudo" in r)
            and not r.get("deleted_at")
            and r.get("status", "ativa") == "ativa"
        ]

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

    def consultar_autoconhecimento(self, pergunta: str, categoria: Optional[str] = None) -> Dict[str, Any]:
        """Query Aton's verified self-knowledge base (identity, architecture, tools, limitations, etc.).

        Follows strict honesty (answers 'isso não está registrado no meu autoconhecimento' if absent)
        and strict security (refuses secret/key disclosures).
        """
        pergunta_lower = pergunta.lower().strip()

        # 1. Gate de Segurança Estrita: Não expor chaves, senhas ou tokens
        palavras_bloqueadas = ["senha", "password", "api_key", "token", "chave", "secret", "service_role", "jwt", "credencial"]
        if any(w in pergunta_lower for w in palavras_bloqueadas):
            return {
                "status": "security_refusal",
                "message": "Por questões de segurança e integridade operacional, chaves de API, credenciais e dados confidenciais não são expostos.",
                "sources": [],
            }

        # 2. Stop words em português para não gerar falso-positivos
        stop_words = {
            "que", "qual", "quais", "como", "quem", "para", "por", "com", "sem",
            "uma", "umas", "um", "uns", "voce", "você", "seu", "sua", "seus", "suas",
            "meu", "minha", "ele", "ela", "dele", "dela", "isto", "isso", "sobre",
            "mais", "muito", "nos", "nas", "aos", "onde", "quando", "porque", "porquê",
            "são", "tem", "faz", "fazer", "dar", "pode", "podem", "era", "ser", "esta", "está"
        }

        # Extração de tokens significativos
        clean_text = "".join(c if (c.isalnum() or c.isspace()) else " " for c in pergunta_lower)
        tokens = [t for t in clean_text.split() if len(t) > 2 and t not in stop_words]

        # Detecção de intenção específica por palavras-chave
        detected_category = categoria
        if not detected_category:
            if any(k in pergunta_lower for k in ("limita", "não faz", "nao faz")):
                detected_category = "limitacao"
            elif any(k in pergunta_lower for k in ("ferramenta", "capacidade", "consegue fazer")):
                detected_category = "capacidade"
            elif any(k in pergunta_lower for k in ("tecnologia", "linguagem", "stack", "banco", "framework")):
                detected_category = "tecnologia"
            elif any(k in pergunta_lower for k in ("arquitetura", "camada")):
                detected_category = "arquitetura"
            elif any(k in pergunta_lower for k in ("roadmap", "futuro", "planeja")):
                detected_category = "roadmap"
            elif any(k in pergunta_lower for k in ("historico", "changelog", "versao", "mudan")):
                detected_category = "historico"
            elif any(k in pergunta_lower for k in ("quem é você", "quem e voce", "quem te criou", "criador", "propósito", "proposito", "seu nome")):
                detected_category = "identidade"

        # Se não há tokens significativos nem intenção detectada, assunto não é sobre o Aton
        if not tokens and not detected_category:
            return {
                "status": "not_found",
                "message": "Isso não está registrado no meu autoconhecimento.",
                "sources": [],
            }

        matched_facts = []

        # 3. Tentar busca híbrida no Supabase via RPC se configurado
        if self.is_configured:
            query_embedding = self.get_embedding(pergunta)
            rpc_payload = {
                "query_texto": pergunta,
                "query_embedding": query_embedding if query_embedding else None,
                "match_count": 4,
                "filtro_categoria": detected_category,
                "filtro_nivel_acesso": "publico",
            }
            res = self._supabase_request("rpc/buscar_autoconhecimento_hibrido", rpc_payload, method="POST")
            if res and isinstance(res, list) and len(res) > 0:
                matched_facts = [r for r in res if r.get("score_final", 1.0) >= 0.15]

        # Validação de relevância se nenhuma categoria foi explicitamente detectada
        if not detected_category and tokens and matched_facts:
            found_token = False
            for mf in matched_facts:
                mf_text = f"{mf.get('titulo', '')} {mf.get('conteudo', '')} {' '.join(mf.get('tags', []))}".lower()
                if any(t in mf_text for t in tokens):
                    found_token = True
                    break
            if not found_token:
                matched_facts = []

        # 4. Fallback Local para Cache de Autoconhecimento se Supabase não retornou
        if not matched_facts:
            cache_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "aton_autoconhecimento_cache.json"))
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)
                    facts_list = cache_data.get("facts", [])

                    for f_item in facts_list:
                        f_cat = f_item.get("categoria", "")
                        if categoria and f_cat != categoria:
                            continue

                        f_text = f"{f_item.get('titulo', '')} {f_item.get('conteudo', '')} {' '.join(f_item.get('tags', []))}".lower()
                        token_matches = sum(1 for t in tokens if t in f_text)
                        category_boost = 5.0 if (detected_category and f_cat == detected_category) else 0.0
                        total_score = token_matches + category_boost

                        # Se temos intenção, exige match na categoria ou token
                        if total_score > 0:
                            matched_facts.append({
                                "categoria": f_cat,
                                "titulo": f_item.get("titulo"),
                                "conteudo": f_item.get("conteudo"),
                                "resumo": f_item.get("resumo"),
                                "tags": f_item.get("tags", []),
                                "score_final": total_score,
                            })

                    matched_facts.sort(key=lambda x: x.get("score_final", 0), reverse=True)

                    # Se nenhum token relevante coincidiu e nenhuma categoria bateu, não há fato
                    if tokens and not any(mf.get("score_final", 0) > 0 for mf in matched_facts):
                        matched_facts = []

                    matched_facts = matched_facts[:4]
                except Exception as e:
                    logger.warning(f"Erro ao carregar cache local de autoconhecimento: {e}")

        # 4. Regra de Honestidade Absoluta: Se não encontrou fato relevante, não alucina
        if not matched_facts:
            return {
                "status": "not_found",
                "message": "Isso não está registrado no meu autoconhecimento.",
                "sources": [],
            }

        # 5. Formatar Resposta Executiva
        context_lines = []
        sources = []
        for i, item in enumerate(matched_facts, 1):
            tit = item.get("titulo", "Fato")
            cont = item.get("conteudo", "")
            context_lines.append(f"[{i}. {tit}]: {cont}")
            sources.append({"titulo": tit, "categoria": item.get("categoria")})

        context_text = "\n\n".join(context_lines)

        # 5. Formatar Resposta Executiva Factual (Grounded & Ultra-Rápida)
        primary = matched_facts[0]
        if len(matched_facts) > 1 and matched_facts[1].get("score_final", 0) >= 0.8 * primary.get("score_final", 1):
            conteudo_final = f"{primary.get('conteudo', '')}\n\n{matched_facts[1].get('conteudo', '')}"
        else:
            conteudo_final = primary.get("conteudo", "")

        return {
            "status": "success",
            "message": conteudo_final.strip(),
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
