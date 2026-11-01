# Contexto de Tarefa e Confirmação de Resultados

Este documento descreve a arquitetura, o contrato de evidências e os mecanismos de confirmação que permitem ao **Aton** acompanhar tarefas de controle físico e reprodução no PC e no Amazon Fire TV Stick, entender continuações, correções, seleções ordinais e distinguir com precisão entre o envio do comando e o resultado efetivamente observado.

---

## 1. Arquitetura e Modelo de Estados

O gerenciamento de tarefas é centralizado no `TaskContextManager` ([`src/core/task_context.py`](file:///c:/xampp/htdocs/amr/src/core/task_context.py)), que unifica o contexto de destino da sessão (PC vs. Fire Stick) e a máquina de estados da tarefa em execução, atuando como a **fonte única da verdade**.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Gemini Live (Voz Aoede)                        │
│   "Abra o YouTube" -> "No Fire Stick" -> "Pause" -> "Ele abriu?"      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               TaskContextManager (`src/core/task_context.py`)          │
│   - task_id e action_id únicos por operação                            │
│   - Estados: aguardando_esclarecimento, pronta, executando,            │
│              verificando, concluida, inconclusiva, falhou, cancelada   │
│   - Transporte: not_sent, sent_confirmed, sent_uncertain               │
│   - Verificação: unverified, confirmed, inconclusive, failed           │
│   - Referências: app_name, artist, video_id, candidates (opções reais) │
│   - Prevenção de concorrência: 1 tarefa de controle físico por vez    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                 ┌──────────────────┴──────────────────┐
                 ▼                                     ▼
┌─────────────────────────────────┐   ┌──────────────────────────────────┐
│   Verificadores no Fire Stick   │   │     Verificadores no Windows     │
│ - Pacote no topo (dumpsys)      │   │ - Janela visível correlacionada  │
│ - Sessão de mídia ativa         │   │ - Processo ativo (psutil)        │
│ - Teclas: transporte confirmado │   │ - Abrir navegador NÃO confirma   │
│   sem inventar seleção visual   │   │   carregamento da página         │
└─────────────────────────────────┘   └──────────────────────────────────┘
```

---

## 2. Contrato de Evidências e Níveis de Confirmação

Cada ação física retorna uma estrutura padronizada compatível com os consumidores existentes:

| Nível de Confirmação | Campo / Estado | Significado Técnico | Comportamento na Voz |
| :--- | :--- | :--- | :--- |
| **Transporte** | `transport_state: "sent_confirmed"` | O pacote ou comando ADB/subprocesso foi aceito pelo sistema. | Não alega que a tela já abriu. |
| **Incerteza no Transporte** | `transport_state: "sent_uncertain"` | A rede ou processo falhou durante ou após o envio; o comando pode ter chegado. | Não repete automaticamente a ação para evitar duplicidade. |
| **Estado Observado** | `verification_state: "confirmed"` | O pacote do app ou janela visível foi correlacionado com sucesso no dispositivo. | *"O YouTube abriu no Fire Stick."* |
| **Estado Inconclusivo** | `verification_state: "inconclusive"` | O comando foi enviado, mas a exibição no topo ou página não apareceu no prazo limite. | *"Enviei o comando, mas o aplicativo ainda não apareceu."* |
| **Objetivo Não Comprovado** | `verification_state: "inconclusive"` | A mídia está tocando no Cobalt, mas não foi possível ler metadados do vídeo solicitado. | *"O YouTube está reproduzindo, mas não consegui confirmar se é a música solicitada."* |
| **Navegação Não Verificada** | `verification_state: "unverified"` | Teclas direcionais (`up`, `down`, `select`) enviadas sem captura de tela visual. | *"Comando de navegação enviado."* (sem inventar seleção visual). |

---

## 3. Continuações, Escolhas Ordinais e Correções

### A. Resolução de Escolhas Ordinais (*"a segunda"*, *"a primeira"*)
- Ao buscar artistas ambíguos, as opções encontradas são registradas estruturadamente em `task.references["candidates"]` com seus identificadores reais (`id`, `title`, `index`, `task_id`).
- Quando o usuário responde *"a segunda"*, *"o primeiro"* ou *"número 2"*, a ferramenta `selecionar_opcao_pendente` consulta a lista daquela tarefa específica:
  - Se válida: dispara a reprodução com o `video_id` real correspondente.
  - Se inválida ou sem lista: recusa honestamente sem supor escolhas.
  - Ao iniciar um novo pedido, as opções antigas são invalidadas atômica e imediatamente.

### B. Correção e Cancelamento Cooperativo
- **Antes do envio**: Se o usuário cancelar antes do envio (`is_action_allowed` retorna `False`), o comando físico é bloqueado antes de chamar ADB ou subprocesso, relatando cancelamento sem efeitos físicos.
- **Depois do envio**: Se o comando já foi despachado (`transport_state == "sent_confirmed"`), o Aton informa com honestidade:
  > *“Tarefa cancelada. O comando para 'abrir netflix' já havia sido enviado ao Fire Stick, mas interrompi as próximas etapas.”*
- **Descarte de Callbacks Atrasados**: Retornos assíncronos antigos contendo `task_id` defasado são automaticamente ignorados e não afetam a nova tarefa.

---

## 4. Novas Ferramentas Integradas (`src/tools/task_tools.py`)

1. **`consultar_status_tarefa(verificar_ao_vivo: bool = False, pergunta: str = "")`**:
   - Responde dúvidas como *"Ele abriu?"*, *"O que você está fazendo?"*, *"Deu certo?"*.
   - Se for uma pergunta sobre a presença atual no momento (*"ele abriu?"*), executa uma leitura rápida de baixo custo (`dumpsys window windows` ou janela ativa no PC) sem reenviar a ação.
   - Caso contrário, relata a evidência histórica com carimbo de data/hora UTC.
2. **`selecionar_opcao_pendente(escolha: str)`**:
   - Resolve ordinais falados (*"a segunda"*, *"a primeira"*) e aciona a opção escolhida.
3. **`cancelar_tarefa_atual(motivo: str = "")`**:
   - Interrompe a tarefa ativa, bloqueia novas etapas e relata se houve despacho prévio.

---

## 5. Testes Automatizados

A suíte em [`tests/test_task_context.py`](file:///c:/xampp/htdocs/amr/tests/test_task_context.py) valida:
1. Transições válidas de estado (`aguardando_esclarecimento` -> `pronta` -> `executando` -> `verificando` -> `concluida`).
2. Retomada após esclarecimento de destino sem perder o pedido pendente.
3. Resolução ordinal contra candidatos reais apresentados.
4. Rejeição de ordinais inválidos ou quando não há lista prévia.
5. Invalidação de opções antigas quando novo pedido chega.
6. Cancelamento antes do envio impedindo ação física.
7. Cancelamento pós-envio relatando honestamente o despacho.
8. Descarte de callbacks assíncronos com `task_id` defasado.
9. Comando enviado sem confirmação no prazo (`inconclusive`).
10. Falha de transporte com incerteza (`sent_uncertain`) evitando repetição.
11. Limpeza ao dormir cancelando tarefas pendentes.
12. Correlação de janela no PC (abrir navegador não comprova carregamento de página/vídeo).
13. `consultar_status_tarefa` diferenciando evidência histórica de consulta ao vivo.
14. Despachante unificado integrando as novas ferramentas.

