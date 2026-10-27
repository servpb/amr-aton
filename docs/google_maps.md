# Documentação: Navegação, Rotas e GPS com Google Maps (google_maps)

## 1. Objetivo
O módulo **google_maps** inicia a **Fase 3 (Presença Móvel & Carro: Android + GPS)** do Aton. Ele capacita o assistente a traçar rotas ponto a ponto, verificar congestionamentos em tempo real e encontrar postos de combustível e serviços ao longo do trajeto, com operação 100% gratuita através de esquemas de *Android Intents* nativos e links diretos do Google Maps.

---

## 2. Componentes e Estrutura

| Arquivo | Responsabilidade |
| :--- | :--- |
| `src/tools/google_maps.py` | Lógica de montagem de URLs de rotas, geração de *Android Intents* (`google.navigation:q=...`), consulta de trânsito ao vivo e busca de pontos de interesse. |
| `src/tools/__init__.py` | Integração na lista `ALL_ATON_TOOLS` (17 ferramentas ativas) e despacho no `dispatch_tool()`. |
| `tests/test_google_maps.py` | Bateria de testes unitários automatizados cobrindo rotas, opções de desvio de pedágio/rodovias e busca de locais. |

---

## 3. Ferramentas no Gemini Live

### 3.1. `navigate_to`
- **Descrição:** Calcula rota e inicia a navegação curva a curva para o destino especificado.
- **Parâmetros:**
  - `destination` (string, obrigatório): Destino desejado (ex: *"Aeroporto de Guarulhos"*, *"Avenida Paulista, 1000"*, *"Shopping Morumbi"*).
  - `mode` (string, opcional): Modo de transporte (`'driving'`, `'walking'`, `'transit'`, `'bicycling'`).
  - `avoid` (string, opcional): Opção para evitar `'tolls'` (pedágios) ou `'highways'` (rodovias).
- **Exemplo Falado:**
  - *"Aton, trace uma rota até o Aeroporto de Congonhas"*
  - *"Aton, como chego em Santos evitando pedágios?"*

### 3.2. `find_places_nearby`
- **Descrição:** Localiza pontos de interesse e serviços próximos no Google Maps.
- **Parâmetros:**
  - `place_type` (string, obrigatório): Tipo de local (`'posto de gasolina'`, `'restaurante'`, `'farmácia'`, `'hospital'`, `'estacionamento'`).
  - `location` (string, opcional): Bairro ou cidade de referência.
- **Exemplo Falado:**
  - *"Aton, encontre o posto de gasolina mais próximo"*
  - *"Aton, procure farmácias abertas aqui perto"*

### 3.3. `estimate_traffic_route`
- **Descrição:** Consulta as condições de trânsito em tempo real e abre o mapa de congestionamento.
- **Parâmetros:**
  - `destination` (string, obrigatório): Destino para checar o fluxo de trânsito.
  - `origin` (string, opcional): Ponto de partida (padrão: localização atual).
- **Exemplo Falado:**
  - *"Aton, como está o trânsito até a Marginal Pinheiros?"*

---

## 4. Integração no Celular e no Carro (Custo Zero)

- **No Computador / Navegador:** Abre a rota interativa completa em tela cheia com a camada de trânsito ativada.
- **No Smartphone Android / Android Auto:** Utiliza o URI de Intent nativo:
  ```text
  google.navigation:q={destino}&mode=d
  ```
  Ao receber esse intent, o smartphone Android inicia imediatamente o modo GPS curva a curva oficial do Google Maps, conectando-se ao som do carro via Bluetooth ou Android Auto, **sem gastar créditos da Google Cloud Platform**.

---

## 5. Como Testar

Para executar a bateria de testes automatizados:
```powershell
.\run.bat test
```
Ou diretamente:
```powershell
python -m pytest tests/test_google_maps.py
```

### Teste Interativo por Voz:
1. Inicie o Aton:
   ```powershell
   .\run.bat
   ```
2. Acorde o Aton dizendo *"Aton"* (ou pressione `[ENTER]`).
3. Diga: *"Aton, trace uma rota para a Avenida Paulista evitando pedágios"*.
4. O Google Maps abrirá instantaneamente na tela traçando a rota enquanto o Aton confirma por voz: *"Traçando rota sem pedágios para 'Avenida Paulista', senhor. Boa viagem!"*.
