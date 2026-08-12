"""Static values for the users module."""

from typing import Final

# Supabase table backing per-user profile / onboarding state.
USER_PROFILES_TABLE: Final[str] = "user_profiles"

# Active ISO-4217 currency codes accepted for a user's display currency.
#
# The LLM proposes a code (inferred from what the user says) and this canonical
# set is the authority that validates it — a tiny inline frozenset kept on
# purpose (no pycountry, no country->currency table). It is not exhaustive of the
# whole standard: it covers LatAm currencies plus the major world ones the app
# is likely to see. Currency is display/labeling only (no conversion), so a
# wrong code corrupts every shown amount — hence validation is strict.
ISO_4217_CODES: Final[frozenset[str]] = frozenset(
    {
        # Latin America
        "COP",  # Colombian peso (primary market)
        "MXN",  # Mexican peso
        "ARS",  # Argentine peso
        "CLP",  # Chilean peso
        "PEN",  # Peruvian sol
        "BRL",  # Brazilian real
        "GTQ",  # Guatemalan quetzal
        "CRC",  # Costa Rican colón
        "DOP",  # Dominican peso
        "UYU",  # Uruguayan peso
        "BOB",  # Bolivian boliviano
        "PYG",  # Paraguayan guaraní
        "VES",  # Venezuelan bolívar
        "HNL",  # Honduran lempira
        "NIO",  # Nicaraguan córdoba
        "PAB",  # Panamanian balboa
        "CUP",  # Cuban peso
        # North America / world reserve
        "USD",  # US dollar
        "CAD",  # Canadian dollar
        "EUR",  # Euro
        "GBP",  # Pound sterling
        "CHF",  # Swiss franc
        "JPY",  # Japanese yen
        "CNY",  # Chinese yuan renminbi
        # Europe (non-euro)
        "NOK",  # Norwegian krone
        "SEK",  # Swedish krona
        "DKK",  # Danish krone
        "PLN",  # Polish złoty
        "CZK",  # Czech koruna
        "HUF",  # Hungarian forint
        "RON",  # Romanian leu
        "BGN",  # Bulgarian lev
        "ISK",  # Icelandic króna
        "UAH",  # Ukrainian hryvnia
        "RUB",  # Russian ruble
        "TRY",  # Turkish lira
        # Asia-Pacific
        "AUD",  # Australian dollar
        "NZD",  # New Zealand dollar
        "HKD",  # Hong Kong dollar
        "SGD",  # Singapore dollar
        "TWD",  # New Taiwan dollar
        "KRW",  # South Korean won
        "INR",  # Indian rupee
        "IDR",  # Indonesian rupiah
        "MYR",  # Malaysian ringgit
        "THB",  # Thai baht
        "PHP",  # Philippine peso
        "VND",  # Vietnamese đồng
        "PKR",  # Pakistani rupee
        "BDT",  # Bangladeshi taka
        # Middle East / Africa
        "AED",  # UAE dirham
        "SAR",  # Saudi riyal
        "QAR",  # Qatari riyal
        "ILS",  # Israeli new shekel
        "ZAR",  # South African rand
        "EGP",  # Egyptian pound
        "NGN",  # Nigerian naira
        "KES",  # Kenyan shilling
        "MAD",  # Moroccan dirham
        "GHS",  # Ghanaian cedi
    }
)
