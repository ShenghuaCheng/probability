# Copyright 2019 The TensorFlow Probability Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================

"""Double-sided Maxwell distribution class."""


from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import tensorflow.compat.v2 as tf

from tensorflow_probability.python import math as tfp_math
from tensorflow_probability.python.distributions import distribution
from tensorflow_probability.python.internal import assert_util
from tensorflow_probability.python.internal import dtype_util
from tensorflow_probability.python.internal import prefer_static
from tensorflow_probability.python.internal import reparameterization
from tensorflow_probability.python.internal import tensor_util
from tensorflow_probability.python.util.seed_stream import SeedStream


__all__ = [
    'DoublesidedMaxwell',
]


class DoublesidedMaxwell(distribution.Distribution):
  r"""Double-sided Maxwell distribution.

  This distribution is useful to compute measure valued derivatives for Gaussian
  distributions. See [Mohamed et al. 2019][1] for more details.

  #### Mathematical details

  The double-sided Maxwell distribution generalizes the Maxwell distribution to
  the entire real line.

  ```none
  pdf(x; mu, sigma) = 1/(sigma*sqrt(2*pi)) * ((x-mu)/sigma)^2
                     * exp(-0.5 ((x-mu)/sigma)^2)
  ```

  where `loc = mu` and `scale = sigma`.

  The DoublesidedMaxwell distribution is a member of the
  [location-scale family](https://en.wikipedia.org/wiki/Location-scale_family),
  i.e., it can be constructed as,

  ```none
  X ~ DoublesidedMaxwell(loc=0, scale=1)
  Y = loc + scale * X
  ```

  The double-sided Maxwell is a symmetric distribution that extends the
  one-sided maxwell from R+ to the entire real line. Their densities are
  therefore the same up to a factor of 0.5.

  It has several methods for generating random variates from it. The version
  here uses 3 Gaussian variates and a uniform variate to generate the samples
  The sampling path is:
  mu + sigma* sgn(U-0.5)* sqrt(X^2 + Y^2 + Z^2) U~Unif; X,Y,Z ~N(0,1)

  In the sampling process above, the random variates generated by
  sqrt(X^2 + Y^2 + Z^2) are samples from the one-sided Maxwell
  (or Maxwell-Boltzmann) distribution.

  #### Examples

  ```python
  import tensorflow_probability as tfp
  tfd = tfp.distributions

  # Define a single scalar DoublesidedMaxwell distribution.
  dist = tfd.DoublesidedMaxwell(loc=0., scale=3.)

  # Evaluate the cdf at 1, returning a scalar.
  dist.cdf(1.)

  # Define a batch of two scalar valued DoublesidedMaxwells.
  # The first has mean 1 and standard deviation 11, the second 2 and 22.
  dist = tfd.DoublesidedMaxwell(loc=[1, 2.], scale=[11, 22.])

  # Evaluate the pdf of the first distribution on 0, and the second on 1.5,
  # returning a length two tensor.
  dist.prob([0, 1.5])

  # Get 3 samples, returning a 3 x 2 tensor.
  dist.sample([3])
  ```

  #### References
   [1]: Mohamed, et all, "Monte Carlo Gradient Estimation in Machine Learning.",
      2019 https://arxiv.org/abs/1906.10652
   [2] B. Heidergott, et all "Sensitivity estimation for Gaussian
      systems", 2008.  European Journal of Operational Research,
      vol. 187, pp193-207.
   [3] G. Pflug. "Optimization of Stochastic Models: The Interface Between
    Simulation and Optimization", 2002. Chp. 4.2, pg 247.
  """

  def __init__(self,
               loc,
               scale,
               validate_args=False,
               allow_nan_stats=True,
               name='doublesided_maxwell'):
    """Construct a Double-sided Maxwell distribution with `scale`.

    Args:
      loc: Floating point tensor; location of the distribution
      scale: Floating point tensor; the scales of the distribution
        Must contain only positive values.
      validate_args: Python `bool`, default `False`. When `True` distribution
        parameters are checked for validity despite possibly degrading runtime
        performance. When `False` invalid inputs may silently render incorrect
        outputs. Default value: `False` (i.e., do not validate args).
      allow_nan_stats: Python `bool`, default `True`. When `True`, statistics
        (e.g., mean, mode, variance) use the value "`NaN`" to indicate the
        result is undefined. When `False`, an exception is raised if one or more
        of the statistic's batch members are undefined.
        Default value: `True`.
      name: Python `str` name prefixed to Ops created by this class.
        Default value: 'doublesided_maxwell'.
    """
    parameters = dict(locals())
    with tf.name_scope(name) as name:
      dtype = dtype_util.common_dtype([loc, scale], dtype_hint=tf.float32)

      self._loc = tensor_util.convert_nonref_to_tensor(
          value=loc, name='loc', dtype=dtype)
      self._scale = tensor_util.convert_nonref_to_tensor(
          value=scale, name='scale', dtype=dtype)

    super(DoublesidedMaxwell, self).__init__(
        dtype=self._scale.dtype,
        reparameterization_type=reparameterization.FULLY_REPARAMETERIZED,
        validate_args=validate_args,
        allow_nan_stats=allow_nan_stats,
        parameters=parameters,
        name=name)

  @staticmethod
  def _param_shapes(sample_shape):
    return dict(
        zip(('loc', 'scale'),
            ([tf.convert_to_tensor(value=sample_shape, dtype=tf.int32)] * 2)))

  @classmethod
  def _params_event_ndims(cls):
    return dict(loc=0, scale=0)

  @property
  def loc(self):
    """Distribution parameter for the mean."""
    return self._loc

  @property
  def scale(self):
    """Distribution parameter for the scale."""
    return self._scale

  def _batch_shape_tensor(self, loc=None, scale=None):
    return tf.broadcast_dynamic_shape(
        tf.shape(self.loc if loc is None else loc),
        tf.shape(self.scale if scale is None else scale))

  def _batch_shape(self):
    return tf.broadcast_static_shape(self.loc.shape, self.scale.shape)

  def _event_shape_tensor(self):
    return tf.constant([], dtype=tf.int32)

  def _event_shape(self):
    return tf.TensorShape([])

  def _log_prob(self, x):
    scale = tf.convert_to_tensor(self.scale)
    z = self._z(x, scale=scale)

    square_z = tf.square(z)
    log_unnormalized_prob = -0.5 * square_z + tf.math.log(square_z)
    log_normalization = 0.5 * np.log(2. * np.pi) + tf.math.log(scale)
    return log_unnormalized_prob - log_normalization

  def _z(self, x, scale=None):
    """Standardize input `x` to a standard maxwell."""
    with tf.name_scope('standardize'):
      return (x - self.loc) / (self.scale if scale is None else scale)

  def _sample_n(self, n, seed=None):
    # Generate samples using:
    # mu + sigma* sgn(U-0.5)* sqrt(X^2 + Y^2 + Z^2) U~Unif; X,Y,Z ~N(0,1)
    seed = SeedStream(seed, salt='DoublesidedMaxwell')

    loc = tf.convert_to_tensor(self.loc)
    scale = tf.convert_to_tensor(self.scale)
    shape = prefer_static.pad(
        self._batch_shape_tensor(loc=loc, scale=scale),
        paddings=[[1, 0]], constant_values=n)

    # Generate one-sided Maxwell variables by using 3 Gaussian variates
    norm_rvs = tf.random.normal(
        shape=prefer_static.pad(shape, paddings=[[0, 1]], constant_values=3),
        dtype=self.dtype,
        seed=seed())
    maxwell_rvs = tf.norm(norm_rvs, axis=-1)

    # Generate random signs for the symmetric variates.
    random_sign = tfp_math.random_rademacher(shape, seed=seed())
    sampled = random_sign * maxwell_rvs * scale + loc
    return sampled

  def _mean(self):
    return self.loc * tf.ones_like(self.scale)

  def _stddev(self):
    return np.sqrt(3.) * self.scale * tf.ones_like(self.loc)

  def _parameter_control_dependencies(self, is_init):
    assertions = []

    if is_init:
      try:
        self._batch_shape()
      except ValueError:
        raise ValueError(
            'Arguments `loc` and `scale` must have compatible shapes; '
            'loc.shape={}, scale.shape={}.'.format(
                self.loc.shape, self.scale.shape))
      # We don't bother checking the shapes in the dynamic case because
      # all member functions access both arguments anyway.

    if not self.validate_args:
      assert not assertions  # Should never happen.
      return []

    if is_init != tensor_util.is_ref(self.scale):
      assertions.append(assert_util.assert_positive(
          self.scale, message='Argument `scale` must be positive.'))

    return assertions
