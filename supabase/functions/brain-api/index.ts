// ==============================================================================
// Aton Segundo Cérebro - Supabase Edge Function: Unified Brain API (Deno/TypeScript)
// ==============================================================================

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.38.4";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Content-Type": "application/json",
};

serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL") || "";
    const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
    const geminiApiKey = Deno.env.get("GEMINI_API_KEY") || "";

    const supabase = createClient(supabaseUrl, supabaseKey);
    const url = new URL(req.url);
    const action = url.pathname.split("/").pop() || "";
    const body = req.method === "POST" ? await req.json() : {};

    // Helper: Gerar Embedding de 768 dimensões com Gemini text-embedding-004
    async function generateEmbedding(text: string): Promise<number[]> {
      if (!geminiApiKey || !text) return [];
      try {
        const resp = await fetch(
          `https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key=${geminiApiKey}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              model: "models/text-embedding-004",
              content: { parts: [{ text }] },
            }),
          }
        );
        const data = await resp.json();
        return data?.embedding?.values || [];
      } catch (err) {
        console.error("Erro ao gerar embedding:", err);
        return [];
      }
    }

    // 1. AÇÃO: Salvar Memória Permanente
    if (action === "save_memory") {
      const { tipo, assunto, conteudo, resumo, tags, importancia, projeto_id, cliente_id, fonte } = body;
      const textToEmbed = `${assunto}: ${conteudo} ${tags ? tags.join(" ") : ""}`;
      const embedding = await generateEmbedding(textToEmbed);

      const { data, error } = await supabase.from("memoria_longo_prazo").insert([
        {
          tipo: tipo || "fato",
          assunto,
          conteudo,
          resumo: resumo || conteudo.slice(0, 150),
          tags: tags || [],
          importancia: importancia || 3,
          embedding: embedding.length ? embedding : null,
          projeto_id: projeto_id || null,
          cliente_id: cliente_id || null,
          fonte: fonte || "conversa_aton",
        },
      ]).select().single();

      if (error) throw error;
      return new Response(JSON.stringify({ status: "success", memory: data }), { headers: corsHeaders });
    }

    // 2. AÇÃO: Busca Híbrida Inteligente
    if (action === "search_memory") {
      const { query, match_count = 5, tipo, projeto_id } = body;
      const queryEmbedding = await generateEmbedding(query);

      const { data, error } = await supabase.rpc("buscar_memoria_hibrida", {
        query_texto: query,
        query_embedding: queryEmbedding.length ? queryEmbedding : null,
        match_count,
        filtro_tipo: tipo || null,
        filtro_projeto_id: projeto_id || null,
      });

      if (error) throw error;
      return new Response(JSON.stringify({ status: "success", results: data || [] }), { headers: corsHeaders });
    }

    // 3. AÇÃO: Perguntar ao Cérebro (Q&A com RAG e Citação de Fontes e Datas)
    if (action === "ask_brain") {
      const { question } = body;
      const queryEmbedding = await generateEmbedding(question);

      const { data: memories, error } = await supabase.rpc("buscar_memoria_hibrida", {
        query_texto: question,
        query_embedding: queryEmbedding.length ? queryEmbedding : null,
        match_count: 5,
      });

      if (error) throw error;

      if (!memories || memories.length === 0 || (memories[0].score_final < 0.25)) {
        return new Response(
          JSON.stringify({
            status: "not_found",
            message: "Não encontrei nenhuma memória registrada sobre isso em minha base permanente.",
            sources: [],
          }),
          { headers: corsHeaders }
        );
      }

      // Sintetizar contexto para responder
      const contextBlocks = memories.map((m: any, i: number) => {
        const dataStr = new Date(m.data_fato).toLocaleDateString("pt-BR");
        return `[Fonte ${i + 1} - Data: ${dataStr} | Assunto: ${m.assunto}]: ${m.conteudo}`;
      }).join("\n\n");

      // Gerar resposta sintetizada via Gemini Flash
      let answer = "";
      if (geminiApiKey) {
        const prompt = `Você é o Aton, o assistente pessoal do seu criador. 
Com base EXCLUSIVAMENTE nas seguintes memórias recuperadas do seu Segundo Cérebro:
${contextBlocks}

Responda à pergunta do usuário de forma direta, executiva e precisa em português do Brasil: "${question}".
Cite a data e o contexto quando relevante. Se a informação não estiver nas fontes acima, diga categoricamente que não possui esse registro.`;

        const resp = await fetch(
          `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${geminiApiKey}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              contents: [{ parts: [{ text: prompt }] }],
            }),
          }
        );
        const dataJson = await resp.json();
        answer = dataJson?.candidates?.[0]?.content?.parts?.[0]?.text || "";
      }

      return new Response(
        JSON.stringify({
          status: "success",
          answer: answer || contextBlocks,
          memories,
        }),
        { headers: corsHeaders }
      );
    }

    // 4. AÇÃO: Criar e Buscar Clientes
    if (action === "create_client") {
      const { nome, segmento, valor_mensal, entregaveis, observacoes } = body;
      const { data, error } = await supabase.from("clientes").insert([
        {
          nome,
          segmento,
          valor_mensal_recorrente: valor_mensal || 0.0,
          entregaveis_prometidos: entregaveis || [],
          observacoes,
        },
      ]).select().single();
      if (error) throw error;
      return new Response(JSON.stringify({ status: "success", client: data }), { headers: corsHeaders });
    }

    // 5. AÇÃO: Criar e Concluir Tarefas
    if (action === "create_task") {
      const { titulo, prioridade, prazo, projeto_id, cliente_id } = body;
      const { data, error } = await supabase.from("tarefas").insert([
        {
          titulo,
          prioridade: prioridade || "media",
          prazo_fatal: prazo || null,
          projeto_id: projeto_id || null,
          cliente_id: cliente_id || null,
        },
      ]).select().single();
      if (error) throw error;
      return new Response(JSON.stringify({ status: "success", task: data }), { headers: corsHeaders });
    }

    // 6. AÇÃO: Resumo do Dia Consolidado
    if (action === "daily_summary") {
      const today = new Date().toISOString().split("T")[0];
      const { data: agenda } = await supabase
        .from("agenda_eventos")
        .select("*")
        .gte("data_inicio", `${today}T00:00:00Z`)
        .lte("data_inicio", `${today}T23:59:59Z`)
        .order("data_inicio", { ascending: true });

      const { data: tarefas } = await supabase
        .from("tarefas")
        .select("*")
        .in("status", ["pendente", "em_andamento"])
        .order("prazo_fatal", { ascending: true })
        .limit(10);

      const { data: clientesPendentes } = await supabase
        .from("clientes")
        .select("nome, pendencias_abertas")
        .not("pendencias_abertas", "eq", "{}")
        .limit(5);

      return new Response(
        JSON.stringify({
          status: "success",
          summary: {
            agenda: agenda || [],
            tarefas: tarefas || [],
            clientes_com_pendencias: clientesPendentes || [],
          },
        }),
        { headers: corsHeaders }
      );
    }

    return new Response(JSON.stringify({ error: `Ação '${action}' desconhecida.` }), {
      status: 404,
      headers: corsHeaders,
    });
  } catch (err: any) {
    return new Response(JSON.stringify({ error: err.message }), {
      status: 500,
      headers: corsHeaders,
    });
  }
});
