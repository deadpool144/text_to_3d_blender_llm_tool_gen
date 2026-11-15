"""
model_build.py - Blender builder for Universal 3D Model Spec (1.0.0) JSON files.

Supports:
- Primitives: cube, uv_sphere, ico_sphere, cylinder, cone, torus, plane, circle
- 2D Profiles: lathe (revolution), extrude
- Curves: Bezier, Poly, NURBS with bevel_depth/caps (pipes, wires, handles)
- Text: extruded 3D text
- Custom Meshes: raw vertices and faces
- Mesh Operations: bevel, solidify/extrude, inset
- Modifiers: Subsurf, Mirror, Array, Solidify, Bevel, Boolean, Curve
- Materials: PBR Principled BSDF (base_color, metallic, roughness, specular, IOR, transmission, emission)
- Textures: Image nodes (color, roughness, normal) with box/smart UV mapping
- Hierarchy: Parent-child spatial links
- Duplicates: Linear, Grid, Radial, Explicit patterns
- Scene: Three-point lights, Auto-framing Camera, World color/lighting, Ground plane
- Export: .blend and .glb
"""
import json
import math
import os
import sys

try:
    import bpy
    from mathutils import Vector, Matrix
except ImportError:
    bpy = None
    Vector = Matrix = None


def log(*a):
    print("[builder]", *a)


# --------------------------------------------------------------------------- args
def parse_args():
    default_input = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "outputs", "json-file", "model.json")
    )
    default_out = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "outputs", "blender-files")
    )
    default_schema = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "data", "schemas", "model_spec_1.0.0.json")
    )

    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    spec_path = argv[0] if argv and not argv[0].startswith("--") else default_input
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else default_out
    schema_path = argv[argv.index("--schema") + 1] if "--schema" in argv else default_schema

    return spec_path, out_dir, schema_path


# --------------------------------------------------------------------------- checks
def validate(spec, spec_path, schema_path):
    if not schema_path or not os.path.exists(schema_path):
        log("schema file not found or not specified, skipping schema check")
        return
    try:
        import jsonschema
    except ImportError:
        log("jsonschema not available in Blender Python, skipping check")
        return
    try:
        with open(schema_path, encoding="utf-8") as f:
            jsonschema.Draft202012Validator(json.load(f)).validate(spec)
        log("schema validation OK")
    except Exception as e:
        log(f"WARNING: Schema validation: {e}")


def basic_checks(spec):
    ids = [o["id"] for o in spec.get("objects", [])]
    if len(set(ids)) != len(ids):
        sys.exit("Error: duplicate object ids")
    mats = {m["id"] for m in spec.get("materials", [])}
    for o in spec.get("objects", []):
        if o.get("parent") and o["parent"] not in ids:
            sys.exit(f"Error: {o['id']} has unknown parent {o['parent']}")
        if o.get("material") and o["material"] not in mats:
            sys.exit(f"Error: {o['id']} uses unknown material {o['material']}")
        for m in o.get("modifiers", []):
            if m["type"] == "boolean" and m["operand"] not in ids:
                sys.exit(f"Error: {o['id']} boolean operand {m['operand']} not found")
    for d in spec.get("duplicates", []):
        if d["source"] not in ids:
            sys.exit(f"Error: duplicate {d['id']} source {d['source']} not found")


# --------------------------------------------------------------------------- helpers
def link(obj):
    bpy.context.collection.objects.link(obj)


def make_active(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def apply_scale(obj):
    make_active(obj)
    bpy.ops.object.transform_apply(scale=True)


def fix_normals(obj):
    make_active(obj)
    if obj.type == "MESH":
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode="OBJECT")


def apply_modifier(obj, name):
    make_active(obj)
    bpy.ops.object.modifier_apply(modifier=name)


def set_in(node, names, value):
    for n in names:
        if n in node.inputs:
            node.inputs[n].default_value = value
            return


def resolve_target(t, objs):
    if isinstance(t, str):
        return objs[t].matrix_world.translation.copy()
    return Vector(t)


def point_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


# --------------------------------------------------------------------------- geometry
def make_primitive(g):
    shape, dims = g["shape"], g["dimensions"]
    seg = g.get("segments", 32)
    rings = g.get("rings", 16)
    scale = list(dims)
    if shape == "cube":
        bpy.ops.mesh.primitive_cube_add(size=1)
    elif shape == "uv_sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings, radius=0.5)
    elif shape == "ico_sphere":
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.5)
    elif shape == "cylinder":
        fill = "NGON" if g.get("caps", True) else "NOTHING"
        bpy.ops.mesh.primitive_cylinder_add(vertices=seg, radius=0.5, depth=1, end_fill_type=fill)
    elif shape == "cone":
        fill = "NGON" if g.get("caps", True) else "NOTHING"
        bpy.ops.mesh.primitive_cone_add(vertices=seg, radius1=0.5, radius2=0.5 * g.get("top_ratio", 0),
                                        depth=1, end_fill_type=fill)
    elif shape == "torus":
        t = g.get("tube_ratio", 0.25)
        major = 0.5 / (1 + t)
        minor = major * t
        bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=seg)
        scale[2] = dims[2] / (2 * minor)
    elif shape == "plane":
        bpy.ops.mesh.primitive_plane_add(size=1)
        scale[2] = 1
    elif shape == "circle":
        bpy.ops.mesh.primitive_circle_add(vertices=seg, radius=0.5, fill_type="NGON")
        scale[2] = 1
    obj = bpy.context.active_object
    obj.scale = scale
    apply_scale(obj)
    return obj


def make_profile(g, name):
    plane = g.get("plane", "XZ")
    pts = g["points"]
    if plane == "XZ":
        verts = [(x, 0, z) for x, z in pts]
    elif plane == "XY":
        verts = [(x, y, 0) for x, y in pts]
    else:
        verts = [(0, y, z) for y, z in pts]
    n = len(verts)
    closed = g.get("closed", True)
    mode = g["mode"]
    mesh = bpy.data.meshes.new(name)
    if mode == "extrude":
        mesh.from_pydata(verts, [], [list(range(n))])
    else:
        edges = [(i, i + 1) for i in range(n - 1)]
        if closed:
            edges.append((n - 1, 0))
        mesh.from_pydata(verts, edges, [])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    link(obj)

    if mode == "lathe":
        steps = g.get("segments", 32)
        mod = obj.modifiers.new("Lathe", "SCREW")
        mod.axis = g.get("axis", "Z")
        mod.angle = math.radians(g.get("angle_deg", 360))
        mod.steps = steps
        mod.render_steps = steps
        mod.use_merge_vertices = True
        mod.merge_threshold = 0.0001
        apply_modifier(obj, "Lathe")
        fix_normals(obj)
    elif mode == "extrude":
        mod = obj.modifiers.new("Extrude", "SOLIDIFY")
        mod.thickness = g.get("depth", 0.1)
        mod.offset = 0
        apply_modifier(obj, "Extrude")
        fix_normals(obj)
    else:
        log(f"WARNING: profile mode '{mode}' not supported, object {name} left as outline")
    return obj


def make_curve(g, name):
    """Create 3D curve (Bezier or Poly) with tube radius / bevel."""
    curve_data = bpy.data.curves.new(name, type="CURVE")
    curve_data.dimensions = "3D"
    curve_data.bevel_depth = g.get("bevel_depth", 0.02)
    curve_data.bevel_resolution = g.get("bevel_resolution", 4)
    curve_data.use_fill_caps = g.get("fill_caps", True)

    points = g.get("points", [])
    curve_type = g.get("curve_type", "poly")

    spline = curve_data.splines.new("BEZIER" if curve_type == "bezier" else "POLY")
    spline.use_cyclic_u = g.get("cyclic", False)

    if curve_type == "bezier":
        spline.bezier_points.add(len(points) - 1)
        for i, pt in enumerate(points):
            bp = spline.bezier_points[i]
            bp.co = pt.get("co", [0, 0, 0])
            if "handle_left" in pt:
                bp.handle_left = pt["handle_left"]
            if "handle_right" in pt:
                bp.handle_right = pt["handle_right"]
            bp.radius = pt.get("radius", 1.0)
    else:
        spline.points.add(len(points) - 1)
        for i, pt in enumerate(points):
            co = pt.get("co", [0, 0, 0])
            spline.points[i].co = (co[0], co[1], co[2], 1.0)

    obj = bpy.data.objects.new(name, curve_data)
    link(obj)
    return obj


def make_text(g, name):
    """Create extruded 3D Text object."""
    font_curve = bpy.data.curves.new(name=name, type="FONT")
    font_curve.body = g.get("body", "Text")
    font_curve.size = g.get("size", 1.0)
    font_curve.extrude = g.get("extrude", 0.05)
    font_curve.bevel_depth = g.get("bevel_depth", 0.005)

    align = g.get("align", "center").upper()
    if align in ["LEFT", "CENTER", "RIGHT"]:
        font_curve.align_x = align

    obj = bpy.data.objects.new(name, font_curve)
    link(obj)
    return obj


def make_custom_mesh(g, name):
    """Create custom polygon mesh from vertices and faces."""
    verts = [tuple(v) for v in g.get("vertices", [])]
    faces = [tuple(f) for f in g.get("faces", [])]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    link(obj)
    fix_normals(obj)
    return obj


def create_object(o):
    g = o["geometry"]
    kind = g["kind"]
    if kind == "primitive":
        obj = make_primitive(g)
    elif kind == "profile":
        obj = make_profile(g, o["id"])
    elif kind == "curve":
        obj = make_curve(g, o["id"])
    elif kind == "text":
        obj = make_text(g, o["id"])
    elif kind == "custom_mesh":
        obj = make_custom_mesh(g, o["id"])
    elif kind == "empty":
        obj = bpy.data.objects.new(o["id"], None)
        link(obj)
    else:
        sys.exit(f"Error: geometry kind '{kind}' not supported (object {o['id']})")

    obj.name = o["id"]
    t = o.get("transform", {})
    obj.location = t.get("location", [0, 0, 0])
    obj.rotation_euler = [math.radians(a) for a in t.get("rotation_deg", [0, 0, 0])]
    obj.scale = t.get("scale", [1, 1, 1])
    return obj


# --------------------------------------------------------------------------- materials
def make_material(m, textures, root):
    mat = bpy.data.materials.new(m["id"])
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    set_in(bsdf, ["Base Color"], m.get("base_color", [0.8, 0.8, 0.8, 1]))
    set_in(bsdf, ["Metallic"], m.get("metallic", 0))
    set_in(bsdf, ["Roughness"], m.get("roughness", 0.5))
    set_in(bsdf, ["Specular IOR Level", "Specular"], m.get("specular", 0.5))
    set_in(bsdf, ["IOR"], m.get("ior", 1.45))
    set_in(bsdf, ["Transmission Weight", "Transmission"], m.get("transmission", 0))
    set_in(bsdf, ["Coat Weight", "Clearcoat"], m.get("clearcoat", 0))
    set_in(bsdf, ["Alpha"], m.get("alpha", 1))
    em = m.get("emission")
    if em:
        set_in(bsdf, ["Emission Color", "Emission"], list(em["color"]) + [1])
        set_in(bsdf, ["Emission Strength"], em.get("strength", 1.0))
    if m.get("blend_mode", "opaque") != "opaque" or m.get("alpha", 1) < 1:
        try:
            mat.surface_render_method = "DITHERED"
        except AttributeError:
            mat.blend_method = "HASHED"

    tex_spec = m.get("texture")
    if tex_spec:
        add_texture(nt, bsdf, tex_spec, textures.get(tex_spec["texture_id"]), root, m["id"])
    return mat


def add_texture(nt, bsdf, spec, asset, root, mat_id):
    if not asset:
        log(f"WARNING: material {mat_id} references unknown texture {spec['texture_id']}")
        return
    size = asset.get("real_world_size_m", 1.0)
    box = spec.get("projection", "box") == "box"
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = [s / size for s in spec.get("scale", [1, 1, 1])]
    mapping.inputs["Rotation"].default_value = [math.radians(a) for a in spec.get("rotation_deg", [0, 0, 0])]
    mapping.inputs["Location"].default_value = spec.get("offset", [0, 0, 0])
    nt.links.new(coord.outputs["Object" if box else "UV"], mapping.inputs["Vector"])

    def image_node(rel, colorspace):
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            log(f"WARNING: texture file missing, skipped: {path}")
            return None
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(path)
        node.image.colorspace_settings.name = colorspace
        node.projection = "BOX" if box else "FLAT"
        node.projection_blend = 0.2
        nt.links.new(mapping.outputs["Vector"], node.inputs["Vector"])
        return node

    maps = asset.get("maps", {})
    if "color" in maps and (n := image_node(maps["color"], "sRGB")):
        nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
    if "roughness" in maps and (n := image_node(maps["roughness"], "Non-Color")):
        nt.links.new(n.outputs["Color"], bsdf.inputs["Roughness"])
    if "normal" in maps and (n := image_node(maps["normal"], "Non-Color")):
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = spec.get("normal_strength", 1.0)
        nt.links.new(n.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])


# --------------------------------------------------------------------------- finishing objects
def finish_object(o, obj, objs, mats):
    if o.get("parent"):
        obj.parent = objs[o["parent"]]

    if obj.type in ("MESH", "CURVE", "FONT"):
        if o.get("material") and o["material"] in mats:
            obj.data.materials.append(mats[o["material"]])
        if obj.type == "MESH" and o.get("shading", {}).get("smooth"):
            for p in obj.data.polygons:
                p.use_smooth = True

    for op in o.get("operations", []):
        add_operation(obj, op, o["id"])
    for m in o.get("modifiers", []):
        add_modifier(obj, m, objs, o["id"])

    if not o.get("visible", True):
        obj.hide_viewport = obj.hide_render = True
    try:
        obj.visible_shadow = o.get("cast_shadow", True)
    except AttributeError:
        pass


def add_operation(obj, op, oid):
    if op["op"] == "bevel":
        sel = op.get("select", {})
        mod = obj.modifiers.new("Bevel_op", "BEVEL")
        mod.width = op.get("width", 0.01)
        mod.segments = op.get("segments", 2)
        if sel.get("by") == "sharp":
            mod.limit_method = "ANGLE"
            mod.angle_limit = math.radians(sel.get("angle_deg", 30))
        elif sel.get("by") == "all":
            mod.limit_method = "NONE"
        else:
            mod.limit_method = "ANGLE"
    elif op["op"] in ("extrude", "solidify"):
        mod = obj.modifiers.new("Extrude_op", "SOLIDIFY")
        mod.thickness = op.get("distance", op.get("thickness", 0.05))
    elif op["op"] == "subdivide":
        mod = obj.modifiers.new("Subdivide_op", "SUBSURF")
        mod.levels = op.get("cuts", 1)
    else:
        log(f"WARNING: operation '{op['op']}' skipped for object {oid}")


def add_modifier(obj, m, objs, oid):
    t = m["type"]
    if t == "subsurf":
        mod = obj.modifiers.new("Subsurf", "SUBSURF")
        mod.levels = m.get("levels", 2)
        mod.render_levels = m.get("render_levels", 2)
    elif t == "mirror":
        mod = obj.modifiers.new("Mirror", "MIRROR")
        for i, ax in enumerate("XYZ"):
            mod.use_axis[i] = ax in m.get("axes", ["X"])
        mod.use_mirror_merge = m.get("merge", True)
        mod.merge_threshold = m.get("merge_threshold", 0.001)
        mod.use_clip = m.get("clip", True)
        if m.get("mirror_object") and m["mirror_object"] in objs:
            mod.mirror_object = objs[m["mirror_object"]]
    elif t == "array":
        mod = obj.modifiers.new("Array", "ARRAY")
        mod.count = m.get("count", 2)
        if m.get("constant_offset"):
            mod.use_relative_offset = False
            mod.use_constant_offset = True
            mod.constant_offset_displace = m["constant_offset"]
        else:
            mod.relative_offset_displace = m.get("relative_offset", [1, 0, 0])
        mod.use_merge_vertices = m.get("merge", False)
    elif t == "solidify":
        mod = obj.modifiers.new("Solidify", "SOLIDIFY")
        mod.thickness = m.get("thickness", 0.02)
        mod.offset = m.get("offset", -1)
        mod.use_even_offset = m.get("even_thickness", True)
    elif t == "bevel":
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = m.get("width", 0.01)
        mod.segments = m.get("segments", 3)
        if m.get("limit", "angle") == "angle":
            mod.limit_method = "ANGLE"
            mod.angle_limit = math.radians(m.get("angle_deg", 30))
        else:
            mod.limit_method = "NONE"
    elif t == "boolean":
        mod = obj.modifiers.new("Boolean", "BOOLEAN")
        mod.operation = m.get("operation", "difference").upper()
        if m.get("operand") in objs:
            mod.object = objs[m["operand"]]
        mod.solver = m.get("solver", "EXACT")
        if m.get("hide_operand", True) and m.get("operand") in objs:
            objs[m["operand"]].hide_render = True
            objs[m["operand"]].hide_viewport = True
    elif t == "curve":
        mod = obj.modifiers.new("Curve_Deform", "CURVE")
        if m.get("curve_object") in objs:
            mod.object = objs[m["curve_object"]]
        mod.deform_axis = m.get("deform_axis", "POS_X")
    else:
        log(f"WARNING: modifier '{t}' not supported yet, skipped ({oid})")


# --------------------------------------------------------------------------- duplicates
def copy_obj(src, name, linked):
    c = src.copy()
    if src.data is not None and not linked:
        c.data = src.data.copy()
    c.name = name
    link(c)
    return c


def make_duplicates(d, objs):
    src = objs[d["source"]]
    p = d["pattern"]
    linked = d.get("linked", True)
    n = 0

    def new(loc=None, rot=None):
        nonlocal n
        n += 1
        c = copy_obj(src, f"{d['id']}_{n}", linked)
        if loc is not None:
            c.location = loc
        if rot is not None:
            c.rotation_euler = rot
        return c

    kind = p["type"]
    if kind == "linear":
        for i in range(1, p["count"]):
            new(src.location + Vector(p["offset"]) * i)
    elif kind == "grid":
        cx, cy, cz = p["counts"]
        sx, sy, sz = p["spacing"]
        for ix in range(cx):
            for iy in range(cy):
                for iz in range(cz):
                    if (ix, iy, iz) != (0, 0, 0):
                        new(src.location + Vector((ix * sx, iy * sy, iz * sz)))
    elif kind == "radial":
        center = Vector(p.get("center", [0, 0, 0]))
        axis = p.get("axis", "Z")
        total = math.radians(p.get("angle_deg", 360))
        count = p["count"]
        step = total / count if total >= 2 * math.pi - 1e-6 else total / max(count - 1, 1)
        for i in range(1, count):
            rot = Matrix.Rotation(step * i, 4, axis)
            loc = center + rot @ (src.location - center)
            r = None
            if p.get("rotate_copies", True):
                r = (rot @ src.rotation_euler.to_matrix().to_4x4()).to_euler()
            new(loc, r)
    elif kind == "explicit":
        for t in p["transforms"]:
            c = new(Vector(t.get("location", [0, 0, 0])),
                    [math.radians(a) for a in t.get("rotation_deg", [0, 0, 0])])
            c.scale = t.get("scale", [1, 1, 1])
    if not d.get("include_source", True):
        src.hide_render = src.hide_viewport = True


# --------------------------------------------------------------------------- scene
def scene_bounds():
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in bpy.context.scene.objects:
        if o.type in ("MESH", "CURVE", "FONT") and not o.hide_render:
            eo = o.evaluated_get(dg)
            pts += [o.matrix_world @ Vector(c) for c in eo.bound_box]
    if not pts:
        return Vector((0, 0, 0)), 1.0, 0.0
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center = (lo + hi) / 2
    return center, max((p - center).length for p in pts), lo.z


def add_light(name, kind, loc, energy, color=(1, 1, 1), size=1.0, target=None,
              rot_deg=None, spot_deg=45, blend=0.15, shadow=True):
    data = bpy.data.lights.new(name, kind.upper())
    data.energy = energy
    data.color = color
    if kind == "area":
        data.size = size
    elif kind in ("point", "spot"):
        data.shadow_soft_size = size
    if kind == "spot":
        data.spot_size = math.radians(spot_deg)
        data.spot_blend = blend
    data.use_shadow = shadow
    obj = bpy.data.objects.new(name, data)
    link(obj)
    obj.location = loc
    if target is not None:
        point_at(obj, target)
    elif rot_deg:
        obj.rotation_euler = [math.radians(a) for a in rot_deg]
    return obj


def build_scene(spec, objs):
    sc = spec.get("scene", {})
    center, radius, zmin = scene_bounds()

    # world
    w = bpy.data.worlds.new("World")
    if bpy.app.version < (5, 0, 0):
        w.use_nodes = True
    bpy.context.scene.world = w
    wd = sc.get("world", {})
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = list(wd.get("color", [0.05, 0.05, 0.05])) + [1]
        bg.inputs[1].default_value = wd.get("strength", 1.0)

    # ground
    gd = sc.get("ground")
    if gd and gd.get("enabled"):
        bpy.ops.mesh.primitive_plane_add(size=gd.get("size_m", 20),
                                         location=(center.x, center.y, zmin + gd.get("z_offset", 0)))
        ground = bpy.context.active_object
        ground.name = "ground"
        if gd.get("material") and gd["material"] in bpy.data.materials:
            ground.data.materials.append(bpy.data.materials[gd["material"]])
        if gd.get("shadow_catcher"):
            ground.is_shadow_catcher = True

    # lights
    preset = sc.get("lighting_preset", "three_point")
    if preset == "three_point":
        d = radius * 3
        k = max((d / 3) ** 2, 0.1)
        add_light("key", "area", center + Vector((d * 0.8, -d * 0.8, d * 0.7)), 800 * k,
                  size=radius * 1.5, target=center)
        add_light("fill", "area", center + Vector((-d, -d * 0.6, d * 0.3)), 300 * k,
                  size=radius * 2, target=center)
        add_light("rim", "area", center + Vector((0, d, d * 0.8)), 500 * k,
                  size=radius, target=center)
    for L in sc.get("lights", []):
        add_light(L["id"], L["type"], L.get("location", [0, 0, 5]), L.get("energy", 100),
                  color=L.get("color", [1, 1, 1]), size=L.get("size_m", 1),
                  target=resolve_target(L["look_at"], objs) if "look_at" in L else None,
                  rot_deg=L.get("rotation_deg"), spot_deg=L.get("spot_angle_deg", 45),
                  blend=L.get("spot_blend", 0.15), shadow=L.get("shadow", True))

    # camera
    cd = sc.get("camera", {"auto_frame": True})
    cam_data = bpy.data.cameras.new("Camera")
    cam = bpy.data.objects.new("Camera", cam_data)
    link(cam)
    bpy.context.scene.camera = cam
    cam_data.lens = cd.get("focal_length_mm", 50)
    cam_data.clip_start = cd.get("clip_start", 0.01)
    cam_data.clip_end = cd.get("clip_end", 100)
    if cd.get("type") == "orthographic":
        cam_data.type = "ORTHO"
    if cd.get("auto_frame", True) and "location" not in cd:
        views = {"iso": (1, -1, 0.8), "front": (0, -1, 0.15), "back": (0, 1, 0.15),
                 "left": (-1, 0, 0.15), "right": (1, 0, 0.15), "top": (0, -0.001, 1),
                 "three_quarter": (0.7, -1, 0.4)}
        direction = Vector(views.get(cd.get("view_preset", "iso"), (1, -1, 0.8))).normalized()
        res = spec.get("render", {}).get("resolution", [1024, 768])
        aspect = res[0] / res[1]
        half = (cam_data.sensor_width / 2) / cam_data.lens
        fov = 2 * math.atan(min(half, half / aspect))
        margin = cd.get("margin", 1.3)
        dist = radius * margin / math.sin(fov / 2)
        cam.location = center + direction * dist
        point_at(cam, center)
        cam_data.ortho_scale = radius * 2 * margin
    else:
        cam.location = cd.get("location", [5, -5, 4])
        point_at(cam, resolve_target(cd.get("look_at", [0, 0, 0]), objs))


# --------------------------------------------------------------------------- render + export
def setup_render(spec):
    sc = bpy.context.scene
    r = spec.get("render", {})
    engine = r.get("engine", "EEVEE")
    names = {"EEVEE": ["BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"], "CYCLES": ["CYCLES"],
             "WORKBENCH": ["BLENDER_WORKBENCH"]}.get(engine, ["BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"])
    for n in names:
        try:
            sc.render.engine = n
            break
        except TypeError:
            continue
    samples = r.get("samples", 64)
    if engine == "CYCLES":
        sc.cycles.device = "CPU"
        sc.cycles.samples = samples
        sc.cycles.use_denoising = r.get("denoise", True)
        sc.cycles.max_bounces = r.get("max_bounces", 8)
        sc.cycles.seed = r.get("seed", 0)
    elif engine == "EEVEE":
        if hasattr(sc.eevee, "taa_render_samples"):
            sc.eevee.taa_render_samples = samples
        elif hasattr(sc.eevee, "samples"):
            sc.eevee.samples = samples
    res = r.get("resolution", [1024, 768])
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = r.get("film_transparent", False)
    try:
        sc.view_settings.view_transform = r.get("view_transform", "AgX")
    except TypeError:
        sc.view_settings.view_transform = "Standard"
    sc.view_settings.exposure = r.get("exposure", 0)
    sc.view_settings.gamma = r.get("gamma", 1)


def export_files(spec, out_dir, name):
    os.makedirs(out_dir, exist_ok=True)
    ex = spec.get("export", {})
    mods = ex.get("apply_modifiers", True)
    formats = ex.get("formats", ["blend", "glb"])

    if "blend" not in formats:
        formats.insert(0, "blend")

    for f in formats:
        path = os.path.join(out_dir, f"{name}.{f}")
        try:
            if f == "blend":
                bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
            elif f == "glb":
                bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_apply=mods)
            elif f == "fbx":
                bpy.ops.export_scene.fbx(filepath=path, use_mesh_modifiers=mods)
            elif f == "obj":
                bpy.ops.wm.obj_export(filepath=path, apply_modifiers=mods)
            elif f == "stl":
                bpy.ops.wm.stl_export(filepath=path, apply_modifiers=mods)
            else:
                log(f"export format '{f}' not supported yet")
                continue
            log("saved", path)
        except Exception as e:
            log(f"WARNING: export to {f} failed: {e}")


# --------------------------------------------------------------------------- main
def main():
    spec_path, out_dir, schema_path = parse_args()

    if not os.path.exists(spec_path):
        sys.exit(f"Error: JSON model specification file not found at: {spec_path}")

    log(f"Reading model spec from: {spec_path}")
    root = os.path.dirname(os.path.abspath(spec_path))
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)

    validate(spec, spec_path, schema_path)
    basic_checks(spec)
    os.makedirs(out_dir, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)

    textures = {t["id"]: t for t in spec.get("textures", [])}
    mats = {m["id"]: make_material(m, textures, root) for m in spec.get("materials", [])}

    objs = {o["id"]: create_object(o) for o in spec["objects"]}
    for o in spec["objects"]:
        finish_object(o, objs[o["id"]], objs, mats)
    for d in spec.get("duplicates", []):
        make_duplicates(d, objs)

    build_scene(spec, objs)
    setup_render(spec)

    export_files(spec, out_dir, spec["meta"]["id"])
    log(f"Successfully generated 3D model in: {out_dir}")


if __name__ == "__main__":
    main()
