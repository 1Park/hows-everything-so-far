"""Real child-process protocol tests; these do not measure NPU performance."""

import asyncio
import json
import subprocess
import sys

import numpy as np
import pytest
from fastapi.testclient import TestClient

from common.config import ROOT, Settings
from services.sensory import create_sensory_app
from services.vision.backend import DinoVisionBackend
from services.vision.resident import ResidentRunner
from tests.test_vision_backend import make_bundle


@pytest.fixture
def worker(tmp_path, monkeypatch):
    child = tmp_path / "worker.py"
    child.write_text('''import argparse,os,sys,time
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser()
p.add_argument("--model_path")
p.add_argument("--vision_resident")
a=p.parse_args()
model=Path(a.model_path)
factor=float(model.read_text())
with (model.parent/"starts").open("a") as f: f.write(str(os.getpid())+"\\n")
if model.stem=="startup_hang": time.sleep(30)
if model.stem=="startup_crash": sys.exit(1)
print("VISION_READY",flush=True)
while line:=sys.stdin.readline():
    dest=Path(sys.stdin.readline().strip())
    if model.stem=="hang": time.sleep(30)
    if model.stem=="crash": sys.exit(1)
    for i,path in enumerate(Path(line.strip()).read_text().splitlines()):
        if model.stem=="missing": continue
        x=np.fromfile(path,dtype=np.float32)
        y=np.array([[float(x.sum())*factor,0]],np.float32)
        if model.stem=="badsize": y=y[:,:1]
        y.tofile(dest/f"output_{i}_0.raw")
    print("VISION_DONE",flush=True)
''', encoding="utf-8")
    original = subprocess.Popen
    children = []

    def launch(command, **kwargs):
        process = original([sys.executable, str(child), *command[1:]], **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr("services.vision.resident.subprocess.Popen", launch)
    yield tmp_path, children
    assert all(p.poll() is not None for p in children), "Native workers must be reaped"


def model(folder, name="dino"):
    path = folder / f"{name}.pte"
    path.write_text("2")
    return path


def test_model_loaded_once_inputs_change_and_output_arrays_are_independent(worker):
    folder, children = worker
    pte = model(folder)
    runner = ResidentRunner("native-worker", pte, (1, 2))
    try:
        assert runner.resident and len(children) == 1
        pte.write_text("100")  # A reloaded model would now use a different factor.
        first = runner.run([np.array([1], np.float32), np.array([3], np.float32)])
        second = runner.run([np.array([5], np.float32)])
        assert [x.tolist() for x in first] == [[[2, 0]], [[6, 0]]]
        assert second[0].tolist() == [[10, 0]]
        assert runner.status["pid"] == children[0].pid
        assert len((folder / "starts").read_text().splitlines()) == 1
    finally:
        runner.close()
    assert not runner.resident


@pytest.mark.parametrize("name", ["crash", "missing", "badsize", "hang"])
def test_failed_inference_invalidates_worker(worker, name):
    folder, _ = worker
    runner = ResidentRunner("native-worker", model(folder, name), (1, 2), timeout=0.15)
    try:
        with pytest.raises((RuntimeError, TimeoutError)):
            runner.run([np.ones(1, np.float32)])
        assert not runner.resident
        with pytest.raises(RuntimeError, match="not resident"):
            runner.run([np.ones(1, np.float32)])
    finally:
        runner.close()


@pytest.mark.parametrize("name", ["startup_crash", "startup_hang"])
def test_failed_startup_reaps_worker(worker, name):
    folder, _ = worker
    with pytest.raises((RuntimeError, TimeoutError)):
        ResidentRunner("native-worker", model(folder, name), (1, 2), startup_timeout=0.8)


def test_api_preloads_cli_bundle_without_any_analysis(worker):
    folder, children = worker
    bundle = make_bundle(folder, {"mode": "center"})
    cfg = json.loads((bundle / "bundle.json").read_text())
    cfg["dino"]["runner"] = "cli"
    (bundle / "bundle.json").write_text(json.dumps(cfg))
    model(folder)
    settings = Settings(vision_model_backend="external", vision_adapter="test:factory",
                        vision_model_path=str(bundle), vision_worker_bin="unused-worker")
    backend = DinoVisionBackend(settings=settings)
    with TestClient(create_sensory_app("vision", settings, backend)) as client:
        ready = client.get("/ready").json()
        assert ready["runners"]["dino"]["resident"] and len(children) == 1
        for scene in ("scene-1", "scene-2"):
            response = client.post("/v1/analyze", data={"scene_id": scene},
                                   files={"file": ("cup.jpg", (ROOT / "docs/assets/cups-example.jpg").read_bytes(), "image/jpeg")})
            assert response.status_code == 200, response.text
        assert client.get("/ready").json()["runners"]["dino"]["pid"] == children[0].pid
        assert len(children) == 1


def test_partial_model_load_failure_closes_first_worker(worker):
    folder, children = worker
    bundle = make_bundle(folder, {"mode": "yolo", "pte": "missing.pte", "runner": "cli"})
    cfg = json.loads((bundle / "bundle.json").read_text())
    cfg["dino"]["runner"] = "cli"
    (bundle / "bundle.json").write_text(json.dumps(cfg))
    model(folder)
    settings = Settings(vision_model_path=str(bundle), vision_worker_bin="unused-worker")
    backend = DinoVisionBackend(settings=settings)

    async def load():
        try:
            with pytest.raises(Exception, match="startup failed"):
                await backend.startup()
            assert not await backend.ready()
        finally:
            await backend.close()

    asyncio.run(load())
    assert len(children) == 1 and children[0].poll() is not None


def test_pipeline_loads_detector_and_dino_as_separate_resident_workers(worker):
    from services.vision.pipeline import VisionPipeline

    folder, children = worker
    bundle = make_bundle(folder, {"mode": "yolo", "pte": "detector.pte", "runner": "cli"})
    cfg = json.loads((bundle / "bundle.json").read_text())
    cfg["dino"]["runner"] = "cli"
    (bundle / "bundle.json").write_text(json.dumps(cfg))
    model(folder)
    model(folder, "detector")
    pipeline = VisionPipeline(bundle, resident=True, worker_bin="native-worker")
    try:
        assert len(children) == 2 and pipeline.resident
        assert pipeline.status["dino"]["pid"] != pipeline.status["detector"]["pid"]
    finally:
        pipeline.close()


async def test_http_cancellation_kills_inflight_native_worker(worker):
    folder, children = worker
    bundle = make_bundle(folder, {"mode": "center"})
    cfg = json.loads((bundle / "bundle.json").read_text())
    cfg["dino"].update(pte="hang.pte", runner="cli")
    (bundle / "bundle.json").write_text(json.dumps(cfg))
    model(folder, "hang")
    backend = DinoVisionBackend(settings=Settings(
        vision_model_path=str(bundle), vision_worker_bin="unused-worker"))
    try:
        await backend.startup()
        task = asyncio.create_task(backend.infer(
            (ROOT / "docs/assets/cups-example.jpg").read_bytes(), "image/jpeg", "scene", "normal"))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not await backend.ready()
        assert children[0].poll() is not None
    finally:
        await backend.close()
