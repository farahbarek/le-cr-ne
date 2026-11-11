"""Tests de l'interface web (serveur Flask). Lancer depuis la racine du projet :

    python -m unittest discover -s viewer/tests -v
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
VIEWER = os.path.dirname(HERE)
sys.path.insert(0, VIEWER)

import app as viewer_app  # noqa: E402


class ViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        viewer_app.app.config["TESTING"] = True
        cls.client = viewer_app.app.test_client()

    def test_index_page(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Visualiseur 3D", r.data)
        r.close()

    def test_vendor_files_served(self):
        for name in ("three.module.js", "STLLoader.js", "OrbitControls.js"):
            r = self.client.get(f"/static/vendor/{name}")
            self.assertEqual(r.status_code, 200, name)
            r.close()

    def test_info(self):
        data = self.client.get("/api/info").get_json()
        self.assertIn("bone", data["tissues"])

    def test_rejects_missing_file(self):
        r = self.client.post("/api/convert", data={"tissue": "bone"})
        self.assertEqual(r.status_code, 400)

    def test_rejects_bad_tissue(self):
        r = self.client.post("/api/convert", data={"sample": "1", "tissue": "../../etc"})
        self.assertEqual(r.status_code, 400)

    def test_stl_id_is_validated(self):
        self.assertEqual(self.client.get("/api/stl/../../etc/passwd.stl").status_code, 404)
        self.assertEqual(self.client.get("/api/stl/notahexid.stl").status_code, 404)

    @unittest.skipUnless(os.path.exists(viewer_app.SAMPLE), "échantillon absent")
    def test_convert_sample_and_download(self):
        r = self.client.post("/api/convert", data={"sample": "1", "tissue": "bone", "reduce": "0.95"})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        data = r.get_json()
        self.assertGreater(data["triangles"], 1000)
        stl = self.client.get(data["stl_url"])
        self.assertEqual(stl.status_code, 200)
        self.assertGreater(len(stl.data), 80 + 50 * 1000)  # STL binaire
        stl.close()

    @unittest.skipUnless(os.path.exists(viewer_app.SAMPLE), "échantillon absent")
    def test_convert_uploaded_nifti(self):
        with open(viewer_app.SAMPLE, "rb") as f:
            data = {"files": (f, "mon scanner.nii.gz"), "tissue": "skin", "reduce": "0.95"}
            r = self.client.post("/api/convert", data=data, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertTrue(r.get_json()["stl_url"].endswith(".stl"))


if __name__ == "__main__":
    unittest.main()
