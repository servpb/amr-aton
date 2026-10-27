-- ==============================================================================
-- Aton Segundo Cérebro - Migration 08: Funções de Soft Delete, Versionamento e Busca Filtrada
-- ==============================================================================

-- 1. Atualizar buscar_memoria_hibrida para ignorar registros com deleted_at preenchido
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
          AND m.deleted_at IS NULL
          AND m.status = 'ativa'
        ORDER BY m.embedding <=> query_embedding
        LIMIT match_count * 3
    ),
    busca_textual AS (
        SELECT
            m.id,
            ts_rank_cd(m.busca_texto, plainto_tsquery('portuguese', query_texto)) AS text_score
        FROM public.memoria_longo_prazo m
        WHERE m.busca_texto @@ plainto_tsquery('portuguese', query_texto)
          AND m.deleted_at IS NULL
          AND m.status = 'ativa'
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
            -- Fórmula ponderada: 65% semântica + 35% texto exato + bônus de importância
            (COALESCE(bs.sim_score, 0.0) * 0.65) +
            (LEAST(COALESCE(bt.text_score, 0.0), 1.0) * 0.35) +
            ((m.importancia - 1) * 0.03)
        )::FLOAT AS score_final
    FROM public.memoria_longo_prazo m
    LEFT JOIN busca_semantica bs ON m.id = bs.id
    LEFT JOIN busca_textual bt ON m.id = bt.id
    WHERE
        m.deleted_at IS NULL
        AND m.status = 'ativa'
        AND (bs.sim_score IS NOT NULL OR bt.text_score IS NOT NULL)
        AND (filtro_tipo IS NULL OR m.tipo = filtro_tipo)
        AND (filtro_projeto_id IS NULL OR m.projeto_id = filtro_projeto_id)
        AND (m.importancia >= filtro_importancia_min)
    ORDER BY score_final DESC
    LIMIT match_count;
END;
$$;

-- 2. Função de Soft Delete Segura (Arquivamento sem exclusão física)
CREATE OR REPLACE FUNCTION public.soft_delete_memoria(p_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_count INT;
BEGIN
    UPDATE public.memoria_longo_prazo
    SET deleted_at = now(),
        status = 'arquivada',
        updated_at = now()
    WHERE id = p_id AND deleted_at IS NULL;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    IF v_count > 0 THEN
        RETURN jsonb_build_object(
            'status', 'success',
            'message', 'Memória arquivada com sucesso via soft delete.',
            'id', p_id
        );
    ELSE
        RETURN jsonb_build_object(
            'status', 'not_found',
            'message', 'Registro não encontrado ou já arquivado.',
            'id', p_id
        );
    END IF;
END;
$$;

-- 3. Função de Exclusão Física Definitiva com Confirmação Obrigatória
CREATE OR REPLACE FUNCTION public.hard_delete_memoria(p_id UUID, p_confirmacao BOOLEAN)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_count INT;
BEGIN
    IF p_confirmacao IS NOT TRUE THEN
        RETURN jsonb_build_object(
            'status', 'error',
            'message', 'Exclusão definitiva recusada: confirmação explícita obrigatória não fornecida.'
        );
    END IF;

    DELETE FROM public.memoria_longo_prazo
    WHERE id = p_id;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    IF v_count > 0 THEN
        RETURN jsonb_build_object(
            'status', 'success',
            'message', 'Registro excluído definitivamente do banco.',
            'id', p_id
        );
    ELSE
        RETURN jsonb_build_object(
            'status', 'not_found',
            'message', 'Registro não localizado para exclusão definitiva.',
            'id', p_id
        );
    END IF;
END;
$$;
