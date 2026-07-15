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


PROFILE_GENDER_TO_USER_GENDER = {
    "man": "male",
    "woman": "female",
    "non_binary": "non_binary",
    "other": "prefer_not_to_say",
}


PROFILE_PREFERENCE_TO_USER_PREFERENCE = {
    "men": "male",
    "women": "female",
    "everyone": "both",
}


IDENTITY_ISSUE_MESSAGES = {
    "missing_display_name": "Add the name you want people to see.",
    "missing_date_of_birth": "Confirm your date of birth.",
    "invalid_legal_age": (
        "Heartly Discover is available only to confirmed adults "
        "between 18 and 100."
    ),
    "profile_age_mismatch": (
        "Your stored age needs to be synchronized with your date of birth."
    ),
    "missing_or_invalid_gender": "Choose your gender.",
    "missing_or_invalid_preference": "Choose who you want to meet.",
    "gender_not_synchronized": (
        "Confirm your gender so your account and profile match."
    ),
    "preference_not_synchronized": (
        "Confirm who you want to meet so your account and profile match."
    ),
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


def mapped_user_gender(profile_gender):
    return PROFILE_GENDER_TO_USER_GENDER.get(
        (profile_gender or "").strip()
    )


def mapped_user_preference(profile_preference):
    return PROFILE_PREFERENCE_TO_USER_PREFERENCE.get(
        (profile_preference or "").strip()
    )


def identity_repair_issues(user, profile):
    issues = []

    if not profile:
        return [
            "missing_display_name",
            "missing_date_of_birth",
            "missing_or_invalid_gender",
            "missing_or_invalid_preference",
        ]

    if not (getattr(profile, "display_name", "") or "").strip():
        issues.append("missing_display_name")

    date_of_birth = getattr(user, "date_of_birth", None)
    confirmed_age = confirmed_legal_age(user)

    if not date_of_birth:
        issues.append("missing_date_of_birth")
    elif confirmed_age is None:
        issues.append("invalid_legal_age")
    elif getattr(profile, "age", None) != confirmed_age:
        issues.append("profile_age_mismatch")

    profile_gender = (
        getattr(profile, "gender", "") or ""
    ).strip()
    expected_user_gender = mapped_user_gender(profile_gender)

    if expected_user_gender is None:
        issues.append("missing_or_invalid_gender")
    elif (
        getattr(user, "gender", "") or ""
    ).strip() != expected_user_gender:
        issues.append("gender_not_synchronized")

    profile_preference = (
        getattr(profile, "interested_in", "") or ""
    ).strip()
    expected_user_preference = mapped_user_preference(
        profile_preference
    )

    if expected_user_preference is None:
        issues.append("missing_or_invalid_preference")
    elif (
        getattr(user, "interested_in", "") or ""
    ).strip() != expected_user_preference:
        issues.append("preference_not_synchronized")

    return issues


def identity_issue_messages(user, profile):
    return [
        IDENTITY_ISSUE_MESSAGES.get(issue, issue)
        for issue in identity_repair_issues(user, profile)
    ]


def identity_is_complete(user, profile):
    return not identity_repair_issues(user, profile)
