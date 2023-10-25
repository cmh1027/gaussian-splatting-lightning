import os
import argparse
import numpy as np
import torch
from scipy.spatial.transform import Rotation as R
from dataclasses import dataclass
from internal.utils.colmap import rotmat2qvec, qvec2rotmat
from internal.utils.general_utils import build_rotation
import internal.utils.gaussian_utils


@dataclass
class Gaussian(internal.utils.gaussian_utils.Gaussian):
    @staticmethod
    def rx(theta):
        return np.matrix([[1, 0, 0],
                          [0, np.cos(theta), -np.sin(theta)],
                          [0, np.sin(theta), np.cos(theta)]])

    @staticmethod
    def ry(theta):
        return np.matrix([[np.cos(theta), 0, np.sin(theta)],
                          [0, 1, 0],
                          [-np.sin(theta), 0, np.cos(theta)]])

    @staticmethod
    def rz(theta):
        return np.matrix([[np.cos(theta), -np.sin(theta), 0],
                          [np.sin(theta), np.cos(theta), 0],
                          [0, 0, 1]])

    def rescale(self, scale: float):
        if scale != 1.:
            self.xyz *= scale
            self.scales += np.log(scale)

            print("rescaled with factor {}".format(scale))

    def rotate(self, x: float, y: float, z: float):
        """
        rotate in z-y-x order, radians as unit
        """

        if x == 0. and y == 0. and z == 0.:
            return

        rotation_matrix = np.asarray(self.rx(x) @ self.ry(y) @ self.rz(z), dtype=np.float32)

        # rotate xyz
        self.xyz = np.asarray(np.matmul(self.xyz, rotation_matrix.T))

        # rotate gaussian
        # rotate via quaternions, seems not work correctly
        # def quat_multiply(quaternion0, quaternion1):
        #     x0, y0, z0, w0 = np.split(quaternion0, 4, axis=-1)
        #     x1, y1, z1, w1 = np.split(quaternion1, 4, axis=-1)
        #     return np.concatenate(
        #         (x1 * w0 + y1 * z0 - z1 * y0 + w1 * x0,
        #          -x1 * z0 + y1 * w0 + z1 * x0 + w1 * y0,
        #          x1 * y0 - y1 * x0 + z1 * w0 + w1 * z0,
        #          -x1 * x0 - y1 * y0 - z1 * z0 + w1 * w0),
        #         axis=-1)
        #
        # quaternions = rotmat2qvec(rotation_matrix)[np.newaxis, ...]
        # rotations_from_quats = quat_multiply(quaternions, self.rotations)
        # self.rotations = rotations_from_quats

        # rotate via rotation matrix
        gaussian_rotation = build_rotation(torch.from_numpy(self.rotations)).cpu()
        gaussian_rotation = torch.from_numpy(rotation_matrix) @ gaussian_rotation
        xyzw_quaternions = R.from_matrix(gaussian_rotation.numpy()).as_quat(canonical=False)
        wxyz_quaternions = xyzw_quaternions
        wxyz_quaternions[:, [0, 1, 2, 3]] = wxyz_quaternions[:, [3, 0, 1, 2]]
        rotations_from_matrix = wxyz_quaternions
        #
        self.rotations = rotations_from_matrix

        # TODO: rotate shs
        print("set sh_degree=0 when rotation transform enabled")
        self.sh_degrees = 0

    def translation(self, x: float, y: float, z: float):
        if x == 0. and y == 0. and z == 0.:
            return

        self.xyz += np.asarray([x, y, z])
        print("translation transform applied")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")

    # TODO: support degrees > 1
    parser.add_argument("--sh-degrees", "--sh-degree", "-s", type=int, default=3)
    parser.add_argument("--new-sh-degrees", "--ns", type=int, default=-1)

    # translation
    parser.add_argument("--tx", type=float, default=0)
    parser.add_argument("--ty", type=float, default=0)
    parser.add_argument("--tz", type=float, default=0)

    # rotation in euler angeles
    parser.add_argument("--rx", type=float, default=0, help="in radians")
    parser.add_argument("--ry", type=float, default=0, help="in radians")
    parser.add_argument("--rz", type=float, default=0, help="in radians")

    # scale
    parser.add_argument("--scale", type=float, default=1)

    args = parser.parse_args()
    args.input = os.path.expanduser(args.input)
    args.output = os.path.expanduser(args.output)

    return args


def main():
    args = parse_args()
    assert args.input != args.output
    assert args.sh_degrees >= 1 and args.sh_degrees <= 3
    assert args.scale > 0
    assert os.path.exists(args.input)

    gaussian = Gaussian.load_from_ply(args.input, args.sh_degrees)

    if args.new_sh_degrees >= 0:
        gaussian.sh_degrees = args.new_sh_degrees

    gaussian.rescale(args.scale)
    gaussian.rotate(args.rx, args.ry, args.rz)
    gaussian.translation(args.tx, args.ty, args.tz)

    gaussian.save_to_ply(args.output)

    print(args.output)


main()