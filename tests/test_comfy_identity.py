"""
Tests for ComfyUI local identity workflows (PuLID / InstantID).

All Comfy HTTP traffic is mocked. The generator must:
  - resolve skills.comfyui.identityWorkflow to a bundled or custom graph,
  - upload the face reference and substitute %reference% (plus the usual
    placeholders) into the graph,
  - skip-if-missing: fall back to the plain workflow when the server lacks
    the identity nodes,
  - keep ignoring reference images when no identity workflow is configured.
"""
import base64
import json
import os
from unittest.mock import MagicMock

import pytest

from herandhim.core.image_gen.generator import (
    IDENTITY_WORKFLOWS,
    SeedreamError,
    SeedreamGenerator,
    _identity_workflow_path,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fakepixels"


# ── Fake Comfy HTTP server ───────────────────────────────────────────────────

class FakeComfy:
    """Answers the generator's requests.post/get like a ComfyUI server."""

    def __init__(self, node_classes=None):
        self.node_classes = node_classes  # None → mirror whatever is asked
        self.submitted_graphs = []
        self.uploads = []

    def _response(self, payload=None, content=b""):
        r = MagicMock()
        r.ok = True
        r.json.return_value = payload
        r.content = content
        return r

    def post(self, url, **kw):
        if url.endswith("/upload/image"):
            self.uploads.append(kw)
            return self._response({"name": "ref_upload.jpg", "subfolder": "", "type": "input"})
        if url.endswith("/prompt"):
            self.submitted_graphs.append(kw["json"]["prompt"])
            return self._response({"prompt_id": "pid-1"})
        raise AssertionError(f"unexpected POST {url}")

    def get(self, url, **kw):
        if url.endswith("/object_info"):
            classes = self.node_classes
            if classes is None:
                # Everything exists — build from all graphs we might submit
                classes = _all_known_classes()
            return self._response({c: {} for c in classes})
        if "/history/" in url:
            return self._response({"pid-1": {"outputs": {
                "15": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]},
            }}})
        if url.endswith("/view"):
            return self._response(content=PNG_BYTES)
        raise AssertionError(f"unexpected GET {url}")


def _all_known_classes():
    classes = set()
    tpl_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "herandhim", "templates", "comfyui",
    )
    for fname in os.listdir(tpl_dir):
        if fname.endswith(".json"):
            with open(os.path.join(tpl_dir, fname)) as f:
                graph = json.load(f)
            classes |= {n["class_type"] for n in graph.values()}
    # Built-in nodes used by the default workflow
    classes |= {"KSampler", "CheckpointLoaderSimple", "EmptyLatentImage",
                "CLIPTextEncode", "VAEDecode", "SaveImage"}
    return classes


@pytest.fixture
def fake_comfy(monkeypatch):
    server = FakeComfy()
    monkeypatch.setattr("herandhim.core.image_gen.generator.requests.post", server.post)
    monkeypatch.setattr("herandhim.core.image_gen.generator.requests.get", server.get)
    return server


@pytest.fixture
def reference_file(tmp_path):
    ref = tmp_path / "companion_reference.jpg"
    ref.write_bytes(b"\xff\xd8\xff" + b"fakejpeg")
    return str(ref)


def make_generator():
    return SeedreamGenerator(provider="comfyui", api_key="",
                             base_url="http://localhost:8188", model="")


# ── Workflow path resolution ─────────────────────────────────────────────────

class TestIdentityWorkflowPath:
    def test_unset_returns_empty(self, monkeypatch):
        monkeypatch.delenv("HERANDHIM_COMFYUI_IDENTITY_WORKFLOW", raising=False)
        assert _identity_workflow_path() == ""

    @pytest.mark.parametrize("alias", sorted(IDENTITY_WORKFLOWS))
    def test_bundled_aliases_resolve_to_packaged_files(self, alias, monkeypatch):
        monkeypatch.setenv("HERANDHIM_COMFYUI_IDENTITY_WORKFLOW", alias)
        path = _identity_workflow_path()
        assert os.path.isfile(path), f"{alias} → {path} missing"
        with open(path) as f:
            graph = json.load(f)  # must be valid API-format JSON
        inputs = [v for n in graph.values() for v in n["inputs"].values()]
        assert "%reference%" in inputs
        assert "%prompt%" in inputs

    def test_custom_path_passed_through(self, monkeypatch):
        monkeypatch.setenv("HERANDHIM_COMFYUI_IDENTITY_WORKFLOW", "/tmp/my_graph.json")
        assert _identity_workflow_path() == "/tmp/my_graph.json"


# ── Reference injection ──────────────────────────────────────────────────────

class TestIdentityGeneration:
    def test_reference_uploaded_and_injected(self, fake_comfy, reference_file, monkeypatch):
        monkeypatch.setenv("HERANDHIM_COMFYUI_IDENTITY_WORKFLOW", "flux-pulid")
        gen = make_generator()
        out = gen.generate("selfie at the beach", size="1024x1024", seed=42,
                           reference_image=reference_file)

        assert out == [{"b64": base64.b64encode(PNG_BYTES).decode()}]
        assert len(fake_comfy.uploads) == 1
        graph = fake_comfy.submitted_graphs[0]
        classes = {n["class_type"] for n in graph.values()}
        assert "ApplyPulidFlux" in classes

        load_image = next(n for n in graph.values() if n["class_type"] == "LoadImage")
        assert load_image["inputs"]["image"] == "ref_upload.jpg"

    def test_placeholders_substituted(self, fake_comfy, reference_file, monkeypatch):
        monkeypatch.setenv("HERANDHIM_COMFYUI_IDENTITY_WORKFLOW", "sdxl-instantid")
        gen = make_generator()
        gen.generate("portrait in the park", size="768x1152", seed=7,
                     reference_image=reference_file)

        graph = fake_comfy.submitted_graphs[0]
        sampler = next(n for n in graph.values() if n["class_type"] == "KSampler")
        assert sampler["inputs"]["seed"] == 7
        latent = next(n for n in graph.values() if n["class_type"] == "EmptyLatentImage")
        assert latent["inputs"]["width"] == 768
        assert latent["inputs"]["height"] == 1152
        positive = next(n for n in graph.values()
                        if n["class_type"] == "CLIPTextEncode"
                        and n["inputs"]["text"] == "portrait in the park")
        assert positive
        # No placeholder left behind anywhere
        leftovers = [v for n in graph.values() for v in n["inputs"].values()
                     if isinstance(v, str) and v.startswith("%") and v.endswith("%")]
        assert leftovers == []

    def test_missing_nodes_fall_back_to_plain_workflow(self, reference_file, monkeypatch):
        """Skip-if-missing: PuLID pack not installed → plain txt2img, no upload."""
        server = FakeComfy(node_classes={"KSampler", "CheckpointLoaderSimple",
                                         "EmptyLatentImage", "CLIPTextEncode",
                                         "VAEDecode", "SaveImage"})
        monkeypatch.setattr("herandhim.core.image_gen.generator.requests.post", server.post)
        monkeypatch.setattr("herandhim.core.image_gen.generator.requests.get", server.get)
        monkeypatch.setenv("HERANDHIM_COMFYUI_IDENTITY_WORKFLOW", "flux-pulid")

        gen = make_generator()
        out = gen.generate("selfie", size="1024x1024", seed=1,
                           reference_image=reference_file)

        assert out  # generation still succeeded
        assert server.uploads == []
        classes = {n["class_type"] for n in server.submitted_graphs[0].values()}
        assert "ApplyPulidFlux" not in classes
        assert "KSampler" in classes

    def test_no_identity_config_keeps_old_behaviour(self, fake_comfy, reference_file, monkeypatch):
        """supports_ref stays False without config: reference silently dropped."""
        monkeypatch.delenv("HERANDHIM_COMFYUI_IDENTITY_WORKFLOW", raising=False)
        gen = make_generator()
        out = gen.generate("selfie", size="1024x1024", seed=1,
                           reference_image=reference_file)

        assert out
        assert fake_comfy.uploads == []
        classes = {n["class_type"] for n in fake_comfy.submitted_graphs[0].values()}
        assert "LoadImage" not in classes

    def test_custom_identity_workflow_missing_file_raises(self, fake_comfy, reference_file, monkeypatch):
        monkeypatch.setenv("HERANDHIM_COMFYUI_IDENTITY_WORKFLOW", "/nonexistent/graph.json")
        gen = make_generator()
        with pytest.raises(SeedreamError, match="identity workflow not found"):
            gen.generate("selfie", size="1024x1024", seed=1,
                         reference_image=reference_file)

    def test_upload_failure_falls_back(self, reference_file, monkeypatch):
        server = FakeComfy()
        orig_post = server.post

        def failing_post(url, **kw):
            if url.endswith("/upload/image"):
                r = MagicMock()
                r.ok = False
                r.status_code = 500
                r.text = "disk full"
                r.json.side_effect = ValueError
                return r
            return orig_post(url, **kw)

        monkeypatch.setattr("herandhim.core.image_gen.generator.requests.post", failing_post)
        monkeypatch.setattr("herandhim.core.image_gen.generator.requests.get", server.get)
        monkeypatch.setenv("HERANDHIM_COMFYUI_IDENTITY_WORKFLOW", "flux-pulid")

        gen = make_generator()
        out = gen.generate("selfie", size="1024x1024", seed=1,
                           reference_image=reference_file)

        assert out
        classes = {n["class_type"] for n in server.submitted_graphs[0].values()}
        assert "ApplyPulidFlux" not in classes
