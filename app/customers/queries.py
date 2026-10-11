def customer_by_email(conn, email):
    return conn.execute("SELECT * FROM person WHERE email=?", (email,)).fetchone()


def insert_customer(conn, data, password_hash):
    return conn.execute("""INSERT INTO person(first_name,last_name,email,phone,address,password_hash)
        VALUES (?,?,?,?,?,?)""", (data.first_name,data.last_name,data.email,data.phone,data.address,password_hash)).lastrowid
