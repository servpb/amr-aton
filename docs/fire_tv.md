# Módulo de Controle do Amazon Fire TV Stick pelo Aton

O Aton permite controlar o Amazon Fire TV Stick por comandos de voz captados no microfone do PC, utilizando o ecossistema Gemini Live e comandos ADB estruturados e seguros pela rede local Wi-Fi.

> [!NOTE]
> Esta integração opera sem alterar o controle remoto físico, sem substituir a Alexa e sem necessidade de instalar aplicativos adicionais no Fire Stick. O áudio, a síntese de voz e a inteligência conversacional permanecem 100% no computador.

---

## 1. Arquitetura e Configuração

### Parâmetros de Ambiente (`.env`)
- `FIRE_TV_IP`: Endereço IPv4 prioritário ou fallback do Fire Stick na rede local (ex: `192.168.0.13`).
- `FIRE_TV_ADB_PATH`: Caminho absoluto para o executável `adb.exe` da plataforma oficial (ex: `scripts/firetv-platform-tools/adb.exe`).
- `FIRE_TV_APP_WAIT_SECONDS`: Tempo de espera para confirmação de foco de aplicativo em primeiro plano (padrão: `4.0`, limitado entre `1.0` e `6.0` segundos).
- `FIRE_TV_EXPECTED_MAC`: Endereço MAC físico esperado da placa Wi-Fi do Fire Stick (ex: `24:CE:33:E2:0F:9E`).
- `FIRE_TV_EXPECTED_SERIAL`: Número de série estável de hardware do Fire Stick (ex: `G071CQ2042741DJK`).
- `FIRE_TV_EXPECTED_MODEL`: Modelo interno do dispositivo (ex: `AFTSS`).
- `FIRE_TV_DISCOVERY_ENABLED`: Ativação da recuperação e redescoberta automática quando o IP mudar via DHCP (padrão: `true`).
- `FIRE_TV_DISCOVERY_SUBNET`: Sub-rede IPv4 específica para varredura ou vazia para auto-detecção da placa de rede ativa (ex: `192.168.0.0/24`).
- `FIRE_TV_DISCOVERY_TIMEOUT_SECONDS`: Timeout de conexão por host no scan de portas (padrão: `0.35s`).
- `FIRE_TV_DISCOVERY_CONCURRENCY`: Número máximo de threads paralelas no scan (padrão: `24`).
- `FIRE_TV_DISCOVERY_MIN_INTERVAL_SECONDS`: Intervalo mínimo entre varreduras completas da rede para evitar sobrecarga (padrão: `30.0s`).

### Dispositivo Validado
- **Modelo:** Amazon Fire TV Stick Lite / Standard (`AFTSS`).
- **Número de Série Hardware:** `G071...1DJK` (obtido via `ro.serialno` / `ro.boot.serialno`).
- **Endereço MAC:** `24:CE:33:E2:0F:9E`.
- **Sistema:** Fire OS 7 / Android 9 (`PS7717.5746N`).
- **Porta ADB:** `5555`.

---

## 2. Descoberta Dinâmica de IP, Reconexão e Verificação de Identidade (DHCP Recovery)

Como roteadores comuns em ambiente doméstico frequentemente operam com DHCP dinâmico sem reserva fixa de IP, o Aton conta com o módulo `src/core/fire_tv_discovery.py` com `FireTVConnectionManager`.

### A. Precedência Estrita de Resolução de IP
1. **IP Confirmado no Arquivo de Estado Local:** Gravado atomicamente em `data/fire_tv_state.json`. Tem a maior prioridade para manter o dispositivo acessível imediatamente após reinicializações.
2. **IP Configurado em `FIRE_TV_IP` no `.env`:** Serve como fallback prioritário inicial. O `.env` nunca é modificado automaticamente em tempo de execução.
3. **IP Redescoberto na Rede:** Encontrado dinamicamente via varredura ARP ou scan de sub-rede.

### B. Fluxo de Reconexão e Descoberta em 3 Fases
```
[Tentativa no IP Prioritário (State / .env)]
                     │
         ┌───────────┴───────────┐
      (Sucesso)               (Falha)
         │                       │
[Atualiza Cache TTL]    [Verifica se Discovery Ativo]
                                 │
                 ┌───────────────┴───────────────┐
           [1. Consulta ARP Windows]       [2. Scan TCP Sub-rede]
           (Busca MAC 24:CE:33:E2:0F:9E)   (Porta 5555 na sub-rede /24)
                 │                               │
                 └───────────────┬───────────────┘
                                 │
                     [3. Verificação Estrita]
                     - getprop ro.serialno == G071...1DJK
                     - getprop ro.product.model == AFTSS
                     - MAC da tabela ARP confere
                                 │
                 ┌───────────────┴───────────────┐
              (Confirmado)                  (Falha/Impostor)
                 │                               │
       [Salva atomicamente em]         [Mensagem Clara de Erro]
     [data/fire_tv_state.json]         [Sem Travar Assistente]
```

### C. Identificação Segura e Imutável de Hardware
- **Por que não usar apenas o modelo ou IP:** Qualquer outro aparelho na rede (como outra TV ou smartphone Android) poderia responder na porta 5555 ou declarar o modelo `AFTSS`.
- **Por que não usar o serial reportado por `adb devices`:** O identificador em conexões TCP é o próprio `IP:porta` (ex: `192.168.0.13:5555`), sendo efêmero e dependente do IP.
- **Identificador Definitivo:** Consulta direta às propriedades do sistema `ro.serialno` e `ro.boot.serialno` sob a sessão autenticada. Apenas o dispositivo com o serial `G071...1DJK` é aceito. Dispositivos com modelo idêntico mas número de série divergente são sumariamente rejeitados. O número de série é mascarado em todos os relatórios, logs e retornos para o modelo (`G071...1DJK`), preservando o valor completo internamente apenas para a comparação segura.

### D. Persistência Atômica Sem Alterar `.env`
O último IP confirmado é persistido em `data/fire_tv_state.json` através do padrão atômico de escrita temporária (`fire_tv_state.json.tmp`) seguido de `os.replace`. Dessa forma, quedas de energia ou encerramentos abruptos nunca corrompem o arquivo.

### E. Trava de Concorrência e Rate Limiting
- Apenas uma rotina de descoberta pode rodar por vez (`threading.Lock`).
- Requisições concorrentes aguardam a conclusão da descoberta em andamento e compartilham o resultado.
- Intervalo mínimo de 30 segundos entre varreduras completas da sub-rede para preservar a banda da rede Wi-Fi e a CPU.
- Cache de verificação em memória com TTL de 60 segundos; falhas de rede invalidam o cache imediatamente.

---

## 3. Proteção contra Incerteza e Duplicação de Comandos

O envio de comandos ao Fire TV separa estritamente ações de leitura de ações físicas modificadoras de estado:
- **Ações de Leitura/Idempotentes (`is_read_only=True`):** `dumpsys`, `getprop`, `pm path`, verificação de estado. Em caso de falha, retornam código de erro e invalidam o cache de conexão.
- **Ações Físicas Sensíveis (`is_read_only=False`):** `select`, navegação direcional (`up`, `down`, `left`, `right`), `next`, início de reprodução.
- **Tratamento de Incerteza:** Se ocorrer timeout ou erro de rede durante ou após a transmissão de uma ação física, o sistema **nunca duplica o comando automaticamente**. Retorna:
  ```json
  {
    "status": "uncertain",
    "message": "O comando pode ter sido enviado; não vou repeti-lo automaticamente."
  }
  ```

---

## 4. Proteção Programática de Destino e Inteligência Conversacional

### A. Proteção no Fluxo de Execução (`src/core/destination_guard.py`)
A separação de destinos **não depende apenas do prompt**:
- Diante de qualquer comando de aplicativo compartilhado (`youtube`, `netflix`, `spotify`) ou controle de mídia (`pause`, `play`), o despachante avalia o destino antes de qualquer chamada ao sistema operacional.
- O nome da ferramenta escolhido pelo Gemini não serve, sozinho, como prova do destino.
- **Sem destino definido (fala ou contexto de sessão):** A ação física é **bloqueada**, o pedido original é preservado em `TargetContextManager` e o sistema solicita esclarecimento verbal (*"No computador ou no Fire Stick?"*).
- **Retomada Automática (`resolve_destination`):** Quando o usuário responde *"No Fire Stick"* ou *"No computador"*, o sistema resgata o pedido pendente, define o contexto ativo e executa a ação no destino correto.
- **Comandos Inequívocos:** Aplicativos exclusivos de PC (como Chrome, Notepad, Word, Excel) ou exclusivos do Fire Stick (como Downloader, AirScreen, UniTV) nunca são bloqueados.

### B. Regras Estritas de Volume e Energia
- **Volume do Computador:** Controla diretamente o áudio mestre do Windows via `set_system_volume`.
- **Volume da TV:** Informa com honestidade que a função ainda não está disponível nesta versão (`"status": "unavailable"`). **Nunca substitui um pedido de TV por uma ação no PC.**
- **"Aumente o volume" sem destino:** Bloqueia a execução física, preserva o pedido e solicita esclarecimento (*"No computador ou na TV?"*).
- **Energia da TV:** Pedidos de ligar ou desligar a televisão informam que a função não está disponível e **nunca são encaminhados para o PC**. Funções simuladas que retornavam falso sucesso foram expurgadas.

### C. Confirmação Configurável de Foco (Padrão 4.0s)
Após disparar o lançamento do aplicativo via `monkey`:
- O módulo monitora o foco via `dumpsys window windows` (campo `mCurrentFocus`) pelo tempo configurado em `FIRE_TV_APP_WAIT_SECONDS` (padrão: 4,0s; limite de segurança: 1s a 6s).
- Se confirmado: retorna `"confirmed": True` (*"Aplicativo X aberto e confirmado no Fire Stick"*).
- Se expirar: retorna `"confirmed": False` (*"Comando enviado, mas a exibição em primeiro plano ainda não foi confirmada"*), sem mentir e sem travar a conversa.

### D. Navegação Repetida Delimitada (`count` de 1 a 10)
- **Ações repetíveis:** `up`, `down`, `left`, `right`, `rewind`, `fast_forward`.
- **Ações de clique único estrito:** `select`, `home`, `back`, `menu`, `play`, `pause`, `stop`, `next`, `previous` rejeitam repetição > 1.
- **Separação semântica:** `right` (navegação direcional, código 22), `next` (pular faixa, código 87), `fast_forward` (avançar tempo, código 90).

### E. Busca e Reprodução de Músicas e Vídeos no YouTube do Fire Stick
- **Integração por Intents Verificados:** Utiliza o componente nativo Cobalt (`com.amazon.firetv.youtube/dev.cobalt.app.MainActivity`), disparando pesquisas e vídeos específicos via URI scheme oficial (`https://www.youtube.com/results?search_query=...` e `https://www.youtube.com/watch?v=...`) sem depender de navegação cega por setas de interface.
- **Consulta de Catálogo com Custo Zero:** O módulo `src/tools/youtube_search.py` realiza busca em tempo real de metadados públicos sem custos de cota e sem inventar IDs ou títulos de vídeos.
- **Quatro Estados Granulares de Retorno:**
  1. `search_sent`: Pesquisa enviada ao Fire Stick via intent ADB.
  2. `search_opened_in_app`: Pesquisa aberta no aplicativo com confirmação de primeiro plano (`dumpsys window windows`).
  3. `video_selected_and_opened`: Vídeo específico identificado e intent de reprodução entregue.
  4. `playback_confirmed`: Reprodução ativamente confirmada via `dumpsys media_session` (`state=3`, velocidade `1.0` e título correspondente no campo `metadata.description`).
- **Esclarecimento para Pedidos Genéricos:** Se o senhor disser *"Toque uma música do Roberto Carlos"* (sem especificar o título), o sistema identifica o pedido genérico, busca as melhores faixas reais do catálogo e pergunta qual música prefere tocar antes de iniciar qualquer reprodução.
- **Não Inicia Reprodução em Buscas Explícitas:** Pedidos explícitos de pesquisa (*"Pesquise Roberto Carlos no YouTube do Fire Stick"*) apenas abrem os resultados da busca na TV, deixando a reprodução a critério do usuário.

---

## 5. Catálogo de Ferramentas Ativas

| Ferramenta | Parâmetros | Descrição |
|---|---|---|
| `resolve_destination` | `destination: str` | Resolve destino esclarecido pelo usuário e retoma o pedido pendente. |
| `get_fire_tv_status` | *nenhum* | Consulta conectividade, autorização e modelo do Fire Stick via ADB com redescoberta automática. |
| `launch_fire_tv_app` | `app_name: str`, `destination: Optional[str]` | Abre aplicativo no Fire Stick e confirma foco via `dumpsys`. |
| `control_fire_tv` | `action: str`, `count: int = 1`, `destination: Optional[str]` | Navegação e mídia no Fire Stick com repetição delimitada (1 a 10) e proteção de incerteza. |
| `search_fire_tv_youtube` | `query: str`, `destination: Optional[str]` | Abre pesquisa de vídeos/músicas no YouTube da TV sem tocar automaticamente. |
| `play_fire_tv_youtube` | `query: Optional[str]`, `video_id: Optional[str]`, `destination: Optional[str]` | Busca e reproduz música ou vídeo específico com confirmação via media_session. |
| `control_tv_volume` | `action: str` | Informa com honestidade indisponibilidade do controle de volume da TV. |
| `control_tv_power` | `action: str` | Informa com honestidade indisponibilidade do controle de energia da TV. |

---

## 6. Testes Automatizados

A suíte conta com **51 testes automatizados** dedicados ao Fire TV, descoberta dinâmica e proteção de destino:
- **`tests/test_fire_tv_discovery.py` (12 testes):**
  1. Normalização de MAC (dois-pontos, traços, maiúsculas/minúsculas).
  2. IP prioritário válido conecta sem varredura e armazena em cache.
  3. IP prioritário com número de série divergente dispara descoberta e localiza Fire Stick.
  4. Aparelho com mesmo modelo (`AFTSS`) mas número de série divergente é sumariamente rejeitado.
  5. Troca de IP descoberta na tabela ARP conecta diretamente.
  6. Tabela ARP desatualizada recorre à varredura TCP na porta 5555 da sub-rede local e confirma identidade.
  7. Dispositivo não autorizado orienta autorização na TV sem travar o assistente.
  8. Nenhum candidato localizado retorna mensagem clara em português sem exceção fatal.
  9. Ambiguidade de múltiplos candidatos solicita esclarecimento sem adivinhar.
  10. Persistência atômica no arquivo de estado e precedência estrita sobre o `.env`.
  11. Falha em comando físico não idempotente retorna status `uncertain` sem duplicação automática.
  12. Trava de concorrência e respeito ao intervalo mínimo de 30 segundos.
- **`tests/test_fire_tv_youtube.py` (10 testes):** Busca sem tocar, estados de retorno granulares, confirmação de reprodução via `media_session`, esclarecimento para pedidos genéricos, bloqueio de busca/música ambígua e resolução de destino.
- **`tests/test_destination_guard.py` (11 testes):** Bloqueio sem efeito físico, retomada após esclarecimento (Fire TV e PC), comandos inequívocos (Chrome/Downloader), precedência de destino explícito, troca de contexto, limpeza no adormecimento, regras de volume e energia.
- **`tests/test_fire_tv.py` (18 testes):** Esquema de declarações, rejeição de IP inválido/público, detecção de ADB ausente, autorização pendente na TV, confirmação de foco com timeout configurável, validação de limites de count, distinção de teclas e aliases.

---

## 7. Demonstração Prática de Recuperação (`scripts/demonstrar_recuperacao_fire_tv.py`)

Para validar a recuperação sem alterar configurações do roteador físico nem derrubar a rede, foi criado o utilitário de demonstração em tempo real:
- **Simulação Controlada:** Injeta um IP propositalmente incorreto e inacessível (`192.168.0.244`) no arquivo de estado local [data/fire_tv_state.json](file:///c:/xampp/htdocs/amr/data/fire_tv_state.json).
- **Bloqueio de Fallback:** Anula temporariamente a variável `FIRE_TV_IP` em memória durante o teste para impedir atalhos pelo `.env`.
- **Validação de Hardware e Persistência:** Observa a falha rápida de conexão (pré-teste TCP de 0,5s), o acionamento da descoberta por ARP do Windows com identificação do MAC `24:CE:33:E2:0F:9E`, auditoria do número de série hardware `ro.serialno`, salvamento atômico do IP correto e execução de consulta de status com tempo total médio de **1,34 segundos**.
- **Diferenciação Estrita:** Esta demonstração comprova com precisão a resiliência programática do algoritmo quando confrontado com um endereço stale. A troca física espontânea pelo servidor DHCP do roteador continua como validação pendente para quando o lease expirar naturalmente em produção.
