"""Smoke test for LaoZhang AI: Seedream image + Seedance video generation."""
import os
import sys
from pathlib import Path

# Load .env
from dotenv import load_dotenv

load_dotenv("config/.env")

# Add agents/ dir so common.py is importable as a peer module
sys.path.insert(0, str(Path(__file__).parent / "agents"))

from generate_video import (
    LAOZHANG_SEEDANCE_DEFAULT,
    LAOZHANG_VIDEO_MODELS,
    SEEDREAM_DEFAULT_MODEL,
    generate_image_seedream,
    generate_video_laozhang,
)

output_dir = Path("test_output")
output_dir.mkdir(exist_ok=True)


def test_seedream_image(model_name: str, model_id: str):
    """Generate a minimal Seedream image via LaoZhang AI."""
    print("=" * 60)
    print(f"TEST: Seedream image — model={model_name} ({model_id})")
    print("=" * 60)
    out = generate_image_seedream(
        prompt="A cute cartoon cat sitting on a windowsill watching rain, anime style, soft pastel colors",
        model=model_name,
        output_path=output_dir / f"seedream_{model_name.replace('.', '_')}_test.png",
    )
    size_kb = out.stat().st_size / 1024
    print(f"\nResult: {out} ({size_kb:.1f} KB)")
    assert out.exists() and size_kb > 1, "Image file too small or missing"
    print("PASS\n")
    return True


def test_seedance_video(model_name: str = "seedance2.0"):
    """Generate a minimal Seedance video via LaoZhang AI (requires SeeDance2 group token)."""
    model_id = LAOZHANG_VIDEO_MODELS.get(model_name, LAOZHANG_SEEDANCE_DEFAULT)
    print("=" * 60)
    print(f"TEST: Seedance video — model={model_name} ({model_id}), 5s")
    print("=" * 60)
    prompt = {
        "description": "A cat sitting on a windowsill watching rain fall outside, calm atmosphere",
        "duration_seconds": 5,
    }
    out = generate_video_laozhang(
        prompt=prompt,
        model=model_name,
        quality="standard",
        seed=42,
        output_path=output_dir / f"seedance_{model_name.replace('.', '_')}_test.mp4",
    )
    size_kb = out.stat().st_size / 1024
    print(f"\nResult: {out} ({size_kb:.1f} KB)")
    assert out.exists() and size_kb > 10, "Video file too small or missing"
    print("PASS\n")
    return True


if __name__ == "__main__":
    key = os.getenv("LAOZHANG_API_KEY")
    seedance_key = os.getenv("LAOZHANG_SEEDANCE_API_KEY")
    if not key and not seedance_key:
        print("ERROR: LAOZHANG_API_KEY not set in config/.env")
        sys.exit(1)
    if key:
        print(f"LAOZHANG_API_KEY: {key[:8]}...{key[-4:]}")
    if seedance_key:
        print(f"LAOZHANG_SEEDANCE_API_KEY: {seedance_key[:8]}...{seedance_key[-4:]}")
    else:
        print("LAOZHANG_SEEDANCE_API_KEY: not set (Seedance video test may fail)")
    print()

    results = {}

    # Test Seedream image models
    models_to_test = [
        ("seedream-5.0", "seedream-5-0-260128"),
        ("seedream-4.5", "seedream-4-5-251128"),
        ("seedream-4.0", "seedream-4-0-250828"),
    ]
    for model_name, model_id in models_to_test:
        try:
            test_seedream_image(model_name, model_id)
            results[f"image:{model_name}"] = "PASS"
        except Exception as e:
            print(f"FAIL: {model_name} test failed: {e}\n")
            results[f"image:{model_name}"] = f"FAIL: {e}"

    # Test Seedance video (requires SeeDance2 group token)
    try:
        test_seedance_video("seedance2.0")
        results["video:seedance2.0"] = "PASS"
    except Exception as e:
        err_str = str(e)
        if "no available channels" in err_str:
            print(
                "SKIP: Seedance video requires a SeeDance2 group token.\n"
                "      Create one at LaoZhang token management with group=SeeDance2\n"
                "      and set LAOZHANG_SEEDANCE_API_KEY in config/.env\n"
            )
            results["video:seedance2.0"] = "SKIP (needs SeeDance2 token)"
        else:
            print(f"FAIL: Seedance video test failed: {e}\n")
            results["video:seedance2.0"] = f"FAIL: {e}"

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, status in results.items():
        print(f"  {name}: {status}")
    print(f"\nDefault image model: {SEEDREAM_DEFAULT_MODEL}")
    print(f"Default video model: {LAOZHANG_SEEDANCE_DEFAULT}")
    print("Done. Check test_output/ for results.")
