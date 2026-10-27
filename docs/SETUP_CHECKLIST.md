# SETUP_CHECKLIST.md - Checklist de Configuração do AMR

Este checklist contém os passos manuais que você precisa realizar para rodar o AMR pela primeira vez. O processo leva menos de 5 minutos e não tem custos.

---

## 📋 Passo 1: Obter a Chave Gratuita do Google AI Studio

1. Acesse o portal oficial gratuito do Google: **[https://aistudio.google.com/](https://aistudio.google.com/)**
2. Faça login com a sua conta Google comum (@gmail.com).
3. No canto superior esquerdo, clique no botão azul **"Get API key"** (Obter chave de API).
4. Clique em **"Create API key"** (Criar chave de API) e selecione um projeto padrão (ou crie um novo gratuitamente).
5. Copie a chave gerada (ela começa com `AIzaSy...`).

> **Nota de Custo:** Essa chave opera na **camada gratuita (Free Tier)** do Google AI Studio, sem necessidade de cadastrar cartão de crédito.

---

## 📋 Passo 2: Configurar o Arquivo `.env`

1. Na pasta raiz do projeto (`amr/`), localize o arquivo `.env.example`.
2. Crie uma cópia dele com o nome exato **`.env`** (ou execute o comando no terminal: `copy .env.example .env`).
3. Abra o arquivo `.env` com seu editor de texto de preferência.
4. Cole sua chave obtida no Passo 1 na linha correspondente:
   ```env
   GEMINI_API_KEY=AIzaSySuaChaveAqui...
   ```
5. Salve o arquivo.

---

## 📋 Passo 3: Verificar Áudio no Windows

1. Certifique-se de que seu **microfone** e seus **alto-falantes/fones** estão conectados e definidos como os dispositivos padrão do Windows.
2. No menu Iniciar do Windows, pesquise por *"Configurações de som"* e confirme se a barra de teste do microfone se mexe quando você fala.

---

## 📋 Passo 4: Instalar as Dependências

Na raiz do projeto, abra o prompt de comando (PowerShell ou CMD) e execute:
```cmd
run.bat install
```
O script criará automaticamente o ambiente virtual isolado (`.venv`) e instalará as dependências necessárias.
