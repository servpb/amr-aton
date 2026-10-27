-- ==============================================================================
-- Aton Segundo Cérebro - Rollback da Migration 09: Autoconhecimento do Aton & Changelog
-- ==============================================================================

-- 1. Remover RPC de Busca Híbrida de Autoconhecimento
DROP FUNCTION IF EXISTS public.buscar_autoconhecimento_hibrido(TEXT, vector(768), INT, VARCHAR, VARCHAR);

-- 2. Remover Triggers e Funções de Gatilho
DROP TRIGGER IF EXISTS trg_busca_texto_autoconhecimento ON public.aton_autoconhecimento;
DROP TRIGGER IF EXISTS trg_updated_at_autoconhecimento ON public.aton_autoconhecimento;
DROP TRIGGER IF EXISTS trg_audit_autoconhecimento ON public.aton_autoconhecimento;
DROP FUNCTION IF EXISTS public.aton_atualizar_busca_autoconhecimento();

-- 3. Remover Tabelas Criadas
DROP TABLE IF EXISTS public.aton_autoconhecimento CASCADE;
DROP TABLE IF EXISTS public.aton_changelog CASCADE;

-- 4. Remover Registro do Módulo em modulos_sistema
DELETE FROM public.modulos_sistema WHERE slug = 'autoconhecimento';
