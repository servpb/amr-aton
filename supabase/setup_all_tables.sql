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


-- ==============================================================================
-- Aton Segundo Cérebro - Migration 02: Perfil do Criador & Clientes (CRM)
-- ==============================================================================

-- 1. Perfil do Criador
CREATE TABLE IF NOT EXISTS public.perfil_criador (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_preferido VARCHAR(100) NOT NULL DEFAULT 'Criador',
    biografia_resumo TEXT,
    estilo_comunicacao VARCHAR(50) DEFAULT 'direto e prestativo', -- direto, detalhado, executivo
    horario_trabalho_inicio TIME DEFAULT '08:00',
    horario_trabalho_fim TIME DEFAULT '19:00',
    preferencias_gerais JSONB DEFAULT '{}'::jsonb,
    rotina_matinal JSONB DEFAULT '{}'::jsonb,
    metas_atuais JSONB DEFAULT '[]'::jsonb,
    valores_principais TEXT[] DEFAULT '{}',
    habitos_saude JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Histórico de Decisões Estratégicas
CREATE TABLE IF NOT EXISTS public.historico_decisoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    titulo VARCHAR(255) NOT NULL,
    descricao TEXT NOT NULL,
    contexto TEXT,
    impacto VARCHAR(50) DEFAULT 'medio', -- baixo, medio, alto, estrategico
    tags TEXT[] DEFAULT '{}',
    metadados JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Clientes da Agência Digital (CRM)
CREATE TABLE IF NOT EXISTS public.clientes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome VARCHAR(200) NOT NULL,
    razao_social VARCHAR(200),
    segmento VARCHAR(100),
    status VARCHAR(50) DEFAULT 'ativo', -- lead, ativo, pausado, encerrado
    valor_mensal_recorrente NUMERIC(10,2) DEFAULT 0.00,
    entregaveis_prometidos TEXT[] DEFAULT '{}',
    pendencias_abertas TEXT[] DEFAULT '{}',
    data_inicio_contrato DATE DEFAULT CURRENT_DATE,
    observacoes TEXT,
    metadados JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_clientes_nome ON public.clientes (nome);
CREATE INDEX IF NOT EXISTS idx_clientes_status ON public.clientes (status);

-- Contatos dos Clientes
CREATE TABLE IF NOT EXISTS public.contatos_clientes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id UUID NOT NULL REFERENCES public.clientes(id) ON DELETE CASCADE,
    nome VARCHAR(150) NOT NULL,
    cargo VARCHAR(100),
    email VARCHAR(200),
    telefone_whatsapp VARCHAR(50),
    e_contato_principal BOOLEAN DEFAULT false,
    observacoes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_contatos_cliente_id ON public.contatos_clientes (cliente_id);

-- Histórico de Interações com Clientes
CREATE TABLE IF NOT EXISTS public.interacoes_clientes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id UUID NOT NULL REFERENCES public.clientes(id) ON DELETE CASCADE,
    tipo VARCHAR(50) NOT NULL, -- reuniao, whatsapp, email, alinhamento, entrega
    assunto VARCHAR(255) NOT NULL,
    resumo TEXT NOT NULL,
    pendencias TEXT[] DEFAULT '{}',
    data_interacao TIMESTAMPTZ DEFAULT now(),
    metadados JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_interacoes_cliente_data ON public.interacoes_clientes (cliente_id, data_interacao DESC);


-- ==============================================================================
-- Aton Segundo Cérebro - Migration 03: Negócios, Projetos & Tarefas
-- ==============================================================================

-- 1. Projetos & Frentes de Negócio (Agência Digital + Alta Restauração)
CREATE TABLE IF NOT EXISTS public.projetos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    frente_negocio VARCHAR(50) NOT NULL DEFAULT 'alta_restauracao', -- agencia_digital, alta_restauracao, pessoal
    nome VARCHAR(200) NOT NULL,
    descricao TEXT,
    veiculo_alvo VARCHAR(100), -- Ex: 'Siena 2006' para o canal Alta Restauração
    cliente_id UUID REFERENCES public.clientes(id) ON DELETE SET NULL,
    status VARCHAR(50) DEFAULT 'em_andamento', -- planejamento, em_andamento, gravado, em_edicao, publicado, concluido
    data_inicio DATE DEFAULT CURRENT_DATE,
    prazo_final DATE,
    orcamento_previsto NUMERIC(10,2) DEFAULT 0.00,
    receita_prevista NUMERIC(10,2) DEFAULT 0.00,
    tags TEXT[] DEFAULT '{}',
    metadados JSONB DEFAULT '{}'::jsonb, -- Flexibilidade para detalhes de peças, molduras DIN, etc.
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_projetos_frente ON public.projetos (frente_negocio);
CREATE INDEX IF NOT EXISTS idx_projetos_status ON public.projetos (status);
CREATE INDEX IF NOT EXISTS idx_projetos_veiculo ON public.projetos (veiculo_alvo);

-- Etapas dos Projetos (Milestones)
CREATE TABLE IF NOT EXISTS public.etapas_projeto (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    projeto_id UUID NOT NULL REFERENCES public.projetos(id) ON DELETE CASCADE,
    nome VARCHAR(200) NOT NULL,
    ordem INT DEFAULT 1,
    status VARCHAR(50) DEFAULT 'pendente', -- pendente, em_progresso, concluida
    data_prevista DATE,
    data_conclusao TIMESTAMPTZ,
    observacoes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_etapas_projeto_id ON public.etapas_projeto (projeto_id, ordem);

-- Banco de Ideias Futuras para Projetos e Conteúdo
CREATE TABLE IF NOT EXISTS public.ideias_projetos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    frente_negocio VARCHAR(50) NOT NULL DEFAULT 'alta_restauracao',
    titulo VARCHAR(255) NOT NULL,
    descricao TEXT,
    potencial VARCHAR(50) DEFAULT 'medio', -- baixo, medio, alto
    status VARCHAR(50) DEFAULT 'rascunho', -- rascunho, aprovada, descartada, em_producao
    tags TEXT[] DEFAULT '{}',
    metadados JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Trabalho & Tarefas Operacionais
CREATE TABLE IF NOT EXISTS public.tarefas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    projeto_id UUID REFERENCES public.projetos(id) ON DELETE SET NULL,
    cliente_id UUID REFERENCES public.clientes(id) ON DELETE SET NULL,
    titulo VARCHAR(255) NOT NULL,
    descricao TEXT,
    prioridade VARCHAR(30) DEFAULT 'media', -- baixa, media, alta, urgente
    status VARCHAR(30) DEFAULT 'pendente', -- pendente, em_andamento, bloqueada, concluida
    prazo_fatal TIMESTAMPTZ,
    data_conclusao TIMESTAMPTZ,
    recorrencia VARCHAR(30) DEFAULT 'nenhuma', -- nenhuma, diaria, semanal, mensal
    responsavel VARCHAR(100) DEFAULT 'Criador',
    tags TEXT[] DEFAULT '{}',
    metadados JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tarefas_status ON public.tarefas (status);
CREATE INDEX IF NOT EXISTS idx_tarefas_prioridade ON public.tarefas (prioridade);
CREATE INDEX IF NOT EXISTS idx_tarefas_prazo ON public.tarefas (prazo_fatal);
CREATE INDEX IF NOT EXISTS idx_tarefas_projeto_id ON public.tarefas (projeto_id);

-- Dependências entre Tarefas (Bloqueios)
CREATE TABLE IF NOT EXISTS public.dependencias_tarefas (
    tarefa_id UUID NOT NULL REFERENCES public.tarefas(id) ON DELETE CASCADE,
    bloqueada_por_tarefa_id UUID NOT NULL REFERENCES public.tarefas(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (tarefa_id, bloqueada_por_tarefa_id)
);


-- ==============================================================================
-- Aton Segundo Cérebro - Migration 04: Agenda Inteligente & Base de Conhecimento
-- ==============================================================================

-- 1. Agenda de Eventos & Compromissos
CREATE TABLE IF NOT EXISTS public.agenda_eventos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    titulo VARCHAR(255) NOT NULL,
    descricao TEXT,
    tipo VARCHAR(50) DEFAULT 'reuniao', -- reuniao, gravacao, oficina, prazo, pessoal
    data_inicio TIMESTAMPTZ NOT NULL,
    data_fim TIMESTAMPTZ NOT NULL,
    dia_inteiro BOOLEAN DEFAULT false,
    local_ou_link TEXT,
    projeto_id UUID REFERENCES public.projetos(id) ON DELETE SET NULL,
    cliente_id UUID REFERENCES public.clientes(id) ON DELETE SET NULL,
    google_event_id VARCHAR(255), -- ID de sincronização bidirecional com Google Calendar
    recorrencia VARCHAR(50) DEFAULT 'nenhuma',
    status VARCHAR(30) DEFAULT 'agendado', -- agendado, concluido, cancelado
    metadados JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agenda_data_inicio ON public.agenda_eventos (data_inicio);
CREATE INDEX IF NOT EXISTS idx_agenda_status ON public.agenda_eventos (status);
CREATE INDEX IF NOT EXISTS idx_agenda_google_id ON public.agenda_eventos (google_event_id);

-- Lembretes Associados a Eventos
CREATE TABLE IF NOT EXISTS public.lembretes_agenda (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evento_id UUID NOT NULL REFERENCES public.agenda_eventos(id) ON DELETE CASCADE,
    minutos_antes INT DEFAULT 15,
    mensagem_falada TEXT,
    disparado BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lembretes_evento_id ON public.lembretes_agenda (evento_id);

-- 2. Base de Conhecimento (SOPs, Manuais, Scripts e Guias Técnicos)
CREATE TABLE IF NOT EXISTS public.base_conhecimento (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    categoria VARCHAR(50) NOT NULL DEFAULT 'procedimento', -- procedimento, manual_veiculo, script_video, esquema_eletrico, processo_agencia
    titulo VARCHAR(255) NOT NULL,
    conteudo TEXT NOT NULL,
    resumo TEXT,
    tags TEXT[] DEFAULT '{}',
    links_referencia TEXT[] DEFAULT '{}',
    arquivos_anexos JSONB DEFAULT '[]'::jsonb,
    metadados JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conhecimento_categoria ON public.base_conhecimento (categoria);
CREATE INDEX IF NOT EXISTS idx_conhecimento_titulo ON public.base_conhecimento (titulo);


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

        -- Política para Chave Pública (Anon / Publishable)
        EXECUTE format('
            DROP POLICY IF EXISTS anon_user_access ON public.%I;
            CREATE POLICY anon_user_access ON public.%I
            FOR ALL TO anon USING (true) WITH CHECK (true);
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
