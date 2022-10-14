import omni.ui as ui

PROGRESS_WINDOW_WIDTH = 360
PROGRESS_WINDOW_HEIGHT = 300
PROGRESS_BAR_WIDTH = 216
PROGRESS_BAR_HEIGHT = 20
TRIANGLE_WIDTH = 6
TRIANGLE_HEIGHT = 10
TRIANGLE_OFFSET_Y = 10

PROGRESS_WIN_DARK_STYLE = {
    "Triangle::progress_marker": {"background_color": 0xFFD1981D},
    "Rectangle::progress_bar_background": {"border_width": 0.5, "border_radius": 0, "background_color": 0xFF888888},
    "Rectangle::progress_bar_full": {"border_width": 0.5, "border_radius": 0, "background_color": 0xFFD1981D},
    "Rectangle::progress_bar": {
        "background_color": 0xFFD1981D,
        "border_radius": 0,
        "corner_flag": ui.CornerFlag.LEFT,
        "alignment": ui.Alignment.LEFT,
    },
}

COLLAPSABLEFRAME_STYLE = {
    "CollapsableFrame": {
        "background_color": 0xFF343432,
        "secondary_color": 0xFF343432,
        "color": 0xFFAAAAAA,
        "border_radius": 4.0,
        "border_color": 0x0,
        "border_width": 1,
        "font_size": 14.0,
        "padding": 6,
        "border_radius": 3.0,
    },
    "CollapsableFrame.Header": {"font_size": 14.0, "background_color": 0xFF545454, "color": 0xFF545454},
    "HStack::header": {"margin": 5},
    "CollapsableFrame:hovered": {"secondary_color": 0xFF3A3A3A},
    "CollapsableFrame:pressed": {"secondary_color": 0xFF343432},
}
