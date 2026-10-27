-- ==============================================================================
-- Aton Segundo Cérebro - Rollback da Migration 07 (Offline Sync Preparation)
-- ==============================================================================
-- Este script desfaz EXCLUSIVAMENTE o que foi adicionado pela Migration 07,
-- preservando 100% da estrutura e dos dados das Migrations 01 a 06.

-- 1. Remover Módulo modo_offline
DELETE FROM public.modulos_sistema WHERE slug = 'modo_offline';

-- 2. Remover Índices Criados na Migration 07
DROP INDEX IF EXISTS public.idx_memoria_updated_at;
DROP INDEX IF EXISTS public.idx_clientes_updated_at;
DROP INDEX IF EXISTS public.idx_tarefas_updated_at;
DROP INDEX IF EXISTS public.idx_agenda_updated_at;
DROP INDEX IF EXISTS public.idx_projetos_updated_at;
DROP INDEX IF EXISTS public.idx_memoria_active;
DROP INDEX IF EXISTS public.idx_clientes_active;
DROP INDEX IF EXISTS public.idx_tarefas_active;
DROP INDEX IF EXISTS public.idx_agenda_active;
DROP INDEX IF EXISTS public.idx_memoria_emb_pendente;
DROP INDEX IF EXISTS public.idx_sync_log_dispositivo;

-- 3. Remover Triggers de updated_at
DO $$
DECLARE
    tbl text;
    tabelas_array text[] := ARRAY[
        'perfil_criador', 'historico_decisoes', 'clientes', 'contatos_clientes',
        'interacoes_clientes', 'projetos', 'etapas_projeto', 'ideias_projetos',
        'tarefas', 'dependencias_tarefas', 'agenda_eventos', 'lembretes_agenda',
        'base_conhecimento', 'conversas_sessao', 'turnos_conversa', 'memoria_longo_prazo',
        'modulos_sistema', 'configuracao_sistema'
    ];
BEGIN
    FOREACH tbl IN ARRAY tabelas_array LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_updated_at_%I ON public.%I;', tbl, tbl);
    END LOOP;
END $$;

-- 4. Remover Função handle_updated_at
DROP FUNCTION IF EXISTS public.handle_updated_at();

-- 5. Remover Colunas de memoria_longo_prazo
ALTER TABLE public.memoria_longo_prazo
    DROP COLUMN IF EXISTS embedding_pendente,
    DROP COLUMN IF EXISTS sensivel,
    DROP COLUMN IF EXISTS status,
    DROP COLUMN IF EXISTS versao,
    DROP COLUMN IF EXISTS memoria_origem_id;

-- 6. Remover Colunas de Controle de Sincronização
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
        EXECUTE format('ALTER TABLE public.%I DROP COLUMN IF EXISTS deleted_at;', tbl);
        EXECUTE format('ALTER TABLE public.%I DROP COLUMN IF EXISTS origem_dispositivo;', tbl);
    END LOOP;
END $$;

-- 7. Remover Novas Tabelas (sync_log e configuracao_sistema)
DROP TABLE IF EXISTS public.sync_log CASCADE;
DROP TABLE IF EXISTS public.configuracao_sistema CASCADE;
