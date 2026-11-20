class DomainError(Exception):
    """Base para erros esperados da aplicação."""


class AIServiceUnavailableError(DomainError):
    """O serviço de IA (Ollama) está fora do ar, lento demais ou sem o modelo
    necessário. A camada de apresentação converte isso em HTTP 503."""
