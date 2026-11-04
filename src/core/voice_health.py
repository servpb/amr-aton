"""Pure readiness and conversation limits, independent of audio hardware."""
def readiness(*, muted, microphone_healthy, detector_ready, warmup_complete, warmup_error):
    if muted:
        return "muted", "Microfone silenciado"
    if not detector_ready:
        return "init_error", "Reconhecimento local indisponível"
    if not microphone_healthy:
        return "mic_error", "Aguardando áudio do microfone"
    if warmup_error:
        return "init_error", "Falha no carregamento de componentes"
    if not warmup_complete:
        return "local_listening", "Escuta local ativa (carregando componentes)"
    return "ready", "Pronto para conversar (diga Aton)"

def session_expired(started_at, now, maximum_seconds):
    return started_at > 0 and now - started_at >= maximum_seconds
