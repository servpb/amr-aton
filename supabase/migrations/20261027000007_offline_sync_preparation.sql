-- ==============================================================================
-- Aton Segundo Cérebro - Migration 07: Preparação Aditiva para Modo Offline & Sync
-- ==============================================================================
-- REGRA DE OURO: Aditiva e Idempotente. Nada é removido ou renomeado.
-- Compatível com os dados existentes em produção.

-- 1. Função Genérica e Segura para Atualização Automática de updated_at
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

-- 2. Tabela de Configurações Centrais do Sistema
CREATE TABLE IF NOT EXISTS public.configuracao_sistema (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chave VARCHAR(100) UNIQUE NOT NULL,
    valor JSONB NOT NULL,
    descricao TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE public.configuracao_sistema ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS conf_read_policy ON public.configuracao_sistema;
CREATE POLICY conf_read_policy ON public.configuracao_sistema
    FOR SELECT TO anon, authenticated, service_role USING (true);

DROP POLICY IF EXISTS conf_write_policy ON public.configuracao_sistema;
CREATE POLICY conf_write_policy ON public.configuracao_sistema
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Valores padrão para o ecossistema de embeddings e busca
INSERT INTO public.configuracao_sistema (chave, valor, descricao)
VALUES
    ('embedding_model', '"gemini-embedding-001"'::jsonb, 'Modelo padrão do Gemini para vetores semânticos'),
    ('embedding_dimension', '768'::jsonb, 'Dimensionalidade fixa dos vetores pgvector'),
    ('search_min_similarity', '0.25'::jsonb, 'Limiar mínimo de relevância na busca semântica'),
    ('sync_batch_size', '50'::jsonb, 'Tamanho do lote para sincronização incremental offline-online')
ON CONFLICT (chave) DO NOTHING;

DROP TRIGGER IF EXISTS trg_updated_at_configuracao ON public.configuracao_sistema;
CREATE TRIGGER trg_updated_at_configuracao
    BEFORE UPDATE ON public.configuracao_sistema
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- 3. Tabela de Log de Sincronização (Auditoria de Sync Offline-Online)
CREATE TABLE IF NOT EXISTS public.sync_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dispositivo VARCHAR(100) NOT NULL DEFAULT 'windows_pc',
    iniciado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    finalizado_em TIMESTAMPTZ,
    enviados INT DEFAULT 0,
    recebidos INT DEFAULT 0,
    status VARCHAR(30) DEFAULT 'em_progresso', -- em_progresso, sucesso, falha
    erros JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE public.sync_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS sync_log_access_policy ON public.sync_log;
CREATE POLICY sync_log_access_policy ON public.sync_log
    FOR ALL TO anon, authenticated, service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sync_log_dispositivo ON public.sync_log (dispositivo, iniciado_em DESC);

-- 4. Adicionar Colunas de Sincronização em Todas as Tabelas de Negócio
DO $$
DECLARE
    tbl text;
    tabelas_array text[] := ARRAY[
        'perfil_criador', 'historico_decisoes', 'clientes', 'contatos_clientes',
        'interacoes_clientes', 'projetos', 'etapas_projeto', 'ideias_projetos',
        'tarefas', 'dependencias_tarefas', 'agenda_eventos', 'lembretes_agenda',
        'base_conhecimento', 'conversas_sessao', 'turnos_conversa', 'memoria_longo_prazo',
        'modulos_sistema'
    ];
BEGIN
    FOREACH tbl IN ARRAY tabelas_array LOOP
        -- Adicionar colunas se não existirem
        EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();', tbl);
        EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();', tbl);
        EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL;', tbl);
        EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS origem_dispositivo TEXT DEFAULT ''legado'';', tbl);

        -- Preenchimento retroativo em registros existentes
        EXECUTE format('UPDATE public.%I SET updated_at = created_at WHERE updated_at IS NULL;', tbl);
        EXECUTE format('UPDATE public.%I SET origem_dispositivo = ''legado'' WHERE origem_dispositivo IS NULL;', tbl);

        -- Ligar trigger de updated_at automático
        EXECUTE format('DROP TRIGGER IF EXISTS trg_updated_at_%I ON public.%I;', tbl, tbl);
        EXECUTE format('CREATE TRIGGER trg_updated_at_%I BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();', tbl, tbl);
    END LOOP;
END $$;

-- 5. Extensões Aditivas em memoria_longo_prazo
ALTER TABLE public.memoria_longo_prazo ADD COLUMN IF NOT EXISTS embedding_pendente BOOLEAN DEFAULT false;
ALTER TABLE public.memoria_longo_prazo ADD COLUMN IF NOT EXISTS sensivel BOOLEAN DEFAULT false;
ALTER TABLE public.memoria_longo_prazo ADD COLUMN IF NOT EXISTS status VARCHAR(30) DEFAULT 'ativa'; -- ativa, candidata, substituida, arquivada
ALTER TABLE public.memoria_longo_prazo ADD COLUMN IF NOT EXISTS versao INT DEFAULT 1;
ALTER TABLE public.memoria_longo_prazo ADD COLUMN IF NOT EXISTS memoria_origem_id UUID REFERENCES public.memoria_longo_prazo(id) ON DELETE SET NULL;

-- Marcar embedding_pendente = true APENAS onde embedding for nulo
UPDATE public.memoria_longo_prazo
SET embedding_pendente = true
WHERE embedding IS NULL AND (embedding_pendente IS NULL OR embedding_pendente = false);

-- 6. Índices para Otimização de Sincronização Incremental e Soft Delete
CREATE INDEX IF NOT EXISTS idx_memoria_updated_at ON public.memoria_longo_prazo (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_clientes_updated_at ON public.clientes (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tarefas_updated_at ON public.tarefas (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_agenda_updated_at ON public.agenda_eventos (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_projetos_updated_at ON public.projetos (updated_at DESC);

-- Índices parciais (WHERE deleted_at IS NULL)
CREATE INDEX IF NOT EXISTS idx_memoria_active ON public.memoria_longo_prazo (id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_clientes_active ON public.clientes (id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tarefas_active ON public.tarefas (id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_agenda_active ON public.agenda_eventos (id) WHERE deleted_at IS NULL;

-- Índice para a fila de geração de embeddings pendentes
CREATE INDEX IF NOT EXISTS idx_memoria_emb_pendente ON public.memoria_longo_prazo (id) WHERE embedding_pendente = true;

-- 7. Registrar Módulo modo_offline em modulos_sistema
INSERT INTO public.modulos_sistema (
    slug, nome, descricao, versao, ativo, tabelas_principais, pontos_integracao, metadados
)
VALUES (
    'modo_offline',
    'Modo Offline & Sincronização',
    'Preparação aditiva para sincronização bidirecional local-first com fila de pendências.',
    '0.1.0',
    false,
    ARRAY['sync_log', 'configuracao_sistema'],
    '{"local_sqlite": true, "sync_engine": true}'::jsonb,
    '{"status": "planejado"}'::jsonb
)
ON CONFLICT (slug) DO UPDATE
SET metadados = '{"status": "planejado"}'::jsonb,
    updated_at = now();

-- 8. Correção de Segurança em Funções SECURITY DEFINER (Fixar search_path)
ALTER FUNCTION public.processar_auditoria_trigger() SET search_path = public, pg_temp;
ALTER FUNCTION public.buscar_memoria_hibrida(TEXT, vector, INT, VARCHAR, UUID, INT) SET search_path = public, pg_temp;
ALTER FUNCTION public.exportar_dados_segundo_cerebro_json() SET search_path = public, pg_temp;
