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
