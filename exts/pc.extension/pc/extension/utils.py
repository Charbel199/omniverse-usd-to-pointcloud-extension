import os
import time
import asyncio

import numpy as np

from PIL import Image

import omni.usd

from pxr import Usd, UsdGeom, Sdf, UsdShade, Semantics


async def recreate_stage(app):
    # close stage stage
    await omni.usd.get_context().close_stage_async()
    # update Kit
    for _ in range(2):
        await app.next_update_async()
    # create a new one
    await omni.usd.get_context().new_stage_async()
    # update Kit
    for _ in range(2):
        await app.next_update_async()
    # get stage
    return omni.usd.get_context().get_stage()


def add_ref(target_prim, source_path, source_prim_path=None):
    if source_prim_path:
        reference = Sdf.Reference(source_path, source_prim_path)
    else:
        reference = Sdf.Reference(source_path)

    references = target_prim.GetReferences()
    omni.kit.commands.execute(
        "AddReferenceCommand",
        stage=references.GetPrim().GetStage(),
        prim_path=references.GetPrim().GetPath(),
        reference=reference,
    )


def add_semantic_label(prim, label: str = "object"):
    sem = Semantics.SemanticsAPI.Apply(prim, "Semantics")
    sem.CreateSemanticTypeAttr()
    sem.CreateSemanticDataAttr()
    sem.GetSemanticTypeAttr().Set("class")
    sem.GetSemanticDataAttr().Set(label)


def _create_domelight_texture(shade: int):
    """Create Dome Light texture

    Args:
        shade (int): shading level of the dome light
    """
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    img = Image.fromarray(np.ones((10, 10, 3), dtype=np.uint8) * shade)
    tex_dir = os.path.join(cur_dir, "_textures")
    os.makedirs(tex_dir, exist_ok=True)
    tex_path = os.path.join(tex_dir, "grey.jpg")
    img.save(tex_path)


def get_stage_content() -> list:
    """Get stage content.

    Returns:
        tuple: list of tuples of root paths and types in the stage
    """
    # get current omniverse stage
    stage = omni.usd.get_context().get_stage()

    subpaths = []
    types = {}

    material_binds = {}
    for prim in stage.Traverse():

        # detect if material have bindings and if they refer to the root of the project add them to the dictionary
        if prim.HasRelationship("material:binding"):
            rel = prim.GetRelationship("material:binding")
            material_binds[str(prim.GetPath())] = [t for t in rel.GetTargets() if str(t).startswith("/")]

        name = str(prim.GetPath())
        types[name] = str(prim.GetTypeName())
        subpaths.append(f"/{name.split('/')[1]}")

    subpaths = list(set(subpaths))

    # get corresponding types
    res = [(p, types[p]) for p in subpaths]

    return res, material_binds, types


def fix_materials(stage, material_binds: dict, path: str):
    # fix materials
    for prim in stage.Traverse():
        prim_path = prim.GetPath()
        if str(prim_path) in material_binds:
            # clear relationship targets
            rel = prim.GetRelationship("material:binding")
            #             rel.ClearTargets(False)
            # update material binds
            for m in material_binds[str(prim_path)]:
                #                 # remove old target
                #                 rel.RemoveTarget(m)
                # add new target
                omni.kit.commands.execute(
                    "BindMaterialCommand",
                    prim_path=Sdf.Path(prim_path),
                    material_path=Sdf.Path(f"{path}{str(m)}"),
                    strength=UsdShade.Tokens.weakerThanDescendants,
                )


def create_prim(
    stage,
    path: str,
    prim_type: str,
    translation: tuple = None,
    rotation: tuple = None,
    scale: tuple = None,
    ref: str = None,
    paths_types_list: list = None,
    material_binds: dict = {},
    mat_paths_types_list: list = [],
    semantic_label: str = None,
    attributes: dict = {},
    ignore_types: list = ["Camera", "Skeleton", "DomeLight", "DistantLight"],
    inactive_types: list = ["Skeleton"],
    **kwargs,
):
    """Create a prim, apply specified transforms, apply semantic label and
        set specified attributes.

        args:
            stage: USD Stage
            path (str): The path of the new prim.
            prim_type (str): Prim type name
            translation (tuple(float, float, float), optional): prim translation (applied last)
            rotation (tuple(float, float, float), optional): prim rotation in radians with rotation
                order ZYX.
            scale (tuple(float, float, float), optional): scaling factor in x, y, z.
            ref (str, optional): Path to the USD that this prim will reference.
            semantic_label (str, optional): Semantic label.
            attributes (dict, optional): Key-value pairs of prim attributes to set.
        """
    # remove prim if it exists
    stage.RemovePrim(path)
    # add new prim
    prim = stage.DefinePrim(path, prim_type)

    for k, v in attributes.items():
        if k == "fov":
            h_aperture = prim.GetAttribute("horizontalAperture").Get()
            focal_length = fov_to_focal_length(math.radians(v), h_aperture)
            k, v = "focalLength", focal_length
        prim.GetAttribute(k).Set(v)
    xform_api = UsdGeom.XformCommonAPI(prim)
    if ref:
        if paths_types_list is None:
            add_ref(prim, ref)
        #             prim.GetReferences().AddReference(ref)
        else:
            # add USD items to the stage that need to be added to the root level
            for p, t in mat_paths_types_list:
                sub_prim = stage.DefinePrim(f"{p}", t)
                add_ref(sub_prim, ref, p)

            # loop for all subpath found in prim:
            # > create a new prim of the correct type
            # > add a reference to the object
            for p, t in paths_types_list:
                if t not in ignore_types:
                    sub_prim = stage.DefinePrim(f"{path}{p}", t)
                    add_ref(sub_prim, ref, p)

    for sub_prim in stage.Traverse():
        if str(sub_prim.GetPath()).find(path) < 0:
            continue
        if str(sub_prim.GetTypeName()) in inactive_types:
            sub_prim.SetActive(False)

    # update material binds
    material_binds = {f"{path}{k}": v for k, v in material_binds.items()}

    # fix materials that might be referenced outside scope
    fix_materials(stage, material_binds, path)

    if semantic_label:
        add_semantic_label(prim, semantic_label)
    if rotation:
        xform_api.SetRotate(rotation, UsdGeom.XformCommonAPI.RotationOrderZYX)
    if scale:
        xform_api.SetScale(scale)
    if translation:
        xform_api.SetTranslate(translation)
    return prim


def get_world_bounds(prim, cache=None):
    bounds = UsdGeom.Imageable(prim).ComputeLocalBound(0, "default")
    return bounds


async def stage_event_compat() -> int:
    """Calls `kit.stage_event` in a compatible way between versions"""
    # at some point in 2020.3 the APIs changed again
    usd_context = omni.usd.get_context()

    if hasattr(usd_context, "next_stage_event_async"):
        stage_event_fn = omni.usd.get_context().next_stage_event_async
    else:
        stage_event_fn = omni.kit.asyncapi.stage_event

    result = await stage_event_fn()
    # Old behaviour
    if isinstance(result, int):
        return result

    # New behaviour somewhere in 2020.3
    event, _ = result
    event = int(event)
    return event


class async_loading_wrapper:
    def __init__(
        self,
        context,
        mode="event",
        enabled: bool = True,
        status: dict = {},
        syncloads: bool = True,
        n_events: int = 2,
        sub=None,
        **kwargs,
    ):
        self.timeout = kwargs.get("timeout", float(os.getenv("RENDERING_TIMEOUT", "600")))
        self.enabled = enabled
        self.status = status
        self.context = context
        self.syncloads = syncloads
        self.n_events = n_events
        self.mode = mode

    def get_status(self):
        """Get the status of the renderer to see if anything is loading"""
        return self.context.get_stage_loading_status()

    def is_loading(self):
        """convenience function to see if any files are being loaded"""
        _, files_loaded, total_files = self.get_status()
        return files_loaded < total_files

    async def __aenter__(self):
        self.loading_start = time.time()
        return self

    async def __aexit__(self, *args, **kwargs):
        if self.enabled:
            if self.mode == "event":
                assets_loaded_count = 0
                required_assets_loaded = 1
                if not self.syncloads:
                    required_assets_loaded = int(self.n_events)

                if required_assets_loaded == 0:
                    self.status["loaded"] = True
                    self.status["load_time"] = time.time() - self.loading_start
                else:
                    self.status["loaded"] = False
                    while time.time() - self.loading_start < self.timeout:
                        event = await stage_event_compat()

                        # TODO: compare to actual enum value when Kit fixes its return types
                        if event == int(omni.usd.StageEventType.ASSETS_LOADED):
                            assets_loaded_count += 1
                            # The user can specify how many assets_loaded to wait for in async mode
                            if assets_loaded_count < required_assets_loaded:
                                continue
                            self.status["loaded"] = True
                            break
                        # error that something went wrong
                        elif event == int(omni.usd.StageEventType.OPEN_FAILED):
                            self.status["error"] = "Received OPEN_FAILED"
                            break
                        elif event == int(omni.usd.StageEventType.ASSETS_LOAD_ABORTED):
                            self.status["error"] = "Received ASSETS_LOAD_ABORTED"
                            break
                        elif event == int(omni.usd.StageEventType.CLOSING):
                            self.status["error"] = "Received CLOSING"
                            break
                        elif event == int(omni.usd.StageEventType.CLOSED):
                            self.status["error"] = "Received CLOSED"
                            break

                self.status["load_time"] = time.time() - self.loading_start
            elif self.mode == "editor":
                await asyncio.sleep(1)
                bg = time.time()
                while self.is_loading() and time.time() - bg < self.timeout:
                    await asyncio.sleep(1)

                # log that asset is loaded
                self.status["loaded"] = not self.is_loading()
            else:
                raise ValueError(f"Unknown mode: '{self.mode}'")
        else:
            self.status["loaded"] = True

        # make sure all the materials are loaded
        await asyncio.sleep(0.2)


def camera_fit_to_prim(camera, camera_rig, focus_prim, distance_multiplier: float = 1.2):
    """Move camera rig to centroid elevation and set camera distance so to fit `focus_prim`.
    """
    horiz_aperture = camera.GetAttribute("horizontalAperture").Get()
    vert_aperture = camera.GetAttribute("verticalAperture").Get()
    bounds_world = get_world_bounds(focus_prim)
    asset_range = bounds_world.GetRange()

    translation = asset_range.GetMidpoint()

    # Setting the camera rig to the center of the object.
    camera_rig.ClearXformOpOrder()
    camera_rig.AddTranslateOp().Set(translation)

    # Calculate distance to move camera from asset
    distance = np.linalg.norm(np.array(asset_range.GetSize()))
    distance *= distance_multiplier  # Scale factor of distance from object centroid to camera

    translation[0], translation[1] = 0, 0  # Only setting the z axis of the camera.
    translation[2] += distance
    UsdGeom.Xformable(camera).ClearXformOpOrder()
    UsdGeom.Xformable(camera).AddTranslateOp().Set(translation)


async def create_viewport(resolution=None, camera=None, window_width=0, window_height=0):
    x_pos, y_pos = 0, 0
    vp_iface = omni.kit.viewport.get_viewport_interface()
    viewport_instance = vp_iface.create_instance()
    viewport = vp_iface.get_viewport_window(viewport_instance)
    viewport_name = vp_iface.get_viewport_window_name(viewport_instance)
    viewport.set_window_size(window_width, window_height)
    viewport.set_window_pos(x_pos, y_pos)
    x_pos = x_pos + 50
    y_pos = y_pos + 50

    if resolution:
        viewport.set_texture_resolution(*resolution)

    if camera:
        viewport.set_active_camera(str(camera.GetPath()))

    # Wait for some frames to draw before creating the next window
    for _ in range(10):
        await omni.kit.app.get_app_interface().next_update_async()

    return viewport_name
