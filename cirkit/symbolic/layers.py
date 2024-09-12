from abc import ABC
from enum import IntEnum, auto
from typing import Any, Dict, Optional, Tuple, cast

from cirkit.symbolic.initializers import NormalInitializer
from cirkit.symbolic.parameters import (
    Parameter,
    ParameterFactory,
    ScaledSigmoidParameter,
    TensorParameter,
)
from cirkit.utils.scope import Scope


class LayerOperator(IntEnum):
    """The avaliable symbolic operators defined over layers."""

    INTEGRATION = auto()
    """The integration operator defined over input layers."""
    DIFFERENTIATION = auto()
    """The differentiation operator defined over layers."""
    MULTIPLICATION = auto()
    """The multiplication operator defined over layers."""
    CONJUGATION = auto()
    """The conjugation opereator defined over sum and input layers."""


class Layer(ABC):
    """The symbolic layer class. A symbolic layer consists of useful metadata of input, product
    and sum layers. A layer that specializes this class must specify two property methods:
        1. config(self) -> Dict[str, Any]: A dictionary mapping the non-parameter arguments to
            the ```__init__``` method to the corresponding values, e.g., the arity.
        2. params(self) -> Dict[str, Parameter]: A dictionary mapping the parameter arguments
            the ```__init__``` method to the corresponding symbolic parameter, e.g., the mean and
            standard deviations symbolic parameters in a
            [GaussianLayer][cirkit.symbolic.layers.GaussianLayer].
    """

    def __init__(
        self,
        scope: Scope,
        num_input_units: int,
        num_output_units: int,
        arity: int = 1,
    ):
        """Initializes a symbolic layer.

        Args:
            scope: The variables scope of the layer.
            num_input_units: The number of units in each input layer.
            num_output_units: The number of output units, i.e., the number of computational units
                in this layer.
            arity: The arity of the layer, i.e., the number of input layers to this layer.
        """
        self.scope = scope
        self.num_input_units = num_input_units
        self.num_output_units = num_output_units
        self.arity = arity

    @property
    def config(self) -> Dict[str, Any]:
        """Retrieves the configuartion of the layer, i.e., a dictionary mapping hyperparameters
        of the layer to their values. The hyperparameter names must match the argument names in
        the ```__init__``` method.

        Returns:
            Dict[str, Any]: A dictionary from hyperparameter names to their value.
        """
        return {
            "scope": self.scope,
            "num_input_units": self.num_input_units,
            "num_output_units": self.num_output_units,
            "arity": self.arity,
        }

    @property
    def params(self) -> Dict[str, Parameter]:
        """Retrieve the symbolic parameters of the layer, i.e., a dictionary mapping the names of
        the symbolic parameters to the actual symbolic parameter instance. The parameter names must
        match the argument names in the```__init__``` method.

        Returns:
            Dict[str, Parameter]: A dictionary from parameter names to the corresponding symbolic
                parameter instance.
        """
        return {}


class InputLayer(Layer):
    """The symbolic input layer class."""

    def __init__(self, scope: Scope, num_output_units: int, num_channels: int = 1):
        """Initializes a symbolic input layer.

        Args:
            scope: The variables scope of the layer.
            num_output_units: The number of input units in the layer.
            num_channels: The number of channels for each variable in the scope. Defaults to 1.
        """
        super().__init__(scope, len(scope), num_output_units, num_channels)

    @property
    def num_variables(self) -> int:
        """The number of variables modelled by the input layer.

        Returns:
            int: The number of variables in the scope.
        """
        return self.num_input_units

    @property
    def num_channels(self) -> int:
        """The number of channels per variable modelled by the input layer.

        Returns:
            int: The number of channels per variable.
        """
        return self.arity

    @property
    def config(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "num_output_units": self.num_output_units,
            "num_channels": self.num_channels,
        }


class CategoricalLayer(InputLayer):
    def __init__(
        self,
        scope: Scope,
        num_output_units: int,
        num_channels: int,
        num_categories: int,
        logits: Optional[Parameter] = None,
        probs: Optional[Parameter] = None,
        logits_factory: Optional[ParameterFactory] = None,
        probs_factory: Optional[ParameterFactory] = None,
    ):
        if len(scope) != 1:
            raise ValueError("The Categorical layer encodes a univariate distribution")
        if logits is not None and probs is not None:
            raise ValueError("At most one between 'logits' and 'probs' can be specified")
        if logits_factory is not None and probs_factory is not None:
            raise ValueError(
                "At most one between 'logits_factory' and 'probs_factory' can be specified"
            )
        if num_categories < 2:
            raise ValueError("At least two categories must be specified")
        super().__init__(scope, num_output_units, num_channels)
        self.num_categories = num_categories
        if logits is None and probs is None:
            if logits_factory is not None:
                logits = logits_factory(self.probs_logits_shape)
            elif probs_factory is not None:
                probs = probs_factory(self.probs_logits_shape)
            else:
                logits = Parameter.from_leaf(
                    TensorParameter(*self.probs_logits_shape, initializer=NormalInitializer())
                )
        if logits is not None and logits.shape != self.probs_logits_shape:
            raise ValueError(
                f"Expected parameter shape {self.probs_logits_shape}, found {logits.shape}"
            )
        if probs is not None and probs.shape != self.probs_logits_shape:
            raise ValueError(
                f"Expected parameter shape {self.probs_logits_shape}, found {probs.shape}"
            )
        self.probs = probs
        self.logits = logits

    @property
    def probs_logits_shape(self) -> Tuple[int, ...]:
        return self.num_output_units, self.num_channels, self.num_categories

    @property
    def config(self) -> dict:
        config = super().config
        config.update(num_categories=self.num_categories)
        return config

    @property
    def params(self) -> Dict[str, Parameter]:
        if self.logits is None:
            return {"probs": self.probs}
        return {"logits": self.logits}


class GaussianLayer(InputLayer):
    def __init__(
        self,
        scope: Scope,
        num_output_units: int,
        num_channels: int,
        mean: Optional[Parameter] = None,
        stddev: Optional[Parameter] = None,
        log_partition: Optional[Parameter] = None,
        mean_factory: Optional[ParameterFactory] = None,
        stddev_factory: Optional[ParameterFactory] = None,
    ):
        if len(scope) != 1:
            raise ValueError("The Gaussian layer encodes a univariate distribution")
        super().__init__(scope, num_output_units, num_channels)
        if mean is None:
            if mean_factory is None:
                mean = Parameter.from_leaf(
                    TensorParameter(*self.mean_stddev_shape, initializer=NormalInitializer())
                )
            else:
                mean = mean_factory(self.mean_stddev_shape)
        if stddev is None:
            if stddev_factory is None:
                stddev = Parameter.from_unary(
                    ScaledSigmoidParameter(self.mean_stddev_shape, vmin=1e-5, vmax=1.0),
                    TensorParameter(*self.mean_stddev_shape, initializer=NormalInitializer()),
                )
            else:
                stddev = stddev_factory(self.mean_stddev_shape)
        if mean.shape != self.mean_stddev_shape:
            raise ValueError(
                f"Expected parameter shape {self.mean_stddev_shape}, found {mean.shape}"
            )
        if stddev.shape != self.mean_stddev_shape:
            raise ValueError(
                f"Expected parameter shape {self.mean_stddev_shape}, found {stddev.shape}"
            )
        if log_partition is not None and log_partition.shape != self.log_partition_shape:
            raise ValueError(
                f"Expected parameter shape {self.log_partition_shape}, found {log_partition.shape}"
            )
        self.mean = mean
        self.stddev = stddev
        self.log_partition = log_partition

    @property
    def mean_stddev_shape(self) -> Tuple[int, ...]:
        return self.num_output_units, self.num_channels

    @property
    def log_partition_shape(self) -> Tuple[int, ...]:
        return self.num_output_units, self.num_channels

    @property
    def params(self) -> Dict[str, Parameter]:
        params = {"mean": self.mean, "stddev": self.stddev}
        if self.log_partition is not None:
            params.update(log_partition=self.log_partition)
        return params


class LogPartitionLayer(InputLayer):
    def __init__(self, scope: Scope, num_output_units: int, num_channels: int, value: Parameter):
        super().__init__(scope, num_output_units, num_channels)
        if value.shape != self.value_shape:
            raise ValueError(f"Expected parameter shape {self.value_shape}, found {value.shape}")
        self.value = value

    @property
    def value_shape(self) -> Tuple[int, ...]:
        return (self.num_output_units,)

    @property
    def params(self) -> Dict[str, Parameter]:
        params = super().params
        params.update(value=self.value)
        return params


class ProductLayer(Layer, ABC):
    """The abstract base class for Symbolic product layers."""

    def __init__(self, scope: Scope, num_input_units: int, num_output_units: int, arity: int = 2):
        super().__init__(scope, num_input_units, num_output_units, arity)

    @property
    def config(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "num_input_units": self.num_input_units,
            "arity": self.arity,
        }


class HadamardLayer(ProductLayer):
    """The Symbolic Hadamard product layer."""

    def __init__(self, scope: Scope, num_input_units: int, arity: int = 2):
        if arity < 2:
            raise ValueError("The arity should be at least 2")
        super().__init__(
            scope, num_input_units, HadamardLayer.num_prod_units(num_input_units), arity=arity
        )

    @staticmethod
    def num_prod_units(in_num_units: int) -> int:
        return in_num_units


class KroneckerLayer(ProductLayer):
    """The Symbolic Kronecker product layer."""

    def __init__(self, scope: Scope, num_input_units: int, arity: int = 2):
        super().__init__(
            scope,
            num_input_units,
            KroneckerLayer.num_prod_units(num_input_units, arity),
            arity=arity,
        )

    @staticmethod
    def num_prod_units(in_num_units: int, arity: int) -> int:
        return cast(int, in_num_units**arity)


class SumLayer(Layer, ABC):
    """The abstract base class for Symbolic sum layers."""


class DenseLayer(SumLayer):
    """The Symbolic dense sum layer."""

    def __init__(
        self,
        scope: Scope,
        num_input_units: int,
        num_output_units: int,
        weight: Optional[Parameter] = None,
        weight_factory: Optional[ParameterFactory] = None,
    ):
        super().__init__(scope, num_input_units, num_output_units, arity=1)
        if weight is None:
            if weight_factory is None:
                weight = Parameter.from_leaf(
                    TensorParameter(*self.weight_shape, initializer=NormalInitializer())
                )
            else:
                weight = weight_factory(self.weight_shape)
        if weight.shape != self.weight_shape:
            raise ValueError(f"Expected parameter shape {self.weight_shape}, found {weight.shape}")
        self.weight = weight

    @property
    def weight_shape(self) -> Tuple[int, ...]:
        return self.num_output_units, self.num_input_units

    @property
    def config(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "num_input_units": self.num_input_units,
            "num_output_units": self.num_output_units,
        }

    @property
    def params(self) -> Dict[str, Parameter]:
        return {"weight": self.weight}


class MixingLayer(SumLayer):
    """The Symbolic mixing sum layer."""

    def __init__(
        self,
        scope: Scope,
        num_units: int,
        arity: int,
        weight: Optional[Parameter] = None,
        weight_factory: Optional[ParameterFactory] = None,
    ):
        super().__init__(scope, num_units, num_units, arity)
        if weight is None:
            if weight_factory is None:
                weight = Parameter.from_leaf(
                    TensorParameter(*self.weight_shape, initializer=NormalInitializer())
                )
            else:
                weight = weight_factory(self.weight_shape)
        if weight.shape != self.weight_shape:
            raise ValueError(f"Expected parameter shape {self.weight_shape}, found {weight.shape}")
        self.weight = weight

    @property
    def weight_shape(self) -> Tuple[int, ...]:
        return self.num_input_units, self.arity

    @property
    def config(self) -> Dict[str, Any]:
        return {"scope": self.scope, "num_units": self.num_input_units, "arity": self.arity}

    @property
    def params(self) -> Dict[str, Parameter]:
        return {"weight": self.weight}
