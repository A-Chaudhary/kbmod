import time
import warnings
import os

import numpy as np
from .analysis_utils import Interface, PostProcess
from .astro_utils import *
from .image_info import *
import kbmod.search as kb
import koffi
from .result_list import *


class run_search:
    """
    Run the KBMoD grid search.

    Parameters
    ----------
    input_parameters : `dict`
        Input parameters. Merged with the `defaults` dictionary.
        Must contain `im_filepath` and `res_filepath` keys, paths to
        the image and results directory respectively. Should contain
        `v_arr`, and `ang_arr`, which are lists containing the lower
        and upper velocity and angle limits.

    Attributes
    ----------
    default_mask_bits_dict : `dict`
        Map between mask key and bit values.
    default_flag_keys : `list`
        Pixels marked with these flags will be ignored in the search.
        Default: `["BAD", "EDGE", "NO_DATA", "SUSPECT", "UNMASKEDNAN"]`
    default_repeated_flag_keys : `list`
        Don't know
    config : `dict`
        Search parameters.
    """

    def __init__(self, input_parameters):
        default_mask_bits_dict = {
            "BAD": 0,
            "CLIPPED": 9,
            "CR": 3,
            "CROSSTALK": 10,
            "DETECTED": 5,
            "DETECTED_NEGATIVE": 6,
            "EDGE": 4,
            "INEXACT_PSF": 11,
            "INTRP": 2,
            "NOT_DEBLENDED": 12,
            "NO_DATA": 8,
            "REJECTED": 13,
            "SAT": 1,
            "SENSOR_EDGE": 14,
            "SUSPECT": 7,
            "UNMASKEDNAN": 15,
        }
        default_flag_keys = ["BAD", "EDGE", "NO_DATA", "SUSPECT", "UNMASKEDNAN"]
        default_repeated_flag_keys = []
        defaults = {  # Mandatory values
            "im_filepath": None,
            "res_filepath": None,
            "time_file": None,
            "psf_file": None,
            # Suggested values
            "v_arr": [92.0, 526.0, 256],
            "ang_arr": [np.pi / 15, np.pi / 15, 128],
            # Optional values
            "output_suffix": "search",
            "mjd_lims": None,
            "average_angle": None,
            "do_mask": True,
            "mask_num_images": 2,
            "mask_threshold": None,
            "mask_grow": 10,
            "lh_level": 10.0,
            "psf_val": 1.4,
            "num_obs": 10,
            "num_cores": 1,
            "visit_in_filename": [0, 6],
            "sigmaG_lims": [25, 75],
            "chunk_size": 500000,
            "max_lh": 1000.0,
            "center_thresh": 0.00,
            "peak_offset": [2.0, 2.0],
            "mom_lims": [35.5, 35.5, 2.0, 0.3, 0.3],
            "stamp_type": "sum",
            "stamp_radius": 10,
            "eps": 0.03,
            "gpu_filter": False,
            "do_clustering": True,
            "do_stamp_filter": True,
            "clip_negative": False,
            "cluster_type": "all",
            "cluster_function": "DBSCAN",
            "mask_bits_dict": default_mask_bits_dict,
            "flag_keys": default_flag_keys,
            "repeated_flag_keys": default_repeated_flag_keys,
            "bary_dist": None,
            "encode_psi_bytes": -1,
            "encode_phi_bytes": -1,
            "known_obj_thresh": None,
            "known_obj_jpl": False,
            "known_obj_obs": 3,
        }
        # Make sure input_parameters contains valid input options
        for key, val in input_parameters.items():
            if key in defaults:
                defaults[key] = val
            else:
                warnings.warn('Key "{}" is not a valid option. It is being ignored.'.format(key))
        self.config = defaults
        if self.config["im_filepath"] is None:
            raise ValueError("Image filepath not set")
        if self.config["res_filepath"] is None:
            raise ValueError("Results filepath not set")
        return

    def do_gpu_search(self, search, img_info, ec_angle, post_process):
        """
        Performs search on the GPU.

        Parameters
        ----------
        search : `kbmod.search.Search`
            Search object.
        img_info : `kbmod.search.ImageInfo`
            ImageInfo object.
        ec_angle : `float`
            Angle a 12 arcsecond segment parallel to the ecliptic is
            seen under from the image origin.
        post_process :
            Don't know
        """
        search_params = {}

        # Run the grid search
        # Set min and max values for angle and velocity
        if self.config["average_angle"] == None:
            average_angle = ec_angle
        else:
            average_angle = self.config["average_angle"]
        ang_min = average_angle - self.config["ang_arr"][0]
        ang_max = average_angle + self.config["ang_arr"][1]
        vel_min = self.config["v_arr"][0]
        vel_max = self.config["v_arr"][1]
        search_params["ang_lims"] = [ang_min, ang_max]
        search_params["vel_lims"] = [vel_min, vel_max]

        # If we are using barycentric corrections, compute the parameters and
        # enable it in the search function.
        if "bary_dist" in self.config.keys() and self.config["bary_dist"] is not None:
            bary_corr = calc_barycentric_corr(img_info, self.config["bary_dist"])
            # print average barycentric velocity for debugging

            mjd_range = img_info.get_duration()
            bary_vx = bary_corr[-1, 0] / mjd_range
            bary_vy = bary_corr[-1, 3] / mjd_range
            bary_v = np.sqrt(bary_vx * bary_vx + bary_vy * bary_vy)
            bary_ang = np.arctan2(bary_vy, bary_vx)
            print("Average Velocity from Barycentric Correction", bary_v, "pix/day", bary_ang, "angle")
            search.enable_corr(bary_corr.flatten())

        search_start = time.time()
        print("Starting Search")
        print("---------------------------------------")
        param_headers = (
            "Ecliptic Angle",
            "Min. Search Angle",
            "Max Search Angle",
            "Min Velocity",
            "Max Velocity",
        )
        param_values = (ec_angle, *search_params["ang_lims"], *search_params["vel_lims"])
        for header, val in zip(param_headers, param_values):
            print("%s = %.4f" % (header, val))

        # If we are using gpu_filtering, enable it and set the parameters.
        if self.config["gpu_filter"]:
            print("Using in-line GPU sigmaG filtering methods", flush=True)
            self.config["sigmaG_coeff"] = post_process._find_sigmaG_coeff(self.config["sigmaG_lims"])
            search.enable_gpu_sigmag_filter(
                np.array(self.config["sigmaG_lims"]) / 100.0,
                self.config["sigmaG_coeff"],
                self.config["lh_level"],
            )

        # If we are using an encoded image representation on GPU, enable it and
        # set the parameters.
        if self.config["encode_psi_bytes"] > 0 or self.config["encode_phi_bytes"] > 0:
            search.enable_gpu_encoding(self.config["encode_psi_bytes"], self.config["encode_phi_bytes"])

        search.search(
            int(self.config["ang_arr"][2]),
            int(self.config["v_arr"][2]),
            *search_params["ang_lims"],
            *search_params["vel_lims"],
            int(self.config["num_obs"]),
        )
        print("Search finished in {0:.3f}s".format(time.time() - search_start), flush=True)
        return (search, search_params)

    def run_search(self):
        """This function serves as the highest-level python interface for starting
        a KBMOD search.

        INPUT - The following key : values from the self.config dictionary are
        needed:
        im_filepath : string
            Path to the folder containing the images to be ingested into
            KBMOD and searched over.
        res_filepath : string
            Path to the folder that will contain the results from the search.
        out_suffix : string
            Suffix to append to the output files. Used to differentiate
            between different searches over the same stack of images.
        time_file : string
            Path to the file containing the image times (or None to use
            values from the FITS files).
        psf_file : string
            Path to the file containing the image PSFs (or None to use default).
        lh_level : float
            Minimum acceptable likelihood level for a trajectory.
            Trajectories with likelihoods below this value will be discarded.
        psf_val : float
            The value of the variance of the default PSF to use.
        mjd_lims : numpy array
            Limits the search to images taken within the limits input by
            mjd_lims (or None for no filtering).
        average_angle : float
            Overrides the ecliptic angle calculation and instead centers
            the average search around average_angle.
        """
        start = time.time()
        kb_interface = Interface()

        # Load the PSF.
        default_psf = kb.psf(self.config["psf_val"])

        # Load images to search
        stack, img_info = kb_interface.load_images(
            self.config["im_filepath"],
            self.config["time_file"],
            self.config["psf_file"],
            self.config["mjd_lims"],
            self.config["visit_in_filename"],
            default_psf,
        )

        # Compute the ecliptic angle for the images.
        center_pixel = (img_info.stats[0].width / 2, img_info.stats[0].height / 2)
        ec_angle = calc_ecliptic_angle(img_info.stats[0].wcs, center_pixel)

        # Set up the post processing data structure.
        kb_post_process = PostProcess(self.config, img_info.get_all_mjd())

        # Apply the mask to the images.
        if self.config["do_mask"]:
            stack = kb_post_process.apply_mask(
                stack,
                mask_num_images=self.config["mask_num_images"],
                mask_threshold=self.config["mask_threshold"],
                mask_grow=self.config["mask_grow"],
            )

        # Perform the actual search.
        search = kb.stack_search(stack)
        search, search_params = self.do_gpu_search(search, img_info, ec_angle, kb_post_process)

        # Load the KBMOD results into Python and apply a filter based on
        # 'filter_type.
        mjds = np.array(img_info.get_all_mjd())
        keep = kb_post_process.load_and_filter_results(
            search,
            self.config["lh_level"],
            chunk_size=self.config["chunk_size"],
            max_lh=self.config["max_lh"],
        )
        if self.config["do_stamp_filter"]:
            kb_post_process.apply_stamp_filter(
                keep,
                search,
                center_thresh=self.config["center_thresh"],
                peak_offset=self.config["peak_offset"],
                mom_lims=self.config["mom_lims"],
                stamp_type=self.config["stamp_type"],
                stamp_radius=self.config["stamp_radius"],
            )

        if self.config["do_clustering"]:
            cluster_params = {}
            cluster_params["x_size"] = img_info.get_x_size()
            cluster_params["y_size"] = img_info.get_y_size()
            cluster_params["vel_lims"] = search_params["vel_lims"]
            cluster_params["ang_lims"] = search_params["ang_lims"]
            cluster_params["mjd"] = mjds
            kb_post_process.apply_clustering(keep, cluster_params)

        # Extract all the stamps.
        kb_post_process.get_all_stamps(keep, search, self.config["stamp_radius"])

        # Count how many known objects we found.
        if self.config["known_obj_thresh"]:
            self._count_known_matches(keep, img_info, search)

        del search

        # Save the results
        kb_interface.save_results(
            self.config["res_filepath"],
            self.config["output_suffix"],
            keep,
            img_info.get_all_mjd(),
        )

        end = time.time()
        del keep
        print("Time taken for patch: ", end - start)

    def _count_known_matches(self, result_list, img_info, search):
        """Look up the known objects that overlap the images and count how many
        are found among the results.

        Parameters
        ----------
        result_list : `ResultList`
            The result objects found by the search.
        img_info : `kbmod.search.InfoSet`
            Information from the fits images, including WCS.
        search : `kbmod.search.stack_search`
            A stack_search object containing information about the search.
        """
        # Get the image metadata
        im_filepath = self.config["im_filepath"]
        filenames = sorted(os.listdir(im_filepath))
        image_list = [os.path.join(im_filepath, im_name) for im_name in filenames]
        metadata = koffi.ImageMetadataStack(image_list)

        # Get the pixel positions of results
        ps_list = []

        for row in result_list.results:
            pix_pos_objs = search.get_mult_traj_pos(row.trajectory)
            pixel_positions = list(map(lambda p: [p.x, p.y], pix_pos_objs))
            ps = koffi.PotentialSource()
            ps.build_from_images_and_xy_positions(pixel_positions, metadata)
            ps_list.append(ps)

        print("-----------------")
        matches = {}
        known_obj_thresh = self.config["known_obj_thresh"]
        min_obs = self.config["known_obj_obs"]
        if self.config["known_obj_jpl"]:
            print("Quering known objects from JPL")
            matches = koffi.jpl_query_known_objects_stack(
                potential_sources=ps_list,
                images=metadata,
                min_observations=min_obs,
                tolerance=known_obj_thresh,
            )
        else:
            print("Quering known objects from SkyBoT")
            matches = koffi.skybot_query_known_objects_stack(
                potential_sources=ps_list,
                images=metadata,
                min_observations=min_obs,
                tolerance=known_obj_thresh,
            )

        matches_string = ""
        num_found = 0
        for ps_id in matches.keys():
            if len(matches[ps_id]) > 0:
                num_found += 1
                matches_string += f"result id {ps_id}:" + str(matches[ps_id])[1:-1] + "\n"
        print(
            "Found %i objects with at least %i potential observations." % (num_found, self.config["num_obs"])
        )

        if num_found > 0:
            print(matches_string)
        print("-----------------")
