from unittest import TestCase

import numpy as np

from vectoptal.utils.seed import SEED
from vectoptal.order import ComponentwiseOrder
from vectoptal.algorithms import DecoupledGP
from vectoptal.datasets import get_dataset_instance
from vectoptal.utils.evaluate import calculate_epsilonF1_score


class TestDecoupledGP(TestCase):
    """Test the DecoupledGP class."""

    def setUp(self):
        """A basic setup for the model."""
        np.random.seed(SEED)

        self.epsilon = 0.1
        self.delta = 0.1
        self.dataset_name = "Test"
        self.order = ComponentwiseOrder(2)
        self.dataset_cardinality = get_dataset_instance(self.dataset_name)._cardinality
        self.noise_var = 0.00001
        self.costs = [1.0, 1.5]
        self.cost_budget = 64
        self.algorithm = DecoupledGP(
            dataset_name=self.dataset_name,
            order=self.order,
            noise_var=self.noise_var,
            costs=self.costs,
            cost_budget=self.cost_budget,
        )

    def test_evaluating(self):
        """Test the evaluating method."""
        sample_test = self.algorithm.sample_count
        self.algorithm.evaluating()
        self.assertTrue(self.algorithm.sample_count > sample_test)

    def test_whole_class(self):
        """Test the whole class by running it until the end end checking its score."""
        while True:
            is_done = self.algorithm.run_one_step()
            if is_done:
                break

        pareto_indices = self.algorithm.P
        dataset = get_dataset_instance(self.dataset_name)
        eps_f1 = calculate_epsilonF1_score(
            dataset,
            self.order,
            self.order.get_pareto_set(dataset.out_data),
            list(pareto_indices),
            self.epsilon,
        )
        self.assertTrue(eps_f1 > 0.9)  # Even though algorithm is not using of epsilon.
        self.assertLess(self.algorithm.total_cost, self.cost_budget + max(self.costs))
        self.assertLessEqual(self.algorithm.total_cost, self.algorithm.round * max(self.costs))
        self.assertGreaterEqual(self.algorithm.total_cost, self.algorithm.round * min(self.costs))

    def test_run_one_step(self):
        """Test the run_one_step method."""
        num_rounds = 10
        alg_done = False
        for i in range(num_rounds):  # Run for 10 rounds, it should be enough.
            if not alg_done and i <= 3:  # Save the state at round 3 at the latest.
                cost_test = self.algorithm.total_cost
            alg_done = self.algorithm.run_one_step()

        cost = self.algorithm.total_cost

        self.assertTrue(num_rounds >= self.algorithm.round)
        self.assertTrue(cost_test < cost)
