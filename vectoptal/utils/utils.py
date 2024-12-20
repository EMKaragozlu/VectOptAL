import itertools

from typing import Union, Iterable

import torch
import numpy as np
import cvxpy as cp
import scipy.special
from scipy.stats.qmc import Sobol
from sklearn.metrics.pairwise import euclidean_distances


def set_seed(seed: int) -> None:
    """
    This function sets the seed for both NumPy and PyTorch random number generators.

    :param seed: The seed value to set for the random number generators.
    :type seed: int
    """
    np.random.seed(seed)
    torch.random.manual_seed(seed)


def get_2d_w(cone_angle: float) -> np.ndarray:
    """
    This function generates a 2D cone matrix W with boundaries at an angle cone_angle and
    symmetric around `y=x`.

    :param cone_angle: The angle of the cone in degrees.
    :type cone_angle: float
    :return: A 2x2 numpy array where each row is a normalized normal vector.
    :rtype: numpy.ndarray
    """
    angle_radian = (cone_angle / 180) * np.pi
    if cone_angle <= 90:
        W_1 = np.array([-np.tan(np.pi / 4 - angle_radian / 2), 1])
        W_2 = np.array([+np.tan(np.pi / 4 + angle_radian / 2), -1])
    else:
        W_1 = np.array([-np.tan(np.pi / 4 - angle_radian / 2), 1])
        W_2 = np.array([-np.tan(np.pi / 4 + angle_radian / 2), 1])
    W_1 = W_1 / np.linalg.norm(W_1)
    W_2 = W_2 / np.linalg.norm(W_2)
    W = np.vstack((W_1, W_2))

    return W


def get_alpha(rind: int, W: np.ndarray) -> np.ndarray:
    """
    Compute alpha_rind for row rind of W.

    :param rind: The row index of W for which to compute alpha.
    :type rind: int
    :param W: The cone matrix.
    :type W: numpy.ndarray
    :return: The computed alpha value for the specified row of W.
    :rtype: numpy.ndarray
    """
    m = W.shape[0] + 1  # number of constraints
    D = W.shape[1]
    f = -W[rind, :]
    A = []
    b = []
    c = []
    d = []
    for i in range(W.shape[0]):
        A.append(np.zeros((1, D)))
        b.append(np.zeros(1))
        c.append(W[i, :])
        d.append(np.zeros(1))

    A.append(np.eye(D))
    b.append(np.zeros(D))
    c.append(np.zeros(D))
    d.append(np.ones(1))

    # Define and solve the CVXPY problem.
    x = cp.Variable(D)
    # We use cp.SOC(t, x) to create the SOC constraint ||x||_2 <= t.
    soc_constraints = [cp.SOC(c[i].T @ x + d[i], A[i] @ x + b[i]) for i in range(m)]
    prob = cp.Problem(cp.Minimize(f.T @ x), soc_constraints)
    prob.solve()

    return -prob.value


def get_alpha_vec(W: np.ndarray) -> np.ndarray:
    """
    The alpha vector is computed using the `get_alpha` function for each row index.

    :param W: The cone matrix.
    :type W: numpy.ndarray
    :return: An ndarray of shape (n_constraint, 1) representing the computed alpha vector.
    :rtype: numpy.ndarray
    """
    alpha_vec = np.zeros((W.shape[0], 1))
    for i in range(W.shape[0]):
        alpha_vec[i] = get_alpha(i, W)
    return alpha_vec


def get_closest_indices_from_points(
    pts_to_find: Iterable,
    pts_to_check: Iterable,
    return_distances: bool = False,
    squared: bool = False,
) -> Union[np.ndarray, tuple[np.ndarray, np.ndarray]]:
    """
    This method calculates the closest indices in `pts_to_check` for each point in `pts_to_find`
    using Euclidean distances. Optionally, it can return the distances as well.

    :param pts_to_find: An array of points for which the closest indices need to be found.
    :type pts_to_find: np.ndarray
    :param pts_to_check: An array of points to check against.
    :type pts_to_check: np.ndarray
    :param return_distances: If True, the method also returns the distances to the closest points.
    :type return_distances: bool, optional
    :param squared: If True, the squared Euclidean distances are used and returned.
    :type squared: bool, optional
    :return: An array of the closest indices, or a tuple containing the closest indices and the
        distances.
    :rtype: Union[np.ndarray, tuple[np.ndarray, np.ndarray]]
    """
    if len(pts_to_find) == 0 or len(pts_to_check) == 0:
        return []

    distances = euclidean_distances(pts_to_find, pts_to_check, squared=squared)
    x_inds = np.argmin(distances, axis=1)
    if return_distances:
        return x_inds.astype(int), np.min(distances, axis=1)
    return x_inds.astype(int)


def get_noisy_evaluations_chol(means: np.ndarray, cholesky_cov: np.ndarray) -> np.ndarray:
    """
    This method generates noisy samples from a multivariate normal distribution using the provided
    means and Cholesky decomposition of the covariance matrix. It is used for vectorized
    multivariate normal sampling.

    :param means: An array of mean values for the multivariate normal distribution.
    :type means: np.ndarray
    :param cholesky_cov: The Cholesky decomposition of the covariance matrix, this is a 2D array.
    :type cholesky_cov: np.ndarray
    :return: An array of noisy samples.
    :rtype: np.ndarray
    """
    assert cholesky_cov.ndim == 2, means.shape[1] == cholesky_cov.shape[1]
    n, d = means.shape[0], len(cholesky_cov)
    X = np.random.normal(size=(n, d))
    complicated_X = np.dot(X, cholesky_cov)

    noisy_samples = means + complicated_X

    return noisy_samples


def generate_sobol_samples(dim: int, n: int) -> np.ndarray:
    """
    This method generates `n` samples from a Sobol sequence of dimension `dim`. `n` should be a
    power of 2 in order to generate a balanced sequence.

    :param dim: The dimension of the Sobol sequence.
    :type dim: int
    :param n: The number of samples to generate.
    :type n: int
    :return: An array of Sobol sequence samples.
    :rtype: np.ndarray
    """
    sampler = Sobol(dim, scramble=True)
    samples = sampler.random(n)

    return samples


def get_smallmij(vi: np.ndarray, vj: np.ndarray, W: np.ndarray, alpha_vec: np.ndarray) -> float:
    """
    This method calculates the m(i,j) value, which is used to measure the difference between two
    designs `vi` and `vj` based on the constraint matrix `W` and the alpha vector `alpha_vec`.

    :param vi: A D-vector representing the design vector i.
    :type vi: np.ndarray
    :param vj: A D-vector representing the design vector j.
    :type vj: np.ndarray
    :param W: A (n_constraint, D) ndarray representing the constraint matrix.
    :type W: np.ndarray
    :param alpha_vec: A (n_constraint, 1) ndarray representing the alphas of W.
    :type alpha_vec: np.ndarray
    :return: The computed m(i,j) value.
    :rtype: float
    """
    prod = np.matmul(W, vj - vi)
    prod[prod < 0] = 0
    smallmij = (prod / alpha_vec).min()

    return smallmij


def get_delta(mu: np.ndarray, W: np.ndarray, alpha_vec: np.ndarray) -> np.ndarray:
    """
    This method computes Delta^*_i gap value for each point in the input array `mu`. Delta^*_i is
    calculated based on the provided constraint matrix `W` and the alpha vector `alpha_vec`.

    :param mu: An array of shape (n_points, D) representing the points.
    :type mu: np.ndarray
    :param W: An array of shape (n_constraint, D) representing the constraint matrix.
    :type W: np.ndarray
    :param alpha_vec: An array of shape (n_constraint, 1) representing the alphas of W.
    :type alpha_vec: np.ndarray
    :return: An array of shape (n_points, 1) containing Delta^*_i for each point.
    :rtype: np.ndarray
    """
    num_points = mu.shape[0]
    delta_values = np.zeros(num_points)
    for i in range(num_points):
        for j in range(num_points):
            vi = mu[i, :]
            vj = mu[j, :]
            mij = get_smallmij(vi, vj, W, alpha_vec)
            delta_values[i] = max(delta_values[i], mij)

    return delta_values.reshape(-1, 1)


def get_uncovered_set(p_opt_miss, p_opt_hat, mu, eps, W):
    """
    Check if vi is eps covered by vj for cone matrix W.

    :param p_opt_hat: ndarray of indices of designs in returned Pareto set
    :param p_opt_miss: ndarray of indices of Pareto optimal points not in p_opt_hat
    :mu: An (n_points,D) mean reward matrix
    :param eps: float
    :param W: An (n_constraint,D) ndarray
    :return: ndarray of indices of points in p_opt_miss that are not epsilon covered
    """
    uncovered_set = []

    for i in p_opt_miss:
        for j in p_opt_hat:
            if is_covered(mu[i, :], mu[j, :], eps, W):
                break
        else:
            uncovered_set.append(i)

    return uncovered_set


def get_uncovered_size(p_opt_miss, p_opt_hat, eps, W) -> int:
    count = 0

    for i, ip in enumerate(p_opt_miss):
        for jp in p_opt_hat:
            if is_covered(ip, jp, eps, W):
                break
        else:
            count += 1

    return count


def is_covered(vi, vj, eps, W):
    """
    Check if vi is eps covered by vj for cone matrix W.
    :param vi, vj: (D,1) ndarrays
    :param W: An (n_constraint,D) ndarray
    :param eps: float
    :return: Boolean.
    """
    x = cp.Variable(W.shape[1])

    constraints = [
        W @ x >= 0,
        cp.norm(x + (vi - vj)) <= eps,
        W @ (x + (vi - vj)) >= 0,
    ]

    prob = cp.Problem(cp.Minimize(0), constraints)
    prob.solve()

    return x.value is not None


def hyperrectangle_check_intersection(
    lower1: np.ndarray, upper1: np.ndarray, lower2: np.ndarray, upper2: np.ndarray
) -> bool:
    """
    This function takes the lower and upper bounds of two hyperrectangles and
    determines if they intersect. A hyperrectangle is defined by its lower and
    upper points in an n-dimensional space.

    :param lower1: Lower bounds of the first hyperrectangle.
    :type lower1: np.ndarray
    :param upper1: Upper bounds of the first hyperrectangle.
    :type upper1: np.ndarray
    :param lower2: Lower bounds of the second hyperrectangle.
    :type lower2: np.ndarray
    :param upper2: Upper bounds of the second hyperrectangle.
    :type upper2: np.ndarray
    :return: True if the hyperrectangles intersect, False otherwise.
    :rtype: bool
    """
    if np.any(lower1 >= upper2) or np.any(upper1 <= lower2):
        return False

    return True


def hyperrectangle_get_vertices(lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    """
    This method takes an n-dimensional lower bound array and an n-dimensional upper bound array,
    and constructs the vertices of the corresponding hyperrectangle by combining these bounds.

    :param lower: An array of shape (n,) representing the lower bounds of the hyperrectangle.
    :type lower: np.ndarray
    :param upper: An array of shape (n,) representing the upper bounds of the hyperrectangle.
    :type upper: np.ndarray
    :return: An array of shape (2^n, n) containing the vertices of the hyperrectangle.
    :rtype: np.ndarray
    """
    a = [[l1, l2] for l1, l2 in zip(lower, upper)]
    vertex_list = [element for element in itertools.product(*a)]
    return np.array(vertex_list)


def hyperrectangle_get_region_matrix(
    lower: np.ndarray, upper: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """
    This method takes an n-dimensional lower bound array and an n-dimensional upper bound array,
    and constructs a matrix form for the hyperrectangle. For all points `x` inside the region of
    the hyperrectangle, the condition `region_matrix @ x >= region_boundary` holds true.

    :param lower: An array of shape (n,) representing the lower bounds of the hyperrectangle.
    :type lower: np.ndarray
    :param upper: An array of shape (n,) representing the upper bounds of the hyperrectangle.
    :type upper: np.ndarray
    :return: A tuple containing two elements:
        - region_matrix: An array of shape (2*n, n) representing the matrix form of the
        hyperrectangle.
        - region_boundary: An array of shape (2*n,) representing the boundary conditions of the
        hyperrectangle.
    :rtype: tuple[np.ndarray, np.ndarray]
    """
    dim = len(lower)
    region_matrix = np.vstack((np.eye(dim), -np.eye(dim)))
    region_boundary = np.hstack((np.array(lower), -np.array(upper)))

    return region_matrix, region_boundary


def is_pt_in_extended_polytope(pt, polytope, invert_extension=False):
    dim = polytope.shape[1]

    if invert_extension:

        def comp_func(x, y):
            return x >= y

    else:

        def comp_func(x, y):
            return x <= y

    # Vertex is trivially an element
    for vert in polytope:
        if comp_func(vert, pt).all():
            return True

    # Check intersections with polytope. If any intersection is dominated, then an element.
    for dim_i in range(dim):
        edges_of_interest = np.empty((0, 2, dim), dtype=np.float64)
        for vert_i, vert1 in enumerate(polytope):
            for vert_j, vert2 in enumerate(polytope):
                if vert_i == vert_j:
                    continue

                if vert1[dim_i] <= pt[dim_i] and pt[dim_i] <= vert2[dim_i]:
                    edges_of_interest = np.vstack(
                        (edges_of_interest, np.expand_dims(np.vstack((vert1, vert2)), axis=0))
                    )

        for edge in edges_of_interest:
            intersection = line_seg_pt_intersect_at_dim(edge[0], edge[1], pt, dim_i)
            if intersection is not None and comp_func(intersection, pt).all():
                # Vertex is an element due to the intersection point
                return True

    return False


def line_seg_pt_intersect_at_dim(P1, P2, target_pt, target_dim):
    t = (target_pt[target_dim] - P1[target_dim]) / (P2[target_dim] - P1[target_dim])

    if t < 0 or t > 1:
        # No intersection
        return None

    point_on_line = P1 + t * (P2 - P1)
    return point_on_line


def binary_entropy(x):
    return -(scipy.special.xlogy(x, x) + scipy.special.xlog1py(1 - x, -x)) / np.log(2)
