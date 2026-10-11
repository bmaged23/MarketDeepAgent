from app.utils.errors import ServiceError
from app.database.connection import connection
from app.customers.queries import customer_by_email, insert_customer
from app.utils.passwords import hash_password, verify_password


class CustomerService:
    def __init__(self, database_path):
        self.database_path = database_path

    def register(self, payload):
        with connection(self.database_path, write=True) as conn:
            if customer_by_email(conn, payload.email):
                raise ServiceError(400, "Email already registered")
            person_id = insert_customer(conn, payload, hash_password(payload.password))
            return {"person_id": person_id, "first_name": payload.first_name, "message": "Registered successfully"}

    def login(self, payload):
        with connection(self.database_path) as conn:
            row = customer_by_email(conn, payload.email)
        if not row or not row["password_hash"] or not verify_password(payload.password, row["password_hash"]):
            raise ServiceError(401, "Invalid email or password")
        return {"person_id": row["person_id"], "first_name": row["first_name"], "last_name": row["last_name"]}
