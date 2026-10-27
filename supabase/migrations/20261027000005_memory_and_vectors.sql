-- ==============================================================================
-- Aton Segundo Cérebro - Migration 05: Memória Curto/Longo Prazo, Vetores & Busca Híbrida
-- ==============================================================================

-- 1. Memória de Curto Prazo (Sessões e Turnos de Conversa)
CREATE TABLE IF NOT EXISTS public.conversas_sessao (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    iniciada_em TIMESTAMPTZ DEFAULT now(),
    encerrada_em TIMESTAMPTZ,
    consolidada BOOLEAN DEFAULT false,
    resumo_sessao TEXT,
    metadados JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_conversas_sessao_status ON public.conversas_sessao (consolidada, iniciada_em DESC);

CREATE TABLE IF NOT EXISTS public.turnos_conversa (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sessao_id UUID NOT NULL REFERENCES public.conversas_sessao(id) ON DELETE CASCADE,
    papel VARCHAR(20) NOT NULL, -- 'usuario', 'aton'
    conteudo TEXT NOT NULL,
    audio_rms DOUBLE PRECISION,
    metadados JSONB DEFAULT '{}'::jsonb,
    timestamp_turno TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_turnos_sessao ON public.turnos_conversa (sessao_id, timestamp_turno ASC);

-- 2. Memória Permanente de Longo Prazo (Vetorizada & Indexada)
CREATE TABLE IF NOT EXISTS public.memoria_longo_prazo (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo VARCHAR(50) NOT NULL DEFAULT 'fato', -- fato, regra, projeto, cliente, preferencia, decisao, nota
    assunto VARCHAR(255) NOT NULL,
    conteudo TEXT NOT NULL,
    resumo TEXT,
    tags TEXT[] DEFAULT '{}',
    importancia INT CHECK (importancia BETWEEN 1 AND 5) DEFAULT 3,
    embedding vector(768), -- Vetores de 768 dimensões gerados pela API Gemini (text-embedding-004)
    busca_texto tsvector,
    fonte VARCHAR(100) DEFAULT 'conversa_aton',
    projeto_id UUID REFERENCES public.projetos(id) ON DELETE SET NULL,
    cliente_id UUID REFERENCES public.clientes(id) ON DELETE SET NULL,
    tarefa_id UUID REFERENCES public.tarefas(id) ON DELETE SET NULL,
    metadados JSONB DEFAULT '{}'::jsonb,
    data_fato TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Trigger para atualização automática do tsvector de busca textual em português
CREATE OR REPLACE FUNCTION public.memoria_atualizar_busca_texto()
RETURNS TRIGGER AS $$
BEGIN
    NEW.busca_texto := to_tsvector(
        'portuguese',
        coalesce(NEW.assunto, '') || ' ' ||
        coalesce(NEW.conteudo, '') || ' ' ||
        coalesce(NEW.resumo, '') || ' ' ||
        coalesce(array_to_string(NEW.tags, ' '), '')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_memoria_atualizar_busca_texto ON public.memoria_longo_prazo;
CREATE TRIGGER trg_memoria_atualizar_busca_texto
BEFORE INSERT OR UPDATE ON public.memoria_longo_prazo
FOR EACH ROW
EXECUTE FUNCTION public.memoria_atualizar_busca_texto();

-- Índices HNSW para Similaridade Cosseno de Altíssima Velocidade
CREATE INDEX IF NOT EXISTS idx_memoria_embedding_hnsw
ON public.memoria_longo_prazo
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Índice GIN para Busca Textual Full-Text Search em Português
CREATE INDEX IF NOT EXISTS idx_memoria_busca_texto_gin
ON public.memoria_longo_prazo
USING gin (busca_texto);

CREATE INDEX IF NOT EXISTS idx_memoria_tipo ON public.memoria_longo_prazo (tipo);
CREATE INDEX IF NOT EXISTS idx_memoria_importancia ON public.memoria_longo_prazo (importancia DESC);
CREATE INDEX IF NOT EXISTS idx_memoria_projeto ON public.memoria_longo_prazo (projeto_id);

-- 3. Função PostgreSQL para Busca Híbrida Inteligente (Semântica + Palavra-Chave)
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
            -- Fórmula de Fusão Ponderada: 65% semântica + 35% texto exato + bônus de importância
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
