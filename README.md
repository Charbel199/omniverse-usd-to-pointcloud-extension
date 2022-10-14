# Running the extension

`./app/kit/kit --ext-folder exts -enable pc.extension`

# Current Issue

This [line](exts/pc.extension/pc/extension/pointcloud_converter.py#L200) of code:
`self.__vp_widget.viewport_api.render_product_path`
returns
`None`

This might be the issue since the current error when pressing 'Start Generating Pointcloud' after importing a USD model is:

`
...
File "/home/charbel199/.local/share/ov/pkg/deps/a2b9fc40eb4e1a4f50259f9f40e47fc3/extscore/omni.syntheticdata/omni/syntheticdata/scripts/SyntheticData.py", line 578, in _get_graph_path
    prim = usdStage.GetPrimAtPath(renderProductPath)
Boost.Python.ArgumentError: Python argument types in
    None.GetPrimAtPath(Stage, NoneType)
did not match C++ signature:
    GetPrimAtPath(pxrInternal_v0_20__pxrReserved__::UsdStage {lvalue}, pxrInternal_v0_20__pxrReserved__::SdfPath path)
`

