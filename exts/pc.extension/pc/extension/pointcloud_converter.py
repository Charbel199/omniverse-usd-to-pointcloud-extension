# This file convert USD mesh to USDGeomPoints
import os
import math

import asyncio
import omni.usd
from omni import ui
import omni.ext
import omni.kit
import carb
import omni.syntheticdata as syn
from .syntheticdata_utils import SyntheticDataHelper, SENSORS
from .utils import async_loading_wrapper, _create_domelight_texture, recreate_stage
from .utils import get_stage_content, create_prim, get_world_bounds, camera_fit_to_prim
from .utils import create_viewport

from pxr import Usd, UsdLux, UsdGeom, Vt, Semantics
import numpy as np

from PIL import Image
from omni.kit.widget.viewport import ViewportWidget
# AZIMUTHS and ELEVATIONS for rendering GT images
AZIMUTHS = [45, 135, 225, 315]
ELEVATIONS = [-60, 0, 60]


class PointCloudGenerator:
    def __init__(self):
        self.sd_helper = SyntheticDataHelper()
        self.app = omni.kit.app.get_app()
        self.viewpoints = {"azimuth": AZIMUTHS, "elevation": ELEVATIONS}
        self.asset_status = {}

        self.settings_interface = carb.settings.get_settings()

        # Camera parameters
        self.base_fov_multiplier = 0.5
        self.base_camera_distance_multiplier = 1.0
        self.camera_fov_multiplier = 4

        # variable to store pointcloud
        self.pointcloud = None

        # variable to hold the reference of the Usd Mesh
        self.ref = None

        self.stage = None

        # Setting the upaxis of stage. Default: Z
        self.stage_up_axis = "Z"

        # resolution to render the mesh, default 448
        self.height_resolution = 448
        self.width_resolution = 448

        self._settings_cache = {}

        self._render_viewport = None

    def clean(self):
        """ Clean all the variable to get ready for next point cloud generation.
        """
        self.pointcloud = None

        self.stage = None

        self.ref = None

    async def set_camera(self, fov_multiplier: float = 0.5):
        self.camera_rig1 = UsdGeom.Xformable(self.stage.DefinePrim("/World/CameraRig1", "Xform"))
        self.camera_rig2 = UsdGeom.Xformable(self.stage.DefinePrim("/World/CameraRig1/CameraRig2", "Xform"))

        self.camera = self.stage.DefinePrim("/World/CameraRig1/CameraRig2/Camera", "Camera")

        # Set camera parameters
        horizontal_aperture = self.camera.GetAttribute("horizontalAperture").Get()
        vertical_aperture = horizontal_aperture * self.width_resolution / self.height_resolution
        fov = math.radians(60 / 2.0)
        focal_length = horizontal_aperture / math.tan(fov) * fov_multiplier

        self.camera.GetAttribute("verticalAperture").Set(vertical_aperture)
        self.camera.GetAttribute("focalLength").Set(focal_length)
        self.camera.GetAttribute("clippingRange").Set((0.1, 10000))

        # Check if viewport is already assigned to camera. If not, create one.
        # vp_iface = omni.kit.viewport_legacy.get_viewport_interface()
        # viewport_instances = vp_iface.get_instance_list()
        # for vpi in viewport_instances:
        #     viewport = vp_iface.get_viewport_window(vpi)
        #     viewport_name = vp_iface.get_viewport_window_name(vpi)
        #     camera = viewport.get_active_camera()

        #     # If viewport is using the default perspective camera, re-use it for pointcloud gen
        #     if camera == "/OmniverseKit_Persp":
        #         viewport.set_active_camera(str(self.camera.GetPath()))
        #         camera = viewport.get_active_camera()

        #     if camera == str(self.camera.GetPath()):
        #         self._render_viewport = viewport

        #         # Ensure viewport is visible
        #         if not self._render_viewport.is_visible():
        #             self._render_viewport.set_visible(True)

        #         # Set resolution in case it changed
        #         self._render_viewport.set_texture_resolution(self.width_resolution, self.height_resolution)
        #         break

        # Create new viewport and set resolution and active camera
        if self._render_viewport is None:
            self.vp_name = "HELLO"
            self.vp_usd_context = ""
            self.__vp_widget = ViewportWidget(usd_context_name=self.vp_usd_context,name=self.vp_name,camera_path="/World/CameraRig1/CameraRig2/Camera",resolution=(self.width_resolution, self.height_resolution))
            vp_iface = self.__vp_widget.get_instances()
            viewport_name = self.vp_usd_context
 
            # viewport_name = await create_viewport(
            #     window_width=400,
            #     window_height=300, 
            #     resolution=(self.width_resolution, self.height_resolution),
            #     camera=self.camera,
            # )
            # self._render_viewport = vp_iface.get_viewport_window(vp_iface.get_instance(viewport_name))
            self._render_viewport = self.__vp_widget

        # main_viewport_window = ui.Workspace.get_window(self.vp_name)
        # render_viewport_window = ui.Workspace.get_window(viewport_name)
        # print(f"Main viewport window is {main_viewport_window}")
        # print(f"Render viewport window is {render_viewport_window}")
        # render_viewport_window.dock_in(main_viewport_window, ui.DockPosition.RIGHT, 0.33)

        await self.app.next_update_async()

    def cache_current_settings(self):
        settings_to_cache = [
            "/rtx/rendermode",
            "/rtx/hydra/subdivision/refinementLevel",
            "/persistent/app/viewport/displayOptions",
            "/app/viewport/grid/enabled",
            "/app/hydra/supportOldMdlSchema",
            "/rtx/materialDb/syncLoads",
            "/omni.kit.plugin/syncUsdLoads",
        ]
        for setting in settings_to_cache:
            self._settings_cache[setting] = self.settings_interface.get(setting)

    def restore_settings(self):
        for setting, val in self._settings_cache.items():
            self.settings_interface.set(setting, val)

    def set_default_settings(self):
        # rendering settings
        self.settings_interface.set_string("/rtx/rendermode", "PathTracing")
        self.settings_interface.set_int("/rtx/hydra/subdivision/refinementLevel", 2)

        # switch off some viewport options
        self.settings_interface.set_int("/persistent/app/viewport/displayOptions", 0)
        self.settings_interface.set_bool("/app/viewport/grid/enabled", False)

        # support for old matrial schema
        self.settings_interface.set_bool(
            "/app/hydra/supportOldMdlSchema", os.getenv("OMNI_RENDER_OLD_MDL_SUPPORT", "False").lower() in ("true", "1")
        )

        self.settings_interface.set_bool("/rtx/materialDb/syncLoads", True)
        self.settings_interface.set_bool("/omni.kit.plugin/syncUsdLoads", True)

    def start(self):
        asyncio.ensure_future(self.async_start())

    async def async_start(self):
        """
        Extract the pointcloud from mesh and load then into the scene.
        """
        await self.get_asset_pointcloud()
        await self.load_pointcloud()

    async def generate_pointcloud(self):
        # cache current settings so they can be re-applied later
        self.cache_current_settings()

        asset = self.ref

        # set the camera
        await self.set_camera(fov_multiplier=self.camera_fov_multiplier * self.base_fov_multiplier)

        camera_distance_multiplier = self.camera_fov_multiplier * self.base_camera_distance_multiplier

        async def render(el, az):
            # Clear previous transforms
            self.camera_rig2.ClearXformOpOrder()
            # update camera view
            camera_fit_to_prim(self.camera, self.camera_rig1, asset, distance_multiplier=camera_distance_multiplier)
            # Change azimuth angle
            if UsdGeom.GetStageUpAxis(self.stage) == "Z":
                self.camera_rig2.AddRotateZOp().Set(az)
            else:
                self.camera_rig2.AddRotateYOp().Set(az)
            # Change elevation angle
            self.camera_rig2.AddRotateXOp().Set(el)

            self.set_default_settings()
            # help(self.__vp_widget.viewport_api.set_render_product_path)
            # self.__vp_widget.viewport_api.set_render_product_path="test"
            print(f"Render product path is {self.__vp_widget.viewport_api.render_product_path}")
            # return await self.sd_helper.get_groundtruth(self._render_viewport, list(SENSORS.keys()))

            return await self.sd_helper.get_groundtruth(self.__vp_widget.viewport_api, list(SENSORS.keys()))

        output_dict = {f: [] for f in list(SENSORS.values())}
        pointcloud_list = []
        # Fit camera to the asset
        for el in self.viewpoints["elevation"]:
            for az in self.viewpoints["azimuth"]:
                print(f"el is {el} and az is {az}")
                for _ in range(2):
                    gt = await render(el, az)

                for k in output_dict:
                    if k in SENSORS.values():
                        output_dict[k].append(gt[k])

                pointcloud_list.append(
                    self.get_pointcloud(self.camera, gt["linear_depth"], gt["normal"], gt["images"], gt["segmentation"])
                )
        self.restore_settings()
        # self._render_viewport.set_visible(False)  # Hide render viewport
        self.__vp_widget.visible = False  # Hide render viewport
        return np.concatenate(pointcloud_list, axis=0)

    async def initialize_stage(self, file_path: str):
        # create a new one
        await omni.usd.get_context().new_stage_async()

        self.stage = omni.usd.get_context().get_stage()

        # Create dome light and ground for rendering.
        for _ in range(10):
            await self.app.next_update_async()
        await asyncio.sleep(1)
        for _ in range(10):
            await self.app.next_update_async()

        self.stage_up_axis = UsdGeom.GetStageUpAxis(self.stage)

        # create texture for DomeLight
        _create_domelight_texture(255)

        domelight = UsdLux.DomeLight.Define(self.stage, "/World/DomeLight")
        assert domelight
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        domelight.GetTextureFileAttr().Set(os.path.join(cur_dir, "_textures", "grey.jpg"))
        domelight.GetTextureFormatAttr().Set("latlong")
        domelight.GetIntensityAttr().Set(1500)

        # Creage a cube for ground
        # ground = UsdGeom.Cube.Define(self.stage, "/World/Ground")
        # assert ground
        # UsdGeom.Xformable(ground).AddTranslateOp().Set((0., 0., -0.5))
        # UsdGeom.Xformable(ground).AddScaleOp().Set((100000., 100000., 1.))
        # ground.GetSizeAttr().Set(1)

        self.ref = self.stage.DefinePrim("/World/Object")

        sem = Semantics.SemanticsAPI.Apply(self.ref, "Semantics")
        sem.CreateSemanticTypeAttr()
        sem.CreateSemanticDataAttr()
        sem.GetSemanticTypeAttr().Set("class")
        sem.GetSemanticDataAttr().Set("Target")

        # Load usd mesh to the scene
        usd_context = omni.usd.get_context()

        async with async_loading_wrapper(usd_context, status=self.asset_status, mode="event"):
            self.ref.GetReferences().AddReference(file_path)

    async def get_asset_pointcloud(self, **kwargs) -> dict:
        """Get the pointcloud of the current loaded
          asset. Must be called after `self.initialize_stage`.

        Returns:
            dict: dictionary with scene renderings
        """
        for _ in range(2):
            await self.app.next_update_async()

        self.pointcloud = await self.generate_pointcloud()
        print("Self . pointcloud is ",self.pointcloud)

    async def load_pointcloud(self):
        """
        Load Pointcloud as UsdGeomPoints into the scene.

        Args:
            pointcloud (np.array): Point cloud that contains positions, normals and rgb color.
            scale (int): scale to scale up the points for better visualization.
        """
        # Recreate stage
        for _ in range(10):
            await self.app.next_update_async()
        await asyncio.sleep(1)
        self.stage = await recreate_stage(self.app)
        for _ in range(10):
            await self.app.next_update_async()

        UsdGeom.SetStageUpAxis(self.stage, self.stage_up_axis)
        self._load_pointcloud(self.stage, self.pointcloud, "/World/Pointcloud")

    def _load_pointcloud(self, stage, pointcloud, scene_path):
        points = pointcloud[..., :3]

        normals = pointcloud[..., 3:6]
        rgb = pointcloud[..., 6:]

        points_prim = stage.DefinePrim(scene_path, "Points")
        geom_points = UsdGeom.Points(points_prim)

        # Calculate default point scale
        bounds = points.max(axis=0) - points.min(axis=0)
        min_bound = np.min(bounds)
        point_size = (min_bound / points.shape[0] ** (1 / 3)).item()

        # Generate instancer parameters
        positions = points.tolist()
        point_size = [point_size] * points.shape[0]

        # Populate UsdGeomPoints
        geom_points.GetPointsAttr().Set(points)
        geom_points.GetWidthsAttr().Set(Vt.FloatArray(point_size))

        # Set color
        geom_points.GetDisplayColorAttr().Set(rgb / 255)

        # Set normals
        geom_points.GetNormalsAttr().Set(normals)

    def get_pointcloud(
        self,
        camera,
        depth: np.ndarray,
        normals: np.ndarray,
        rgba: np.ndarray,
        binary_mask: np.ndarray,
        depth_scale: float = 100.0,
    ) -> np.ndarray:

        # Preprocess depth, normals and rgba to binary mask
        binary_mask = binary_mask.astype(bool)
        depth[binary_mask == 0] = 0
        normals[binary_mask == 0] = 0
        rgba[binary_mask == 0] = 0

        metadata = self.get_camera_metadata(camera)

        height, width = depth.shape[:2]
        mask = (depth != 0).reshape(-1)
        fov_h = 2 * np.arctan(metadata["horizontal_aperture"] / metadata["focal_length"] / 2)
        alpha_h = (np.pi - fov_h) / 2
        ii, jj = np.meshgrid(np.arange(width)[::-1], np.arange(height), indexing="xy")
        gamma_h = alpha_h + ii * fov_h / width
        x = depth.reshape(-1, 1)[mask] / np.tan(gamma_h.reshape(-1, 1)[mask])
        fov_w = 2 * np.arctan(metadata["vertical_aperture"] / metadata["focal_length"] / 2)
        alpha_w = 2 * np.pi - fov_w / 2
        gamma_w = alpha_w + jj * fov_w / height
        y = -depth.reshape(-1, 1)[mask] * np.tan(gamma_w.reshape(-1, 1)[mask])
        z = -depth.reshape(-1, 1)[mask]

        points_cam = np.concatenate([x, y, z], axis=1) * depth_scale
        points_world = np.pad(points_cam, ((0, 0), (0, 1)), constant_values=1) @ metadata["local_to_world_tf"]
        normals = normals.reshape(-1, 3)[mask]
        rgb = rgba.reshape(-1, 4)[mask][:, :3]
        pointcloud = np.concatenate([points_world[..., :3], normals, rgb], axis=1)

        return pointcloud

    def get_camera_metadata(self, camera) -> dict:
        # get some additional camera attributes
        camera_attributes = camera.GetPropertyNames()
        # get camera metadata
        metadata = {
            "clipping_range": np.array(camera.GetAttribute("clippingRange").Get()),
            "focal_length": camera.GetAttribute("focalLength").Get(),
            "horizontal_aperture": camera.GetAttribute("horizontalAperture").Get(),
            "vertical_aperture": camera.GetAttribute("verticalAperture").Get(),
            "local_to_world_tf": np.array(UsdGeom.Imageable(camera).ComputeLocalToWorldTransform(0.0)),
            "prim_path": str(camera.GetPath()),
        }
        # > camera tags NOTE: this is for drivesim (might not be generic)
        if "searchTags" in camera_attributes:
            metadata["searchTags"] = [t.strip() for t in str(camera.GetAttribute("searchTags").Get()).split(",")]

        return metadata
