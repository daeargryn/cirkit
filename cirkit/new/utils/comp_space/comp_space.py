from abc import ABC, abstractmethod
from typing import Callable, Dict, Optional, Sequence, Type, TypeVar, Union, cast
from typing_extensions import Self, TypeVarTuple, Unpack  # TODO: in typing from 3.11

from torch import Tensor

Ts = TypeVarTuple("Ts")

CompSpaceT = TypeVar("CompSpaceT", bound=Type["ComputationSapce"])


def register_comp_space(cls: CompSpaceT) -> CompSpaceT:
    """Register a concrete ComputationSapce by its name.

    Args:
        cls (CompSpaceT): The ComputationSapce subclass to register.

    Returns:
        CompSpaceT: The class passed in.
    """
    # Cast: A cast is needed because __final__ may be undefined.
    assert cast(
        bool, getattr(cls, "__final__", False)
    ), "Subclasses of ComputationSapce should be final."
    # Disable: Access to _registry is by design.
    ComputationSapce._registry[cls.name] = cls  # pylint: disable=protected-access
    return cls


class ComputationSapce(ABC):
    """The abstract base class for compotational spaces.

    Due to numerical precision, the actual units in computational graph may hold values in, e.g., \
    log space, instead of linear space. And therefore, this provides a unified interface for the \
    computations so that computation can be done in a space suitable to the implementation \
    regardless of the global setting.
    """

    _registry: Dict[str, Type["ComputationSapce"]] = {}

    @staticmethod
    def get_comp_space_by_name(name: str) -> Type["ComputationSapce"]:
        """Get a ComputationSapce by its registered name.

        Args:
            name (str): The name to probe.

        Returns:
            Type[ComputationSapce]: The retrieved concrete ComputationSapce.
        """
        return ComputationSapce._registry[name]

    def __new__(cls) -> Self:  # TODO: NoReturn should be used, but mypy is not happy.
        """Raise an error when this class is instantiated.

        Raises:
            TypeError: When this class is instantiated.

        Returns:
            Self: This method never returns.
        """
        raise TypeError("This class cannot be instantiated.")

    # NOTE: Subclasses should implement all the following and should be @final.

    name: str
    """The name to be registered."""

    # TODO: if needed, we can also have to_log, to_lin.
    @classmethod
    @abstractmethod
    def from_log(cls, x: Tensor) -> Tensor:
        """Convert a value from log space to the current space.

        Args:
            x (Tensor): The value in log space.

        Returns:
            Tensor: The value in the current space.
        """

    @classmethod
    @abstractmethod
    def from_linear(cls, x: Tensor) -> Tensor:
        """Convert a value from linear space to the current space.

        Args:
            x (Tensor): The value in linear space.

        Returns:
            Tensor: The value in the current space.
        """

    # TODO: it's difficult to bound a variadic to Tensor with TypeVars, we can only use unbounded
    #       Unpack[TypeVarTuple].
    @classmethod
    @abstractmethod
    def sum(
        cls,
        func: Callable[[Unpack[Ts]], Tensor],
        *xs: Unpack[Ts],
        dim: Union[int, Sequence[int]],
        keepdim: bool,
    ) -> Tensor:
        """Apply a sum-like functions to the tensor(s).

        The sum units may perform not just plain sum, but also weighted sum or even einsum. In \
        fact, it can possibly be any function that is linear to the each input. All that kind of \
        func can be used here.

        It is expected that func always does computation in the linear space, as with numerical \
        tricks, only relatively significant numbers contribute the final answer, and underflow \
        will not affect much. However the input/output values may still be in another space, and \
        needs to be projected here.

        Args:
            func (Callable[[Unpack[Ts]], Tensor]): The sum-like function to be applied.
            *xs (Unpack[Ts]): The input tensors. Type expected to be Tensor.
            dim (Union[int, Sequence[int]]): The dimension(s) along which the values are \
                correlated and must be scaled together, i.e., the dim(s) to sum along. This should \
                match the actual operation done by func. The same dim is shared among all inputs.
            keepdim (bool): Whether the dim is kept as a size-1 dim, should match the actual \
                operation done by func.

        Returns:
            Tensor: The sum result.
        """

    @classmethod
    @abstractmethod
    def prod(
        cls, x: Tensor, /, *, dim: Optional[Union[int, Sequence[int]]] = None, keepdim: bool = False
    ) -> Tensor:
        """Do the product within a tensor on given dim(s).

        Args:
            x (Tensor): The input tensor.
            dim (Optional[Union[int, Sequence[int]]], optional): The dimension(s) to reduce along, \
                None for all dims. Defaults to None.
            keepdim (bool, optional): Whether the dim is kept as a size-1 dim. Defaults to False.

        Returns:
            Tensor: The product result.
        """

    @classmethod
    @abstractmethod
    def mul(cls, *xs: Tensor) -> Tensor:
        """Do the multiply among broadcastable tensors.

        Args:
            *xs (Tensor): The input tensors, should have broadcastable shapes.

        Returns:
            Tensor: The multiply result.
        """
