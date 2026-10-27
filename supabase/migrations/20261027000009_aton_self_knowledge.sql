-- ==============================================================================
-- Aton Segundo Cérebro - Migration 09: Módulo de Autoconhecimento do Aton & Changelog
-- ==============================================================================
-- Armazena fatos verificáveis e gerados sobre a identidade, capacidades,
-- arquitetura, tecnologias, limitações e changelog do próprio assistente Aton.

-- 1. Tabela Principal de Fatos de Autoconhecimento
CREATE TABLE IF NOT EXISTS public.aton_autoconhecimento (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    categoria VARCHAR(50) NOT NULL, -- identidade, tecnologia, arquitetura, capacidade, limitacao, roadmap, historico, faq
    titulo VARCHAR(255) NOT NULL,
    conteudo TEXT NOT NULL,
    resumo TEXT,
    tags TEXT[] DEFAULT '{}',
    nivel_acesso VARCHAR(20) DEFAULT 'publico', -- publico, interno
    fonte VARCHAR(50) DEFAULT 'gerado_automaticamente', -- gerado_automaticamente, manual
    versao_sistema VARCHAR(20) DEFAULT '0.8.0',
    versao INT DEFAULT 1,
    fato_origem_id UUID REFERENCES public.aton_autoconhecimento(id) ON DELETE SET NULL,
    status VARCHAR(30) DEFAULT 'ativa', -- ativa, substituida, arquivada
    ativo BOOLEAN DEFAULT true,
    embedding vector(768),
    embedding_pendente BOOLEAN DEFAULT false,
    busca_texto tsvector,
    metadados JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    deleted_at TIMESTAMPTZ NULL,
    origem_dispositivo TEXT DEFAULT 'windows_pc'
);

-- Trigger para Busca Textual em Português
CREATE OR REPLACE FUNCTION public.aton_atualizar_busca_autoconhecimento()
RETURNS TRIGGER AS $$
BEGIN
    NEW.busca_texto := to_tsvector(
        'portuguese',
        coalesce(NEW.titulo, '') || ' ' ||
        coalesce(NEW.conteudo, '') || ' ' ||
        coalesce(NEW.resumo, '') || ' ' ||
        coalesce(array_to_string(NEW.tags, ' '), '')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = public, pg_temp;

DROP TRIGGER IF EXISTS trg_busca_texto_autoconhecimento ON public.aton_autoconhecimento;
CREATE TRIGGER trg_busca_texto_autoconhecimento
    BEFORE INSERT OR UPDATE ON public.aton_autoconhecimento
    FOR EACH ROW EXECUTE FUNCTION public.aton_atualizar_busca_autoconhecimento();

-- Trigger de updated_at
DROP TRIGGER IF EXISTS trg_updated_at_autoconhecimento ON public.aton_autoconhecimento;
CREATE TRIGGER trg_updated_at_autoconhecimento
    BEFORE UPDATE ON public.aton_autoconhecimento
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- Trigger de Auditoria
DROP TRIGGER IF EXISTS trg_audit_autoconhecimento ON public.aton_autoconhecimento;
CREATE TRIGGER trg_audit_autoconhecimento
    AFTER INSERT OR UPDATE OR DELETE ON public.aton_autoconhecimento
    FOR EACH ROW EXECUTE FUNCTION public.processar_auditoria_trigger();

-- Índices HNSW e GIN
CREATE INDEX IF NOT EXISTS idx_autoconhecimento_embedding_hnsw
    ON public.aton_autoconhecimento
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_autoconhecimento_busca_gin
    ON public.aton_autoconhecimento
    USING gin (busca_texto);

CREATE INDEX IF NOT EXISTS idx_autoconhecimento_cat_status
    ON public.aton_autoconhecimento (categoria, status);

CREATE INDEX IF NOT EXISTS idx_autoconhecimento_active
    ON public.aton_autoconhecimento (id)
    WHERE deleted_at IS NULL AND status = 'ativa';

-- 2. Tabela de Changelog e Linha do Tempo de Atualizações
CREATE TABLE IF NOT EXISTS public.aton_changelog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data TIMESTAMPTZ DEFAULT now(),
    versao VARCHAR(20) NOT NULL,
    titulo VARCHAR(200) NOT NULL,
    descricao TEXT NOT NULL,
    tipo VARCHAR(50) DEFAULT 'migration', -- migration, nova_tool, ajuste_seguranca, refatoracao
    referencia VARCHAR(100),
    metadados JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    origem_dispositivo TEXT DEFAULT 'windows_pc'
);

CREATE INDEX IF NOT EXISTS idx_changelog_versao ON public.aton_changelog (versao);
CREATE INDEX IF NOT EXISTS idx_changelog_data ON public.aton_changelog (data DESC);

-- 3. Função RPC de Busca Híbrida de Autoconhecimento
CREATE OR REPLACE FUNCTION public.buscar_autoconhecimento_hibrido(
    query_texto TEXT,
    query_embedding vector(768),
    match_count INT DEFAULT 5,
    filtro_categoria VARCHAR DEFAULT NULL,
    filtro_nivel_acesso VARCHAR DEFAULT 'publico'
)
RETURNS TABLE (
    id UUID,
    categoria VARCHAR,
    titulo VARCHAR,
    conteudo TEXT,
    resumo TEXT,
    tags TEXT[],
    nivel_acesso VARCHAR,
    fonte VARCHAR,
    versao_sistema VARCHAR,
    versao INT,
    data_atualizacao TIMESTAMPTZ,
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
            a.id,
            1 - (a.embedding <=> query_embedding) AS sim_score
        FROM public.aton_autoconhecimento a
        WHERE a.embedding IS NOT NULL
          AND a.deleted_at IS NULL
          AND a.status = 'ativa'
          AND (filtro_nivel_acesso = 'interno' OR a.nivel_acesso = 'publico')
        ORDER BY a.embedding <=> query_embedding
        LIMIT match_count * 3
    ),
    busca_textual AS (
        SELECT
            a.id,
            ts_rank_cd(a.busca_texto, plainto_tsquery('portuguese', query_texto)) AS text_score
        FROM public.aton_autoconhecimento a
        WHERE a.busca_texto @@ plainto_tsquery('portuguese', query_texto)
          AND a.deleted_at IS NULL
          AND a.status = 'ativa'
          AND (filtro_nivel_acesso = 'interno' OR a.nivel_acesso = 'publico')
        LIMIT match_count * 3
    )
    SELECT
        a.id,
        a.categoria,
        a.titulo,
        a.conteudo,
        a.resumo,
        a.tags,
        a.nivel_acesso,
        a.fonte,
        a.versao_sistema,
        a.versao,
        a.updated_at AS data_atualizacao,
        COALESCE(bs.sim_score, 0.0)::FLOAT AS score_similaridade,
        COALESCE(bt.text_score, 0.0)::FLOAT AS score_texto,
        (
            (COALESCE(bs.sim_score, 0.0) * 0.65) +
            (LEAST(COALESCE(bt.text_score, 0.0), 1.0) * 0.35)
        )::FLOAT AS score_final
    FROM public.aton_autoconhecimento a
    LEFT JOIN busca_semantica bs ON a.id = bs.id
    LEFT JOIN busca_textual bt ON a.id = bt.id
    WHERE
        a.deleted_at IS NULL
        AND a.status = 'ativa'
        AND (filtro_nivel_acesso = 'interno' OR a.nivel_acesso = 'publico')
        AND (bs.sim_score IS NOT NULL OR bt.text_score IS NOT NULL)
        AND (filtro_categoria IS NULL OR a.categoria = filtro_categoria)
    ORDER BY score_final DESC
    LIMIT match_count;
END;
$$;

-- 4. Registrar Módulo em modulos_sistema
INSERT INTO public.modulos_sistema (
    slug, nome, descricao, versao, ativo, tabelas_principais, pontos_integracao, metadados
)
VALUES (
    'autoconhecimento',
    'Autoconhecimento do Aton',
    'Base de fatos reais, tecnologias, ferramentas e limitações sobre o próprio assistente com introspecção dinâmica.',
    '1.0.0',
    true,
    ARRAY['aton_autoconhecimento', 'aton_changelog'],
    '{"gemini_live": true, "introspection": true}'::jsonb,
    '{"status": "ativo"}'::jsonb
)
ON CONFLICT (slug) DO UPDATE
SET ativo = true,
    versao = '1.0.0',
    updated_at = now();

-- 5. Habilitar e Configurar RLS (Row Level Security)
ALTER TABLE public.aton_autoconhecimento ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aton_changelog ENABLE ROW LEVEL SECURITY;

-- Políticas para aton_autoconhecimento
DROP POLICY IF EXISTS auto_read_policy ON public.aton_autoconhecimento;
CREATE POLICY auto_read_policy ON public.aton_autoconhecimento
    FOR SELECT TO anon, authenticated, service_role USING (true);

DROP POLICY IF EXISTS auto_write_policy ON public.aton_autoconhecimento;
CREATE POLICY auto_write_policy ON public.aton_autoconhecimento
    FOR ALL TO service_role, authenticated, anon USING (true) WITH CHECK (true);

-- Políticas para aton_changelog
DROP POLICY IF EXISTS changelog_read_policy ON public.aton_changelog;
CREATE POLICY changelog_read_policy ON public.aton_changelog
    FOR SELECT TO anon, authenticated, service_role USING (true);

DROP POLICY IF EXISTS changelog_write_policy ON public.aton_changelog;
CREATE POLICY changelog_write_policy ON public.aton_changelog
    FOR ALL TO service_role, authenticated, anon USING (true) WITH CHECK (true);
