from __future__ import annotations

import re
import unittest

from hidrostatik_test import app_metadata


class AppMetadataTests(unittest.TestCase):
    def test_version_is_semver(self) -> None:
        self.assertRegex(app_metadata.APP_VERSION, r"^\d+\.\d+\.\d+$")

    def test_release_tag_and_asset_templates_use_the_version(self) -> None:
        tag = f"{app_metadata.RELEASE_TAG_PREFIX}{app_metadata.APP_VERSION}"
        self.assertTrue(tag.startswith("hidrostatik-test-v"))
        windows = app_metadata.RELEASE_ASSET_TEMPLATE.format(version=app_metadata.APP_VERSION)
        macos = app_metadata.RELEASE_ASSET_TEMPLATE_MACOS.format(version=app_metadata.APP_VERSION)
        self.assertIn(app_metadata.APP_VERSION, windows)
        self.assertIn(app_metadata.APP_VERSION, macos)
        self.assertTrue(windows.endswith("-windows-x64.zip"))
        self.assertTrue(macos.endswith("-macos-universal.dmg"))

    def test_repository_identity_is_stable(self) -> None:
        self.assertEqual(app_metadata.GITHUB_OWNER, "SLedgehammer-dev12")
        self.assertEqual(app_metadata.GITHUB_REPO, "HYDRO")
        self.assertIn(app_metadata.GITHUB_REPO, app_metadata.RELEASES_API_URL)
        self.assertTrue(re.search(r"5007", app_metadata.SPEC_DOCUMENT_CODE))


if __name__ == "__main__":
    unittest.main()
