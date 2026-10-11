class ServiceError(Exception):
    """An expected business-rule failure, translated to HTTP only at the API edge."""
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail
