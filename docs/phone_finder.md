# Documentação: Localizador de Celular Android (phone_finder)

## 1. Objetivo
O módulo **phone_finder** permite localizar o smartphone Android na casa ou escritório por comando de voz (*"Aton, onde está meu celular?"*), disparando um alerta sonoro contínuo em volume máximo mesmo que o aparelho esteja no silencioso ou vibrando.

---

## 2. Componentes e Estrutura

| Arquivo | Responsabilidade |
| :--- | :--- |
| `src/tools/phone_finder.py` | Lógica de disparo de webhook local para o smartphone Android (MacroDroid, Tasker, KDE Connect, Termux:API) e suporte a ADB sem fio. |
| `src/tools/__init__.py` | Registro na lista `ALL_ATON_TOOLS` e despacho no `dispatch_tool()`. |
| `src/config.py` | Configuração das variáveis `ANDROID_PHONE_IP` e `ANDROID_PHONE_PORT`. |
| `tests/test_phone_finder.py` | Bateria de testes unitários automatizados cobrindo disparo e silenciamento de alarmes. |

---

## 3. Ferramentas no Gemini Live

### 3.1. `find_phone`
- **Descrição:** Dispara um alarme sonoro no smartphone Android para localizá-lo ou silencia o alerta.
- **Parâmetros:**
  - `action` (string, obrigatório): `'ring'` (tocar alarme) ou `'stop'` (silenciar alarme).
- **Exemplo Falado:**
  - *"Aton, onde está meu celular?"*
  - *"Aton, faça meu celular tocar"*
  - *"Aton, já achei o celular, pode silenciar"*

---

## 4. Como Configurar no Celular (100% Custo Zero)

Você pode escolher qualquer um dos métodos gratuitos abaixo no seu smartphone Android:

### Opção A: Aplicativo Gratuito de Automação (MacroDroid ou Tasker)
1. Instale o **MacroDroid** (gratuito na Google Play).
2. Crie uma macro simples:
   - **Gatilho:** Webhook HTTP (ou Requisição HTTP recebida na porta 8080).
   - **Ação:** Definir volume de mídia para 100% + Tocar som de alarme contínuo.
3. No arquivo `.env` do Aton no PC:
   ```env
   ANDROID_PHONE_IP=192.168.1.150
   ANDROID_PHONE_PORT=8080
   ```

### Opção B: KDE Connect
1. Instale o KDE Connect no Windows e no Android (ambos no mesmo Wi-Fi).
2. O Aton pode disparar o comando nativo de busca de telefone (*Ring Device*).

---

## 5. Como Testar

Para executar a bateria de testes automatizados:
```powershell
.\run.bat test
```
Ou diretamente:
```powershell
python -m pytest tests/test_phone_finder.py
```

### Teste Interativo por Voz:
1. Inicie o Aton:
   ```powershell
   .\run.bat
   ```
2. Acorde o Aton dizendo *"Aton"* (ou pressione `[ENTER]`).
3. Diga: *"Aton, onde está meu celular?"*.
4. O Aton responderá: *"Disparando alerta sonoro no seu celular agora, senhor. Siga o som!"*.
