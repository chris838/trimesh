"""
segments.py
--------------

Deal with (n, 2, 3) line segments.
"""

import numpy as np

from .. import util
from .. import grouping
from .. import geometry

from ..constants import tol


def segments_to_parameters(segments):
    """
    For 3D line segments defined by two points, turn
    them in to an origin defined as the closest point along
    the line to the zero origin as well as a direction vector
    and start and end parameter.

    Parameters
    ------------
    segments : (n, 2, 3) float
       Line segments defined by start and end points

    Returns
    --------------
    origins : (n, 3) float
       Point on line closest to [0, 0, 0]
    vectors : (n, 3) float
       Unit line directions
    parameters : (n, 2) float
       Start and end distance pairs for each line
    """
    segments = np.asanyarray(segments, dtype=np.float64)
    if not util.is_shape(segments, (-1, 2, (2, 3))):
        raise ValueError('incorrect segment shape!',
                         segments.shape)

    # make the initial origin one of the end points
    endpoint = segments[:, 0]
    vectors = segments[:, 1] - endpoint
    vectors_norm = np.linalg.norm(vectors, axis=1)
    vectors /= vectors_norm.reshape((-1, 1))

    # find the point along the line nearest the origin
    offset = util.diagonal_dot(endpoint, vectors)
    # points nearest [0, 0, 0] will be our new origin
    origins = endpoint + (offset.reshape((-1, 1)) * -vectors)

    # parametric start and end of line segment
    parameters = np.column_stack((offset, offset + vectors_norm))

    return origins, vectors, parameters


def parameters_to_segments(origins, vectors, parameters):
    """
    Convert a parametric line segment representation to
    a two point line segment representation

    Parameters
    ------------
    origins : (n, 3) float
       Line origin point
    vectors : (n, 3) float
       Unit line directions
    parameters : (n, 2) float
       Start and end distance pairs for each line

    Returns
    --------------
    segments : (n, 2, 3) float
       Line segments defined by start and end points
    """
    # don't copy input
    origins = np.asanyarray(origins, dtype=np.float64)
    vectors = np.asanyarray(vectors, dtype=np.float64)
    parameters = np.asanyarray(parameters, dtype=np.float64)

    # turn the segments into a reshapable 2D array
    segments = np.hstack((origins + vectors * parameters[:, :1],
                          origins + vectors * parameters[:, 1:]))

    return segments.reshape((-1, 2, origins.shape[1]))


def colinear_pairs(segments, radius=.01, angle=.01):
    """
    Find pairs of segments which are colinear.

    Parameters
    -------------
    segments : (n, 2, (2, 3)) float
      Two or three dimensional line segments
    radius : float
      Maximum radius line origins can differ
      and be considered colinear
    angle : float
      Maximum angle in radians segments can
      differ and still be considered colinear

    Returns
    ------------
    pairs : (m, 2) int
      Indexes of segments which are colinear
    """
    from scipy import spatial

    # convert segments to parameterized origins
    # which are the closest point on the line to
    # the actual zero- origin
    origins, vectors, parameters = segments_to_parameters(segments)

    # create a kdtree for origins
    tree = spatial.cKDTree(origins)

    # find origins closer than specified radius
    pairs = tree.query_pairs(r=radius, output_type='ndarray')

    # calculate angles between pairs
    angles = geometry.vector_angle(vectors[pairs])

    # angles can be within tolerance of 180 degrees or 0.0 degrees
    angle_ok = np.logical_or(
        util.isclose(angles, np.pi, atol=angle),
        util.isclose(angles, 0.0, atol=angle))

    # check angle threshold
    colinear = pairs[angle_ok]

    return colinear


def split(segments, points, atol=1e-5):
    """
    Find any points that lie on a segment (not an endpoint)
    and then split that segment into two segments.

    We are basically going to find the distance between
    point and both segment vertex, and see if it is with
    tolerance of the segment length.

    Parameters
    --------------
    segments : (n, 2, (2, 3) float
      Line segments in space
    points : (n, (2, 3)) float
      Points in space
    atol : float
      Absolute tolerance for distances

    Returns
    -------------
    split : (n, 2, (3 | 3) float
      Line segments in space, split at vertices
    """

    points = np.asanyarray(points, dtype=np.float64)
    segments = np.asanyarray(segments, dtype=np.float64)
    # reshape to a flat 2D (n, dimension) array
    seg_flat = segments.reshape((-1, segments.shape[2]))

    # find the length of every segment
    length = ((segments[:, 0, :] -
               segments[:, 1, :]) ** 2).sum(axis=1) ** 0.5

    # a mask to remove segments we split at the end
    keep = np.ones(len(segments), dtype=np.bool)
    # append new segments to a list
    new_seg = []

    # loop through every point
    for p in points:
        # note that you could probably get a speedup
        # by using scipy.spatial.distance.cdist here

        # find the distance from point to every segment endpoint
        pair = ((seg_flat - p) ** 2).sum(
            axis=1).reshape((-1, 2)) ** 0.5
        # point is on a segment if it is not on a vertex
        # and the sum length is equal to the actual segment length
        on_seg = np.logical_and(
            util.isclose(length, pair.sum(axis=1), atol=atol),
            ~util.isclose(pair, 0.0, atol=atol).any(axis=1))

        # if we have any points on the segment split it in twain
        if on_seg.any():
            # remove the original segment
            keep = np.logical_and(keep, ~on_seg)
            # split every segment that this point lies on
            for seg in segments[on_seg]:
                new_seg.append([p, seg[0]])
                new_seg.append([p, seg[1]])

    if len(new_seg) > 0:
        return np.vstack((segments[keep], new_seg))
    else:
        return segments


def unique(segments, digits=5):
    """
    Find unique line segments.

    Parameters
    ------------
    segments : (n, 2, (2|3)) float
      Line segments in space
    digits : int
      How many digits to consider when merging vertices

    Returns
    -----------
    unique : (m, 2, (2|3)) float
      Segments with duplicates merged
    """
    segments = np.asanyarray(segments, dtype=np.float64)

    # find segments as unique indexes so we can find duplicates
    inverse = grouping.unique_rows(
        segments.reshape((-1, segments.shape[2])),
        digits=digits)[1].reshape((-1, 2))

    # make sure rows are sorted
    inverse.sort(axis=1)
    # find rows that occur once
    index = grouping.unique_rows(inverse)
    # apply the unique mask
    unique = segments[index[0]]

    return unique


def overlap(origins, vectors, params):
    """
    Find the overlap of two parallel line segments.

    Parameters
    ------------
    origins : (2, 3) float
       Origin points of lines in space
    vectors : (2, 3) float
       Unit direction vectors of lines
    params : (2, 2) float
       Two (start, end) distance pairs

    Returns
    ------------
    length : float
       Overlapping length
    overlap : (n, 2, 3) float
       Line segments for overlapping distance
    """
    # copy inputs and make sure shape is correct
    origins = np.array(origins).reshape((2, 3))
    vectors = np.array(vectors).reshape((2, 3))
    params = np.array(params).reshape((2, 2))

    if tol.strict:
        # convert input to parameters before flipping
        # to make sure we didn't screw it up
        truth = parameters_to_segments(origins,
                                       vectors,
                                       params)

    # this function only works on parallel lines
    dot = np.dot(*vectors)
    assert np.isclose(np.abs(dot), 1.0, atol=.01)

    # if two vectors are reversed
    if dot < 0.0:
        # reverse direction vector
        vectors[1] *= -1.0
        # negate parameters
        params[1] *= -1.0

    if tol.strict:
        # do a check to make sure our reversal didn't
        # inadvertently give us incorrect segments
        assert np.allclose(truth,
                           parameters_to_segments(origins,
                                                  vectors,
                                                  params))

    # merge the parameter ranges
    ok, new_range = range_union(*params)

    if not ok:
        return 0.0, np.array([])

    # create the overlapping segment pairs (2, 2, 3)
    segments = np.array([o + v * new_range.reshape((-1, 1))
                         for o, v in zip(origins, vectors)])
    # get the length of the new range
    length = new_range.ptp()

    return length, segments


def range_union(a, b, digits=8):
    """
    Given a pair of ranges, merge them in to
    one range if they overlap at all

    Parameters
    --------------
    a : (2, ) float
      Start and end of a 1D interval
    b : (2, ) float
      Start and end of a 1D interval

    Returns
    --------------
    is_overlapping : bool
      Indicates if the ranges overlap at all
    new_range : (2, ) float or empty array
      The merged range from the two inputs
    """
    # make sure ranges are sorted
    a = np.sort(a).reshape(2)
    b = np.sort(b).reshape(2)

    # compare in fixed point as integers
    a_int = (a * 10**digits).astype(np.int64)
    b_int = (b * 10**digits).astype(np.int64)

    # A fully overlaps B
    if a_int[0] <= b_int[0] and a_int[1] >= b_int[1]:
        # the intersection of the two ranges is B
        return True, b

    # B fully overlaps A
    if a_int[0] >= b_int[0] and a_int[1] <= b_int[1]:
        # the intersection of the two ranges is A
        return True, a

    # A starts B ends
    # A0   B0     A1        B1
    if (a_int[0] <= b_int[0] and
        b_int[0] < a_int[1] and
            a_int[1] < b_int[1]):
        return True, np.array([b[0], a[1]])

    # B starts A ends
    # B0  A0    B1 A1
    if (b_int[0] <= a_int[0] and
        a_int[0] < b_int[1] and
            b_int[1] < a_int[1]):
        return True, np.array([a[0], b[1]])

    return False, []
