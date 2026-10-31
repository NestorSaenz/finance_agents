"""RateLimitExceededError: a bucket-specific Spanish message, same code and details."""

import pytest

from app.core.exceptions import RateLimitExceededError
from app.src.ratelimit.models import RateLimitBucket

MINUTE_MESSAGE = "Has enviado demasiados mensajes; espera un momento y vuelve a intentarlo."


def _error(bucket: RateLimitBucket, limit: int, retry_after: int) -> RateLimitExceededError:
    return RateLimitExceededError(bucket, limit, retry_after)


def test_minute_bucket_keeps_the_burst_message_whatever_the_wait() -> None:
    assert _error(RateLimitBucket.CHAT_MINUTE, 10, 30).message == MINUTE_MESSAGE


@pytest.mark.parametrize(
    ("retry_after", "when"),
    [
        (1, "en unos minutos"),
        (3599, "en unos minutos"),
        (3600, "en una hora"),
        (3601, "en unas 2 horas"),  # rounded up
        (7200, "en unas 2 horas"),
        (86_000, "en unas 24 horas"),
    ],
)
def test_image_day_message_states_the_limit_and_the_wait(retry_after: int, when: str) -> None:
    error = _error(RateLimitBucket.IMAGE_DAY, 30, retry_after)

    assert error.message == f"Llegaste al límite de 30 imágenes por día. Podrás enviar más {when}."


@pytest.mark.parametrize(
    ("retry_after", "when"),
    [(600, "en unos minutos"), (5400, "en unas 2 horas"), (10_800, "en unas 3 horas")],
)
def test_chat_day_message_states_the_limit_and_the_wait(retry_after: int, when: str) -> None:
    error = _error(RateLimitBucket.CHAT_DAY, 100, retry_after)

    assert error.message == (
        f"Llegaste al límite de 100 mensajes por día. Podrás escribir de nuevo {when}."
    )


def test_code_and_details_are_unchanged() -> None:
    error = _error(RateLimitBucket.IMAGE_DAY, 30, 7200)

    assert error.code == "RATE_LIMIT_EXCEEDED"
    assert error.details == {"bucket": "image_day", "limit": 30, "retry_after": 7200}


def test_a_plain_string_bucket_still_selects_the_message() -> None:
    # The service/repository pass bucket values around as strings in places.
    assert RateLimitExceededError("image_day", 30, 60).message.startswith(
        "Llegaste al límite de 30 imágenes"
    )
