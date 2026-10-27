-- ==============================================================================
-- Aton Segundo Cérebro - Migration 01: Extensões, Catálogo de Módulos & Auditoria
-- ==============================================================================

-- 1. Habilitar extensões essenciais no PostgreSQL
CREATE EXTENSION IF NOT EXISTS "vector";      -- pgvector para busca semântica
CREATE EXTENSION IF NOT EXISTS "pgcrypto";    -- Geração segura de UUIDs gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "unaccent";    -- Normalização e busca sem acentos em português

-- 2. Tabela de Expansibilidade: Catálogo de Módulos Ativos
CREATE TABLE IF NOT EXISTS public.modulos_sistema (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug VARCHAR(50) UNIQUE NOT NULL,
    nome VARCHAR(100) NOT NULL,
    descricao TEXT,
    versao VARCHAR(20) DEFAULT '1.0.0',
    ativo BOOLEAN DEFAULT true,
    tabelas_principais TEXT[] DEFAULT '{}',
    pontos_integracao JSONB DEFAULT '{}'::jsonb,
    metadados JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Inserir os 7 módulos fundacionais do Aton
INSERT INTO public.modulos_sistema (slug, nome, descricao, tabelas_principais, pontos_integracao)
VALUES
    ('perfil', 'Perfil do Criador', 'Dados pessoais, preferências, rotina e histórico de decisões.', ARRAY['perfil_criador', 'historico_decisoes'], '{"mcp": true}'::jsonb),
    ('clientes', 'Clientes & CRM', 'Cadastro, contratos, entregas, pendências e histórico de interações.', ARRAY['clientes', 'contatos_clientes', 'interacoes_clientes'], '{"whatsapp": true, "gmail": true}'::jsonb),
    ('projetos', 'Negócios e Projetos', 'Frentes da agência digital e do canal Alta Restauração (ex: Siena 2006).', ARRAY['projetos', 'etapas_projeto', 'ideias_projetos'], '{"notion": true, "n8n": true}'::jsonb),
    ('tarefas', 'Trabalho e Tarefas', 'Tarefas operacionais, prioridades, dependências e status.', ARRAY['tarefas', 'dependencias_tarefas'], '{"google_tasks": true, "n8n": true}'::jsonb),
    ('agenda', 'Agenda & Eventos', 'Reuniões, compromissos, gravações e prazos fatais.', ARRAY['agenda_eventos', 'lembretes_agenda'], '{"google_calendar": true}'::jsonb),
    ('memoria', 'Memória de Conversas & Fatos', 'Memória de curto prazo (sessões) e longo prazo (fatos vetorizados).', ARRAY['conversas_sessao', 'turnos_conversa', 'memoria_longo_prazo'], '{"gemini_live": true, "mcp": true}'::jsonb),
    ('conhecimento', 'Base de Conhecimento', 'Procedimentos, scripts, gabaritos e notas técnicas.', ARRAY['base_conhecimento'], '{"notion": true, "mcp": true}'::jsonb)
ON CONFLICT (slug) DO UPDATE
SET updated_at = now();

-- 3. Tabela de Auditoria e Conformidade de Segurança
CREATE TABLE IF NOT EXISTS public.auditoria_sistema (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tabela VARCHAR(100) NOT NULL,
    operacao VARCHAR(20) NOT NULL, -- INSERT, UPDATE, DELETE, SELECT_SENSITIVE
    registro_id UUID,
    dados_antigos JSONB,
    dados_novos JSONB,
    usuario_origem VARCHAR(100) DEFAULT current_user,
    ip_origem INET,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Índice para consultas rápidas na trilha de auditoria
CREATE INDEX IF NOT EXISTS idx_auditoria_tabela_created ON public.auditoria_sistema (tabela, created_at DESC);

-- Função genérica de Trigger para auditoria automática de alterações
CREATE OR REPLACE FUNCTION public.processar_auditoria_trigger()
RETURNS TRIGGER AS $$
BEGIN
    IF (TG_OP = 'DELETE') THEN
        INSERT INTO public.auditoria_sistema (tabela, operacao, registro_id, dados_antigos)
        VALUES (TG_TABLE_NAME, 'DELETE', OLD.id, to_jsonb(OLD));
        RETURN OLD;
    ELSIF (TG_OP = 'UPDATE') THEN
        INSERT INTO public.auditoria_sistema (tabela, operacao, registro_id, dados_antigos, dados_novos)
        VALUES (TG_TABLE_NAME, 'UPDATE', NEW.id, to_jsonb(OLD), to_jsonb(NEW));
        RETURN NEW;
    ELSIF (TG_OP = 'INSERT') THEN
        INSERT INTO public.auditoria_sistema (tabela, operacao, registro_id, dados_novos)
        VALUES (TG_TABLE_NAME, 'INSERT', NEW.id, to_jsonb(NEW));
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
