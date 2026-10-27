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
