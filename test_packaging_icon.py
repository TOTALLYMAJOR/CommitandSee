import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent
PIL_AVAILABLE = importlib.util.find_spec("PIL") is not None


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(PIL_AVAILABLE, "Pillow is required to regenerate icon assets")
class PackagingIconTests(unittest.TestCase):
    def test_checked_in_assets_are_reproducible_and_multiresolution(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            png = temporary / "icon.png"
            ico = temporary / "icon.ico"
            subprocess.run(
                [sys.executable, str(ROOT / "packaging" / "generate_icon.py"),
                 "--png", str(png), "--ico", str(ico)],
                check=True,
            )
            self.assertEqual(digest(png), digest(ROOT / "docs" / "images" / "commitandsee-icon.png"))
            self.assertEqual(digest(ico), digest(ROOT / "packaging" / "CommitandSee.ico"))
            with Image.open(ico) as image:
                self.assertEqual(
                    image.ico.sizes(),
                    {(16, 16), (20, 20), (24, 24), (32, 32), (40, 40),
                     (48, 48), (64, 64), (128, 128), (256, 256)},
                )

    def test_pyinstaller_spec_embeds_icon(self):
        spec = (ROOT / "packaging" / "CommitandSee.spec").read_text(encoding="utf-8")
        self.assertIn("icon=str(root / 'packaging' / 'CommitandSee.ico')", spec)


if __name__ == "__main__":
    unittest.main()
