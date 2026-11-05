# Continuidade de historias entre chamadas

Pedido autorizado em05/11/2026. GeminiLiveClient preserva em RAM um pedido de historia
recente (1500caracteres) e trecho gerado (2500caracteres), validade15min. Transcricoes
input/output do proprio Gemini alimentam o contexto; nao grava audio ou transcricao
em arquivo nem encaminha a Groq/OpenRouter. Novo pedido explicito de historia troca
referencia antiga; pergunta de conta nao substitui o tema. Continuar/retomar conserva.
Contexto e incluido como dados sem autoridade para executar acoes na proxima sessao.
O trecho pode nao ter sido ouvido integralmente. Modelo deve esclarecer ambiguidade
e aguardar pedido, nunca continuar automaticamente ao despertar.
Limites: reconhecimento textual pode errar, pedidos sem a palavra historia podem nao
ser capturados; sem contexto preexistente deve pedir qual historia. Nao persiste apos
reinicio do processo. Nao reativa confirmacoes de ferramentas ou destino de dispositivo.
Validacao simulada em tests/test_story_context.py; retomada real ainda pendente.
Teste: Aton conte historia de castelo; Pare; Aton quanto e7+5; Pare; Aton continue a
historia. Esperado: castelo, sem escolher historia antiga. Repetir com novo tema.
