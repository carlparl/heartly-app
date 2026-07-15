from datetime import date


MINIMUM_LEGAL_AGE = 18
MAXIMUM_LEGAL_AGE = 100


USER_GENDER_TO_PROFILE_GENDER = {
    "male": "man",
    "female": "woman",
    "non_binary": "non_binary",
}


USER_PREFERENCE_TO_PROFILE_PREFERENCE = {
    "male": "men",
    "female": "women",
    "both": "everyone",
}


def age_from_date_of_birth(date_of_birth, *, on_date=None):
    if not date_of_birth:
        return None

    on_date = on_date or date.today()

    return (
        on_date.year
        - date_of_birth.year
        - (
            (on_date.month, on_date.day)
            < (date_of_birth.month, date_of_birth.day)
        )
    )


def confirmed_legal_age(user, *, on_date=None):
    age = age_from_date_of_birth(
        getattr(user, "date_of_birth", None),
        on_date=on_date,
    )

    if age is None:
        return None

    if not MINIMUM_LEGAL_AGE <= age <= MAXIMUM_LEGAL_AGE:
        return None

    return age


def _years_before(day, years):
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(
            year=day.year - years,
            month=2,
            day=28,
        )


def legal_birth_date_bounds(*, on_date=None):
    """
    Return (oldest_exclusive, youngest_inclusive).

    A confirmed adult must have:
      date_of_birth > oldest_exclusive
      date_of_birth <= youngest_inclusive
    """
    on_date = on_date or date.today()

    oldest_exclusive = _years_before(
        on_date,
        MAXIMUM_LEGAL_AGE + 1,
    )
    youngest_inclusive = _years_before(
        on_date,
        MINIMUM_LEGAL_AGE,
    )

    return oldest_exclusive, youngest_inclusive


def mapped_profile_gender(user_gender):
    return USER_GENDER_TO_PROFILE_GENDER.get(
        (user_gender or "").strip()
    )


def mapped_profile_preference(user_preference):
    return USER_PREFERENCE_TO_PROFILE_PREFERENCE.get(
        (user_preference or "").strip()
    )
