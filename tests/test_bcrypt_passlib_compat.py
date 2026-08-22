from passlib.context import CryptContext


def test_passlib_bcrypt_backend_can_hash_and_verify() -> None:
    context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    plain_text = "phase52-compatibility-check"
    hashed = context.hash(plain_text)

    assert hashed.startswith("$2")
    assert context.verify(plain_text, hashed) is True
