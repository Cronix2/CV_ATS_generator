class APIError(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after: int | None = None):
        self.status, self.code, self.message, self.retry_after = status, code, message, retry_after
        super().__init__(code)


def missing():
    return APIError(404, "not_found", "Ressource inconnue ou expirée.")
