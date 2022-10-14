# Copyright (c) 2020-2021, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

# This code is from: https://gitlab-master.nvidia.com/omniverse/deeptag/deeptag-services/-/blob/master/modules/deeptag_renderer/deeptag_renderer/omni_helpers/syntheticdata_async.py#L134

"""Helper class for obtaining groundtruth data from OmniKit. Support provided for RGB, instance segmentation.
"""

# standard modules
import os
import sys
import time
import asyncio

# third party modules
import numpy as np

# local/ proprietary modules
import omni
import omni.syntheticdata as syn


# define a list of supported sensor that are extracted from USD file
# > mapping sensor type to field name

SENSORS = {
    syn._syntheticdata.SensorType.Rgb: "images",
    syn._syntheticdata.SensorType.Depth: "depth",
    syn._syntheticdata.SensorType.DepthLinear: "linear_depth",
    syn._syntheticdata.SensorType.Normal: "normal",
    syn._syntheticdata.SensorType.InstanceSegmentation: "segmentation",
}


class SyntheticDataHelper:
    def __init__(self):
        self.app = omni.kit.app.get_app_interface()
        # vp_iface = omni.kit.viewport.get_viewport_interface()

    async def enable_sensors(self, viewport, sensors):
        """Enable syntheticdata sensors.

        Args:
            sensors: List of sensor names. Valid sensors names: rgb, depth,
                     instanceSegmentation, semanticSegmentation, boundingBox2DTight,
                     boundingBox2DLoose, boundingBox3D, camera, normal
        """
        # Enable sensor
        await syn.sensors.initialize_async(viewport, sensors)

        for _ in range(2):
            await self.app.next_update_async()

    async def _wait_for_data(self, viewport, timeout: float = 10):
        # HACK Render until data is available (remove when no longer needed)
        data = np.empty(0)
        start = time.time()
        while data.size == 0 and time.time() < start + timeout:
            await self.app.next_update_async()
            data = syn.sensors.get_bounding_box_2d_loose(viewport)

    async def get_instance_segmentation(self, viewport):
        """Get instance segmentation data.
        Generate a list of N instance names and corresponding array of N
        binary instance masks.

        Returns:
            A tuple of a list of instance names, and a bool array with shape (N, H, W).
        """
        # get instance segmentation
        instance_tex = syn.sensors.get_instance_segmentation(viewport, parsed=True, return_mapping=False)
        return instance_tex

    async def get_groundtruth(self, viewport, gt_sensors: list, err_limit: int = 10) -> dict:
        """Get groundtruth from specified gt_sensors.
        Enable syntheticdata sensors if required, render a frame and
        collect groundtruth from the specified gt_sensors

        If a sensor requiring RayTracedLighting mode is specified, render
        an additional frame in RayTracedLighting mode.

        Args:
            gt_sensors (list): List of strings of sensor names. Valid sensors names: rgb, depth,
                instanceSegmentation, semanticSegmentation, boundingBox2DTight,
                boundingBox2DLoose, boundingBox3D, camera, normal

        Returns:
            Dict of sensor outputs
        """

        gt = {}
        # make sure sensors are enabled
        await self.enable_sensors(viewport, gt_sensors)

        for sensor in gt_sensors:
            received = False
            err_count = 0
            while not received and err_count < err_limit:
                try:
                    field = SENSORS[sensor]
                    if sensor == syn._syntheticdata.SensorType.Rgb:
                        gt[field] = syn.sensors.get_rgb(viewport)
                    elif sensor == syn._syntheticdata.SensorType.InstanceSegmentation:
                        instance_mask = await self.get_instance_segmentation(viewport)
                        gt[field] = instance_mask
                    elif sensor == syn._syntheticdata.SensorType.Depth:
                        gt[field] = syn.sensors.get_depth(viewport)
                    elif sensor == syn._syntheticdata.SensorType.DepthLinear:
                        gt[field] = syn.sensors.get_depth_linear(viewport)
                    elif sensor == syn._syntheticdata.SensorType.Normal:
                        gt[field] = syn.sensors.get_normals(viewport)
                    else:
                        raise NotImplementedError(f"Sensor '{sensor}' is currently not implemented in this helper")
                    received = True
                except Exception as e:
                    print(e)
                    err_count += 1
                    await self.enable_sensors(viewport, gt_sensors)
        return gt
