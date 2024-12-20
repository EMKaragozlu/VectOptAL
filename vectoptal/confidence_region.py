from abc import ABC, abstractmethod
from typing import Optional

import numpy as np
import cvxpy as cp
import scipy as sp

from vectoptal.order import Order
from vectoptal.utils import (
    hyperrectangle_check_intersection,
    hyperrectangle_get_vertices,
    is_pt_in_extended_polytope,
    hyperrectangle_get_region_matrix,
)


class ConfidenceRegion(ABC):
    """Abstract base class for confidence regions."""

    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    def update(self) -> None:
        pass


class RectangularConfidenceRegion(ConfidenceRegion):
    """
    Implements the axis-aligned hyperrectangular confidence region object.

    :param dim: The dimension of the hyperrectangle.
    :type dim: int
    :param lower: An array representing the lower bounds (lower-most corner) of the hyperrectangle.
    :type lower: Optional[np.ndarray]
    :param upper: An array representing the upper bounds (upper-most corner) of the hyperrectangle.
    :type upper: Optional[np.ndarray]
    :param intersect_iteratively: If True, the confidence region is updated by intersecting each
        incoming hyperrectangle with the current one.
    :type intersect_iteratively: bool
    """

    def __init__(
        self,
        dim: int,
        lower: Optional[np.ndarray] = None,
        upper: Optional[np.ndarray] = None,
        intersect_iteratively: bool = False,
    ) -> None:
        super().__init__()

        self.intersect_iteratively = intersect_iteratively

        if lower is not None and upper is not None:
            assert (
                len(lower) == dim and len(upper) == dim
            ), "Bounds must have the same dimensions as the space."
            assert np.all(lower <= upper), "Lower bound must be less than or equal to upper bound."

            self.lower = lower
            self.upper = upper
        else:
            self.lower = np.array([-1e12] * dim)  # TODO: Magic large number.
            self.upper = np.array([1e12] * dim)

    def diagonal(self) -> float:
        """
        Returns the euclidean norm of the diagonal of the hyperrectangle.

        :return: Norm of the diagonal.
        :rtype: float
        """
        return np.linalg.norm(self.upper - self.lower)

    def update(
        self, mean: np.ndarray, covariance: np.ndarray, scale: np.ndarray = np.array(1.0)
    ) -> None:
        """
        Updates the hyperrectangle using a new mean and covariance matrix. Intersects the new
        hyperrectangle with the current one if intersect_iteratively is True, otherwise uses the
        new one.

        :param mean: Mean for the new hyperrectangle.
        :type mean: np.ndarray
        :param covariance: Covariance matrix for the new hyperrectangle.
        :type covariance: np.ndarray
        :param scale: Scaling factor for the covariance matrix.
        :type scale: np.ndarray
        """
        if covariance.shape[-1] != covariance.shape[-2]:
            raise AssertionError("Covariance matrix must be square.")
        std = np.sqrt(np.diag(covariance.squeeze()))

        L = mean - std * scale
        U = mean + std * scale

        if self.intersect_iteratively:
            self.intersect(L, U)
        else:
            self.lower = L
            self.upper = U

    @property
    def center(self) -> np.ndarray:
        """
        Returns the center of the hyperrectangle.

        :return: Center of the hyperrectangle.
        :rtype: np.ndarray
        """
        return (self.lower + self.upper) / 2

    def intersect(self, lower: np.ndarray, upper: np.ndarray) -> None:
        """
        Intersect the hyperrectangle with a new hyperrectangle. If there is no intersection, then
        the new hyperrectangle is used.

        :param lower: Bottom-left corner of the new hyperrectangle.
        :type lower: np.ndarray
        :param upper: Upper-right corner of the new hyperrectangle.
        :type upper: np.ndarray
        """
        # if the two rectangles overlap
        if hyperrectangle_check_intersection(self.lower, self.upper, lower, upper):
            self.lower = np.maximum(self.lower, lower)
            self.upper = np.minimum(self.upper, upper)
        else:
            # if there is no intersection, then use the new hyperrectangle
            self.lower = lower
            self.upper = upper

    @classmethod
    def is_dominated(
        cls, order: Order, obj1: ConfidenceRegion, obj2: ConfidenceRegion, slackness: np.ndarray
    ) -> bool:
        """
        :param order: Ordering object.
        :type order: Order
        :param obj1: First hyperrectangle.
        :type obj1: ConfidenceRegion
        :param obj2: Second hyperrectangle.
        :type obj2: ConfidenceRegion
        :param slackness: Slackness parameter. Gives a bonus to the second hyperrectangle.
        :type slackness: np.ndarray
        :return: True if the first hyperrectangle is dominated by the second one, False otherwise.
        :rtype: bool
        """

        assert np.array(slackness).size == 1 or slackness.size == len(
            obj1.lower
        ), "Slackness must be a scalar or a vector of the same size as the number of dimensions."

        verts1 = hyperrectangle_get_vertices(obj1.lower, obj1.upper)
        verts2 = hyperrectangle_get_vertices(obj2.lower, obj2.upper)

        for vert1 in verts1:
            for vert2 in verts2:
                if not order.dominates(vert2 + slackness, vert1):
                    return False
        return True

    @classmethod
    def check_dominates(
        cls,
        order: Order,
        obj1: ConfidenceRegion,
        obj2: ConfidenceRegion,
        slackness: np.ndarray = np.array(0.0),
    ) -> bool:
        """
        :param order: Ordering object.
        :type order: Order
        :param obj1: First hyperrectangle.
        :type obj1: ConfidenceRegion
        :param obj2: Second hyperrectangle.
        :type obj2: ConfidenceRegion
        :param slackness: Slackness parameter. Not used, but kept for compatibility.
        :type slackness: np.ndarray
        :return: True if all corners of the first hyperrectangle are dominated by corresponding
            points in the second hyperrectangle, False otherwise.
        :rtype: bool
        """
        cone_matrix = order.ordering_cone.W

        verts1 = hyperrectangle_get_vertices(obj1.lower, obj1.upper) @ cone_matrix.transpose()
        verts2 = hyperrectangle_get_vertices(obj2.lower, obj2.upper) @ cone_matrix.transpose()

        # For every vertex of x', check if element of x+C. Return False if any vertex is not.
        for ref_point in verts1:
            if is_pt_in_extended_polytope(ref_point, verts2) is False:
                return False

        return True

    @classmethod
    def is_covered(
        cls, order: Order, obj1: ConfidenceRegion, obj2: ConfidenceRegion, slackness: np.ndarray
    ) -> bool:
        """
        :param order: Ordering object.
        :type order: Order
        :param obj1: First hyperrectangle.
        :type obj1: ConfidenceRegion
        :param obj2: Second hyperrectangle.
        :type obj2: ConfidenceRegion
        :param slackness: Slackness parameter. Gives a bonus to the second hyperrectangle.
        :type slackness: np.ndarray
        :return: True if the first hyperrectangle can be covered by the second hyperrectangle,
            False otherwise.
        :rtype: bool
        """
        cone_matrix = order.ordering_cone.W
        m = cone_matrix.shape[1]

        assert (
            np.array(slackness).size == 1 or slackness.size == m
        ), "Slackness must be a scalar or a vector of the same size as the number of dimensions."

        z_point = cp.Variable(m)
        z_point2 = cp.Variable(m)

        # Represent rectangular confidence regions as matrices
        obj1_matrix, obj1_boundary = hyperrectangle_get_region_matrix(obj1.lower, obj1.upper)
        obj2_matrix, obj2_boundary = hyperrectangle_get_region_matrix(obj2.lower, obj2.upper)

        constraints = [
            obj1_matrix @ z_point >= obj1_boundary,
            obj2_matrix @ z_point2 >= obj2_boundary,
            cone_matrix @ (z_point2 - z_point - slackness) >= 0,
        ]

        prob = cp.Problem(cp.Minimize(0), constraints=constraints)

        try:
            prob.solve()
        except cp.error.SolverError:
            prob.solve(solver=cp.SCS)

        if prob.status is None:
            return True

        condition = prob.status == "optimal"
        return condition


class EllipsoidalConfidenceRegion(ConfidenceRegion):
    """
    Implements the ellipsoidal confidence region object.

    :param dim: The dimension of the ellipsoid.
    :type dim: int
    :param center: The center of the ellipsoid.
    :type center: Optional[np.ndarray]
    :param sigma: The covariance matrix of the ellipsoid.
    :type sigma: Optional[np.ndarray]
    :param alpha: The scaling factor of the ellipsoid.
    :type alpha: Optional[float]
    """

    def __init__(
        self,
        dim: int,
        center: Optional[np.ndarray] = None,
        sigma: Optional[np.ndarray] = None,
        alpha: Optional[float] = None,
    ) -> None:
        super().__init__()

        if center is not None and sigma is not None and alpha is not None:
            self.center = center
            self.sigma = sigma
            self.alpha = alpha
        else:
            self.center = np.zeros(dim)
            self.sigma = np.eye(dim)
            self.alpha = 1.0

    def update(
        self, mean: np.ndarray, covariance: np.ndarray, scale: np.ndarray = np.array(1.0)
    ) -> None:
        """
        Updates the ellipsoid using a new mean and covariance matrix.

        :param mean: Center for the new ellipsoid.
        :type mean: np.ndarray
        :param covariance: Covariance matrix for the new ellipsoid.
        :type covariance: np.ndarray
        :param scale: Scaling factor for the new ellipsoid.
        :type scale: np.ndarray
        """

        assert covariance.shape[-1] == covariance.shape[-2], "Covariance matrix must be square."
        assert (
            np.array(scale).size == 1
        ), "Scale must be a scalar for this type of confidence region."

        self.center = mean
        self.sigma = covariance
        self.alpha = scale

    @classmethod
    def is_dominated(
        cls, order: Order, obj1: ConfidenceRegion, obj2: ConfidenceRegion, slackness: np.ndarray
    ) -> bool:
        """
        :param order: Ordering object.
        :type order: Order
        :param obj1: First ellipsoid.
        :type obj1: ConfidenceRegion
        :param obj2: Second ellipsoid.
        :type obj2: ConfidenceRegion
        :param slackness: Slackness parameter. Gives a bonus to the second ellipsoid.
        :type slackness: np.ndarray
        :return: True if the first ellipsoid is dominated by the second one, False otherwise.
        :rtype: bool
        """

        output_dim = len(obj1.center)
        cone_matrix = order.ordering_cone.W

        if np.array(slackness).size == 1:
            slackness = np.array([slackness] * cone_matrix.shape[0])
        assert (
            slackness.size == cone_matrix.shape[0]
        ), "Slackness must be a scalar or a vector of the same size as the number of constraints."

        mux = cp.Variable(output_dim)
        muy = cp.Variable(output_dim)

        # Equivalently, quad_form( A * x - b, Q ) <= 1
        # cons1 = cp.quad_form((mux - mx).T, np.linalg.inv(sigma_x)) <= alpha
        # cons2 = cp.quad_form((muy - my).T, np.linalg.inv(sigma_y)) <= alpha
        # norm( Qsqrt * ( A * x - b ) ) <= 1
        cons1 = (
            cp.norm(sp.linalg.sqrtm(np.linalg.inv(obj1.sigma)) @ (mux - obj1.center).T)
            <= obj1.alpha
        )
        cons2 = (
            cp.norm(sp.linalg.sqrtm(np.linalg.inv(obj2.sigma)) @ (muy - obj2.center).T)
            <= obj2.alpha
        )

        constraints = [cons1, cons2]

        for n in range(cone_matrix.shape[0]):
            objective = cp.Minimize(cone_matrix[n] @ (muy - mux))

            prob = cp.Problem(objective, constraints)
            try:
                prob.solve()
            except cp.error.SolverError:
                prob.solve(solver=cp.SCS)

            if prob.value < -slackness[n]:
                return False

        return True

    @classmethod
    def check_dominates(
        cls,
        order: Order,
        obj1: ConfidenceRegion,
        obj2: ConfidenceRegion,
        slackness: np.ndarray = np.array(0.0),
    ) -> bool:
        """
        Would check if first ellipsoids worst case w.r.t. the order dominates the second ellipsoids
        worst case w.r.t. the order. Currently not implemented.

        :param order: Ordering object.
        :type order: Order
        :param obj1: First ellipsoid.
        :type obj1: ConfidenceRegion
        :param obj2: Second ellipsoid.
        :type obj2: ConfidenceRegion
        :param slackness: Slackness parameter. Not used, but kept for compatibility.
        :type slackness: np.ndarray
        :return: True if first ellipsoid dominates the second ellipsoid at their worst points,
            False otherwise.
        :rtype: bool
        """
        raise NotImplementedError

    @classmethod
    def is_covered(
        cls, order: Order, obj1: ConfidenceRegion, obj2: ConfidenceRegion, slackness: np.ndarray
    ):
        """
        :param order: Ordering object.
        :type order: Order
        :param obj1: First ellipsoid.
        :type obj1: ConfidenceRegion
        :param obj2: Second ellipsoid.
        :type obj2: ConfidenceRegion
        :param slackness: Slackness parameter. Gives a bonus to the second ellipsoid.
        :type slackness: np.ndarray
        :return: True if the first ellipsoid can be covered by the second ellipsoid,
            False otherwise.
        :rtype: bool
        """
        cone_matrix = order.ordering_cone.W
        output_dim = cone_matrix.shape[1]

        assert (
            np.array(slackness).size == 1 or slackness.size == cone_matrix.shape[0]
        ), "Slackness must be a scalar or a vector of the same size as the number of constraints."

        mux = cp.Variable(output_dim)
        muy = cp.Variable(output_dim)

        # norm( Qsqrt * ( A * x - b ) ) <= 1
        cons1 = (
            cp.norm(sp.linalg.sqrtm(np.linalg.inv(obj1.sigma)) @ (mux - obj1.center).T)
            <= obj1.alpha
        )
        cons2 = (
            cp.norm(sp.linalg.sqrtm(np.linalg.inv(obj2.sigma)) @ (muy - obj2.center).T)
            <= obj2.alpha
        )
        cons3 = cone_matrix @ (muy - mux) >= slackness  # Vector of constraints.

        constraints = [cons1, cons2, cons3]

        objective = cp.Minimize(0)

        prob = cp.Problem(objective, constraints)

        try:
            prob.solve()
        except cp.error.SolverError:
            prob.solve(solver=cp.SCS)

        if "infeasible" in prob.status:
            return False
        else:
            return True


def confidence_region_is_dominated(
    order: Order, region1: ConfidenceRegion, region2: ConfidenceRegion, slackness: np.ndarray
) -> bool:
    """
    Helper function to call the is_dominated method of the appropriate confidence region object.
    Checks if the second confidence region dominates the first one at each possible pair of points.

    :param order: Ordering object.
    :type order: Order
    :param obj1: First confidence region.
    :type obj1: ConfidenceRegion
    :param obj2: Second confidence region.
    :type obj2: ConfidenceRegion
    :param slackness: Slackness parameter. Gives a bonus to the second confidence region.
    :type slackness: np.ndarray
    :return: True if the first confidence region is dominated by the second one, False otherwise.
    :rtype: bool
    """
    if isinstance(region1, RectangularConfidenceRegion):
        return RectangularConfidenceRegion.is_dominated(order, region1, region2, slackness)
    elif isinstance(region1, EllipsoidalConfidenceRegion):
        return EllipsoidalConfidenceRegion.is_dominated(order, region1, region2, slackness)
    else:
        raise NotImplementedError


def confidence_region_check_dominates(
    order: Order, region1: ConfidenceRegion, region2: ConfidenceRegion
) -> bool:
    """
    Helper function to call the check_dominates method of the appropriate confidence region object.
    Checks if all corners of the first confidence region has a corresponding point in the second
    confidence region dominated by it. Used for pessimistic comparison.

    :param order: Ordering object.
    :type order: Order
    :param obj1: First confidence region.
    :type obj1: ConfidenceRegion
    :param obj2: Second confidence region.
    :type obj2: ConfidenceRegion
    :param slackness: Slackness parameter. Not used, but kept for compatibility.
    :type slackness: np.ndarray
    :return: True if all corners of the first confidence region are dominated by corresponding
        points in the second confidence region, False otherwise.
    :rtype: bool
    """
    if isinstance(region1, RectangularConfidenceRegion):
        return RectangularConfidenceRegion.check_dominates(order, region1, region2)
    elif isinstance(region1, EllipsoidalConfidenceRegion):
        return EllipsoidalConfidenceRegion.check_dominates(order, region1, region2)
    else:
        raise NotImplementedError


def confidence_region_is_covered(
    order: Order, region1: ConfidenceRegion, region2: ConfidenceRegion, slackness: np.ndarray
) -> bool:
    """
    Helper function to call the is_covered method of the appropriate confidence region object.
    Checks if there is at least one point in the second confidence region that dominates at least
    one point from the first confidence region.

    :param order: Ordering object.
    :type order: Order
    :param obj1: First confidence region.
    :type obj1: ConfidenceRegion
    :param obj2: Second confidence region.
    :type obj2: ConfidenceRegion
    :param slackness: Slackness parameter. Gives a bonus to the second confidence region.
    :type slackness: np.ndarray
    :return: True if the first confidence region can be covered by the second confidence region,
        False otherwise.
    :rtype: bool
    """
    # TODO: is_covered may be a bad name. Maybe is_not_dominated?
    if isinstance(region1, RectangularConfidenceRegion):
        return RectangularConfidenceRegion.is_covered(order, region1, region2, slackness)
    elif isinstance(region1, EllipsoidalConfidenceRegion):
        return EllipsoidalConfidenceRegion.is_covered(order, region1, region2, slackness)
    else:
        raise NotImplementedError
