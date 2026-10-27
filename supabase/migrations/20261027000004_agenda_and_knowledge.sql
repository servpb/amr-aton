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
