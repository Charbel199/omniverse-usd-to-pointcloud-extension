import omni.ui as ui
import asyncio
import omni
from typing import Union, List
from omni.kit.widget.viewport import ViewportWidget
import omni.ui_scene.scene as sc
from omni.kit.manipulator.camera import ViewportCameraManipulator
class StagePreviewWidget:
    def __init__(self, usd_context_name: str = '', camera_path: str = None, resolution: Union[tuple, str] = None, *ui_args ,**ui_kw_args):
        """StagePreviewWidget contructor
        Args:
            usd_context_name (strViewportCameraManipulator): The name of a UsdContext the Viewport will be viewing.
            camera_path (str): The path of the initial camera to render to.
            resolution (x, y): The resolution of the backing texture, or 'fill_frame' to match the widget's ui-size
            *ui_args, **ui_kw_args: Additional arguments to pass to the ViewportWidget's parent frame
        """
        # Put the Viewport in a ZStack so that a background rectangle can be added underneath
        self.__ui_container = ui.ZStack()
        with self.__ui_container:
            # Add a background Rectangle that is black by default, but can change with a set_style 
            ui.Rectangle(style_type_name_override='ViewportBackgroundColor', style={'ViewportBackgroundColor': {'background_color': 0xff000000}})

            # Create the ViewportWidget, forwarding all of the arguments to this constructor
            self.__vp_widget = ViewportWidget(usd_context_name=usd_context_name, camera_path=camera_path, resolution=resolution, *ui_args, **ui_kw_args)
            print(f"view port widget : {dir(self.__vp_widget)}")
            print(f"view port api : {dir(self.viewport_api)}")
            print(f"Render product path in test is {self.__vp_widget.viewport_api.render_product_path}")
            # Add the omni.ui.scene.SceneView that is going to host the camera-manipulator
            self.__scene_view = sc.SceneView(aspect_ratio_policy=sc.AspectRatioPolicy.STRETCH)

            # And finally add the camera-manipulator into that view
            with self.__scene_view.scene:
                self.__camera_manip = ViewportCameraManipulator(self.viewport_api)
                model = self.__camera_manip.model

                # Let's disable any undo for these movements as we're a preview-window
                model.set_ints('disable_undo', [1])

                # We'll also let the Viewport automatically push view and projection changes into our scene-view
                self.viewport_api.add_scene_view(self.__scene_view)

    def __del__(self):
        self.destroy()

    def destroy(self):
        self.__view_change_sub = None
        if self.__camera_manip:
            self.__camera_manip.destroy()
            self.__camera_manip = None
        if self.__scene_view:
            self.__scene_view.destroy()
            self.__scene_view = None
        if self.__vp_widget:
            self.__vp_widget.destroy()
            self.__vp_widget = None
        if self.__ui_container:
            self.__ui_container.destroy()
            self.__ui_container = None

    @property
    def viewport_api(self):
        # Access to the underying ViewportAPI object to control renderer, resolution
        return self.__vp_widget.viewport_api

    @property
    def scene_view(self):
        # Access to the omni.ui.scene.SceneView
        return self.__scene_view

    def set_style(self, *args, **kwargs):
        # Give some styling access
        self.__ui_container.set_style(*args, **kwargs)
class StagePreviewWindow(ui.Window):
    def __init__(self, title: str, usd_context_name: str = '', window_width: int = 1280, window_height: int = 720 + 20, flags: int = ui.WINDOW_FLAGS_NO_SCROLLBAR, *vp_args, **vp_kw_args):
        """StagePreviewWindow contructor
        Args:
            title (str): The name of the Window.
            usd_context_name (str): The name of a UsdContext this Viewport will be viewing.
            window_width(int): The width of the Window.
            window_height(int): The height of the Window.
            flags(int): ui.WINDOW flags to use for the Window.
            *vp_args, **vp_kw_args: Additional arguments to pass to the StagePreviewWidget
        """
        # We may be given an already valid context, or we'll be creating and managing it ourselves
        usd_context = omni.usd.get_context(usd_context_name)
        if not usd_context:
            self.__usd_context_name = usd_context_name
            self.__usd_context = omni.usd.create_context(usd_context_name)
        else:
            self.__usd_context_name = None
            self.__usd_context = None

        super().__init__(title, width=window_width, height=window_height, flags=flags)
        with self.frame:
            self.__preview_viewport = StagePreviewWidget(usd_context_name, *vp_args, **vp_kw_args)

    def __del__(self):
        self.destroy()

    @property
    def preview_viewport(self):
        return self.__preview_viewport

    def open_stage(self, file_path: str):
        # Reach into the StagePreviewWidget and get the viewport where we can retrieve the usd_context or usd_context_name
        self.__preview_viewport.viewport_api.usd_context.open_stage(file_path)
        # the Viewport doesn't have any idea of omni.ui.scene so give the models a sync after open (camera may have changed)
        self.__preview_viewport.sync_models()

    def destroy(self):
        if self.__preview_viewport:
            self.__preview_viewport.destroy()
            self.__preview_viewport = None
        if self.__usd_context:
            # We can't fully tear down everything yet, so just clear out any active stage
            self.__usd_context.remove_all_hydra_engines()
            # self.__usd_context = None
            # omni.usd.destroy_context(self.__usd_context_name)
        super().destroy()