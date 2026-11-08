"""Uma tarefa em execução e apenas a consulta pendente mais recente."""
import logging
import threading


class LatestRequestWorker:
    def __init__(self, dispatch):
        self._dispatch = dispatch
        self._condition = threading.Condition()
        self._generation = 0
        self._pending = None
        self._closed = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def invalidate(self):
        with self._condition:
            self._generation += 1
            self._pending = None

    def submit(self, task, callback):
        with self._condition:
            if self._closed:
                return
            self._generation += 1
            self._pending = (self._generation, task, callback)
            if self._thread.ident is None:
                self._thread.start()
            self._condition.notify()

    def close(self):
        with self._condition:
            self._closed = True
            self._generation += 1
            self._pending = None
            self._condition.notify()

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or self._pending is not None)
                if self._closed:
                    return
                generation, task, callback = self._pending
                self._pending = None
            try:
                result = task()
            except Exception:
                logging.exception("Falha na consulta em segundo plano")
                result = None
            # Verificar novamente na entrega: o loop principal pode estar ocupado.
            self._dispatch(self._deliver, generation, callback, result)
            # The worker may now sleep for the rest of the session.
            del task, callback, result

    def _deliver(self, generation, callback, result):
        with self._condition:
            current = not self._closed and generation == self._generation
        if current:
            callback(result)
        return False
