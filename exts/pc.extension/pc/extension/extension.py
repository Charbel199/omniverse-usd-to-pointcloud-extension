import asyncio
import omni.ext
from functools import partial
from omni.kit.window.filepicker import FilePickerDialog
import omni.ui as ui
from .pointcloud_converter import PointCloudGenerator
from .setup_window import SetupWindow
from .test_window import StagePreviewWindow
import os

import posixpath

from functools import partial


class PointCloudGeneratorExtension(omni.ext.IExt):
    # ext_id is current extension id. It can be used with extension manager to query additional information, like where
    # this extension is located on filesystem.
    def on_startup(self, ext_id):
        self._window_name = "Point Cloud Generator"
        self._menu_path = "Window/PointCloudGenerator"

        # Generator that mainly do the job
        self.pc_generator = PointCloudGenerator()

        self._setup_window = None

        self._create_setup_window()

        ui.Workspace.set_show_window_fn(self._window_name, partial(self.show_setup_window, None))
        editor_menu = omni.kit.ui.get_editor_menu()
        if editor_menu:
            self._menus = [
                editor_menu.add_item(self._menu_path, self.show_setup_window, toggle=True, value=True),
                editor_menu.add_item("PointCloud/Import USD File", self.load_usd_file),
            ]

        ui.Workspace.show_window(self._window_name)


    def on_shutdown(self):
        self._menus = None

        ui.Workspace.show_window(self._window_name, False)
        ui.Workspace.set_show_window_fn(self._window_name, None)


    def _create_setup_window(self):
        self._setup_window = SetupWindow(self.pc_generator)
        self._view_window = StagePreviewWindow("Test2")
        
        self._setup_window.set_visibility_changed_fn(self._visibility_changed_fn)
        self._setup_window.show()

    def show_setup_window(self, _, value):
        self._set_menu(value)
        if value:
            if not self._setup_window:
                self._create_setup_window()
        elif self._setup_window:
            self._setup_window.set_visibility_changed_fn(None)
            self._setup_window.destroy()
            self._setup_window = None

    def _set_menu(self, value):
        """Set the menu to create this window on and off"""
        editor_menu = omni.kit.ui.get_editor_menu()
        if editor_menu:
            editor_menu.set_value(self._menu_path, value)

    def _visibility_changed_fn(self, visible):
        if visible:
            self._set_menu(visible)
        else:
            # Destroy the window
            self.show_setup_window(None, False)

    def load_usd_file(self, menu_item, value):
        # Re-initialize the point cloud generator everytime you open a new file
        self.pc_generator.clean()
        dialog = FilePickerDialog(
            "Open USD File",
            apply_button_label="Open",
            click_apply_handler=lambda filename, dirname: self._on_usd_file_open(dialog, filename, dirname),
            item_filter_options=[("*.usd", "*.usda", "USD files (*.*)")],
            item_filter_fn=self._on_filter_usd_files,
        )
        dialog.show()

    def _on_usd_file_open(self, dialog, filename, dirname):
        dialog.hide()
        asyncio.ensure_future(self.pc_generator.initialize_stage(posixpath.join(dirname, filename)))

    def _on_filter_usd_files(self, item) -> bool:
        """Callback to filter the choices of file names in the open or save dialog"""
        if not item or item.is_folder:
            return True
        return os.path.splitext(item.path)[1] == ".usd" or os.path.splitext(item.path)[1] == ".usda"
