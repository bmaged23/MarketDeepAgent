import hashlib
from types import SimpleNamespace
import pytest
from app.customers.service import CustomerService
from app.utils.passwords import hash_password,verify_password
from app.utils.errors import ServiceError


def test_new_password_hash_and_legacy_verification():
    hashed=hash_password('test-password')
    assert hashed.startswith('pbkdf2_sha256$')
    assert verify_password('test-password',hashed)
    assert not verify_password('wrong',hashed)
    legacy='salt$'+hashlib.sha256(b'salttest-password').hexdigest()
    assert verify_password('test-password',legacy)
    assert not verify_password('password','bad-format')


def test_registration_login_and_duplicate_email(catalog):
    database,_=catalog
    service=CustomerService(database)
    data=SimpleNamespace(first_name='Test',last_name='Customer',email='test@example.com',password='password',phone=None,address=None)
    result=service.register(data)
    assert service.login(data)['person_id'] == result['person_id']
    with pytest.raises(ServiceError):
        service.register(data)
