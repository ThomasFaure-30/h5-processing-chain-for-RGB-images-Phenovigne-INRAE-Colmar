"""
lidar extract

This module generates a point cloud from lidars data generated by Phenomobile v2

Author: Eric David (Ephesia)
Initial Date: October 2019
"""
import sys
import numpy as np
import time
import math
import utils
from lidar_calc import LidarCalc
from h5_info.position import Position
from h5_info.logger import Logger
from h5_info.errors import DataError
from h5_info import constants
from checker import Checker, ArgumentError, ERROR_CODE
from h5_info import H5Info, Geo

class extracting:

    @staticmethod
    def get_lidar_files(file,output_directory):

        COMMAND_LINE = "path/to/hdf5.file " \
                       "path/to/output/folder " \
                       "--mat2to1 path/to/transformation/matrix2to1.txt " \
                       "--mat3to1 path/to/transformation/matrix3to1.txt " \
                       "--debug false " \
                       "--format las " \
                       "--merge true " \
                       "--isLidar3Reversed false"


        PARAM_DEBUG = "--debug"
        PARAM_MAT_2TO1 = "--mat2to1"
        PARAM_MAT_3TO1 = "--mat3to1"
        PARAM_MERGE = "--merge"
        PARAM_FORMAT = "--format"
        PARAM_REVERSED = "--isLidar3Reversed"

        MANDATORY_ARG_LIST = [
            'Path to the HDF5 File (relative to the current folder)',
            'Path to the Output Folder (relative to the current folder)'
        ]

        OPTIONAL_ARG_LIST = {
            PARAM_DEBUG: 'Flag for displaying debug level logs (true or false)',
            PARAM_MAT_2TO1: 'Path to Lidar 2 to 1 transformation matrix (relative to current folder)',
            PARAM_MAT_3TO1: 'Path to Lidar 3 to 1 transformation matrix (relative to current folder)',
            PARAM_MERGE: 'Flag for merging Lidars 2 and 3 in Lidar 1 coordinates system (true or false)',
            PARAM_FORMAT: 'Name of format used for exporting point clouds (las or xyz)',
            PARAM_REVERSED: 'Flag for applying a correction to Lidar 3 when it is mounted on the opposite side of the tray'
        }

        # DEBUG ONLY
        # sys.argv.append('D:\\tests-pheno\\test-toulouse.h5')
        # sys.argv.append('D:\\tests-pheno\\output-toulouse')
        # sys.argv.append('--mat2to1')
        # sys.argv.append('D:\\tests-pheno\\transformation_matrix2to1.txt')
        # sys.argv.append('--mat3to1')
        # sys.argv.append('D:\\tests-pheno\\transformation_matrix3to1.txt')
        # sys.argv.append('--debug')
        # sys.argv.append('true')
        # sys.argv.append('--merge')
        # sys.argv.append('true')
        # sys.argv.append('--format')
        # sys.argv.append('las')
        # sys.argv.append('--isLidar3Reversed')
        # sys.argv.append('false')

        timer_start = time.time()

        # file = r'C:\Users\thfaure\Desktop\2021\Pop_50025\Avril_2021\uplot_567001_1.h5'
        # output_directory =r'C:\Users\thfaure\Desktop\2021\Pop_50025\Avril_2021\Lidar'

        try:
            # CHECKING PARAMETERS
            print("")
            Logger.info("Validating module input parameters...")

            optional_args = {}
            mandatory_args = [file, output_directory]
            Checker.check_input_arguments(sys.argv,
                                          mandatory_args, optional_args,
                                          MANDATORY_ARG_LIST, OPTIONAL_ARG_LIST,
                                          COMMAND_LINE)

            h5_file = mandatory_args[0]
            Checker.check_file_exists(h5_file)

            output_folder = mandatory_args[1]
            Checker.check_folder_exists(output_folder, True)

            if Checker.is_optional_param_true(PARAM_DEBUG, optional_args, False):
                Logger.init(True)
                Logger.debug("Debug logs will be displayed")

            merge_lidars = Checker.is_optional_param_true(PARAM_MERGE, optional_args)

            mat2to1_path = Checker.get_optional_string_param(PARAM_MAT_2TO1, optional_args)
            if mat2to1_path is not None:
                Checker.check_file_exists(mat2to1_path)

            mat3to1_path = Checker.get_optional_string_param(PARAM_MAT_3TO1, optional_args)
            if mat3to1_path is not None:
                Checker.check_file_exists(mat3to1_path)

            output_format = Checker.get_optional_string_param(PARAM_FORMAT, optional_args, 'las')
            if output_format not in ['las', 'xyz']:
                raise ArgumentError("Value '" + output_format + "' for param '" + PARAM_FORMAT + "' is not valid (must be 'las' or 'xyz')")

            isLidar3Reversed = Checker.is_optional_param_true(PARAM_REVERSED, optional_args, False)

            if isLidar3Reversed:
                Logger.debug("LiDAR 3 is mounted on the opposite side of the tray")

            # EXTRACTING HDF5 INFORMATION
            Logger.info("Reading file '" + h5_file + "'...")
            Logger.info("Loading HDF5 meta-information and raw data...")

            sensor_names = ["Lidar"]

            h5_info = H5Info()
            h5_info.load_data(h5_file, sensor_names)

            plot_prefix = "uplot_" + h5_info.plot.id + "_"

            h5_info.save_metadata(output_folder + "/" + plot_prefix + "lidar_metadata.json")

            # READING / COMPUTING AND CHECKING TRANSFORMATION MATRICES
            Logger.info("Loading Transformation matrices...")

            if mat2to1_path is None:
                Logger.info("Generating transformation matrix 2 to 1 from HDF5 file info")

                # Lidar 1 and Lidar 2 are on the same head
                pos_lms_1 = h5_info.static_transforms['lms_1']
                pos_lms_2 = h5_info.static_transforms['lms_2']

                dx = pos_lms_2.x - pos_lms_1.x
                dy = pos_lms_2.y - pos_lms_1.y
                dz = -(pos_lms_2.z - pos_lms_1.z)
                yaw = -(pos_lms_2.yaw - pos_lms_1.yaw) / 180 * math.pi
                pitch = -(pos_lms_2.pitch - pos_lms_1.pitch) / 180 * math.pi
                roll = -(pos_lms_2.roll - pos_lms_1.roll) / 180 * math.pi

                mat2to1 = utils.compute_transformation_matrix(dx, dy, dz, yaw, pitch, roll)
            else:
                mat2to1 = np.loadtxt(mat2to1_path)
                if mat2to1.shape != (4, 4):
                    raise ValueError("Lidar 2 to 1 transformation matrix doesn't have the correct size. 4x4 matrix is expected.")

            """if mat3to1_path is None:
                Logger.info("Generating transformation matrix 3 to 1 from HDF5 file info")

                # Lidar 1 and Lidar 3 are not on the same head
                # Lidar 1 is on head_ref
                pos_lms_1 = h5_info.static_transforms['lms_1']

                # Lidar 3 is on aux_head (via aux_head_arm > aux_head_pivot > head_ref)
                pos_lms_3 = h5_info.static_transforms['lms_3']
                pos_aux_head = h5_info.static_transforms['aux_head']
                pos_aux_head_arm = h5_info.static_transforms['aux_head_arm']
                pos_aux_head_pivot = h5_info.static_transforms['aux_head_pivot']

                pos_lms_3_ref = Position()
                pos_lms_3_ref.x = pos_lms_3.x + pos_aux_head.x + pos_aux_head_arm.x + pos_aux_head_pivot.x
                pos_lms_3_ref.y = pos_lms_3.y + pos_aux_head.y + pos_aux_head_arm.y + pos_aux_head_pivot.y
                pos_lms_3_ref.z = pos_lms_3.z + pos_aux_head.z + pos_aux_head_arm.z + pos_aux_head_pivot.z
                pos_lms_3_ref.roll = pos_lms_3.roll + pos_aux_head.roll + pos_aux_head_arm.roll + pos_aux_head_pivot.roll
                pos_lms_3_ref.pitch = pos_lms_3.pitch + pos_aux_head.pitch + pos_aux_head_arm.pitch + pos_aux_head_pivot.pitch
                pos_lms_3_ref.yaw = pos_lms_3.yaw + pos_aux_head.yaw + pos_aux_head_arm.yaw + pos_aux_head_pivot.yaw

                dx = pos_lms_3_ref.x - pos_lms_1.x
                dy = pos_lms_3_ref.y - pos_lms_1.y
                dz = -(pos_lms_3_ref.z - pos_lms_1.z)
                yaw = -(pos_lms_3_ref.yaw - pos_lms_1.yaw) / 180 * math.pi
                pitch = -(pos_lms_3_ref.pitch - pos_lms_1.pitch) / 180 * math.pi
                roll = -(pos_lms_3_ref.roll - pos_lms_1.roll) / 180 * math.pi

                mat3to1 = utils.compute_transformation_matrix(dx, dy, dz, yaw, pitch, roll)

            else:
                mat3to1 = np.loadtxt(mat3to1_path)
                if mat3to1.shape != (4, 4):
                    raise ValueError("Lidar 3 to 1 transformation matrix doesn't have the correct size. 4x4 matrix is expected.")
            """
            # READING LIDAR DATA FILE INT 'LIDARS' VARIABLE
            Logger.info("Reading Lidar raw data...")
            lidars = {}
            for sensor in h5_info.sensors:
                if sensor.type == constants.TYPE_LIDAR:
                    image = sensor.images[0]
                    Logger.debug("Loading data from: " + image.name)
                    lidars[sensor.description] = image.scans

            point_cloud = {}
            for lid_id in lidars:

                # COMPUTE LIDAR POSITIONS AND POINT CLOUD
                #########################################
                Logger.info("Compute Lidar '" + lid_id + "' positions and point cloud...")
                lidar = lidars[lid_id]
                point_cloud[lid_id] = LidarCalc.compute_lidar_positions(lidars['lms_1'], lidar, Geo.to_dict_array(h5_info.geo), lid_id == "lms_3", isLidar3Reversed)

                # MERGE LIDARS 2 AND 3 IN LIDAR 1 POSITIONING SYSTEM
                ####################################################
                if lid_id != "lms_1" and merge_lidars:
                    # Merge positions
                    Logger.info("Merging Lidar '"+lid_id+"' positions in Lidar 1 system...")
                    mat_trans = mat2to1
                    if lid_id == "lms_3":
                        mat_trans = mat3to1

                    (x, y, z) = LidarCalc.apply_transformation_matrix(mat_trans, lidar['x'], lidar['y'], lidar['z'])
                    lidar['x'] = x
                    lidar['y'] = y
                    lidar['z'] = z

                    (x, y, z) = LidarCalc.apply_transformation_matrix(mat_trans, point_cloud[lid_id]['pt_x'], point_cloud[lid_id]['pt_y'], point_cloud[lid_id]['pt_z'])
                    point_cloud[lid_id]['pt_x'] = x
                    point_cloud[lid_id]['pt_y'] = y
                    point_cloud[lid_id]['pt_z'] = z

                # ROUND METRIC VALUES TO 1e-6
                #############################
                lidar['x'] = np.round(lidar['x'], 6)
                lidar['y'] = np.round(lidar['y'], 6)
                lidar['z'] = np.round(lidar['z'], 6)
                point_cloud[lid_id]['pt_x'] = np.round(point_cloud[lid_id]['pt_x'], 6)
                point_cloud[lid_id]['pt_y'] = np.round(point_cloud[lid_id]['pt_y'], 6)
                point_cloud[lid_id]['pt_z'] = np.round(point_cloud[lid_id]['pt_z'], 6)

                # EXPORT POSITIONS AND POINT_CLOUD IN DESIRED FORMAT
                ####################################################
                Logger.info("Exporting '"+lid_id+"' positions and point clouds in " + output_format + " format...")

                if output_format == 'xyz':
                    path = output_folder + "/" + plot_prefix + lid_id + "_pos.xyz"
                    Logger.debug("Writing positions file: " + path)
                    keys = {'x': 'lidar_x', 'y': 'lidar_y', 'z': 'lidar_z'}
                    utils.numpy_to_ascii_file(path, lidar, keys, " ", True)

                    path = output_folder + "/" + plot_prefix + lid_id + "_point_cloud.xyz"
                    Logger.debug("Writing point cloud file: " + path)
                    keys = {'pt_x': 'pt_x', 'pt_y': 'pt_y', 'pt_z': 'pt_z', 'reflectivity': 'reflectivity'}
                    utils.numpy_to_ascii_file(path, point_cloud[lid_id], keys, " ", True)

                elif output_format == 'las':
                    path = output_folder + "/" + plot_prefix + lid_id + "_pos.las"
                    Logger.debug("Writing positions file: " + path)

                    utils.create_las_file(path, lidar['x'], lidar['y'], lidar['z'])

                    path = output_folder + "/" + plot_prefix + lid_id + "_point_cloud.las"
                    Logger.debug("Writing point cloud file: " + path)

                    utils.create_las_file(path,
                                          point_cloud[lid_id]['pt_x'],
                                          point_cloud[lid_id]['pt_y'],
                                          point_cloud[lid_id]['pt_z'],
                                          point_cloud[lid_id]['reflectivity'])
        except ArgumentError as error:
            Logger.error(error)
            Logger.error("Lidar Extraction failed")
            sys.exit(ERROR_CODE)
        except DataError as error:
            Logger.error(error)
            Logger.error("Lidar Extraction of {0} failed".format(h5_file))

        timer_end = time.time()
        # print("Lidar pre-processing took " + str(int(timer_end - timer_start)) + " seconds")

