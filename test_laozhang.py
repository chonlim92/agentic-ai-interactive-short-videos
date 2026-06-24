"""Quick smoke test for LaoZhang AI Seedream image generation (all 3 models)."""
import os
import sys
from pathlib import Path

# Load .env
from dotenv import load_dotenv
load_dotenv("config/.env")

# Add agents/ dir so common.py is importable as a peer module
sys.path.insert(0, str(Path(__file__).parent / "agents"))

from generate_video import generate_image_seedream, SEEDREAM_MODELS, SEEDREAM_DEFAULT_MODEL

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


if __name__ == "__main__":
    key = os.getenv("LAOZHANG_API_KEY")
    if not key:
        print("ERROR: LAOZHANG_API_KEY not set in config/.env")
        sys.exit(1)
    print(f"API key loaded: {key[:8]}...{key[-4:]}\n")

    models_to_test = [
        ("seedream-5.0", "seedream-5-0-260128"),
        ("seedream-4.5", "seedream-4-5-251128"),
        ("seedream-4.0", "seedream-4-0-250828"),
    ]

    results = {}
    for model_name, model_id in models_to_test:
        try:
            test_seedream_image(model_name, model_id)
            results[model_name] = "PASS"
        except Exception as e:
            print(f"FAIL: {model_name} test failed: {e}\n")
            results[model_name] = f"FAIL: {e}"

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, status in results.items():
        print(f"  {name}: {status}")
    print(f"\nDefault model: {SEEDREAM_DEFAULT_MODEL}")
    print("Done. Check test_output/ for results.")
