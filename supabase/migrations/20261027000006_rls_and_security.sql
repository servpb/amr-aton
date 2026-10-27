-- ==============================================================================
-- Aton Segundo Cérebro - Migration 06: RLS, Políticas de Segurança & Exportação
-- ==============================================================================

-- 1. Habilitar RLS (Row Level Security) em 100% das Tabelas
ALTER TABLE public.modulos_sistema ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auditoria_sistema ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.perfil_criador ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.historico_decisoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.clientes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contatos_clientes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.interacoes_clientes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.projetos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.etapas_projeto ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ideias_projetos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tarefas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dependencias_tarefas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agenda_eventos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lembretes_agenda ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.base_conhecimento ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversas_sessao ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.turnos_conversa ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memoria_longo_prazo ENABLE ROW LEVEL SECURITY;

-- 2. Políticas de Acesso Seguro:
-- Service Role (Aton Backend / Edge Functions) possui acesso administrativo completo
-- Usuários Autenticados têm acesso total com suas credenciais
DO $$
DECLARE
    tabela text;
    tabelas_array text[] := ARRAY[
        'modulos_sistema', 'auditoria_sistema', 'perfil_criador', 'historico_decisoes',
        'clientes', 'contatos_clientes', 'interacoes_clientes', 'projetos',
        'etapas_projeto', 'ideias_projetos', 'tarefas', 'dependencias_tarefas',
        'agenda_eventos', 'lembretes_agenda', 'base_conhecimento', 'conversas_sessao',
        'turnos_conversa', 'memoria_longo_prazo'
    ];
BEGIN
    FOREACH tabela IN ARRAY tabelas_array LOOP
        -- Política para Service Role
        EXECUTE format('
            DROP POLICY IF EXISTS service_role_full_access ON public.%I;
            CREATE POLICY service_role_full_access ON public.%I
            FOR ALL TO service_role USING (true) WITH CHECK (true);
        ', tabela, tabela);

        -- Política para Usuários Autenticados
        EXECUTE format('
            DROP POLICY IF EXISTS authenticated_user_access ON public.%I;
            CREATE POLICY authenticated_user_access ON public.%I
            FOR ALL TO authenticated USING (true) WITH CHECK (true);
        ', tabela, tabela);
    END LOOP;
END $$;

-- 3. Ativar Triggers de Auditoria Automática nas Tabelas Principais
DROP TRIGGER IF EXISTS trg_audit_perfil ON public.perfil_criador;
CREATE TRIGGER trg_audit_perfil AFTER INSERT OR UPDATE OR DELETE ON public.perfil_criador
FOR EACH ROW EXECUTE FUNCTION public.processar_auditoria_trigger();

DROP TRIGGER IF EXISTS trg_audit_clientes ON public.clientes;
CREATE TRIGGER trg_audit_clientes AFTER INSERT OR UPDATE OR DELETE ON public.clientes
FOR EACH ROW EXECUTE FUNCTION public.processar_auditoria_trigger();

DROP TRIGGER IF EXISTS trg_audit_projetos ON public.projetos;
CREATE TRIGGER trg_audit_projetos AFTER INSERT OR UPDATE OR DELETE ON public.projetos
FOR EACH ROW EXECUTE FUNCTION public.processar_auditoria_trigger();

DROP TRIGGER IF EXISTS trg_audit_tarefas ON public.tarefas;
CREATE TRIGGER trg_audit_tarefas AFTER INSERT OR UPDATE OR DELETE ON public.tarefas
FOR EACH ROW EXECUTE FUNCTION public.processar_auditoria_trigger();

DROP TRIGGER IF EXISTS trg_audit_memoria ON public.memoria_longo_prazo;
CREATE TRIGGER trg_audit_memoria AFTER INSERT OR UPDATE OR DELETE ON public.memoria_longo_prazo
FOR EACH ROW EXECUTE FUNCTION public.processar_auditoria_trigger();

-- 4. Função de Backup / Exportação Completa dos Dados em JSON
CREATE OR REPLACE FUNCTION public.exportar_dados_segundo_cerebro_json()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    backup_payload JSONB;
BEGIN
    SELECT jsonb_build_object(
        'versao_backup', '1.0.0',
        'data_exportacao', now(),
        'perfil', (SELECT jsonb_agg(to_jsonb(p)) FROM public.perfil_criador p),
        'clientes', (SELECT jsonb_agg(to_jsonb(c)) FROM public.clientes c),
        'contatos', (SELECT jsonb_agg(to_jsonb(ct)) FROM public.contatos_clientes ct),
        'interacoes', (SELECT jsonb_agg(to_jsonb(i)) FROM public.interacoes_clientes i),
        'projetos', (SELECT jsonb_agg(to_jsonb(pr)) FROM public.projetos pr),
        'tarefas', (SELECT jsonb_agg(to_jsonb(t)) FROM public.tarefas t),
        'agenda', (SELECT jsonb_agg(to_jsonb(a)) FROM public.agenda_eventos a),
        'conhecimento', (SELECT jsonb_agg(to_jsonb(k)) FROM public.base_conhecimento k),
        'memorias', (SELECT jsonb_agg(to_jsonb(m) - 'embedding') FROM public.memoria_longo_prazo m)
    ) INTO backup_payload;

    RETURN backup_payload;
END;
$$;
