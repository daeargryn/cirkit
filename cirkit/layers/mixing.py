from typing import Optional

import torch
from torch import Tensor, nn

from cirkit.layers.layer import Layer
from cirkit.reparams.leaf import ReparamIdentity
from cirkit.utils.log_trick import log_func_exp
from cirkit.utils.type_aliases import ReparamFactory

# TODO: rework docstrings


class MixingLayer(Layer):
    # TODO: how we fold line here?
    r"""Implement the Mixing Layer, in order to handle sum nodes with multiple children.

    Recall Figure II from above:

           S          S
        /  |  \      / \ 
       P   P  P     P  P
      /\   /\  /\  /\  /\ 
     N  N N N N N N N N N

    Figure II


    We implement such excerpt as in Figure III, splitting sum nodes with multiple \
        children in a chain of two sum nodes:

            S          S
        /   |  \      / \ 
       S    S   S    S  S
       |    |   |    |  |
       P    P   P    P  P
      /\   /\  /\   /\  /\ 
     N  N N N N N N N N N

    Figure III


    The input nodes N have already been computed. The product nodes P and the \
        first sum layer are computed using an
    SumProductLayer, yielding a log-density tensor of shape
        (batch_size, vector_length, num_nodes).
    In this example num_nodes is 5, since the are 5 product nodes (or 5 singleton \
        sum nodes). The MixingLayer
    then simply mixes sums from the first layer, to yield 2 sums. This is just an \
        over-parametrization of the original
    excerpt.
    """

    # TODO: num_output_units is num_input_units
    # pylint: disable-next=too-many-arguments
    def __init__(
        self,
        num_input_components: int,
        num_output_units: int,
        num_folds: int = 1,
        fold_mask: Optional[Tensor] = None,
        *,
        reparam: ReparamFactory = ReparamIdentity,
    ) -> None:
        """Init class.

        Args:
            num_input_components (int): The number of mixing components.
            num_output_units (int): The number of output units.
            num_folds (int): The number of folds.
            fold_mask (Optional[Tensor]): The mask to apply to the folded parameter tensors.
            reparam: The reparameterization function.
        """
        super().__init__(num_folds=num_folds, fold_mask=fold_mask)
        self.reparam = reparam
        self.num_input_components = num_input_components
        self.num_output_units = num_output_units

        self.params = reparam(
            (self.num_folds, num_input_components, num_output_units), dim=1, mask=fold_mask
        )

        self.reset_parameters()

    @torch.no_grad()
    def reset_parameters(self) -> None:
        """Reset parameters to default initialization: U(0.01, 0.99) with normalization."""
        # TODO: is this still correct with reparam?
        for param in self.parameters():
            nn.init.uniform_(param, 0.01, 0.99)
            # TODO: pylint bug?
            # pylint: disable-next=redefined-loop-name
            param /= param.sum(dim=1, keepdim=True)  # type: ignore[misc]

    def _forward_linear(self, x: Tensor) -> Tensor:
        # TODO: too many `self.fold_mask is None` checks across the repo
        #       can use apply_mask method?
        weight = self.params() if self.fold_mask is None else self.params() * self.fold_mask
        return torch.einsum("fck,fckb->fkb", weight, x)

    def forward(self, x: Tensor) -> Tensor:
        """Run forward pass.

        Args:
            x (Tensor): The input to this layer.

        Returns:
            Tensor: The output of this layer.
        """
        return log_func_exp(x, func=self._forward_linear, dim=1, keepdim=False)

    # TODO: see commit 084a3685c6c39519e42c24a65d7eb0c1b0a1cab1 for backtrack
