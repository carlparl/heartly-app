import base64
from datetime import date
from importlib import import_module
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from profiles.models import Profile, ProfilePhoto


User = get_user_model()


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)
class ProfileGalleryModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="galleryuser",
            email="gallery@example.com",
            password="StrongPass123!",
            date_of_birth=date(2000, 1, 1),
        )
        self.profile = Profile.objects.get(user=self.user)

    def add_photo(self, position):
        return ProfilePhoto.objects.create(
            profile=self.profile,
            image=f"profiles/photos/photo-{position}.jpg",
            position=position,
        )

    def test_profile_accepts_four_ordered_photos(self):
        for position in range(1, 5):
            self.add_photo(position)

        self.assertEqual(
            list(self.profile.photos.values_list("position", flat=True)),
            [1, 2, 3, 4],
        )

    def test_position_outside_four_slots_is_rejected(self):
        photo = ProfilePhoto(
            profile=self.profile,
            image="profiles/photos/fifth.jpg",
            position=5,
        )

        with self.assertRaises(ValidationError):
            photo.full_clean()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProfilePhoto.objects.create(
                    profile=self.profile,
                    image="profiles/photos/fifth.jpg",
                    position=5,
                )

    def test_profile_cannot_reuse_a_photo_position(self):
        self.add_photo(1)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.add_photo(1)

    def test_primary_photo_uses_lowest_position(self):
        second = self.add_photo(2)
        first = self.add_photo(1)

        self.assertEqual(self.profile.primary_photo, first)
        self.assertNotEqual(self.profile.primary_photo, second)
        self.assertIn("photo-1.jpg", self.profile.primary_photo_url)

    def test_primary_photo_url_falls_back_to_legacy_field(self):
        self.profile.profile_picture = "profiles/photos/legacy.jpg"
        self.profile.save(update_fields=["profile_picture"])

        self.assertIsNone(self.profile.primary_photo)
        self.assertIn("legacy.jpg", self.profile.primary_photo_url)

    def test_legacy_picture_copy_is_idempotent(self):
        self.profile.profile_picture = "profiles/photos/legacy.jpg"
        self.profile.save(update_fields=["profile_picture"])
        migration = import_module(
            "profiles.migrations.0009_profilephoto"
        )

        migration.copy_legacy_profile_pictures(django_apps, None)
        migration.copy_legacy_profile_pictures(django_apps, None)

        photos = ProfilePhoto.objects.filter(profile=self.profile)
        self.assertEqual(photos.count(), 1)
        self.assertEqual(photos.get().position, 1)
        self.assertEqual(
            photos.get().image.name,
            self.profile.profile_picture.name,
        )

    def test_deleting_profile_deletes_gallery_rows(self):
        self.add_photo(1)
        profile_id = self.profile.id

        self.profile.delete()

        self.assertFalse(
            ProfilePhoto.objects.filter(profile_id=profile_id).exists()
        )


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    },
)
class ProfileGalleryEditingTests(TestCase):
    PNG_BYTES = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElE"
        "QVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
    )

    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.media_override = override_settings(
            MEDIA_ROOT=self.media_directory.name
        )
        self.media_override.enable()

        self.user = User.objects.create_user(
            username="galleryeditor",
            email="galleryeditor@example.com",
            password="StrongPass123!",
            full_name="Gallery Editor",
            gender="female",
            interested_in="male",
            date_of_birth=date(2000, 1, 1),
        )
        self.profile = Profile.objects.get(user=self.user)
        self.profile.display_name = "Gallery Editor"
        self.profile.gender = Profile.GENDER_WOMAN
        self.profile.connection_goal = Profile.CONNECTION_DATING
        self.profile.interested_in = Profile.INTERESTED_IN_MEN
        self.profile.save()
        self.client.force_login(self.user)

    def tearDown(self):
        self.media_override.disable()
        self.media_directory.cleanup()
        super().tearDown()

    def upload(self, name):
        return SimpleUploadedFile(
            name,
            self.PNG_BYTES,
            content_type="image/png",
        )

    def profile_data(self):
        self.profile.refresh_from_db()
        return {
            "profile_version": self.profile.updated_at.isoformat(
                timespec="microseconds"
            ),
            "display_name": "Gallery Editor",
            "username": "galleryeditor",
            "bio": "Testing the four photo gallery.",
            "gender": Profile.GENDER_WOMAN,
            "connection_goal": Profile.CONNECTION_DATING,
            "interested_in": Profile.INTERESTED_IN_MEN,
        }

    def test_edit_page_renders_exactly_four_photo_inputs(self):
        response = self.client.get(reverse("profiles:edit_profile"))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertEqual(html.count('data-profile-photo-input="'), 4)
        self.assertContains(response, "Photo 1")
        self.assertContains(response, "Photo 4")

    def test_uploads_four_photos_and_synchronizes_primary(self):
        data = self.profile_data()
        for position in range(1, 5):
            data[f"photo_{position}"] = self.upload(
                f"gallery-{position}.png"
            )

        response = self.client.post(
            reverse("profiles:edit_profile"),
            data,
        )

        self.assertRedirects(
            response,
            reverse("profiles:profile_home"),
            fetch_redirect_response=False,
        )
        self.profile.refresh_from_db()
        photos = list(self.profile.photos.order_by("position"))
        self.assertEqual([photo.position for photo in photos], [1, 2, 3, 4])
        self.assertEqual(
            self.profile.profile_picture.name,
            photos[0].image.name,
        )

    def test_removing_primary_compacts_slots_and_updates_legacy_field(self):
        first = ProfilePhoto.objects.create(
            profile=self.profile,
            image="profiles/photos/first.jpg",
            position=1,
        )
        second = ProfilePhoto.objects.create(
            profile=self.profile,
            image="profiles/photos/second.jpg",
            position=2,
        )
        self.profile.profile_picture = first.image.name
        self.profile.save(update_fields=["profile_picture"])

        data = self.profile_data()
        data["remove_1"] = "on"
        storage = ProfilePhoto._meta.get_field("image").storage
        with patch.object(storage, "delete") as delete_file:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse("profiles:edit_profile"),
                    data,
                )

        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        remaining = self.profile.photos.get()
        self.assertEqual(remaining.position, 1)
        self.assertEqual(remaining.image.name, second.image.name)
        self.assertEqual(
            self.profile.profile_picture.name,
            second.image.name,
        )
        delete_file.assert_called_once_with(first.image.name)

    def test_edit_forms_include_double_submit_protection(self):
        profile_response = self.client.get(
            reverse("profiles:edit_profile")
        )
        interests_response = self.client.get(
            reverse("profiles:edit_interests")
        )

        for response in (profile_response, interests_response):
            self.assertContains(response, "let isSubmitting = false")
            self.assertContains(response, "submitButton.disabled = true")

    def test_upload_and_remove_same_slot_is_rejected_without_changes(self):
        original = ProfilePhoto.objects.create(
            profile=self.profile,
            image="profiles/photos/original.jpg",
            position=1,
        )
        data = self.profile_data()
        data["photo_1"] = self.upload("replacement.png")
        data["remove_1"] = "on"

        response = self.client.post(
            reverse("profiles:edit_profile"),
            data,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("photo_1", response.context["photo_form"].errors)
        self.assertEqual(self.profile.photos.get(), original)

    def test_profile_media_includes_all_gallery_photos(self):
        for position in range(1, 5):
            ProfilePhoto.objects.create(
                profile=self.profile,
                image=f"profiles/photos/media-{position}.jpg",
                position=position,
            )

        response = self.client.get(reverse("profiles:profile_media"))

        self.assertEqual(response.status_code, 200)
        profile_items = [
            item
            for item in response.context["media_items"]
            if item["type"] == "Profile photo"
        ]
        self.assertEqual(len(profile_items), 4)
