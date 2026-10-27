// ==============================================================================
// Aton Segundo Cérebro - Edge Function: Memória Consolidada (Curto -> Longo Prazo)
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

    // 1. Buscar sessões de conversa ainda não consolidadas
    const { data: sessoes, error: errSessoes } = await supabase
      .from("conversas_sessao")
      .select("id, iniciada_em")
      .eq("consolidada", false)
      .limit(5);

    if (errSessoes) throw errSessoes;
    if (!sessoes || sessoes.length === 0) {
      return new Response(JSON.stringify({ status: "idle", message: "Nenhuma sessão pendente de consolidação." }), { headers: corsHeaders });
    }

    const relatorioConsolidacao = [];

    for (const sessao of sessoes) {
      // Buscar turnos de conversa da sessão
      const { data: turnos } = await supabase
        .from("turnos_conversa")
        .select("papel, conteudo, timestamp_turno")
        .eq("sessao_id", sessao.id)
        .order("timestamp_turno", { ascending: true });

      if (!turnos || turnos.length === 0) {
        await supabase.from("conversas_sessao").update({ consolidada: true }).eq("id", sessao.id);
        continue;
      }

      // Transcrição concatenada
      const dialogoTexto = turnos.map((t: any) => `${t.papel.toUpperCase()}: ${t.conteudo}`).join("\n");

      // Sintetizar fatos duradouros com Gemini Flash
      if (!geminiApiKey) continue;

      const promptExtracao = `Você é o analisador cognitivo do assistente Aton.
Analise a transcrição de diálogo abaixo entre o Criador e o Aton:

${dialogoTexto}

Identifique os fatos permanentes, preferências, atualizações de projetos (ex: Alta Restauração, Siena 2006, agência digital), clientes ou tarefas mencionadas.
Descarte saudações vazias e ruídos.

Responda EXCLUSIVAMENTE em formato JSON (um array de objetos):
[
  {
    "tipo": "fato" | "regra" | "projeto" | "cliente" | "preferencia",
    "assunto": "título curto do fato",
    "conteudo": "descrição completa com todos os detalhes e contexto",
    "tags": ["tag1", "tag2"],
    "importancia": 1 a 5
  }
]
Se não houver fatos duráveis, retorne [].`;

      const resp = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${geminiApiKey}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            contents: [{ parts: [{ text: promptExtracao }] }],
          }),
        }
      );
      const dataJson = await resp.json();
      const rawText = dataJson?.candidates?.[0]?.content?.parts?.[0]?.text || "[]";
      const cleanJson = rawText.replace(/```json/g, "").replace(/```/g, "").trim();

      let fatosExtraidos = [];
      try {
        fatosExtraidos = JSON.parse(cleanJson);
      } catch (e) {
        console.error("Falha ao parsear JSON de fatos:", e);
        continue;
      }

      // 2. Deduplicação e Atualização Inteligente
      let fatosInseridos = 0;
      let fatosAtualizados = 0;

      for (const fato of fatosExtraidos) {
        const textToEmbed = `${fato.assunto}: ${fato.conteudo}`;
        // Gerar embedding do fato
        const embResp = await fetch(
          `https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key=${geminiApiKey}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              model: "models/text-embedding-004",
              content: { parts: [{ text: textToEmbed }] },
            }),
          }
        );
        const embData = await embResp.json();
        const embedding = embData?.embedding?.values || [];

        // Verificar similaridade com memórias existentes
        if (embedding.length > 0) {
          const { data: existentes } = await supabase.rpc("buscar_memoria_hibrida", {
            query_texto: fato.assunto,
            query_embedding: embedding,
            match_count: 1,
          });

          // Se similaridade semântica >= 0.88, atualiza a memória existente (deduplicação)
          if (existentes && existentes.length > 0 && existentes[0].score_similaridade >= 0.88) {
            const memExistente = existentes[0];
            await supabase
              .from("memoria_longo_prazo")
              .update({
                conteudo: `${memExistente.conteudo}\n[Atualização]: ${fato.conteudo}`,
                tags: Array.from(new Set([...(memExistente.tags || []), ...(fato.tags || [])])),
                importancia: Math.max(memExistente.importancia, fato.importancia || 3),
                updated_at: new Date().toISOString(),
              })
              .eq("id", memExistente.id);
            fatosAtualizados++;
            continue;
          }
        }

        // Se for novidade (< 0.88 de similaridade), insere nova memória permanente
        await supabase.from("memoria_longo_prazo").insert([
          {
            tipo: fato.tipo || "fato",
            assunto: fato.assunto,
            conteudo: fato.conteudo,
            resumo: fato.conteudo.slice(0, 150),
            tags: fato.tags || [],
            importancia: fato.importancia || 3,
            embedding: embedding.length ? embedding : null,
            fonte: "consolidacao_automatica",
          },
        ]);
        fatosInseridos++;
      }

      // Marcar sessão como consolidada
      await supabase
        .from("conversas_sessao")
        .update({
          consolidada: true,
          encerrada_em: new Date().toISOString(),
          resumo_sessao: `Consolidada com ${fatosInseridos} novos fatos e ${fatosAtualizados} atualizações.`,
        })
        .eq("id", sessao.id);

      relatorioConsolidacao.push({
        sessao_id: sessao.id,
        fatos_inseridos: fatosInseridos,
        fatos_atualizados: fatosAtualizados,
      });
    }

    return new Response(JSON.stringify({ status: "success", consolidacao: relatorioConsolidacao }), {
      headers: corsHeaders,
    });
  } catch (err: any) {
    return new Response(JSON.stringify({ error: err.message }), { status: 500, headers: corsHeaders });
  }
});
