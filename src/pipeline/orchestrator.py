import os
import json
import shutil
import subprocess
import yaml
from typing import Dict, Any, Tuple, Optional

from src.llm.llm_model import get_gemini_model
from src.llm.prompt_builder import build_generation_prompt
from src.llm.output_parser import clean_json_text, parse_model_spec
from src.rag.retriever import query_rag
from src.prompt_describer.describer import expand_user_prompt

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "settings.yaml")
JSON_OUT_DIR = os.path.join(BASE_DIR, "outputs", "json-file")
BLENDER_OUT_DIR = os.path.join(BASE_DIR, "outputs", "blender-files")
BUILDER_SCRIPT = os.path.join(BASE_DIR, "tools", "model_build.py")


def load_settings() -> Dict[str, Any]:
    """Load configuration from config/settings.yaml."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {}


def find_blender_binary() -> Optional[str]:
    """Find the path to the blender executable.
    Prioritizes the configured path in settings.yaml, then PATH, then common paths.
    """
    settings = load_settings()
    configured_path = settings.get("blender", {}).get("executable_path")
    if configured_path and os.path.exists(configured_path):
        return configured_path

    # Check system PATH
    blender_path = shutil.which("blender")
    if blender_path:
        return blender_path

    # Check common Windows installation paths
    common_paths = [
        r"C:\Program Files\Blender Foundation\Blender 4.3\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender\blender.exe",
        r"D:\app\blender.exe",
    ]
    for path in common_paths:
        if os.path.exists(path):
            return path

    return None


def generate_3d_pipeline(
    user_description: str,
    use_describer: bool = True,
    use_rag: bool = True,
    temperature: float = 0.4,
) -> Tuple[bool, Dict[str, Any], str, str, Optional[str], Optional[str]]:
    """Run full 2-layer AI generation pipeline:
    1. Layer 1 AI (Prompt Describer): Expands user text into a detailed physical & geometric breakdown.
    2. RAG Retrieval: Finds relevant schemas/docs for the detailed prompt.
    3. Layer 2 AI (3D Model Architect): Generates Universal 3D Model Spec JSON.
    4. Parser & Storage: Validates and saves outputs/json-file/<id>.json.
    5. Blender Compiler: Executes tools/model_build.py to compile .blend & .glb.

    Returns:
        (success, spec_json, expanded_description, raw_ai_output, json_file_path, blend_file_path)
    """
    os.makedirs(JSON_OUT_DIR, exist_ok=True)
    os.makedirs(BLENDER_OUT_DIR, exist_ok=True)

    # 1. Layer 1 AI: Prompt Description & Technical Decomposition
    if use_describer:
        print("[Pipeline] Running Layer 1 AI: Prompt Describer...")
        expanded_desc = expand_user_prompt(user_description, temperature=0.5)
    else:
        expanded_desc = user_description

    # 2. RAG retrieval using the rich expanded description
    retrieved_docs = []
    if use_rag:
        try:
            retrieved_docs = query_rag(expanded_desc, top_k=2)
        except Exception:
            retrieved_docs = []

    # 3. Layer 2 AI: 3D Model Spec Generation
    print("[Pipeline] Running Layer 2 AI: 3D Model Architect...")
    llm = get_gemini_model(temperature=temperature)
    messages = build_generation_prompt(expanded_desc, retrieved_docs)
    response = llm.invoke(messages)
    raw_content = response.content

    # 4. Parse JSON
    is_valid, spec, err = parse_model_spec(raw_content)
    if not is_valid:
        return False, spec, expanded_desc, raw_content, None, None

    model_id = spec.get("meta", {}).get("id", "model")
    json_path = os.path.join(JSON_OUT_DIR, f"{model_id}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    # Also maintain default model.json
    default_json_path = os.path.join(JSON_OUT_DIR, "model.json")
    with open(default_json_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    # 5. Compile with Blender
    blender_bin = find_blender_binary()
    blend_path = os.path.join(BLENDER_OUT_DIR, f"{model_id}.blend")

    if blender_bin:
        cmd = [
            blender_bin,
            "-b",
            "-P",
            BUILDER_SCRIPT,
            "--",
            json_path,
            "--out",
            BLENDER_OUT_DIR,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if not os.path.exists(blend_path):
            print(f"Blender builder output: {result.stdout}\n{result.stderr}")
    else:
        print("Note: 'blender' executable not found. Saved .json spec.")

    final_blend = blend_path if os.path.exists(blend_path) else None
    return True, spec, expanded_desc, raw_content, json_path, final_blend
