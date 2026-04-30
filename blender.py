import bpy
import math
import os
import json

# ============================================================================
# Configuration
# ============================================================================

BACKGROUND_IMAGE = "/Users/michael/Documents/Codeology/clash_royacado/cr-assets-png/assets/sc/level_ice_arena_tex_.png"
SCALE_FACTOR     = 3    # how big the scene is
FRAME_END        = 60   # animation length in frames

with open("game_tracks.json", 'r') as f:
    data = json.load(f)
tracks = data["tracks"]

# Open the file and load its contents
with open('labels_yaml.json', 'r') as file:
    yaml_data = json.load(file)
labels = yaml_data

ignore_terms = ["-tower","-bar", "-symbol"]
ignore_classes = ["elixir", "bar", "clock","bar-level","emote"]

def perception_to_ground(perception_coord):
    x,y = perception_coord
    perception_floorW = 576
    perception_floorH = 896

    blender_floorW_half = 40 //2
    blender_floorH_half = 20 //2
    
    mid_w = perception_floorW/2
    x1 = x - mid_w
    x2 = x1 / mid_w * 10

    mid_h = perception_floorH//2
    y1 = y - mid_h
    y2 = y1 / mid_h * 20
    y2*=-1

    return x2,y2

# ============================================================================
# Step 1 — Remove the Default Cube
# ============================================================================

def remove_default_cube():
    # Check if the cube exists before trying to remove it
    if 'Cube' in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects['Cube'], do_unlink=True)


# ============================================================================
# Step 2 — Create a Textured Floor
# ============================================================================

def create_floor_plane(image_path, scale):
    # Create a flat plane at the origin
    bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, 0))
    plane = bpy.context.object   # the new plane is automatically set as active

    # Create a new material and enable node-based editing
    mat = bpy.data.materials.new(name="FloorMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Get the Principled BSDF node (auto-created when use_nodes=True)
    bsdf = nodes["Principled BSDF"]

    # Add an image texture node and load the background image
    tex       = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(image_path)

    # Fix the aspect ratio so the image isn't stretched
    aspect = tex.image.size[0] / tex.image.size[1]
    plane.scale.x *= scale
    plane.scale.y *= scale / aspect

    # Wire the texture into the material: Texture Color → BSDF Base Color
    links.new(bsdf.inputs["Base Color"], tex.outputs["Color"])

    # Attach the material to the plane
    plane.data.materials.append(mat)

    return plane


# ============================================================================
# Step 3 — Import Helpers
# ============================================================================

def import_gltf(filepath):
    if not os.path.isabs(filepath):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(script_dir, filepath)
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"GLB not found: {filepath}")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=filepath)
    return list(set(bpy.data.objects) - before)


def apply_rotation(obj):
    # You MUST set the active object before calling transform_apply
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(rotation=True)


def import_prop(filepath, name, location, rotation, scale):
    import_gltf(filepath)
    obj = bpy.data.objects[name]   # look up by name Blender assigned

    obj.rotation_mode  = 'XYZ'
    obj.rotation_euler = rotation
    apply_rotation(obj)

    obj.location = location
    obj.scale    = scale
    return obj


# ============================================================================
# Step 4 — Sky
# ============================================================================

def setup_sky():
    world = bpy.context.scene.world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()   # remove default nodes before building our own

    # Create the three nodes we need
    sky = nodes.new("ShaderNodeTexSky")
    bg  = nodes.new("ShaderNodeBackground")
    out = nodes.new("ShaderNodeOutputWorld")

    # Use NISHITA if available, fall back to HOSEK_WILKIE on older Blender
    available    = sky.bl_rna.properties["sky_type"].enum_items.keys()
    sky.sky_type = 'NISHITA' if 'NISHITA' in available else 'HOSEK_WILKIE'
    if sky.sky_type == 'NISHITA':
        sky.air_density = 1.0
    sky.sun_elevation = 0.6   # radians (~0.6 = afternoon sun)
    sky.sun_rotation  = 1.0

    # Wire: Sky Color → Background → World Output Surface
    links.new(sky.outputs["Color"],      bg.inputs["Color"])
    links.new(bg.outputs["Background"], out.inputs["Surface"])

    bg.inputs["Strength"].default_value = 3.0

    # Make the sky visible while working in the viewport
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.use_scene_world = True


# ============================================================================
# Step 5 — Walking Animation (Flipbook System)
# ============================================================================

def create_walking_animation(
    models_folder,
    start_pos,
    end_pos,
    start_frame,
    total_frames,
    frames_per_model=2,
    scale=3,
    orientation=math.pi,
):
    # Resolve to absolute path
    if not os.path.isabs(models_folder):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        models_folder = os.path.join(script_dir, models_folder)

    # Get all GLB files in the folder, sorted so order is consistent
    model_files = sorted(f for f in os.listdir(models_folder) if f.endswith(".glb"))
    if not model_files:
        print(f"No .glb files found in '{models_folder}'")
        return []

    # Calculate how far to move each frame
    dx = (end_pos[0] - start_pos[0]) / total_frames
    dy = (end_pos[1] - start_pos[1]) / total_frames
    dz = (end_pos[2] - start_pos[2]) / total_frames

    # --- Import all pose models ---
    imported = []
    for i, filename in enumerate(model_files):
        new_objects  = import_gltf(os.path.join(models_folder, filename))
        mesh_objects = [o for o in new_objects if o.type == 'MESH']

        # Remove any non-mesh objects the GLB brought in (cameras, lights)
        for o in new_objects:
            if o.type != 'MESH':
                bpy.data.objects.remove(o, do_unlink=True)

        if not mesh_objects:
            continue

        # If the GLB imported multiple meshes, join them into one
        if len(mesh_objects) > 1:
            bpy.ops.object.select_all(action='DESELECT')
            for o in mesh_objects:
                o.select_set(True)
            bpy.context.view_layer.objects.active = mesh_objects[0]
            bpy.ops.object.join()   # merge all selected into the active object
            obj = bpy.context.active_object
        else:
            obj = mesh_objects[0]

        # Name it uniquely so multiple walkers don't conflict
        obj.name           = f'Walker_{start_frame}_{i:03d}'
        obj.rotation_mode  = 'XYZ'
        obj.rotation_euler = (0, 0, orientation)
        obj.scale          = (scale, scale, scale)
        apply_rotation(obj)

        obj.location      = start_pos
        obj.hide_viewport = True   # start hidden
        obj.hide_render   = True
        imported.append(obj)

    # --- Keyframe loop ---
    n = len(imported)
    for frame in range(start_frame, start_frame + total_frames):
        offset     = frame - start_frame

        # Which model should be visible? Cycle through using modulo
        active_idx = (offset // frames_per_model) % n

        # Where should the character be at this frame?
        position = (
            start_pos[0] + offset * dx,
            start_pos[1] + offset * dy,
            start_pos[2] + offset * dz,
        )

        bpy.context.scene.frame_set(frame)

        for i, obj in enumerate(imported):
            visible           = (i == active_idx)
            obj.hide_viewport = not visible
            obj.hide_render   = not visible
            obj.keyframe_insert(data_path="hide_viewport")
            obj.keyframe_insert(data_path="hide_render")
            if visible:
                obj.location = position
                obj.keyframe_insert(data_path="location")
                obj.rotation_euler = (0, 0, orientation)
                obj.keyframe_insert(data_path="rotation_euler")

    # Extend timeline if needed
    if start_frame + total_frames - 1 > bpy.context.scene.frame_end:
        bpy.context.scene.frame_end = start_frame + total_frames - 1

    bpy.context.scene.frame_set(1)
    return imported

# Integrated Walking Animation Method

def create_walking_animation_integrated(
    models_folder,
    start_pos,
    end_pos,
    start_frame,
    total_frames,
    pos_list,
    frames_per_model=2,
    scale=3,
    orientation=math.pi,
):
    # Resolve to absolute path
    if not os.path.isabs(models_folder):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        models_folder = os.path.join(script_dir, models_folder)

    # Get all GLB files in the folder, sorted so order is consistent
    model_files = sorted(f for f in os.listdir(models_folder) if f.endswith(".glb"))
    if not model_files:
        print(f"No .glb files found in '{models_folder}'")
        return []

    # # Calculate how far to move each frame
    # dx = (end_pos[0] - start_pos[0]) / total_frames
    # dy = (end_pos[1] - start_pos[1]) / total_frames
    # dz = (end_pos[2] - start_pos[2]) / total_frames

    # --- Import all pose models ---
    imported = []
    for i, filename in enumerate(model_files):
        new_objects  = import_gltf(os.path.join(models_folder, filename))
        mesh_objects = [o for o in new_objects if o.type == 'MESH']

        # Remove any non-mesh objects the GLB brought in (cameras, lights)
        for o in new_objects:
            if o.type != 'MESH':
                bpy.data.objects.remove(o, do_unlink=True)

        if not mesh_objects:
            continue

        # If the GLB imported multiple meshes, join them into one
        if len(mesh_objects) > 1:
            bpy.ops.object.select_all(action='DESELECT')
            for o in mesh_objects:
                o.select_set(True)
            bpy.context.view_layer.objects.active = mesh_objects[0]
            bpy.ops.object.join()   # merge all selected into the active object
            obj = bpy.context.active_object
        else:
            obj = mesh_objects[0]

        # Name it uniquely so multiple walkers don't conflict
        obj.name           = f'Walker_{start_frame}_{i:03d}'
        obj.rotation_mode  = 'XYZ'
        obj.rotation_euler = (0, 0, 0)
        obj.scale          = (scale, scale, scale)
        apply_rotation(obj)

        obj.location      = start_pos
        obj.hide_viewport = True   # start hidden
        obj.hide_render   = True
        imported.append(obj)

    # --- Keyframe loop ---
    n = len(imported)
    bpy.context.scene.frame_set(1)
    for object in imported:
        obj.hide_viewport = True
        obj.hide_render = True
        obj.keyframe_insert(data_path='hide_viewport')
        obj.keyframe_insert(data_path='hide_render')

    for frame in range(start_frame, start_frame + total_frames):
        offset = frame - start_frame
        if offset >= len(pos_list):
            break

        # Which model should be visible? Cycle through using modulo
        active_idx = (offset // frames_per_model) % n

        ground_x, ground_y = perception_to_ground(pos_list[offset])
        position = (ground_x, ground_y, start_pos[2])
        # Where should the character be at this frame?
        # position = (
        #     start_pos[0] + offset * dx,
        #     start_pos[1] + offset * dy,
        #     start_pos[2] + offset * dz,
        # )

        if offset + 4 < len(pos_list):
            next_x, next_y = perception_to_ground(pos_list[offset + 4])
            dx = next_x - ground_x
            dy = next_y - ground_y
        elif offset > 0:
            # Last frame: reuse previous delta
            prev_x, prev_y = perception_to_ground(pos_list[offset - 1])
            dx = ground_x - prev_x
            dy = ground_y - prev_y
        else:
            dx, dy = 0, 1  # fallback if only one position
        still = False
        if abs(dx) > 0.001 or abs(dy) > 0.001:  # avoid jitter when stationary
            if orientation is None:
                orientation = math.atan2(dy, dx) - math.pi / 2
            else:
                ori_new = math.atan2(dy, dx) - math.pi / 2
                orientation = 0.7 * orientation + 0.3 * ori_new 
        else:
            #if orientation is None:
            still = True
            orientation = math.pi  # fallback to default

        bpy.context.scene.frame_set(frame)

        for i, obj in enumerate(imported):
            visible           = (i == active_idx)
            obj.hide_viewport = not visible
            obj.hide_render   = not visible
            obj.keyframe_insert(data_path="hide_viewport")
            obj.keyframe_insert(data_path="hide_render")
            if visible:
                obj.location = position
                obj.keyframe_insert(data_path="location")
                obj.rotation_euler = (0, 0, orientation + math.pi)
                obj.keyframe_insert(data_path="rotation_euler")
    
    end_frame = start_frame + len(pos_list)
    bpy.context.scene.frame_set(end_frame)
    for obj in imported:
        obj.hide_viewport = True
        obj.hide_render   = True
        obj.keyframe_insert(data_path="hide_viewport")
        obj.keyframe_insert(data_path="hide_render")

    if end_frame > bpy.context.scene.frame_end:
        bpy.context.scene.frame_end = end_frame

    bpy.context.scene.frame_set(1)
    print(f"Animation complete: {n} models over {len(pos_list)} frames")
    return imported

# ============================================================================
# Main — Run Everything
# ============================================================================

remove_default_cube()
create_floor_plane(BACKGROUND_IMAGE, SCALE_FACTOR)

# --- Arena props ---
s = SCALE_FACTOR
glb_num = [0]

def next_geo():
    n = glb_num[0]
    name = "geometry_0" if n == 0 else (
           f"geometry_0.00{n}" if n < 10 else f"geometry_0.0{n}")
    glb_num[0] += 1
    return name

# Bridges
import_prop("arena/ice_arena/ice_bridge.glb", next_geo(),
    location=(-8, +2, 0.1), rotation=(0, 0, math.pi),
    scale=(s*1.2, s*1.2, s*1.2))
import_prop("arena/ice_arena/ice_bridge.glb", next_geo(),
    location=(8, +2, 0.1), rotation=(0, 0, math.pi),
    scale=(s*1.2, s*1.2, s*1.2))

pt, ph = 1.8, 1
import_prop("arena/ice_arena/king_tower_blue.glb", next_geo(),
    location=(0,  17.5, ph), rotation=(0, 0, 0),       scale=(s*pt, s*pt, s*pt))
import_prop("arena/ice_arena/king_tower_blue.glb", next_geo(),
    location=(0,  -13, ph), rotation=(0, 0, 0),       scale=(s*pt, s*pt, s*pt))

import_prop("arena/ice_arena/king_blue.glb", next_geo(),
    location=(0,  17.5, 3), rotation=(0, 0, 0),       scale=(s*pt*0.5, s*pt*0.5, s*pt*0.5))
import_prop("arena/ice_arena/king_red.glb", next_geo(),
    location=(0, -13, 3), rotation=(0, 0, math.pi), scale=(s*pt*0.5, s*pt*0.5, s*pt*0.5))

pt_small_blue = pt * 0.6
pt_small_red = pt * 1.2

for loc, rot, color, pt_s in [
    ((8,  13, 1), (0, 0, 0),       "blue", pt_small_blue),
    ((-8, 13, 1), (0, 0, 0),       "blue", pt_small_blue),
    ((8, -9.5, 1), (0, 0, math.pi), "red",  pt_small_red),
    ((-8,-9.5, 1), (0, 0, math.pi), "red",  pt_small_red),
]:
    import_prop(f"arena/ice_arena/king_tower_{color}.glb", next_geo(),
        location=loc, rotation=rot, scale=(s*pt_s, s*pt_s, s*pt_s))

# Princesses on top of each princess tower
for loc, rot in [
    ((8,  13, 2.6),   (0, 0, 0)),
    ((-8, 13, 2.6),   (0, 0, 0)),
    ((8,  -9.5, 2.6), (0, 0, math.pi)),
    ((-8, -9.5, 2.6), (0, 0, math.pi)),
]:
    import_prop("arena/ice_arena/princess.glb", next_geo(),
        location=loc, rotation=rot, scale=(s*pt*0.4, s*pt*0.4, s*pt*0.4))

# # Bleachers
# bs = 5
# for loc, rot in [
#     (( 18,  12, 2), (0, 0, -math.pi/2)),
#     ((-18,  12, 2), (0, 0,  math.pi/2)),
#     (( 18, -12, 2), (0, 0, -math.pi/2)),
#     ((-18, -12, 2), (0, 0,  math.pi/2)),
# ]:
#     import_prop("arena/royal_arena/bleacher.glb", next_geo(), loc, rot, (s*bs, s*bs, s*bs))

setup_sky()
bpy.context.scene.frame_end = FRAME_END

# --- Walking animations ---
for track in tracks:
    class_id = track['class_id']
    class_name = labels[str(class_id)]
    skip = False
    if class_name in ignore_classes:
        continue
    for term in ignore_terms:
        if term in class_name:
            skip = True
    if skip:
        continue

    scale = 3.5
    # adjust scale, adjust file path
    # if class_name == 'skeleton':
    #     scale = 1
    # model_path = f"{class_name} run/models"
    model_path = 'wizard_3d_model' #placeholder since we only have wizards

    position_list = track['positions']
    create_walking_animation_integrated(
        models_folder=model_path,
        start_pos=(-8, -5, 1.7),
        end_pos  =(-8, 5, 1.7),
        start_frame=1, total_frames=150,
        pos_list = position_list,
        scale=2.5, orientation=math.pi,
    )

# create_walking_animation(
#     models_folder="wizard_3d_model",
#     start_pos=(-8, -5, 1.7),
#     end_pos  =(-8, 5, 1.7),
#     start_frame=1, total_frames=150,
#     scale=3.5, orientation=math.pi,
# )

# create_walking_animation(
#     models_folder="wizard_3d_model",
#     start_pos=(8, 5, 1.7),
#     end_pos  =(8, -5, 1.7),
#     start_frame=1, total_frames=150,
#     scale=3.5, orientation=2*math.pi,
# )

# create_walking_animation(
#     models_folder="wizard_3d_model",
#     start_pos=(9, 12, 1.7),
#     end_pos  =(0, 18, 1.7),
#     start_frame=30, total_frames=200,
#     scale=3.5, orientation=5*math.pi/4,
# )

print("Scene setup complete!")
print(f"Objects: {[o.name for o in bpy.data.objects]}")