-- ==============================================================================
-- Aton Segundo Cérebro - Rollback da Migration 08
-- ==============================================================================

DROP FUNCTION IF EXISTS public.hard_delete_memoria(UUID, BOOLEAN);
DROP FUNCTION IF EXISTS public.soft_delete_memoria(UUID);

-- Restaurar buscar_memoria_hibrida anterior
CREATE OR REPLACE FUNCTION public.buscar_memoria_hibrida(
    query_texto TEXT,
    query_embedding vector(768),
    match_count INT DEFAULT 5,
    filtro_tipo VARCHAR DEFAULT NULL,
    filtro_projeto_id UUID DEFAULT NULL,
    filtro_importancia_min INT DEFAULT 1
)
RETURNS TABLE (
    id UUID,
    tipo VARCHAR,
    assunto VARCHAR,
    conteudo TEXT,
    resumo TEXT,
    tags TEXT[],
    importancia INT,
    fonte VARCHAR,
    projeto_id UUID,
    cliente_id UUID,
    data_fato TIMESTAMPTZ,
    score_similaridade FLOAT,
    score_texto FLOAT,
    score_final FLOAT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    RETURN QUERY
    WITH busca_semantica AS (
        SELECT
            m.id,
            1 - (m.embedding <=> query_embedding) AS sim_score
        FROM public.memoria_longo_prazo m
        WHERE m.embedding IS NOT NULL
        ORDER BY m.embedding <=> query_embedding
        LIMIT match_count * 3
    ),
    busca_textual AS (
        SELECT
            m.id,
            ts_rank_cd(m.busca_texto, plainto_tsquery('portuguese', query_texto)) AS text_score
        FROM public.memoria_longo_prazo m
        WHERE m.busca_texto @@ plainto_tsquery('portuguese', query_texto)
        LIMIT match_count * 3
    )
    SELECT
        m.id,
        m.tipo,
        m.assunto,
        m.conteudo,
        m.resumo,
        m.tags,
        m.importancia,
        m.fonte,
        m.projeto_id,
        m.cliente_id,
        m.data_fato,
        COALESCE(bs.sim_score, 0.0)::FLOAT AS score_similaridade,
        COALESCE(bt.text_score, 0.0)::FLOAT AS score_texto,
        (
            (COALESCE(bs.sim_score, 0.0) * 0.65) +
            (LEAST(COALESCE(bt.text_score, 0.0), 1.0) * 0.35) +
            ((m.importancia - 1) * 0.03)
        )::FLOAT AS score_final
    FROM public.memoria_longo_prazo m
    LEFT JOIN busca_semantica bs ON m.id = bs.id
    LEFT JOIN busca_textual bt ON m.id = bt.id
    WHERE
        (bs.sim_score IS NOT NULL OR bt.text_score IS NOT NULL)
        AND (filtro_tipo IS NULL OR m.tipo = filtro_tipo)
        AND (filtro_projeto_id IS NULL OR m.projeto_id = filtro_projeto_id)
        AND (m.importancia >= filtro_importancia_min)
    ORDER BY score_final DESC
    LIMIT match_count;
END;
$$;
