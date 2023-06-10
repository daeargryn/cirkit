from typing import Any, Dict, List, Literal, Optional, Sequence, Type

import torch
from torch import Tensor

from cirkit.region_graph.rg_node import RegionNode

from .exp_family import ExponentialFamilyArray
from .layer import Layer

# TODO: rework docstrings


# TODO: but we don't have a non-factorized one
class FactorizedInputLayer(Layer):
    """Computes all EiNet leaves in parallel, where each leaf is a vector of \
        factorized distributions, where factors are from exponential families.

    In FactorizedLeafLayer, we generate an ExponentialFamilyArray with \
        array_shape = (num_dist, num_replica), where
        num_dist is the vector length of the vectorized distributions \
            (K in the paper), and
        num_replica is picked large enough such that "we compute enough \
            leaf densities". At the moment we rely that
        the PC structure (see Class Graph) provides the necessary information \
            to determine num_replica. In
        particular, we require that each leaf of the graph has the field \
            einet_address.replica_idx defined;
        num_replica is simply the max over all einet_address.replica_idx.
        In the future, it would convenient to have an automatic allocation \
            of leaves to replica, without requiring
        the user to specify this.
    The generate ExponentialFamilyArray has shape (batch_size, num_var, \
        num_dist, num_replica). This array of densities
        will contain all densities over single RVs, which are then multiplied \
        (actually summed, due to log-domain
        computation) together in forward(...).
    """

    scope_tensor: Tensor  # to be registered as buffer

    # pylint: disable-next=too-many-arguments
    def __init__(  # type: ignore[misc]
        self,
        nodes: List[RegionNode],
        num_var: int,
        num_dims: int,
        exponential_family: Type[ExponentialFamilyArray],
        ef_args: Dict[str, Any],
    ):
        """Init class.

        :param nodes: list of PC leaves (DistributionVector, see Graph.py)
        :param num_var: number of random variables (int)
        :param num_dims: dimensionality of RVs (int)
        :param exponential_family: type of exponential family (derived from ExponentialFamilyArray)
        :param ef_args: arguments of exponential_family
        """
        super().__init__()

        self.nodes = nodes
        self.num_var = num_var
        self.num_dims = num_dims

        num_dists = set(n.num_dist for n in self.nodes)
        assert len(num_dists) == 1, "All leaves must have the same number of distributions."
        num_dist = num_dists.pop()

        replica_indices = set(n.einet_address.replica_idx for n in self.nodes)
        num_replica = len(replica_indices)
        assert replica_indices == set(
            range(num_replica)
        ), "Replica indices should be consecutive, starting with 0."

        # this computes an array of (batch, num_var, num_dist, num_repetition)
        # exponential family densities
        # see ExponentialFamilyArray
        self.ef_array = exponential_family(
            num_var, num_dims, (num_dist, num_replica), **ef_args  # type: ignore[misc]
        )

        # self.scope_tensor indicates which densities in self.ef_array belongs to which leaf.
        # TODO: it might be smart to have a sparse implementation --
        # I have experimented a bit with this, but it is not always faster.
        self.register_buffer("scope_tensor", torch.zeros(num_var, num_replica, len(self.nodes)))
        for i, node in enumerate(self.nodes):
            self.scope_tensor[
                list(node.scope), node.einet_address.replica_idx, i  # type: ignore[misc]
            ] = 1
            node.einet_address.layer = self
            node.einet_address.idx = i

        # TODO: ef_array inits itself, no need here

    @property
    def num_params(self) -> int:
        """Get number of params.

        Returns:
            int: The number of params.
        """
        return self.ef_array.params.numel()

    def reset_parameters(self) -> None:
        """Reset parameters to default initialization."""
        self.ef_array.reset_parameters()

    def forward(self, x: Optional[Tensor] = None) -> None:
        """Compute the factorized leaf densities. We are doing the computation \
            in the log-domain, so this is actually \
            computing sums over densities.

        We first pass the data x into self.ef_array, which computes a tensor of shape
            (batch_size, num_var, num_dist, num_replica). This is best interpreted \
            as vectors of length num_dist, for each \
            sample in the batch and each RV. Since some leaves have overlapping \
            scope, we need to compute "enough" leaves, \
            hence the num_replica dimension. The assignment of these log-densities \
            to leaves is represented with \
            self.scope_tensor.
        In the end, the factorization (sum in log-domain) is realized with a single einsum.

        :param x: input data (Tensor).
                  If self.num_dims == 1, this can be either of shape \
                    (batch_size, self.num_var, 1) or
                  (batch_size, self.num_var).
                  If self.num_dims > 1, this must be of shape \
                    (batch_size, self.num_var, self.num_dims).
        no return: log-density vectors of leaves
                 Will be of shape (batch_size, num_dist, len(self.nodes))
                 Note: num_dist is K in the paper, len(self.nodes) is the number of PC leaves
        """
        assert x is not None  # TODO: how we guarantee this?
        self.prob = torch.einsum("bxir,xro->bio", self.ef_array(x), self.scope_tensor)

        # assert not torch.isnan(self.prob).any()
        # assert not torch.isinf(self.prob).any()

    # TODO: how to fix?
    # pylint: disable-next=arguments-differ
    def backtrack(  # type: ignore[misc]
        self,
        dist_idx: Sequence[Sequence[int]],  # TODO: can be iterable?
        node_idx: Sequence[Sequence[int]],
        *_: Any,
        mode: Literal["sample", "argmax"] = "sample",
        **kwargs: Any,
    ) -> Tensor:
        """Backtrackng mechanism for EiNets.

        :param dist_idx: list of N indices into the distribution vectors, which shall be sampled.
        :param node_idx: list of N indices into the leaves, which shall be sampled.
        :param mode: 'sample' or 'argmax'; for sampling or MPE approximation, respectively.
        :param _: ignored
        :param kwargs: keyword arguments
        :return: samples (Tensor). Of shape (N, self.num_var, self.num_dims).
        """
        assert len(dist_idx) == len(node_idx), "Invalid input."

        with torch.no_grad():
            big_n = len(dist_idx)  # TODO: a better name
            ef_values = (
                self.ef_array.sample(big_n, **kwargs)  # type: ignore[misc]
                if mode == "sample"
                else self.ef_array.argmax(**kwargs)  # type: ignore[misc]
            )

            values = torch.zeros(
                big_n, self.num_var, self.num_dims, device=ef_values.device, dtype=ef_values.dtype
            )

            # TODO: use enumerate?
            for n in range(big_n):
                cur_value = torch.zeros(
                    self.num_var, self.num_dims, device=ef_values.device, dtype=ef_values.dtype
                )
                assert len(dist_idx[n]) == len(node_idx[n]), "Invalid input."
                for c, k in enumerate(node_idx[n]):
                    scope = list(self.nodes[k].scope)
                    rep = self.nodes[k].einet_address.replica_idx
                    cur_value[scope, :] = (
                        ef_values[n, scope, :, dist_idx[n][c], rep]
                        if mode == "sample"
                        else ef_values[scope, :, dist_idx[n][c], rep]
                    )
                values[n, :, :] = cur_value  # TODO: directly slice this

            return values

    def set_marginalization_idx(self, idx: Tensor) -> None:
        """Set indicices of marginalized variables.

        Args:
            idx (Tensor): The indices.
        """
        self.ef_array.set_marginalization_idx(idx)

    # TODO: why optional?
    def get_marginalization_idx(self) -> Optional[Tensor]:
        """Get indicices of marginalized variables.

        Returns:
            Tensor: The indices.
        """
        return self.ef_array.get_marginalization_idx()
