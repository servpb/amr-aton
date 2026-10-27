# Documentação: Fundação e Configurações Base (config_and_foundation)

## 1. Objetivo
Este módulo estabelece a estrutura de pastas do projeto **AMR**, o isolamento de ambiente virtual, o gerenciamento seguro de variáveis de ambiente com Pydantic Settings e os scripts de inicialização rápida no Windows.

---

## 2. Componentes Criados

| Arquivo | Finalidade |
| :--- | :--- |
| `.gitignore` | Bloqueia versionamento de credenciais (`.env`), áudios e arquivos temporários. |
| `.env.example` | Modelo de variáveis de ambiente com configurações do Google AI Studio e áudio. |
| `pyproject.toml` | Declaração de dependências do Python (`google-genai`, `sounddevice`, `numpy`, etc.). |
| `run.bat` | Script de automação Windows para instalação, testes e execução do assistente. |
| `src/config.py` | Leitura tipada e validação de variáveis de ambiente via `pydantic-settings`. |
| `tests/test_config.py` | Testes automatizados de validação de configuração. |

---

## 3. Variáveis de Configuração Suportadas

| Variável | Padrão | Descrição |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | `""` | Chave de acesso à API do Google AI Studio. |
| `GEMINI_LIVE_MODEL` | `gemini-2.0-flash-exp` | Modelo multimodal em tempo real do Gemini. |
| `GEMINI_VOICE_NAME` | `Aoede` | Voz em português/inglês para o assistente. |
| `AMR_WAKE_WORD` | `amr` | Palavra de ativação local offline. |
| `AUDIO_SAMPLE_RATE` | `16000` | Taxa de amostragem de áudio em Hz para o microfone. |
| `CONVERSATION_TIMEOUT_SECONDS` | `7` | Segundos de silêncio antes do AMR voltar a dormir. |

---

## 4. Como Testar

Para rodar os testes automatizados deste módulo:
```cmd
run.bat test
```
Ou diretamente no terminal:
```bash
pytest tests/test_config.py
```
