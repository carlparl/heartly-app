from django.conf import settings
from django.test import SimpleTestCase


class TestEnvironmentIsolationTests(SimpleTestCase):
    def test_test_database_is_local_sqlite(self):
        database = settings.DATABASES["default"]

        self.assertTrue(settings.RUNNING_TESTS)
        self.assertEqual(
            database["ENGINE"],
            "django.db.backends.sqlite3",
        )
        database_name = str(database["NAME"])
        self.assertTrue(
            database_name == ":memory:"
            or (
                database_name.startswith("file:memorydb_")
                and "mode=memory" in database_name
            )
        )
        self.assertEqual(
            str(database["TEST"]["NAME"]),
            ":memory:",
        )

    def test_external_services_are_disabled_for_tests(self):
        self.assertEqual(
            settings.STORAGES["default"]["BACKEND"],
            "django.core.files.storage.InMemoryStorage",
        )
        self.assertEqual(
            settings.CHANNEL_LAYERS["default"]["BACKEND"],
            "channels.layers.InMemoryChannelLayer",
        )
        self.assertEqual(
            settings.EMAIL_BACKEND,
            "django.core.mail.backends.locmem.EmailBackend",
        )
        self.assertEqual(
            settings.CACHES["default"]["BACKEND"],
            "django.core.cache.backends.locmem.LocMemCache",
        )
        self.assertFalse(settings.RATELIMIT_ENABLE)
        self.assertEqual(
            settings.PASSWORD_HASHERS,
            [
                "django.contrib.auth.hashers.MD5PasswordHasher",
            ],
        )
