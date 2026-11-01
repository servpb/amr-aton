# Explicação de Módulos e Capacidades Operacionais por Voz

Este documento descreve a arquitetura, as ferramentas e os padrões de resposta por voz que permitem ao **Aton** explicar dinamicamente quais módulos possui, para que serve cada um, como utilizá-los e quais recursos dependem de configuração prévia.

---

## 1. Visão Geral da Arquitetura

O sistema de autoexplicação de módulos é estruturado sobre o princípio da **introspecção em tempo de execução grounded**. Em vez de manter listas estáticas duplicadas de funcionalidades (que se tornariam obsoletas a cada alteração de código), o Aton utiliza o `ModuleRegistry` como fonte da verdade, cruzando as ferramentas efetivamente registradas em `ALL_ATON_TOOLS` com as configurações e dependências locais.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Gemini Live (Voz Aoede)                        │
│   "Quais módulos você tem?" / "O que você faz no Fire Stick?"         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Tool Calling
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               Ferramentas de Introspecção (`module_tools.py`)          │
│   - `listar_modulos(area)`                                            │
│   - `detalhar_modulo(modulo)`                                         │
│   - `listar_recursos_pendentes()`                                     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Consulta Segura (< 3ms)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                Registro Dinâmico (`src/core/module_registry.py`)       │
│   - Cruzamento com `ALL_ATON_TOOLS` (ferramentas ativas)               │
│   - Avaliadores de estado locais (sem chamadas de rede ou cota)        │
│   - Mascaramento estrito de seriais (ex: G071...1DJK) e tokens         │
│   - Omissão de endereços IP na fala gerada                            │
│   - Distinção honesta entre configuração e conectividade em tempo real │
│   - Geração de `mensagem_voz` natural e concisa para fala              │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Fallback Unificado
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             Segundo Cérebro (`consultar_autoconhecimento`)             │
│   - Delegação transparente de consultas de módulos ao ModuleRegistry  │
│   - Zero catálogos concorrentes ou redundantes no sistema             │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. As 5 Áreas Funcionais e os 18 Módulos Canônicos

Para que a resposta falada não seja cansativa ou prolixa no microfone, os 18 módulos operacionais são agrupados em 5 áreas funcionais intuitivas:

### 1. `sistema_windows` (Sistema e Windows)
- **`apps_windows`**: Abertura, fechamento inteligente e listagem de aplicativos no computador.
- **`web_browser`**: Navegação na internet, abertura de páginas e buscas web via navegador.
- **`desktop_automation`**: Digitação de texto, criação de documentos Word/Excel e atalhos de teclado.
- **`system_audio`**: Controle de volume mestre do computador e controle de mídia do Windows.
- **`system_telemetry`**: Telemetria de CPU, memória RAM, disco e bateria do notebook.
- **`network_devices`**: Informações de rede local, escaneamento e pareamento seguro de dispositivos.

### 2. `casa_smart_tv` (Casa Inteligente e Televisão)
- **`fire_tv`**: Navegação completa, abertura de aplicativos, busca e reprodução no Fire TV Stick.
- **`smart_tv`**: Comandos genéricos de Smart TV (mídia e status na rede local).
- **`smart_lights`**: Controle de lâmpadas e tomadas inteligentes na rede Wi-Fi local.
- **`phone_finder`**: Alarme sonoro em volume máximo para encontrar o celular pela rede.

### 3. `google_workspace` (Google Workspace e Produtividade)
- **`youtube`**: Busca e reprodução de vídeos e músicas (com direcionamento PC vs. TV).
- **`gmail`**: Consulta a e-mails não lidos e leitura de mensagens (OAuth 2.0 multi-contas).
- **`calendar`**: Consulta e criação de compromissos na agenda do Google com datas naturais.
- **`tasks`**: Consulta, criação e conclusão de afazeres na lista do Google Tasks.
- **`google_maps`**: Cálculo de trânsito em tempo real, rotas e envio de navegação ao celular.

### 4. `segundo_cerebro_ia` (Segundo Cérebro e Memória)
- **`second_brain`**: Memória permanente na nuvem (Supabase + pgvector) com busca híbrida semântica.
- **`local_memory`**: Memória local de preferências e briefing diário matinal em SQLite.

### 5. `visao_interacao` (Visão Computacional e Tela)
- **`screen_perception`**: Análise visual multimodal da tela do computador e localização de elementos.

---

## 3. Classificação Honesta de Estados e Conectividade

O Aton **nunca** presume que uma funcionalidade externa está online apenas porque seu código existe, uma chave de API foi inserida ou há um registro prévio no cadastro:

| Estado | Significado Técnico | Comportamento na Explicação Falada |
| :--- | :--- | :--- |
| **`disponivel`** | Ferramentas registradas e requisitos de ambiente locais satisfeitos. | Pronto para uso imediato pelo usuário. |
| **`configurado`** | Módulo cadastrado com parâmetros definidos, mas a conexão ativa no exato momento não foi testada na consulta. | Informa que está configurado e oferece verificação ao vivo quando solicitado. |
| **`verificado`** | Identificadores de hardware esperados conferidos em checagem anterior registrada com data e hora. | Informa que a identidade foi conferida na última conexão, sem afirmar que está online neste segundo. |
| **`indisponivel`** | Falta dependência local instalada ou o recurso físico não é suportado pelo hardware atual (ex: volume/energia em TVs sem protocolo de controle direto). | Informa honestamente que o recurso não está disponível nesta versão. |
| **`requer_configuracao`** | Faltam chaves de API, credenciais OAuth ou arquivos de configuração obrigatórios. | Lista exatamente o que falta configurar (ex: `.env` ou autorização de conta). |

### Regra Específica para Dispositivos de Rede e Fire TV Stick
1. **Identidade Conferida Anteriormente**: Havendo registro válido de checagem prévia (IP, serial e data), o Aton fala:
   > *“O módulo do Fire Stick está configurado e a identidade foi conferida na última conexão. Posso verificar se ele está disponível agora.”*
2. **Cadastro sem Verificação Anterior**: Sem o registro completo da checagem anterior, o Aton fala:
   > *“O módulo do Fire Stick está configurado e ainda precisa de verificação. Posso verificar se ele está disponível agora.”*
3. **Ausência de Conexão Automática**: Consultar o catálogo jamais dispara comandos de rede ou conexões ADB. A verificação ao vivo (`get_fire_tv_status`) ocorre somente quando o usuário solicita.
4. **Omissão de Endereços IP**: O IP é omitido da resposta de voz, ficando restrito aos detalhes técnicos quando expressamente solicitados.

---

## 4. Ferramentas Integradas (`src/tools/module_tools.py`)

### `listar_modulos(area: str = "") -> dict`
- **Objetivo**: Retorna visão geral dos módulos disponíveis no Aton, agrupados por área temática.
- **Parâmetros**: `area` (opcional: `sistema_windows`, `casa_smart_tv`, `google_workspace`, `segundo_cerebro_ia`, `visao_interacao`).
- **Retorno**: Lista de módulos ativos com contagem de ferramentas, estado atual e mensagem sintetizada em linguagem natural (`mensagem_voz`).

### `detalhar_modulo(modulo: str) -> dict`
- **Objetivo**: Fornece detalhes completos de um módulo específico: para que serve, o que faz, 2 a 3 exemplos falados de comandos, limitações conhecidas e requisitos.
- **Parâmetros**: `modulo` (slug oficial ou apelido em português, ex: `fire_tv`, `fire stick`, `tv`, `youtube`, `gmail`, `agenda`, `luzes`).
- **Retorno**: Metadados completos com resolução automática de sinônimos e tratamento de ambiguidades.

### `listar_recursos_pendentes() -> dict`
- **Objetivo**: Lista com precisão os recursos do assistente que ainda precisam de configuração (chaves de API, tokens ou arquivos) para funcionar.
- **Retorno**: Diagnóstico preventivo dos módulos que não estão em estado `disponivel`/`verificado`.

---

## 5. Diretrizes de Resposta por Voz

1. **Visão Geral Primeiro**: Ao ser questionado sobre suas capacidades ("Quais módulos você tem?"), o Aton cita as 5 grandes áreas e oferece detalhamento, evitando despejar dezenas de nomes de uma só vez.
2. **Exemplos Práticos**: Ao detalhar um módulo ("Como uso o Fire Stick?"), o Aton apresenta exemplos de comandos exatamente como devem ser falados ("Abra o YouTube no Fire Stick", "Pause o vídeo na TV").
3. **Limitações Verificadas**: O Aton informa honestamente o que o módulo **não** faz (ex: "O Fire Stick não altera o volume físico da TV nem liga/desliga o televisor").
4. **Sem Jargões Técnicos**: Nunca cita funções internas do Python (`search_fire_tv_youtube`), caminhos de disco ou referências a código a menos que o usuário peça explicitamente.
5. **Privacidade e Proteção de Segredos**: Números de série de hardware aparecem sempre mascarados (`G071...1DJK`), e chaves ou tokens jamais são expostos.
6. **Omissão de Endereços IP**: O IP é preservado nos dicionários estruturados, mas é sempre omitido das respostas faladas.

---

## 6. Testes Automatizados

A suíte em [`tests/test_module_registry.py`](file:///c:/xampp/htdocs/amr/tests/test_module_registry.py) valida 12 cenários essenciais:
1. **Registro e Ativação**: Todos os módulos canônicos possuem ferramentas válidas e mapeadas em `ALL_ATON_TOOLS`.
2. **Filtragem por Área**: `listar_modulos(area=...)` filtra estritamente a área desejada e reporta áreas inválidas.
3. **Detalhamento e Exemplos**: `detalhar_modulo(...)` retorna para que serve, exemplos falados e limitações em português.
4. **Resolução de Apelidos**: Suporte a termos falados como "fire stick", "agenda", "tela", "luzes".
5. **Recursos Pendentes**: Diagnóstico preciso dos módulos que requerem configuração.
6. **Zero Chamadas de Rede / Cota**: A inspeção de módulos executa 100% localmente em menos de 10ms.
7. **Mascaramento de Segredos**: Verificação de que nenhum número de série completo ou chave de API vaza na saída.
8. **Integração com o Despachante**: Despacho correto em `dispatch_tool()` para as novas ferramentas.
9. **Integração com Autoconhecimento**: `consultar_autoconhecimento` redireciona sem erros e sem catálogos concorrentes.
10. **Cadastro sem Verificação Prévia**: Informa que o módulo está configurado e precisa de verificação, sem afirmar identidade conferida e sem expor IP.
11. **Registro de Checagem Anterior**: Reconhece que os identificadores esperados foram conferidos na última conexão, mantém a data da verificação nos detalhes estruturados e oferece checagem ao vivo.
12. **Ausência de Conectividade Atual na Fala**: Garante que o Aton jamais afirme que o aparelho está conectado agora pelo simples ato de consultar o cadastro.
