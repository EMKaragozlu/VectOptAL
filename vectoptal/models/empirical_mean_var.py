from typing import Iterable

import numpy as np

from vectoptal.models import Model


class EmpiricalMeanVarModel(Model):
    def __init__(
        self,
        input_dim,
        output_dim,
        noise_var,
        design_count,
        track_means: bool = True,
        track_variances: bool = True,
    ):
        super().__init__()

        self.noise_var = noise_var
        self.input_dim = input_dim
        self.output_dim = output_dim
        self.design_count = design_count

        self.track_means = track_means
        self.track_variances = track_variances

        # Data containers.
        self.clear_data()

    def add_sample(self, indices: Iterable[int], Y_t: np.ndarray):
        """
        Add new samples for specified design indices.

        :param indices: Represents the indices of designs to which the samples belong.
        :type indices: Iterable[int]
        :param Y_t: A N-by-output_dim array containing the new samples to be added.
        :type Y_t: np.ndarray
        """
        assert len(indices) == len(Y_t), "Number of samples is ambiguous."
        assert max(indices) < self.design_count, "Design index out of bounds."

        for idx, y in zip(indices, Y_t):
            self.design_samples[idx] = np.concatenate(
                [self.design_samples[idx], y.reshape(-1, self.output_dim)], axis=0
            )

    def clear_data(self):
        """
        This method generates/clears the sample containers.
        """
        self.design_samples = [np.empty((0, self.output_dim)) for _ in range(self.design_count)]

    def update(self):
        """
        This method calculates and updates the means and variances of the design samples based on
        the current data. If `track_means` is enabled, it updates the `means` attribute with the
        mean of each design sample. If `track_variances` is enabled, it updates the `variances`
        attribute with the variance of each design sample.
        """
        if self.track_means:
            self.means = np.array(
                [
                    np.mean(design, axis=0) if len(design) > 0 else np.zeros(self.output_dim)
                    for design in self.design_samples
                ]
            )
        else:
            self.means = None

        if self.track_variances:
            self.variances = np.array(
                [
                    (
                        np.diag(np.var(design, axis=0))
                        if len(design) > 1
                        else np.eye(self.output_dim) * self.noise_var
                    )
                    for design in self.design_samples
                ]
            )
        else:
            self.variances = None

    def train(self):
        pass

    def predict(self, test_X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """
        This method takes test inputs and returns the predicted means and variances based on the
        tracked data. If `track_means` is enabled, it returns the corresponding means for the test
        inputs. If `track_variances` is enabled, it returns the corresponding variances for the
        test inputs.

        :param test_X: The test inputs for which predictions are to be made. The last column of
        `test_X` should contain indices.
        :type test_X: np.ndarray
        :return: A tuple containing two numpy arrays: the predicted means and variances.
        :rtype: tuple[np.ndarray, np.ndarray]
        """
        assert (
            test_X.shape[1] == self.input_dim + 1
        ), "Test data needs to have an additional column for indices."

        indices = test_X[..., -1].astype(int)
        if self.track_means:
            means = self.means[indices]
        else:
            means = np.zeros((len(indices), self.output_dim))

        if self.track_variances:
            variances = self.variances[indices]
        else:
            variances = np.array([np.eye(self.output_dim) for _ in indices])

        return means, variances
