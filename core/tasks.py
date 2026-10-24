import logging

logger = logging.getLogger(__name__)


def enqueue(task, *args, inline):
    """Enfileira `task`. Se o broker estiver fora do ar, executa `inline(*args)` na hora: atrasar é melhor que perder.

    Nunca levanta: quem chama (uma regra de negócio já concluída) não deve falhar por causa de uma notificação.
    Os argumentos precisam ser simples (ids, textos): vão serializados em JSON para o broker.
    """
    try:
        task.delay(*args)
    except Exception:
        logger.exception("Não foi possível enfileirar %s; executando na hora", task.name)
        try:
            inline(*args)
        except Exception:
            logger.exception("Falha ao executar %s na hora", task.name)
