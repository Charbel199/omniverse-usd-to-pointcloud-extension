import omni.ui as ui
from . import window_style as style
import asyncio


class SetupWindow(ui.Window):
    """The Setup Window is the main ui window for rgbd slam, with options for
    loading as sequence, streaming over TCP, and other sequence options.

    This window is launched by the rgbd_slam when the menu option is clicked.
    When the START button is pressed, a progress window will open which is owned by this class.
    """

    def __init__(self, pointcloud_generator):

        self._visibility_changed_listener = None

        super().__init__(
            "Pointcloud Generator",
            width=style.PROGRESS_WINDOW_WIDTH,
            height=style.PROGRESS_WINDOW_HEIGHT,
            style=style.PROGRESS_WIN_DARK_STYLE,
            flags=ui.WINDOW_FLAGS_NO_SCROLLBAR,
            dockPreference=ui.DockPreference.RIGHT_TOP,
        )
        self.deferred_dock_in("Property", ui.DockPolicy.TARGET_WINDOW_IS_ACTIVE)
        self.dock_order = 0

        self.pc_generator = pointcloud_generator

    def destroy(self):
        super().destroy()
        self._data_fp = None
        self.visible = False
        
    def show(self):

        with self.frame:
            with ui.VStack(spacing=2, height=0):

                self._create_int_setting("Height Resolution", "height_resolution", "Height to sample points.")
                self._create_int_setting("Width Resolution", "width_resolution", "Width to sample points.")

                """ Select Data Path """
                with ui.HStack(height=0, spacing=5, width=ui.Percent(100)):
                    ui.Spacer()
                    # TODO: Adding point cloud generating function here
                    self._start_button = ui.Button(
                        "Start Generating Pointcloud", height=0, clicked_fn=self.pc_generator.start
                    )
                    ui.Spacer()

        self.visible = True

    def _create_int_setting(self, label_name: str, attr_name: str, tooltip: str):
        """Integer settings"""
        with ui.HStack(height=0, spacing=5, width=ui.Percent(100)):
            label = ui.Label(label_name, width=ui.Percent(30))
            model = ui.SimpleIntModel(getattr(self.pc_generator, attr_name))
            widget = ui.IntField(tooltip=tooltip)
            widget.model.add_value_changed_fn(lambda m: setattr(self.pc_generator, attr_name, m.as_int))
            return label, widget
