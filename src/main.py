import os
import sys
import json
import streamlit as st

# Ensure project root is always in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.pipeline.orchestrator import generate_3d_pipeline, find_blender_binary

# Page config
st.set_page_config(
    page_title="3D Gen AI Studio",
    page_icon="🧊",
    layout="wide",
)

st.title("🧊 3D Gen AI Studio")
st.markdown("Dual-layer AI Pipeline: **Prompt Describer** &rarr; **3D Procedural Architect** &rarr; **Blender Compiler**")

# Check Blender availability
blender_path = find_blender_binary()
if blender_path:
    st.caption(f"🔧 **Blender Ready**: `{blender_path}`")
else:
    st.info("ℹ️ **Blender CLI not detected**: Will generate `.json` specs. Configure `config/settings.yaml` to enable `.blend` compile.", icon="ℹ️")

# Layout: Main input vs Output panel
col_input, col_output = st.columns([1.05, 0.95], gap="large")

with col_input:
    st.subheader("📝 Model Description")
    prompt = st.text_area(
        label="Enter simple concept description:",
        placeholder="e.g. A coffee table, or a futuristic sci-fi terminal, or a potion bottle...",
        height=140,
    )

    with st.expander("⚙️ Pipeline Settings", expanded=True):
        use_describer = st.checkbox("Enable AI Describer Layer (Expands prompt into parts/dimensions)", value=True)
        use_rag = st.checkbox("Enable RAG Knowledge Retrieval", value=True)
        temperature = st.slider("3D Generator Temperature", min_value=0.0, max_value=1.0, value=0.4, step=0.05)

    generate_btn = st.button("🚀 Run 3D Pipeline", type="primary", use_container_width=True)

with col_output:
    st.subheader("📦 Generated Outputs & Downloads")

    # State container
    if "latest_generation" not in st.session_state:
        st.session_state.latest_generation = None

    if generate_btn:
        if not prompt.strip():
            st.warning("Please provide a description of the model.")
        else:
            with st.spinner("Processing pipeline (Prompt Expansion ➔ Spec Gen ➔ Blender Build)..."):
                success, spec, expanded_desc, raw_text, json_path, blend_path = generate_3d_pipeline(
                    user_description=prompt,
                    use_describer=use_describer,
                    use_rag=use_rag,
                    temperature=temperature,
                )

                if success:
                    st.session_state.latest_generation = {
                        "spec": spec,
                        "expanded_desc": expanded_desc,
                        "json_path": json_path,
                        "blend_path": blend_path,
                    }
                    st.success("✨ 3D Model and scene compiled successfully!")
                else:
                    st.error("Failed to parse valid 3D model specification.")
                    with st.expander("Raw AI Output"):
                        st.code(raw_text)

    # Render results if available
    latest = st.session_state.latest_generation
    if latest:
        spec = latest["spec"]
        meta = spec.get("meta", {})
        model_id = meta.get("id", "model")
        model_name = meta.get("name", "Generated 3D Model")

        st.markdown(f"### **{model_name}** (`{model_id}`)")

        # Download buttons
        btn_col1, btn_col2 = st.columns(2)

        # 1. Download JSON
        json_data = json.dumps(spec, indent=2)
        btn_col1.download_button(
            label="📥 Download .json Spec",
            data=json_data,
            file_name=f"{model_id}.json",
            mime="application/json",
            use_container_width=True,
        )

        # 2. Download .blend (if built)
        blend_path = latest["blend_path"]
        if blend_path and os.path.exists(blend_path):
            with open(blend_path, "rb") as f:
                blend_bytes = f.read()
            btn_col2.download_button(
                label="📥 Download .blend Scene",
                data=blend_bytes,
                file_name=f"{model_id}.blend",
                mime="application/x-blender",
                use_container_width=True,
            )
        else:
            btn_col2.button(
                label="📁 .blend Not Compiled",
                disabled=True,
                use_container_width=True,
            )

        # Details tabs
        tab_spec, tab_expanded, tab_json = st.tabs(["3D Summary", "Expanded Description (AI Layer 1)", "Raw JSON"])
        
        with tab_spec:
            st.write(f"- **Description**: {meta.get('description', 'N/A')}")
            st.write(f"- **Objects**: {len(spec.get('objects', []))}")
            st.write(f"- **Materials**: {len(spec.get('materials', []))}")
            st.write(f"- **Category**: {meta.get('category', 'N/A')}")
            st.write(f"- **Complexity**: {meta.get('complexity', 'N/A')}")

        with tab_expanded:
            st.markdown(latest["expanded_desc"])

        with tab_json:
            st.json(spec)
    else:
        st.info("Generated models, expanded breakdowns, and download buttons will appear here.")
